import SwiftUI
import FitTrackerCore

@MainActor
final class NativeDietStore: ObservableObject {
    @Published var successMessage: String?
    @Published var days: [String: DietDayResponse] = [:]
    @Published var loading: Set<String> = []
    @Published var errors: [String: String] = [:]
    @Published private(set) var pendingWrites: Set<String> = []
    @Published private(set) var pendingSlots: Set<String> = []
    private var pendingMutations: [String: Int] = [:]
    private var revisions: [String: Int] = [:]
    private var confirmedDays: [String: DietDayResponse] = [:]
    private struct PendingOutcome: Codable {
        let id: UUID
        let date: String
        let slotKey: String
        let mealId: Int
        let outcome: DietSlotOutcome
    }
    private let ownerId: UUID
    private var storageKey: String { "fitTracker.pendingDietOutcomes.\(ownerId.uuidString)" }
    private var queuedOutcomes: [String: [PendingOutcome]] = [:]
    @Published private(set) var resuming = false
    private var writeTasks: [String: (id: UUID, task: Task<Void, Never>)] = [:]

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

    private func persistOutcomes() {
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
            errors[date] = nil
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
                        errors[date] = L("O plano mudou. Confira esta refeição antes de registrar novamente.")
                        removeOutcome(item)
                        continue
                    }
                    if serverSlot.result == item.outcome.rawValue &&
                        (item.outcome == .skipped || serverSlot.selectedPlanMealId == item.mealId && serverSlot.entry != nil) {
                        removeOutcome(item)
                    } else if serverSlot.result != "pending" || serverSlot.selectedPlanMealId != item.mealId {
                        errors[date] = L("Esta refeição foi alterada. Confira o registro atualizado.")
                        removeOutcome(item)
                    } else {
                        await commitOutcome(item, api: api, isCurrentOwner: isCurrentOwner)
                    }
                }
                rebuild(date)
            } catch {
                guard isCurrentOwner() else { return }
                if !isNativeRequestCancellation(error) {
                    errors[date] = RequestFailure.message(error, fallback: L("Ainda não confirmamos seus registros. Suas marcações continuam neste aparelho; tente sincronizar novamente."))
                }
            }
        }
    }

    func retry(_ date: String, api: FitTrackerAPI, isCurrentOwner: @escaping @MainActor () -> Bool) async {
        await resumePending(api: api, isCurrentOwner: isCurrentOwner)
        guard isCurrentOwner() else { return }
        await load(date, api: api, force: true)
    }

    private func removeOutcome(_ item: PendingOutcome) {
        queuedOutcomes[item.date]?.removeAll { $0.id == item.id }
        pendingSlots.remove("\(item.date)|\(item.slotKey)")
        if queuedOutcomes[item.date]?.isEmpty == true { queuedOutcomes[item.date] = nil }
        if queuedOutcomes[item.date] == nil && pendingMutations[item.date, default: 0] == 0 { pendingWrites.remove(item.date) }
        persistOutcomes()
        rebuild(item.date)
    }

    private func definitiveRejection(_ error: Error) -> Bool {
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
        catch { if !isNativeRequestCancellation(error), revisions[date, default: 0] == revision { errors[date] = RequestFailure.message(error, fallback: L("Não foi possível atualizar suas refeições agora.")) } }
    }

    func setOutcome(date: String, slot: DietDaySlot, outcome: DietSlotOutcome, origin: CGPoint? = nil, api: FitTrackerAPI,
                    isCurrentOwner: @escaping @MainActor () -> Bool) async {
        guard !isPending(date: date, slotKey: slot.slotKey), let day = days[date],
              day.slots.contains(where: { $0.slotKey == slot.slotKey && $0.result == "pending" }) else { return }
        if !pendingWrites.contains(date) { confirmedDays[date] = day }
        let operation = PendingOutcome(id: UUID(), date: date, slotKey: slot.slotKey, mealId: slot.selectedPlanMealId, outcome: outcome)
        NativeXPEffects.shared.captureAction(key: operation.id.uuidString, point: origin)
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

    private func commitOutcome(_ item: PendingOutcome, api: FitTrackerAPI,
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
                errors[item.date] = RequestFailure.message(error, fallback: L("Esta refeição precisa ser conferida antes de registrar novamente."))
                removeOutcome(item)
                Task {
                    guard isCurrentOwner() else { return }
                    let failure = errors[item.date]
                    await load(item.date, api: api, refreshAfterCurrent: true)
                    if isCurrentOwner() { errors[item.date] = failure }
                }
            }
            else if !isNativeRequestCancellation(error) {
                errors[item.date] = L("Sua marcação está neste aparelho e aguarda confirmação. Tente sincronizar para conferir os totais.")
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
                errors[date] = RequestFailure.message(error, fallback: succeeded ? L("A alteração foi enviada, mas ainda não conseguimos atualizar seu dia.") : L("Não foi possível confirmar a alteração. Confira a refeição antes de tentar novamente."))
            }
            pendingMutations[date, default: 0] -= 1
            pendingSlots.remove("\(date)|\(slotKey)")
            rebuild(date)
            if queuedOutcomes[date] == nil && pendingMutations[date, default: 0] == 0 {
                pendingWrites.remove(date)
                let failure = errors[date]
                await load(date, api: api, refreshAfterCurrent: true)
                if let failure, !succeeded { errors[date] = failure }
            }
        }
        writeTasks[date] = (id, task)
        await task.value
        if writeTasks[date]?.id == id { writeTasks[date] = nil }
        return succeeded
    }

    private func rebuild(_ date: String) {
        guard var day = confirmedDays[date] else { return }
        for item in queuedOutcomes[date] ?? [] {
            day = day.applyingPlannedOutcome(slotKey: item.slotKey, outcome: item.outcome)
        }
        days[date] = day
    }
}

