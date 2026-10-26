import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
import FitTrackerCore

@MainActor
@Observable final class NativeDietStore {
    var days: [String: DietDayResponse] = [:]
    var loading: Set<String> = []
    var errors: [String: String] = [:]
    var pendingWrites: Set<String> = []
    var pendingSlots: Set<String> = []
    var pendingMutations: [String: Int] = [:]
    var revisions: [String: Int] = [:]
    var confirmedDays: [String: DietDayResponse] = [:]
    struct PendingOutcome: Codable {
        let id: UUID
        let date: String
        let slotKey: String
        let mealId: Int
        let outcome: DietSlotOutcome
    }
    let ownerId: UUID
    var storageKey: String { "fitTracker.pendingDietOutcomes.\(ownerId.uuidString)" }
    var queuedOutcomes: [String: [PendingOutcome]] = [:]
    var resuming = false
    var writeTasks: [String: (id: UUID, task: Task<Void, Never>)] = [:]

    init(ownerId: UUID) {
        self.ownerId = ownerId
        if let data = UserDefaults.standard.data(forKey: storageKey),
           let saved = try? JSONDecoder().decode([PendingOutcome].self, from: data) {
            for item in saved {
                guard !queuedOutcomes[item.date, default: []].contains(where: { $0.slotKey == item.slotKey }) else { continue }
                queuedOutcomes[item.date, default: []].append(item)
                pendingSlots.insert("\(item.date)|\(item.slotKey)")
                pendingWrites.insert(item.date)
            }
        }
    }

    func persistOutcomes() {
        let records = queuedOutcomes.keys.sorted().flatMap { queuedOutcomes[$0] ?? [] }
        if records.isEmpty { UserDefaults.standard.removeObject(forKey: storageKey) }
        else if let data = try? JSONEncoder().encode(records) { UserDefaults.standard.set(data, forKey: storageKey) }
    }

    /// A persisted operation is reconciled before replay, so an ambiguous response
    /// never creates another entry or overwrites a meal changed on another device.
    func resumePending(api: FitTrackerAPI, isCurrentOwner: @escaping @MainActor () -> Bool) async {
        guard !resuming, isCurrentOwner() else { return }
        resuming = true
        defer { resuming = false }
        for date in queuedOutcomes.keys.sorted() {
            if let active = writeTasks[date]?.task { await active.value }
            guard isCurrentOwner(), let queued = queuedOutcomes[date], !queued.isEmpty else { continue }
            let revision = revisions[date, default: 0]
            do {
                let serverDay = try await api.getDietDay(date: date)
                guard isCurrentOwner() else { return }
                guard revisions[date, default: 0] == revision, pendingMutations[date, default: 0] == 0 else { continue }
                confirmedDays[date] = serverDay
                revisions[date, default: 0] += 1
                rebuild(date)
                for item in queued {
                    guard isCurrentOwner(), queuedOutcomes[date]?.contains(where: { $0.id == item.id }) == true else { continue }
                    guard let serverSlot = serverDay.slots.first(where: { $0.slotKey == item.slotKey }) else {
                        errors[date] = "O plano mudou. Confira esta refeição antes de registrar novamente."
                        removeOutcome(item)
                        continue
                    }
                    if serverSlot.result == item.outcome.rawValue &&
                        (item.outcome == .skipped || serverSlot.selectedPlanMealId == item.mealId && serverSlot.entry != nil) {
                        removeOutcome(item)
                    } else if serverSlot.result != "pending" || serverSlot.selectedPlanMealId != item.mealId {
                        errors[date] = "Esta refeição foi alterada. Confira o registro atualizado."
                        removeOutcome(item)
                    } else {
                        await commitOutcome(item, api: api, isCurrentOwner: isCurrentOwner)
                    }
                }
                rebuild(date)
            } catch {
                guard isCurrentOwner() else { return }
                // Keep the durable record for the next foreground or explicit refresh.
            }
        }
    }

    func removeOutcome(_ item: PendingOutcome) {
        queuedOutcomes[item.date]?.removeAll { $0.id == item.id }
        pendingSlots.remove("\(item.date)|\(item.slotKey)")
        if queuedOutcomes[item.date]?.isEmpty == true { queuedOutcomes[item.date] = nil }
        if queuedOutcomes[item.date] == nil && pendingMutations[item.date, default: 0] == 0 { pendingWrites.remove(item.date) }
        persistOutcomes()
        rebuild(item.date)
    }