struct NativeHomeView: View {
    var onOpenProgress: () -> Void = {}
    var onOpenDiet: () -> Void = {}
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @EnvironmentObject private var session: NativeSession
    @EnvironmentObject private var diary: NativeDietStore
    @EnvironmentObject private var tabData: NativeTabDataStore
    @State private var showMeal = false
    @State private var showingWorkoutPlans = false
    @State private var showingDietPlan = false
    private var today: String { dietDate(Date(), timezone: session.profile?.profile?.timezone) }

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(L("Hoje")).font(FitTrackerTheme.pageTitle)
                            Text(Date(), style: .date).font(.subheadline).foregroundColor(.secondary)
                        }
                        Spacer()
                        Button(action: onOpenProgress) {
                            Image(systemName: "calendar").font(.system(size: 20)).frame(width: 44, height: 44).fitPremiumCard()
                        }.buttonStyle(.plain).foregroundColor(.white.opacity(0.85)).accessibilityLabel(L("Abrir calendário de progresso"))
                    }.padding(.bottom, 4)
                    if let summary = tabData.gamification ?? tabData.progressOverview?.gamification {
                        NativeGamificationHomeCard(summary: summary, action: onOpenProgress)
                    } else if tabData.progressLoading {
                        HStack(spacing: 10) {
                            Image(systemName: "rosette.fill").foregroundColor(.fitBlue)
                            Text(L("Carregando seu nível…")).font(.subheadline.weight(.semibold))
                            Spacer()
                            ProgressView().controlSize(.small)
                        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                    }
                    if let message = diary.successMessage {
                        HStack(alignment: .top) {
                            Button { onOpenDiet() } label: { Label(message, systemImage: "checkmark.circle.fill").multilineTextAlignment(.leading) }
                            Spacer()
                            Button { diary.successMessage = nil } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }.accessibilityLabel(L("Fechar confirmação"))
                        }.font(.subheadline).padding(14).background(Color.green.opacity(0.1), in: RoundedRectangle(cornerRadius: 18))
                    }
                    if needsFirstAction { firstActionCard }
                    if let day = diary.days[today], !needsFirstAction {
                        NativeNutritionView(day: day, compact: true, onOpenDiary: onOpenDiet)
                    } else if diary.loading.contains(today) {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(L("Alimentação")).font(FitTrackerTheme.sectionTitle)
                            Text(L("Carregando suas refeições…")).font(.subheadline).foregroundColor(.secondary)
                        }.frame(maxWidth: .infinity, alignment: .leading).padding(16).fitPremiumCard()
                    } else if diary.days[today] == nil && diary.errors[today] == nil {
                        HStack { Text(L("Alimentação de hoje")); Spacer(); ProgressView().controlSize(.small) }
                            .font(FitTrackerTheme.sectionTitle).frame(maxWidth: .infinity, alignment: .leading).padding(16).fitPremiumCard()
                    }
                    if let error = diary.errors[today] { diaryError(error) }
                    if !needsFirstAction { Button { showMeal = true } label: {
                        Label(L("Adicionar refeição"), systemImage: "plus").font(.body.weight(.semibold))
                            .frame(maxWidth: .infinity)
                    }.buttonStyle(FitPrimaryButtonStyle()) }
                    NativeWaterCard().id(session.user?.id)
                    homeSection(L("Seu treino"), action: L("Ver todos")) { showingWorkoutPlans = true }
                    NativeTodayWorkoutCard()
                    if let day = diary.days[today] {
                        homeSection(L("Alimentação"), action: L("Ver plano")) { showingDietPlan = true }
                        let pending = day.slots.filter { $0.result == "pending" }
                        if pending.isEmpty {
                            Text(diary.pendingWrites.contains(today) ? L("Suas marcações aguardam confirmação. Elas continuam neste aparelho enquanto sincronizamos.") : day.plan == nil ? L("Sem plano alimentar por enquanto. Adicione uma refeição ou toque em Ver plano para começar.") : L("Tudo em dia! Veja suas refeições registradas na aba Dieta."))
                                .font(.subheadline).foregroundColor(.secondary)
                        }
                        ForEach(pending) { slot in NativeDietSlotView(slot: slot, date: today, compact: true) }
                            .animation(reduceMotion ? nil : .spring(response: 0.35, dampingFraction: 0.88), value: pending.map(\.id))
                    }
                }.padding(.horizontal, FitTrackerTheme.pagePadding).padding(.vertical, 12)
            }
            .background(FitTrackerTheme.background.ignoresSafeArea())
            .navigationBarHidden(true)
            .refreshable { await retryDiary() }
            .task(id: today) { await diary.load(today, api: session.api) }
            .onReceive(NotificationCenter.default.publisher(for: Notification.Name("fitTrackerDataDidChange"))) { _ in
                Task { await tabData.loadProgress(force: true) }
            }
            .sheet(isPresented: $showMeal) { NativeMealComposer(date: today) }
            .sheet(isPresented: $showingWorkoutPlans) { NativePlansView(kind: .workout) }
            .sheet(isPresented: $showingDietPlan, onDismiss: { Task { await diary.load(today, api: session.api, refreshAfterCurrent: true) } }) { NativePlansView(kind: .diet) }
            .onReceive(NotificationCenter.default.publisher(for: .nativeFirstAction)) { notification in
                if notification.userInfo?["intent"] as? String == "workout" { showingWorkoutPlans = true }
                else { showMeal = true }
            }
            .onReceive(NotificationCenter.default.publisher(for: Notification.Name("fitTrackerNavigate"))) { _ in
                showingWorkoutPlans = false; showingDietPlan = false
            }
            .task { if session.freeAccess == nil { try? await session.refreshFreeAccess() } }
        }.navigationViewStyle(.stack)
    }

    private func homeSection(_ title: String, action: String, onTap: @escaping () -> Void) -> some View {
        HStack {
            Text(title).font(FitTrackerTheme.sectionTitle)
            Spacer()
            Button(action: onTap) { HStack(spacing: 6) { Text(action); Image(systemName: "chevron.right").font(.caption.weight(.semibold)) } }
                .font(.subheadline.weight(.medium)).foregroundColor(FitTrackerTheme.electricBlue)
        }.padding(.top, 4)
    }

    private var needsFirstAction: Bool {
        guard let day = diary.days[today] else { return false }
        return day.entries.isEmpty && day.plan == nil && tabData.workoutToday?.state == "unconfigured"
    }

    private var firstActionCard: some View {
        let startsWithWorkout = session.user.map { NativeFirstDay.intent(owner: $0.id) == .workout } ?? false
        return VStack(alignment: .leading, spacing: 16) {
            Text(L("COMECE POR AQUI")).font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
            Text(startsWithWorkout ? L("Seu primeiro treino, do seu jeito") : L("Uma refeição já é um começo")).font(.title2.bold())
            Text(startsWithWorkout ? L("Monte seu treino ou personalize um plano para sua rotina.") : L("Registre o que você comeu. Você pode começar manualmente, sem configurar um plano.")).foregroundColor(.secondary)
            Button {
                if startsWithWorkout { showingWorkoutPlans = true } else { showMeal = true }
            } label: {
                Text(startsWithWorkout ? L("Criar meu treino") : L("Registrar primeira refeição")).frame(maxWidth: .infinity)
            }.buttonStyle(FitPrimaryButtonStyle())
            Button(startsWithWorkout ? L("Começar pela alimentação") : L("Começar pelo treino")) {
                if startsWithWorkout { showMeal = true } else { showingWorkoutPlans = true }
            }.frame(maxWidth: .infinity, minHeight: 44).font(.subheadline)
        }.padding(20).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius))
    }

    private func diaryError(_ message: String) -> some View {
        NativeRecoveryCard(title: diary.pendingWrites.contains(today) ? L("Vamos confirmar seus registros?") : L("Seu dia continua aqui"), message: diary.days[today] == nil ? message : L("Mostramos a última atualização disponível. ") + message, actionTitle: diary.pendingWrites.contains(today) ? L("Sincronizar registros") : L("Atualizar meu dia")) { Task { await retryDiary() } }
            .disabled(diary.loading.contains(today) || diary.resuming)
    }
    @MainActor private func retryDiary() async {
        let owner = session.user?.id
        NotificationCenter.default.post(name: Notification.Name("FitTrackerWaterRefresh"), object: nil)
        await diary.retry(today, api: session.api, isCurrentOwner: { session.user?.id == owner })
    }
}

private struct NativeGamificationHomeCard: View {
    let summary: GamificationSummary
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    Image(systemName: "rosette.fill").foregroundColor(.fitBlue)
                    NativeXPLevelLabel(summary: summary).font(.subheadline.weight(.semibold))
                    Spacer()
                    Text("\(summary.currentStreak) \(L("dias"))").font(.caption.weight(.semibold)).foregroundColor(.orange)
                    Image(systemName: "flame.fill").foregroundColor(.orange)
                }
                NativeXPProgressBar(summary: summary)
            }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain).accessibilityElement(children: .ignore)
            .accessibilityLabel(L("\(summary.rank), nível \(summary.level), \(summary.currentStreak) dias, ver progresso"))
    }
}

struct NativeDietView: View {
    @EnvironmentObject private var session: NativeSession
    @EnvironmentObject private var diary: NativeDietStore
    @State private var selectedDate = Date()
    @State private var showPlans = false
    @State private var showMeal = false
    private var date: String { dietDate(selectedDate, timezone: session.profile?.profile?.timezone) }

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    DatePicker(L("Dia do diário"), selection: $selectedDate, displayedComponents: .date)
                        .datePickerStyle(.compact)
                    if diary.days[date] == nil && diary.loading.contains(date) { ProgressView(L("Carregando refeições…")) }
                    if let error = diary.errors[date] {
                        NativeRecoveryCard(title: diary.pendingWrites.contains(date) ? L("Seus registros aguardam confirmação") : L("Vamos retomar seu diário?"), message: diary.days[date] == nil ? error : L("Suas refeições carregadas continuam visíveis. ") + error, actionTitle: diary.pendingWrites.contains(date) ? L("Sincronizar registros") : L("Atualizar refeições")) { Task { await retryDiary() } }
                            .disabled(diary.loading.contains(date) || diary.resuming)
                    }
                    if let day = diary.days[date] {
                        if let message = diary.successMessage {
                            HStack { Label(message, systemImage: "checkmark.circle.fill"); Spacer(); Button { diary.successMessage = nil } label: { Image(systemName: "xmark").frame(width: 44, height: 44) }.accessibilityLabel(L("Fechar confirmação")) }.font(.subheadline).foregroundColor(.green)
                        }
                        if !day.entries.isEmpty || day.plan != nil { NativeNutritionView(day: day, compact: false) }
                        if let plan = day.plan {
                            Label(plan.title, systemImage: "list.bullet.rectangle").font(.headline)
                        }
                        if !day.slots.isEmpty {
                            Text(L("A fazer")).font(.title3.bold())
                            ForEach(day.slots.filter { $0.result == "pending" }) { slot in NativeDietSlotView(slot: slot, date: date) }
                            if !day.slots.contains(where: { $0.result == "pending" }) { Text(L("As refeições do plano estão resolvidas para este dia.")).font(.subheadline).foregroundColor(.secondary) }
                        }
                        if day.entries.isEmpty && day.slots.isEmpty {
                            NativeRecoveryCard(title: L("Seu diário começa com uma refeição"), message: L("Ainda não há registros neste dia. Adicione o que comeu, com foto, descrição ou manualmente."), systemImage: "fork.knife", actionTitle: L("Registrar primeira refeição")) { showMeal = true }
                        }
                        if !day.entries.isEmpty { Text(L("Registradas")).font(.title3.bold()) }
                        ForEach(day.entries) { entry in NativeMealRow(entry: entry) }
                        ForEach(day.slots.filter { $0.result == "skipped" }) { slot in NativeDietSlotView(slot: slot, date: date) }
                    }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(L("Alimentação"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button(L("Plano")) { showPlans = true } }
            .safeAreaInset(edge: .bottom) {
                Button { showMeal = true } label: {
                    Label(L("Registrar refeição"), systemImage: "plus").font(.body.weight(.semibold))
                        .frame(maxWidth: .infinity).padding(.vertical, 9)
                }.fitGlassButton(prominent: true).padding(.horizontal, 20).padding(.vertical, 12)
            }
            .refreshable { await retryDiary() }
            .task(id: date) { await diary.load(date, api: session.api) }
            .sheet(isPresented: $showMeal) { NativeMealComposer(date: date) }
            .sheet(isPresented: $showPlans, onDismiss: { Task { await diary.load(date, api: session.api, refreshAfterCurrent: true) } }) { NativePlansView(kind: .diet) }
            .onReceive(NotificationCenter.default.publisher(for: Notification.Name("fitTrackerNavigate"))) { _ in showPlans = false }
        }.navigationViewStyle(.stack)
    }
    @MainActor private func retryDiary() async {
        let owner = session.user?.id
        await diary.retry(date, api: session.api, isCurrentOwner: { session.user?.id == owner })
    }
}