    func definitiveRejection(_ error: Error) -> Bool {
        if case APIError.http(let status, _) = error { return (400..<500).contains(status) && ![401, 408, 429].contains(status) }
        return false
    }

    func isPending(date: String, slotKey: String) -> Bool { pendingSlots.contains("\(date)|\(slotKey)") }

    func load(_ date: String, api: FitTrackerAPI, refreshAfterCurrent: Bool = false, force: Bool = false) async {
        // A write must not reuse a read that started before the write completed.
        if refreshAfterCurrent {
            while loading.contains(date) {
                do { try await Task.sleep(nanoseconds: 50_000_000) }
                catch { return }
            }
        }
        guard (force || refreshAfterCurrent || days[date] == nil), !loading.contains(date), !pendingWrites.contains(date), !Task.isCancelled else { return }
        let revision = revisions[date, default: 0]
        loading.insert(date)
        errors[date] = nil
        defer { loading.remove(date) }
        do {
            // The shared diary read outlives the tab that initiated it.
            let request = Task { try await api.getDietDay(date: date) }
            let day = try await request.value
            guard revisions[date, default: 0] == revision, !pendingWrites.contains(date) else { return }
            days[date] = day
            confirmedDays[date] = day
        }
        catch { if !isNativeRequestCancellation(error), revisions[date, default: 0] == revision { errors[date] = error.localizedDescription } }
    }

    func setOutcome(date: String, slot: DietDaySlot, outcome: DietSlotOutcome, api: FitTrackerAPI,
                    isCurrentOwner: @escaping @MainActor () -> Bool) async {
        guard !isPending(date: date, slotKey: slot.slotKey), let day = days[date],
              day.slots.contains(where: { $0.slotKey == slot.slotKey && $0.result == "pending" }) else { return }
        if !pendingWrites.contains(date) { confirmedDays[date] = day }
        let operation = PendingOutcome(id: UUID(), date: date, slotKey: slot.slotKey, mealId: slot.selectedPlanMealId, outcome: outcome)
        queuedOutcomes[date, default: []].append(operation)
        persistOutcomes()
        pendingWrites.insert(date)
        pendingSlots.insert("\(date)|\(slot.slotKey)")
        revisions[date, default: 0] += 1
        errors[date] = nil
        rebuild(date)
        let previous = writeTasks[date]?.task
        let id = UUID()
        let task = Task {
            if let previous { await previous.value }
            guard isCurrentOwner() else { return }
            await self.commitOutcome(operation, api: api, isCurrentOwner: isCurrentOwner)
        }
        writeTasks[date] = (id, task)
        await task.value
        if writeTasks[date]?.id == id { writeTasks[date] = nil }
    }

    func commitOutcome(_ item: PendingOutcome, api: FitTrackerAPI,
                               isCurrentOwner: @escaping @MainActor () -> Bool) async {
        guard isCurrentOwner() else { return }
        do {
            let state = try await api.setDietSlotOutcome(date: item.date, slotKey: item.slotKey,
                mealId: item.mealId, outcome: item.outcome, idempotencyKey: item.id.uuidString)
            guard isCurrentOwner() else { return }
            confirmedDays[item.date] = confirmedDays[item.date]?.applyingConfirmedOutcome(state)
            removeOutcome(item)
            NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
        } catch {
            guard isCurrentOwner() else { return }
            if definitiveRejection(error) {
                errors[item.date] = error.localizedDescription
                removeOutcome(item)
                Task {
                    guard isCurrentOwner() else { return }
                    let failure = errors[item.date]
                    await load(item.date, api: api, refreshAfterCurrent: true)
                    if isCurrentOwner() { errors[item.date] = failure }
                }
            }
            // Network errors, timeouts and server failures retain the optimistic
            // result and durable record. Only a confirmed response removes it.
        }
    }

    func mutateSlot(date: String, slotKey: String, api: FitTrackerAPI,
                    isCurrentOwner: @escaping @MainActor () -> Bool,
                    action: @escaping @MainActor () async throws -> Void) async -> Bool {
        guard !isPending(date: date, slotKey: slotKey) else { return false }
        errors[date] = nil
        pendingMutations[date, default: 0] += 1
        pendingWrites.insert(date)
        pendingSlots.insert("\(date)|\(slotKey)")
        revisions[date, default: 0] += 1
        let previous = writeTasks[date]?.task
        let id = UUID()
        var succeeded = false
        let task = Task {
            if let previous { await previous.value }
            guard isCurrentOwner() else { return }
            do {
                try await action()
                guard isCurrentOwner() else { return }
                succeeded = true
                NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
                // Later optimistic outcomes must be replayed on the updated server day.
                confirmedDays[date] = try await api.getDietDay(date: date)
            } catch {
                guard isCurrentOwner() else { return }
                errors[date] = error.localizedDescription
            }
            pendingMutations[date, default: 0] -= 1
            pendingSlots.remove("\(date)|\(slotKey)")
            rebuild(date)
            if queuedOutcomes[date] == nil && pendingMutations[date, default: 0] == 0 {
                pendingWrites.remove(date)
                let failure = errors[date]
                await load(date, api: api, refreshAfterCurrent: true)
                if let failure { errors[date] = failure }
            }
        }
        writeTasks[date] = (id, task)
        await task.value
        if writeTasks[date]?.id == id { writeTasks[date] = nil }
        return succeeded
    }

    func rebuild(_ date: String) {
        guard var day = confirmedDays[date] else { return }
        for item in queuedOutcomes[date] ?? [] {
            day = day.applyingPlannedOutcome(slotKey: item.slotKey, outcome: item.outcome)
        }
        days[date] = day
    }
}