private struct NutritionMetric: Identifiable {
    let id: String
    let icon: String
    let color: Color
    let value: Double?
    let target: Double?
    let unit: String
    var fraction: Double { guard let value, let target, target > 0 else { return 0 }; return min(max(value / target, 0), 1) }
}

private struct NativeAnimatedNutritionNumber: View, Animatable {
    var value: Double
    var animatableData: Double {
        get { value }
        set { value = newValue }
    }
    var body: some View {
        Text(value.formatted(.number.locale(NativeLocalization.locale).precision(.fractionLength(0...1))))
            .monospacedDigit().fontWeight(.bold)
    }
}

struct NativeNutritionView: View {
    let day: DietDayResponse
    let compact: Bool
    var onOpenDiary: (() -> Void)? = nil
    @Environment(\.sizeCategory) private var textSize
    @State private var selected: String?
    private var metrics: [NutritionMetric] { [
        .init(id: L("Calorias"), icon: "flame", color: .orange, value: day.totals.calories, target: day.targets.calories, unit: "kcal"),
        .init(id: L("Proteínas"), icon: "p.circle", color: .blue, value: day.totals.protein, target: day.targets.protein, unit: "g"),
        .init(id: L("Carboidratos"), icon: "leaf", color: .mint, value: day.totals.carbs, target: day.targets.carbs, unit: "g"),
        .init(id: L("Gorduras"), icon: "drop", color: .purple, value: day.totals.fat, target: day.targets.fat, unit: "g")
    ] }

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 12 : 16) {
            HStack {
                Text(compact ? L("Seu dia") : L("Resumo do dia"))
                    .font(compact ? .headline : .caption).foregroundColor(compact ? .white : .secondary)
                Spacer()
                if compact, let onOpenDiary {
                    Button(action: onOpenDiary) {
                        HStack(spacing: 5) { Text(mealCountText); Image(systemName: "chevron.right").foregroundColor(FitTrackerTheme.electricBlue) }
                    }.buttonStyle(.plain).accessibilityLabel(L("\(mealCountText). Abrir diário alimentar"))
                } else { Text(mealCountText) }
            }.font(.caption).foregroundColor(.secondary)
            if compact {
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: textSize.isAccessibilityCategory ? 2 : 4), alignment: .center, spacing: 12) {
                    ForEach(Array(metrics.enumerated()), id: \.element.id) { index, metric in
                        Button { toggle(metric.id) } label: {
                            VStack(spacing: 5) {
                                ZStack {
                                    Circle().stroke(metric.color.opacity(0.13), lineWidth: 4)
                                    Circle().trim(from: 0, to: metric.fraction).stroke(metric.color, style: StrokeStyle(lineWidth: 4, lineCap: .round)).rotationEffect(.degrees(-90))
                                    Image(systemName: metric.icon).font(.system(size: 20)).foregroundColor(metric.color)
                                }.frame(width: 44, height: 44)
                                    .background(NativeXPNutritionProbe(index: index))
                                    .animation(.easeOut(duration: 0.55), value: metric.fraction)
                                HStack(spacing: 0) {
                                    if let value = metric.value {
                                        NativeAnimatedNutritionNumber(value: value).foregroundColor(metric.color)
                                    } else {
                                        Text("—").fontWeight(.bold).foregroundColor(metric.color)
                                    }
                                    Text(" / \(numberText(metric.target))\(metric.unit == "g" ? "g" : "")").foregroundColor(.secondary)
                                }
                                    .font(.caption2).lineLimit(1).minimumScaleFactor(0.7)
                                    .animation(.easeOut(duration: 0.55), value: metric.value)
                                Text(metric.id).font(.caption2).foregroundColor(.secondary).lineLimit(1).minimumScaleFactor(0.75)
                            }.frame(maxWidth: .infinity)
                        }.buttonStyle(.plain).accessibilityLabel(L("Detalhes de \(metric.id)"))
                            .accessibilityValue(selected == metric.id ? L("Expandido") : L("Recolhido"))
                    }
                }
            } else {
                    ForEach(Array(metrics.enumerated()), id: \.element.id) { index, metric in
                    Button { toggle(metric.id) } label: {
                        HStack(spacing: 12) {
                            Image(systemName: metric.icon).foregroundColor(metric.color).frame(width: 24)
                            VStack(alignment: .leading, spacing: 7) {
                                HStack { Text(metric.id); Spacer(); Text(nutrientText(metric.value, metric.unit)).fontWeight(.semibold) }
                                GeometryReader { geo in
                                    Capsule().fill(Color.white.opacity(0.08))
                                    Capsule().fill(metric.color).frame(width: geo.size.width * metric.fraction)
                                }.frame(height: 4)
                            }.background(NativeXPNutritionProbe(index: index))
                                .animation(.easeOut(duration: 0.55), value: metric.fraction)
                        }.font(.subheadline).padding(.vertical, 6)
                    }.buttonStyle(.plain).accessibilityLabel(L("Detalhes de \(metric.id)"))
                }
            }
            if let metric = metrics.first(where: { $0.id == selected }) {
                Divider()
                Text(metric.id).font(.headline)
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], alignment: .leading, spacing: 16) {
                    detail(L("Consumido"), nutrientText(metric.value, metric.unit))
                    detail(L("Meta"), nutrientText(metric.target, metric.unit))
                    detail(L("Progresso"), metric.target.map { $0 > 0 ? "\(Int(((metric.value ?? 0) / $0 * 100).rounded()))%" : L("Sem meta") } ?? L("Sem meta"))
                    detail(L("Saldo"), balance(metric))
                }
            }
        }.padding(compact ? 14 : 16)
            .background(compact ? FitTrackerTheme.cardGradient : LinearGradient(colors: [.fitSurface, .fitSurface], startPoint: .top, endPoint: .bottom), in: RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius))
            .overlay(RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius).stroke(compact ? FitTrackerTheme.electricBlue.opacity(0.2) : .clear, lineWidth: 1))
    }
    private var mealCountText: String {
        let count = day.entries.count + day.slots.filter { $0.result == "consumed_planned" && $0.entry == nil }.count
        if compact, !day.slots.isEmpty { return L("\(count) de \(day.slots.count) refeições") }
        return L("\(count) \(count == 1 ? L("refeição") : L("refeições"))")
    }
    private func numberText(_ value: Double?) -> String {
        value.map { $0.formatted(.number.locale(NativeLocalization.locale).precision(.fractionLength(0...1))) } ?? "—"
    }
    private func toggle(_ id: String) { selected = selected == id ? nil : id }
    private func detail(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 5) { Text(title).font(.caption).foregroundColor(.secondary); Text(value).font(.subheadline.weight(.semibold)) }
    }
    private func balance(_ metric: NutritionMetric) -> String {
        guard let target = metric.target, let value = metric.value, target > 0 else { return L("Sem meta") }
        return (target >= value ? L("Faltam ") : L("Acima: ")) + nutrientText(abs(target - value), metric.unit)
    }
}