struct NativeHomeView: View {
    var allowsWorkoutSetup = true
    var onOpenProgress: () -> Void = {}
    var onOpenDiet: () -> Void = {}
    @Environment(\.accessibilityReduceMotion) var reduceMotion
    @Environment(NativeSession.self) var session
    @Environment(NativeDietStore.self) var diary
    @Environment(NativeTabDataStore.self) var tabData
    @State var showMeal = false
    @State var subscription = false
    @State var showingFirstWorkout = false
    @State var showingWorkoutPlans = false
    @State var showingDietPlan = false
    var today: String { dietDate(Date(), timezone: session.profile?.profile?.timezone) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Hoje").font(FitTrackerTheme.pageTitle)
                            Text(Date(), style: .date).font(.subheadline).foregroundColor(.secondary)
                        }
                        Spacer()
                        Button(action: onOpenProgress) {
                            Image(systemName: "calendar").font(.system(size: 20)).frame(width: 44, height: 44).fitPremiumCard()
                        }.buttonStyle(.plain).foregroundColor(.white.opacity(0.85)).accessibilityLabel("Abrir calendário de progresso")
                    }.padding(.bottom, 4)
                    if let day = diary.days[today] {
                        NativeNutritionView(day: day, compact: true, onOpenDiary: onOpenDiet)
                    } else if diary.loading.contains(today) { ProgressView("Carregando seu dia…") }
                    if let error = diary.errors[today] { diaryError(error) }
                    Button { showMeal = true } label: {
                        Label("Adicionar refeição", systemImage: "plus").font(.body.weight(.semibold))
                            .frame(maxWidth: .infinity)
                    }.buttonStyle(FitPrimaryButtonStyle())
                    NativeFreeAccessCard()
                    if session.user?.isPremium != true {
                        Button { subscription = true } label: { NativePremiumBanner() }.buttonStyle(.plain)
                    }
                    homeSection("Seu treino", action: "Ver todos") { showingWorkoutPlans = true }
                    NativeTodayWorkoutCard()
                    if let day = diary.days[today] {
                        homeSection("Alimentação", action: "Ver plano") { showingDietPlan = true }
                        let pending = day.slots.filter { $0.result == "pending" }
                        if pending.isEmpty {
                            Text(day.plan == nil ? "Seu plano alimentar aparecerá aqui. Você também pode adicionar uma refeição." : "Tudo em dia! Veja suas refeições registradas na aba Dieta.")
                                .font(.subheadline).foregroundColor(.secondary)
                        }
                        ForEach(pending) { slot in NativeDietSlotView(slot: slot, date: today, compact: true) }
                            .animation(reduceMotion ? nil : .spring(response: 0.35, dampingFraction: 0.88), value: pending.map(\.id))
                    }
                }.padding(.horizontal, FitTrackerTheme.pagePadding).padding(.vertical, 12)
            }
            .background(FitTrackerTheme.background.ignoresSafeArea())
            .navigationBarHidden(true)
            .refreshable { await diary.load(today, api: session.api, force: true) }
            .task(id: today) { await diary.load(today, api: session.api) }
            .sheet(isPresented: $showMeal) { NativeMealComposer(date: today) }
            .sheet(isPresented: $subscription) { NavigationStack { NativeSubscriptionView() } }
            .sheet(isPresented: $showingWorkoutPlans) { NativePlansView(kind: .workout) }
            .sheet(isPresented: $showingDietPlan, onDismiss: { Task { await diary.load(today, api: session.api, refreshAfterCurrent: true) } }) { NativePlansView(kind: .diet) }
            .sheet(isPresented: $showingFirstWorkout, onDismiss: { Task { await tabData.loadWorkout(force: true) } }) {
                PlanGeneratorView(kind: .workout, firstPlan: true)
            }
            .task(id: allowsWorkoutSetup) { await offerFirstWorkout() }
            .onChange(of: tabData.workoutToday?.state) { _ in Task { await offerFirstWorkout() } }
            .onChange(of: session.profile?.profileComplete) { _ in Task { await offerFirstWorkout() } }
            .task { if session.freeAccess == nil { try? await session.refreshFreeAccess() } }
        }
    }

    func homeSection(_ title: String, action: String, onTap: @escaping () -> Void) -> some View {
        HStack {
            Text(title).font(FitTrackerTheme.sectionTitle)
            Spacer()
            Button(action: onTap) { HStack(spacing: 6) { Text(action); Image(systemName: "chevron.right").font(.caption.weight(.semibold)) } }
                .font(.subheadline.weight(.medium)).foregroundColor(FitTrackerTheme.electricBlue)
        }.padding(.top, 4)
    }

    @MainActor func offerFirstWorkout() async {
        guard allowsWorkoutSetup, session.profile?.profileComplete == true,
              let owner = session.user?.id, !showMeal, !subscription, !showingFirstWorkout, !showingWorkoutPlans, !showingDietPlan else { return }
        await tabData.loadWorkout()
        guard allowsWorkoutSetup, session.user?.id == owner,
              tabData.workoutToday?.state == "unconfigured", !showMeal, !subscription, !showingFirstWorkout, !showingWorkoutPlans, !showingDietPlan else { return }
        let key = "fittracker.native.workoutSetupOffered.\(owner.uuidString.lowercased())"
        guard !UserDefaults.standard.bool(forKey: key) else { return }
        UserDefaults.standard.set(true, forKey: key)
        showingFirstWorkout = true
    }

    func diaryError(_ message: String) -> some View {
        VStack(alignment: .leading) {
            Text(message).foregroundColor(.red)
            Button("Tentar novamente") { Task { await diary.load(today, api: session.api, force: true) } }
        }
    }
}