struct NativeMealRow: View {
    let entry: DietEntry
    @EnvironmentObject private var session: NativeSession
    @EnvironmentObject private var diary: NativeDietStore
    @State private var editing = false
    @State private var confirmDelete = false
    @State private var busy = false
    @State private var error: String?
    var body: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 10) {
                Text(entry.description)
                Text(L("Proteínas: \(nutrientText(entry.protein, "g")) · Carboidratos: \(nutrientText(entry.carbs, "g")) · Gorduras: \(nutrientText(entry.fat, "g"))"))
                    .font(.caption).foregroundColor(.secondary)
                if let notes = entry.notes, !notes.isEmpty { Text(notes).font(.caption) }
                HStack {
                    Button(L("Editar registro")) { editing = true }.frame(minHeight: 44)
                    Spacer()
                    Button(L("Excluir"), role: .destructive) { confirmDelete = true }.frame(minHeight: 44)
                }.disabled(busy)
                if let error { Text(NativeLocalization.display(error)).font(.footnote).foregroundColor(.red) }
            }.padding(.top, 8)
        } label: {
            HStack {
                Image(systemName: "fork.knife").foregroundColor(.fitBlue)
                VStack(alignment: .leading, spacing: 4) { Text(entry.mealType).font(.headline); Text(entry.description).font(.caption).foregroundColor(.secondary).lineLimit(1) }
                Spacer()
                Text(nutrientText(entry.calories, "kcal")).font(.caption)
            }
        }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
            .sheet(isPresented: $editing) { NativeMealComposer(date: entry.date, editingEntry: entry) }
            .confirmationDialog(L("Excluir esta refeição?"), isPresented: $confirmDelete, titleVisibility: .visible) {
                Button(L("Excluir refeição"), role: .destructive) { Task { await remove() } }
                Button(L("Cancelar"), role: .cancel) { }
            } message: { Text(entry.dailyMealStateId == nil ? L("O registro será removido dos totais deste dia.") : L("O consumo será removido e a refeição do plano ficará pendente novamente.")) }
    }
    private func remove() async {
        guard !busy, let owner = session.user?.id else { return }; busy = true; error = nil
        let removed = await diary.mutateSlot(date: entry.date, slotKey: "entry-\(entry.id)", api: session.api,
            isCurrentOwner: { session.user?.id == owner }, action: { try await session.api.deleteDietEntry(id: entry.id) })
        busy = false
        if removed { diary.successMessage = L("Refeição excluída.") }
        else { error = diary.errors[entry.date] }
    }
}

func nutrientText(_ value: Double?, _ unit: String) -> String {
    guard let value else { return L("Não informado") }
    return value.formatted(.number.locale(NativeLocalization.locale).precision(.fractionLength(0...1))) + " " + unit
}

func dietDate(_ date: Date, timezone: String?) -> String {
    let formatter = DateFormatter()
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = timezone.flatMap(TimeZone.init(identifier:)) ?? .current
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.string(from: date)
}

@MainActor
enum NativeWaterStores {
    private final class AccountStore {
        weak var session: NativeSession?
        let tracker: WaterTracker
        init(session: NativeSession, tracker: WaterTracker) { self.session = session; self.tracker = tracker }
    }
    private static var accounts: [UUID: AccountStore] = [:]
    static func tracker(for session: NativeSession, owner: UUID) -> WaterTracker {
        if let existing = accounts[owner], existing.session === session { return existing.tracker }
        let tracker = WaterTracker(api: session.api, ownerId: owner, isCurrentOwner: { [weak session] in session?.user?.id == owner })
        accounts[owner] = AccountStore(session: session, tracker: tracker)
        return tracker
    }
    static func preload(session: NativeSession, owner: UUID) async {
        await tracker(for: session, owner: owner).refresh()
    }
}

struct NativeWaterCard: View {
    @EnvironmentObject private var account: NativeSession
    var body: some View {
        if let owner = account.user?.id {
            NativeWaterContent(water: NativeWaterStores.tracker(for: account, owner: owner)).id(owner)
        }
    }
}