struct NativeDietView: View {
    @Environment(NativeSession.self) var session
    @Environment(NativeDietStore.self) var diary
    @State var selectedDate = Date()
    @State var showPlans = false
    @State var showMeal = false
    var date: String { dietDate(selectedDate, timezone: session.profile?.profile?.timezone) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    DatePicker("Dia do diário", selection: $selectedDate, displayedComponents: .date)
                        .datePickerStyle(.compact)
                    if diary.days[date] == nil && diary.loading.contains(date) { ProgressView("Carregando refeições…") }
                    if let error = diary.errors[date] {
                        Text(error).foregroundColor(.red)
                        Button("Tentar novamente") { Task { await diary.load(date, api: session.api, force: true) } }
                    }
                    if let day = diary.days[date] {
                        NativeNutritionView(day: day, compact: false)
                        if let plan = day.plan {
                            Label(plan.title, systemImage: "list.bullet.rectangle").font(.headline)
                        }
                        Text("Refeições registradas").font(.title3.bold())
                        if day.entries.isEmpty { Text("Nenhuma refeição registrada neste dia.").foregroundColor(.secondary) }
                        ForEach(day.entries) { entry in NativeMealRow(entry: entry) }
                        if !day.slots.isEmpty {
                            Text("Planejado para o dia").font(.title3.bold())
                            ForEach(day.slots) { slot in
                                NativeDietSlotView(slot: slot, date: date)
                            }
                        }
                    }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle("Alimentação")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("Plano") { showPlans = true } }
            .safeAreaInset(edge: .bottom) {
                Button { showMeal = true } label: {
                    Label("Registrar refeição", systemImage: "plus").font(.body.weight(.semibold))
                        .frame(maxWidth: .infinity).padding(.vertical, 9)
                }.buttonStyle(.borderedProminent).padding(.horizontal, 20).padding(.vertical, 12)
            }
            .refreshable { await diary.load(date, api: session.api, force: true) }
            .task(id: date) { await diary.load(date, api: session.api) }
            .sheet(isPresented: $showMeal) { NativeMealComposer(date: date) }
            .sheet(isPresented: $showPlans, onDismiss: { Task { await diary.load(date, api: session.api, refreshAfterCurrent: true) } }) { NativePlansView(kind: .diet) }
        }
    }
}

struct NutritionMetric: Identifiable {
    let id: String
    let icon: String
    let color: Color
    let value: Double?
    let target: Double?
    let unit: String
    var fraction: Double { guard let value, let target, target > 0 else { return 0 }; return min(max(value / target, 0), 1) }
}