private struct NativeWaterContent: View {
    @EnvironmentObject private var account: NativeSession
    @Environment(\.scenePhase) private var scenePhase
    @ObservedObject var water: WaterTracker
    @State private var showing = false
    @State private var editingBottle = false
    @State private var bottleText = ""
    @State private var bottleError: String?
    @State private var currentTime = Date()

    private var day: WaterDay? { water.day }
    private var busy: Bool { water.loading || water.savingBottle }
    private var error: String? { bottleError ?? water.error }
    private var timezone: String { day?.timezone ?? account.profile?.profile?.timezone ?? TimeZone.current.identifier }
    private var date: String { dietDate(currentTime, timezone: timezone) }
    private var pending: [WaterQueuedWrite] { water.queue.visiblePending(date: date, timezone: timezone) }
    private var entries: [WaterEntry] { water.visibleEntries(date: date, timezone: timezone) }
    private var total: Int { water.total(date: date, timezone: timezone) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if day == nil && busy && water.queue.writes.isEmpty {
                VStack(alignment: .leading, spacing: 14) {
                    RoundedRectangle(cornerRadius: 6).fill(Color.white.opacity(0.08)).frame(width: 110, height: 18)
                    RoundedRectangle(cornerRadius: 12).fill(Color.white.opacity(0.05)).frame(height: 42)
                }.accessibilityElement(children: .ignore).accessibilityLabel(L("Carregando água de hoje"))
            } else {
            HStack {
                Label(L("Água hoje"), systemImage: "drop.fill").font(.headline).foregroundColor(.cyan)
                Spacer()
                Text("\(total) ml").font(.title3.bold())
            }
            Button { showing = true } label: {
                Label(L("Registrar água"), systemImage: "plus").frame(maxWidth: .infinity)
            }.fitGlassButton()
            }
            if let error { recovery(error) }
            if water.saving { Text(L("Salvando em segundo plano…")).font(.caption).foregroundColor(.secondary) }
            if let latest = pending.last {
                Button(L("Desfazer último registro")) { water.undoPending(latest.id) }.font(.footnote)
            } else if let latest = entries.first {
                Button(L("Desfazer último registro")) { water.undoConfirmed(latest) }.font(.footnote)
            }
        }
        .padding(16).fitPremiumCard()
        .task(id: date) { await water.refresh() }
        .onReceive(Timer.publish(every: 60, on: .main, in: .common).autoconnect()) { currentTime = $0 }
        .onReceive(NotificationCenter.default.publisher(for: Notification.Name("FitTrackerWaterRefresh"))) { _ in
            currentTime = Date(); Task { await water.refresh() }
        }
        .onChange(of: scenePhase) { phase in
            if phase == .active { currentTime = Date(); Task { await water.refresh() } }
        }
        .sheet(isPresented: $showing) {
            NavigationView {
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        waterSummary
                        if let latest = pending.last {
                            HStack {
                                Text(L("\(latest.entry.amountMl) ml adicionados")).font(.subheadline)
                                Spacer()
                                Button(L("Desfazer")) { water.undoPending(latest.id) }
                            }
                        } else if let latest = entries.first {
                            HStack {
                                Text(L("Último registro: \(latest.amountMl) ml")).font(.subheadline)
                                Spacer()
                                Button(L("Desfazer")) { water.undoConfirmed(latest) }
                            }
                        }

                        VStack(alignment: .leading, spacing: 12) {
                            Text(L("Quanto você bebeu?")).font(.headline)
                            Text(L("Toque para registrar uma quantidade.")).font(.subheadline).foregroundColor(.secondary)
                            waterOption(L("Copo médio"), amount: 200, icon: "cup.and.saucer.fill") { record(200) }
                            waterOption(L("Copo grande"), amount: 300, icon: "cup.and.saucer.fill") { record(300) }
                            if let capacity = day?.bottleCapacityMl {
                                waterOption(L("Minha garrafinha"), amount: capacity, icon: "waterbottle.fill") { record(capacity) }
                            } else {
                                Button { editingBottle = true } label: {
                                    Label(L("Cadastrar minha garrafinha"), systemImage: "plus.circle.fill")
                                        .font(.subheadline.weight(.semibold)).frame(maxWidth: .infinity, minHeight: 48)
                                }.fitGlassButton().disabled(water.savingBottle)
                            }
                        }

                        VStack(alignment: .leading, spacing: 12) {
                            if editingBottle {
                                Text(L("Capacidade da garrafinha")).font(.headline)
                                HStack {
                                    TextField(L("Ex.: 750"), text: $bottleText).keyboardType(.numberPad)
                                        .padding(12).background(Color.fitBackground, in: RoundedRectangle(cornerRadius: 12))
                                    Text("ml").foregroundColor(.secondary)
                                    Button(L("Salvar")) { Task { await saveBottle() } }.fitGlassButton(prominent: true).disabled(busy)
                                }
                                Button(L("Cancelar")) { editingBottle = false }.font(.subheadline)
                                Text(L("Salvar a capacidade não registra água consumida.")).font(.caption).foregroundColor(.secondary)
                            } else if day?.bottleCapacityMl != nil {
                                Button { bottleText = day?.bottleCapacityMl.map(String.init) ?? ""; editingBottle = true } label: {
                                    Label(L("Editar garrafinha"), systemImage: "pencil").font(.subheadline.weight(.semibold))
                                }.disabled(busy)
                            }
                        }

                        if let error { recovery(error) }
                        else if water.saving { Text(L("Salvando em segundo plano…")).font(.caption).foregroundColor(.secondary) }

                        VStack(alignment: .leading, spacing: 12) {
                            Text(L("Registros de hoje")).font(.headline)
                            ForEach(pending) { write in
                                HStack(spacing: 12) {
                                    Image(systemName: "drop.fill").foregroundColor(.cyan)
                                    Text("\(write.entry.amountMl) ml").fontWeight(.semibold)
                                    Spacer()
                                    Text(L("Salvando…")).font(.caption).foregroundColor(.secondary)
                                    Button(L("Desfazer")) { water.undoPending(write.id) }.font(.subheadline)
                                }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                            }
                            if entries.isEmpty && pending.isEmpty {
                                Text(L("Seus registros vão aparecer aqui.")).font(.subheadline).foregroundColor(.secondary)
                            }
                            Group {
                                ForEach(entries) { entry in
                                    HStack(spacing: 12) {
                                        Image(systemName: "drop.fill").foregroundColor(.cyan)
                                        VStack(alignment: .leading, spacing: 3) {
                                            Text("\(entry.amountMl) ml").fontWeight(.semibold)
                                            Text(time(entry.occurredAt)).font(.caption).foregroundColor(.secondary)
                                        }
                                        Spacer()
                                        Button(L("Desfazer")) { water.undoConfirmed(entry) }
                                            .font(.subheadline)
                                            .accessibilityLabel(L("Desfazer \(entry.amountMl) ml às \(time(entry.occurredAt))"))
                                    }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                                }
                            }
                        }
                    }.padding(20)
                }.background(Color.fitBackground.ignoresSafeArea())
                .navigationTitle(L("Água hoje")).navigationBarTitleDisplayMode(.inline)
                .toolbar { Button(L("Fechar")) { showing = false } }
            }.navigationViewStyle(.stack)
        }
    }

    private var waterSummary: some View {
        HStack(spacing: 16) {
            Image(systemName: "drop.fill").font(.title).foregroundColor(.cyan)
                .frame(width: 58, height: 58).background(Color.cyan.opacity(0.14), in: RoundedRectangle(cornerRadius: 18))
            VStack(alignment: .leading, spacing: 4) {
                Text(L("CONSUMO DE HOJE")).font(.caption.weight(.semibold)).tracking(0.8).foregroundColor(.secondary)
                Text("\(total) ml").font(.title.bold())
                Text(water.queue.writes.isEmpty ? L("Consumo registrado") : L("Atualizado agora")).font(.caption).foregroundColor(.secondary)
            }
            Spacer(minLength: 0)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(20)
            .background(LinearGradient(colors: [Color.cyan.opacity(0.14), Color.fitSurface], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 22))
    }

    private func waterOption(_ title: String, amount: Int, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: icon).font(.title3).foregroundColor(.cyan)
                    .frame(width: 44, height: 44).background(Color.cyan.opacity(0.12), in: RoundedRectangle(cornerRadius: 14))
                VStack(alignment: .leading, spacing: 4) {
                    Text(title).font(.subheadline.weight(.semibold)).foregroundColor(.primary)
                    Text("\(amount) ml").font(.caption).foregroundColor(.secondary)
                }
                Spacer()
                Image(systemName: "plus.circle.fill").font(.title3).foregroundColor(.cyan)
            }.padding(14).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain)
            .accessibilityLabel(L("Registrar \(title), \(amount) mililitros"))
    }

    private func recovery(_ message: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(NativeLocalization.display(message)).font(.footnote).foregroundColor(.secondary)
            Button(L("Tentar novamente")) { Task { await water.refresh() } }.disabled(water.saving)
        }
    }

    private func record(_ amount: Int) {
        currentTime = Date()
        water.record(amount, at: currentTime)
        if let key = water.queue.writes.last?.entry.key { NativeXPEffects.shared.captureAction(key: key) }
    }

    @MainActor private func saveBottle() async {
        guard let capacity = Int(bottleText.trimmingCharacters(in: .whitespacesAndNewlines)), (1...10000).contains(capacity) else {
            bottleError = L("Informe a capacidade de 1 a 10.000 ml."); return
        }
        bottleError = nil
        do { try await water.saveBottle(capacity); editingBottle = false }
        catch { bottleError = RequestFailure.message(error, fallback: L("Não foi possível salvar sua garrafinha.")) }
    }

    private func time(_ timestamp: String) -> String {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let value = parser.date(from: timestamp) ?? ISO8601DateFormatter().date(from: timestamp) else { return "" }
        let formatter = DateFormatter()
        formatter.timeZone = TimeZone(identifier: timezone)
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: value)
    }
}