struct NativeNutritionView: View {
    let day: DietDayResponse
    let compact: Bool
    var onOpenDiary: (() -> Void)? = nil
    @State var selected: String?
    var metrics: [NutritionMetric] { [
        .init(id: "Calorias", icon: "flame", color: .orange, value: day.totals.calories, target: day.targets.calories, unit: "kcal"),
        .init(id: "Proteínas", icon: "p.circle", color: .blue, value: day.totals.protein, target: day.targets.protein, unit: "g"),
        .init(id: "Carboidratos", icon: "leaf", color: .mint, value: day.totals.carbs, target: day.targets.carbs, unit: "g"),
        .init(id: "Gorduras", icon: "drop", color: .purple, value: day.totals.fat, target: day.targets.fat, unit: "g")
    ] }

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 12 : 16) {
            HStack {
                Text(compact ? "Seu dia" : "Resumo do dia")
                    .font(compact ? .headline : .caption).foregroundColor(compact ? .white : .secondary)
                Spacer()
                if compact, let onOpenDiary {
                    Button(action: onOpenDiary) {
                        HStack(spacing: 5) { Text(mealCountText); Image(systemName: "chevron.right").foregroundColor(FitTrackerTheme.electricBlue) }
                    }.buttonStyle(.plain).accessibilityLabel("\(mealCountText). Abrir diário alimentar")
                } else { Text(mealCountText) }
            }.font(.caption).foregroundColor(.secondary)
            if compact {
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 2), alignment: .center, spacing: 12) {
                    ForEach(metrics) { metric in
                        Button { toggle(metric.id) } label: {
                            VStack(spacing: 5) {
                                ZStack {
                                    Circle().stroke(metric.color.opacity(0.13), lineWidth: 4)
                                    Circle().trim(from: 0, to: metric.fraction).stroke(metric.color, style: StrokeStyle(lineWidth: 4, lineCap: .round)).rotationEffect(.degrees(-90))
                                    Image(systemName: metric.icon).font(.system(size: 20)).foregroundColor(metric.color)
                                }.frame(width: 44, height: 44)
                                (Text(numberText(metric.value)).fontWeight(.bold).foregroundColor(metric.color) + Text(" / \(numberText(metric.target))\(metric.unit == "g" ? "g" : "")").foregroundColor(.secondary))
                                    .font(.caption2).lineLimit(1).minimumScaleFactor(0.7)
                                Text(metric.id).font(.caption2).foregroundColor(.secondary).lineLimit(1).minimumScaleFactor(0.75)
                            }.frame(maxWidth: .infinity)
                        }.buttonStyle(.plain).accessibilityLabel("Detalhes de \(metric.id)")
                            .accessibilityValue(selected == metric.id ? "Expandido" : "Recolhido")
                    }
                }
            } else {
                ForEach(metrics) { metric in
                    Button { toggle(metric.id) } label: {
                        HStack(spacing: 12) {
                            Image(systemName: metric.icon).foregroundColor(metric.color).frame(width: 24)
                            VStack(alignment: .leading, spacing: 7) {
                                HStack { Text(metric.id); Spacer(); Text(nutrientText(metric.value, metric.unit)).fontWeight(.semibold) }
                                GeometryReader { geo in
                                    Capsule().fill(Color.white.opacity(0.08))
                                    Capsule().fill(metric.color).frame(width: geo.size.width * metric.fraction)
                                }.frame(height: 4)
                            }
                        }.font(.subheadline).padding(.vertical, 6)
                    }.buttonStyle(.plain).accessibilityLabel("Detalhes de \(metric.id)")
                }
            }
            if let metric = metrics.first(where: { $0.id == selected }) {
                Divider()
                Text(metric.id).font(.headline)
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], alignment: .leading, spacing: 16) {
                    detail("Consumido", nutrientText(metric.value, metric.unit))
                    detail("Meta", nutrientText(metric.target, metric.unit))
                    detail("Progresso", metric.target.map { $0 > 0 ? "\(Int(((metric.value ?? 0) / $0 * 100).rounded()))%" : "Sem meta" } ?? "Sem meta")
                    detail("Saldo", balance(metric))
                }
            }
        }.padding(compact ? 14 : 16)
            .background(compact ? FitTrackerTheme.cardGradient : LinearGradient(colors: [.fitSurface, .fitSurface], startPoint: .top, endPoint: .bottom), in: RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius))
            .overlay(RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius).stroke(compact ? FitTrackerTheme.electricBlue.opacity(0.2) : .clear, lineWidth: 1))
    }
    var mealCountText: String {
        let count = day.entries.count + day.slots.filter { $0.result == "consumed_planned" && $0.entry == nil }.count
        if compact, !day.slots.isEmpty { return "\(count) de \(day.slots.count) refeições" }
        return "\(count) \(count == 1 ? "refeição" : "refeições")"
    }
    func numberText(_ value: Double?) -> String {
        value.map { $0.formatted(.number.locale(Locale(identifier: "pt_BR")).precision(.fractionLength(0...1))) } ?? "—"
    }
    func toggle(_ id: String) { selected = selected == id ? nil : id }
    func detail(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 5) { Text(title).font(.caption).foregroundColor(.secondary); Text(value).font(.subheadline.weight(.semibold)) }
    }
    func balance(_ metric: NutritionMetric) -> String {
        guard let target = metric.target, let value = metric.value, target > 0 else { return "Sem meta" }
        return (target >= value ? "Faltam " : "Acima: ") + nutrientText(abs(target - value), metric.unit)
    }
}

struct NativeMealRow: View {
    let entry: DietEntry
    var body: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 10) {
                Text(entry.description)
                Text("Proteínas: \(nutrientText(entry.protein, "g")) · Carboidratos: \(nutrientText(entry.carbs, "g")) · Gorduras: \(nutrientText(entry.fat, "g"))")
                    .font(.caption).foregroundColor(.secondary)
                if let notes = entry.notes, !notes.isEmpty { Text(notes).font(.caption) }
            }.padding(.top, 8)
        } label: {
            HStack {
                Image(systemName: "fork.knife").foregroundColor(.fitBlue)
                VStack(alignment: .leading, spacing: 4) { Text(entry.mealType).font(.headline); Text(entry.description).font(.caption).foregroundColor(.secondary).lineLimit(1) }
                Spacer()
                Text(nutrientText(entry.calories, "kcal")).font(.caption)
            }
        }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
    }
}

func nutrientText(_ value: Double?, _ unit: String) -> String {
    guard let value else { return "Não informado" }
    return value.formatted(.number.locale(Locale(identifier: "pt_BR")).precision(.fractionLength(0...1))) + " " + unit
}

func dietDate(_ date: Date, timezone: String?) -> String {
    let formatter = DateFormatter()
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = timezone.flatMap(TimeZone.init(identifier:)) ?? .current
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.string(from: date)
}
