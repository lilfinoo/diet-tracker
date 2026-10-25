import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
import FitTrackerCore

struct NativeTodayWorkoutCard: View {
    @Environment(NativeSession.self) var session
    @Environment(NativeTabDataStore.self) var tabData
    @State var showingWorkout = false
    @State var showingGenerator = false
    @State var showingPremium = false
    var today: WorkoutToday? { tabData.workoutToday }

    var body: some View {
        Button {
            if today?.state == "unconfigured" { showingGenerator = true }
            else { showingWorkout = true }
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                Text("TREINO DE HOJE")
                    .font(.caption.weight(.bold)).foregroundColor(FitTrackerTheme.electricBlue)
                Text(today?.state == "unconfigured" ? "Crie seu primeiro treino" : today?.currentDay?.title ?? workoutStateTitle(today?.state ?? ""))
                    .font(FitTrackerTheme.cardTitle).foregroundColor(.white).fixedSize(horizontal: false, vertical: true)
                if let today {
                    if today.state == "unconfigured" {
                        Text("Um plano feito para seu objetivo e sua rotina.")
                            .font(.subheadline).foregroundColor(Color.white.opacity(0.72))
                    } else {
                        HStack(alignment: .top, spacing: 12) {
                            if let day = today.currentDay {
                                Label("\(day.exercises.count) exercícios", systemImage: "calendar")
                            }
                            Label(workoutStateTitle(today.state), systemImage: "clock")
                        }
                        .font(.caption).foregroundColor(Color(red: 0.66, green: 0.81, blue: 0.96))
                        .fixedSize(horizontal: false, vertical: true)
                    }
                    if today.currentDay != nil || today.state == "unconfigured" {
                        HStack(spacing: 9) {
                            Text(today.state == "unconfigured" ? "Montar meu treino" : today.state == "active" ? "Continuar treino" : "Ver treino")
                            Image(systemName: "arrow.right")
                        }
                        .fitPrimarySurface(compact: true)
                        .padding(.top, 4)
                    }
                }
                if tabData.workoutLoading && today == nil { ProgressView() }
                if let error = tabData.workoutError { Text(error).font(.caption).foregroundColor(.red) }
            }
            .padding(16).padding(.trailing, workoutImageName == nil ? 0 : 54)
            .frame(maxWidth: .infinity, minHeight: 160, alignment: .leading)
            .background {
                if let name = workoutImageName {
                    GeometryReader { geometry in
                        Image(name).resizable().scaledToFill()
                            .frame(width: geometry.size.width, height: geometry.size.height, alignment: .trailing)
                            .clipped()
                    }
                    .overlay(LinearGradient(stops: [
                        .init(color: Color.fitBackground.opacity(0.95), location: 0),
                        .init(color: Color.fitBackground.opacity(0.80), location: 0.40),
                        .init(color: Color.fitBackground.opacity(0.18), location: 0.75),
                        .init(color: .clear, location: 1)
                    ], startPoint: .leading, endPoint: .trailing))
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius))
            .fitPremiumCard()
            .contentShape(RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius))
        }.buttonStyle(.plain)
        .accessibilityHint("Abrir seu treino")
        .task { await tabData.loadWorkout() }
        .onFitNotification(.nativeWorkoutChanged) { _ in Task { await tabData.loadWorkout(force: true) } }
        .sheet(isPresented: $showingGenerator, onDismiss: { Task { await tabData.loadWorkout(force: true) } }) { PlanGeneratorView(kind: .workout, firstPlan: true) }
        .sheet(isPresented: $showingPremium) { NavigationStack { NativeSubscriptionView() } }
        .fullScreenCover(isPresented: $showingWorkout, onDismiss: { Task { await tabData.loadWorkout(force: true) } }) {
            if let today = tabData.workoutToday, let planId = today.currentPlanId, let day = today.currentDay,
               ["scheduled", "active"].contains(today.state) {
                NativeWorkoutExecutionView(planId: planId, day: day)
            } else { NativeWorkoutView(presented: true) }
        }
    }

    var workoutImageName: String? {
        guard let today, today.state != "rest", today.state != "unconfigured", let day = today.currentDay else { return nil }
        func category(_ text: String) -> String? {
            let text = text.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "pt_BR"))
            if ["perna", "inferior", "quadriceps", "posterior", "glute", "panturrilha"].contains(where: text.contains) { return "Perna" }
            if ["costas", "dorsal", "biceps", "ombro", "deltoid"].contains(where: text.contains) { return "Costas" }
            if ["peito", "peitoral", "triceps", "abdomen", "abdominal", "core"].contains(where: text.contains) { return "Peito" }
            return nil
        }
        guard let group = day.focus.flatMap(category) ?? category(day.title) else { return nil }
        let gender = session.profile?.profile?.gender?.lowercased() ?? ""
        let variant = ["feminino", "female", "f"].contains(gender) ? "Fem" : "Masc"
        return "Workout\(group)\(variant)"
    }

}

struct NativeWorkoutView: View {
    var presented = false
    @Environment(\.dismiss) var dismiss
    @Environment(\.timeZone) var timeZone
    @Environment(NativeSession.self) var session
    @Environment(NativeTabDataStore.self) var tabData
    @State var showPlans = false
    @State var showingGenerator = false
    @State var showingWorkout = false
    @State var selectedWeekday: Int?
    @State var selectedDay: WorkoutDay?
    @State var selectedActivityId: Int?
    @State var selectedState: String?
    @State var selectionError: String?

    var today: WorkoutToday? { tabData.workoutToday }
    var loading: Bool { tabData.workoutLoading }
    var error: String? { selectionError ?? tabData.workoutError }
    var localWeekday: Int { weekdayIndex(for: today?.localDate ?? "") ?? 0 }
    var day: WorkoutDay? {
        guard let selectedWeekday else { return today?.currentDay }
        return selectedWeekday == localWeekday ? today?.currentDay : selectedDay
    }
    var state: String { selectedState ?? today?.state ?? "" }
    var title: String { day?.title ?? (state == "rest" ? "Dia de descanso" : today?.currentPlan?.title ?? "Seu treino") }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if loading && today == nil { ProgressView("Carregando treino…").frame(maxWidth: .infinity) }
                    if let error {
                        Text(error).foregroundColor(.red)
                        Button("Tentar novamente") { Task { await tabData.loadWorkout(force: true) } }
                    }
                    if let today {
                        if !today.week.isEmpty {
                            HStack(spacing: 4) {
                                ForEach(today.week) { weekday in
                                    Button { Task { await select(weekday) } } label: {
                                        VStack(spacing: 7) {
                                            Text(weekday.label).font(.caption)
                                            Circle().fill(weekday.dayTitle == nil ? Color.secondary.opacity(0.25) : Color.fitBlue)
                                                .frame(width: 6, height: 6)
                                        }
                                        .frame(maxWidth: .infinity).padding(.vertical, 10)
                                        .background((selectedWeekday ?? weekdayIndex(for: today.localDate) ?? 0) == weekday.weekday
                                                    ? Color.fitBlue.opacity(0.2) : .clear,
                                                    in: RoundedRectangle(cornerRadius: 12))
                                    }
                                    .buttonStyle(.plain)
                                    .accessibilityLabel("\(weekday.label): \(weekday.dayTitle ?? "Descanso")")
                                }
                            }
                        }

                        if let day {
                            workoutStack(day)
                            Text("Exercícios do plano").font(.headline)
                            ForEach(day.exercises) { exercise in
                                prescription(exercise, completed: state == "completed" ||
                                    (today.session ?? today.completedSession)?.completedExerciseIds.contains(exercise.id) == true)
                            }
                        } else if selectedWeekday != nil || today.state == "rest" {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Dia de descanso").font(.headline)
                                if selectedWeekday == nil, let next = today.nextDay {
                                    Text("Próximo treino: \(next.title)").font(.subheadline).foregroundColor(.secondary)
                                }
                            }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        } else if today.state == "unconfigured" {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Seu primeiro treino começa aqui").font(.headline)
                                Text("Conte seu objetivo e veja um plano feito para você.").font(.subheadline).foregroundColor(.secondary)
                                Button("Criar meu treino") { showingGenerator = true }.buttonStyle(.borderedProminent)
                            }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        }
                    }
                    NavigationLink {
                        NativeWorkoutHistoryView(timezone: today?.timezone)
                    } label: {
                        HStack {
                            Label("Histórico de treinos", systemImage: "clock.arrow.circlepath")
                            Spacer()
                            Image(systemName: "chevron.right").font(.caption)
                        }.padding(18).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                    }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle("Treino")
            .sheet(isPresented: $showPlans, onDismiss: { Task { await tabData.loadWorkout(force: true) } }) { NativePlansView(kind: .workout) }
            .sheet(isPresented: $showingGenerator, onDismiss: { Task { await tabData.loadWorkout(force: true) } }) { PlanGeneratorView(kind: .workout, firstPlan: true) }
            .fullScreenCover(isPresented: $showingWorkout, onDismiss: { Task { await tabData.loadWorkout(force: true) } }) {
                if let selectedActivityId, state == "completed" || state == "partial" {
                    NavigationStack {
                        NativeWorkoutActivityView(id: selectedActivityId)
                            .toolbar { ToolbarItem(placement: .navigationBarLeading) {
                                Button("Fechar") { showingWorkout = false }
                            } }
                    }
                } else if let day, let planId = today?.currentPlanId,
                          (selectedWeekday == nil || selectedWeekday == localWeekday),
                          ["scheduled", "active"].contains(state) {
                    NativeWorkoutExecutionView(planId: planId, day: day)
                } else if let day {
                    NativeWorkoutScheduledDetailsView(day: day, status: state)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) { Button("Planos") { showPlans = true } }
                ToolbarItem(placement: .navigationBarLeading) { if presented { Button("Fechar") { dismiss() } } }
            }
            .onFitNotification(.nativeWorkoutChanged) { _ in Task { await tabData.loadWorkout(force: true) } }
            .refreshable { await tabData.loadWorkout(force: true) }
            .task(id: day?.exercises.compactMap(\.catalogKey) ?? []) {
                guard !presented, let exercises = day?.exercises else { return }
                await NativeWorkoutMediaCache.shared.prefetch(keys: exercises.compactMap(\.catalogKey))
            }
            .task {
                await tabData.loadWorkout()
                if selectedWeekday == nil, let active = tabData.workoutToday?.week.first(where: \.active) {
                    selectedWeekday = active.weekday
                    selectedDay = tabData.workoutToday?.currentDay
                    selectedState = tabData.workoutToday?.state
                    selectedActivityId = tabData.workoutToday?.completedSession?.id
                }
            }
        }
    }

    func workoutStack(_ day: WorkoutDay) -> some View {
        let status = state == "completed" ? "Treino concluído" :
            state == "partial" ? "Treino concluído parcialmente" :
            state == "active" ? "Treino em andamento" :
            state == "scheduled" ? "Treino previsto" :
            state == "notCompleted" ? "Não concluído" : workoutStateTitle(state)
        return ZStack(alignment: .topLeading) {
            RoundedRectangle(cornerRadius: 22).fill(Color.fitSurface.opacity(0.45))
                .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.fitBlue.opacity(0.12), lineWidth: 1))
                .frame(height: 278).offset(x: 16, y: 16)
            RoundedRectangle(cornerRadius: 22).fill(Color.fitSurface.opacity(0.75))
                .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.fitBlue.opacity(0.18), lineWidth: 1))
                .frame(height: 278).offset(x: 8, y: 8)
            Button {
                if let selectedWeekday, selectedWeekday != localWeekday {
                    showingWorkout = true
                } else {
                    showingWorkout = true
                }
            } label: {
                VStack(spacing: 0) {
                    Group {
                        if let first = day.exercises.first {
                            NativeExerciseAnimation(catalogKey: first.catalogKey, showsPlaybackControls: false)
                                .frame(height: 172).frame(maxWidth: .infinity)
                                .background(Color.white, in: RoundedRectangle(cornerRadius: 16))
                                .clipShape(RoundedRectangle(cornerRadius: 16))
                                .overlay(alignment: .bottomTrailing) {
                                    Image(systemName: "play.fill")
                                        .font(.system(size: 16, weight: .bold)).foregroundColor(.white)
                                        .frame(width: 44, height: 44)
                                        .background(Color(red: 0, green: 0.82, blue: 0.69), in: Circle())
                                        .padding(12).accessibilityHidden(true)
                                }
                                .allowsHitTesting(false)
                        } else {
                            Image(systemName: "dumbbell.fill").font(.system(size: 42)).foregroundColor(.fitBlue)
                                .frame(height: 172).frame(maxWidth: .infinity)
                                .background(Color.fitBlue.opacity(0.12), in: RoundedRectangle(cornerRadius: 16))
                        }
                    }
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 5) {
                            Text("\(day.exercises.count) exercícios · \(status)")
                                .font(.caption).foregroundColor(state == "completed" || state == "partial" ? .green : .secondary)
                            Text(day.title).font(.headline).foregroundColor(.primary).lineLimit(2)
                            Text("Ver detalhes do treino →").font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                        }
                        Spacer(minLength: 0)
                    }.padding(.top, 13)
                    Spacer(minLength: 0)
                }
                .padding(14).frame(maxWidth: .infinity).frame(height: 278, alignment: .top)
                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 22))
                .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.fitBlue.opacity(0.26), lineWidth: 1))
                .contentShape(RoundedRectangle(cornerRadius: 22))
            }
            .buttonStyle(.plain)
            .accessibilityHint(state == "completed" || state == "partial" ? "Ver treino concluído e cargas registradas" : "Abrir treino")
        }
        .padding(.trailing, 16).padding(.bottom, 16)
    }

    func select(_ weekday: WorkoutWeekday) async {
        selectedWeekday = weekday.weekday
        selectedDay = nil
        selectedActivityId = nil
        selectionError = nil
        guard let today else { return }
        guard let dayId = weekday.dayId else {
            selectedState = "rest"
            return
        }
        if weekday.weekday == localWeekday, let currentDay = today.currentDay, currentDay.id == dayId {
            selectedDay = currentDay
            selectedState = today.state
            selectedActivityId = today.completedSession?.id
            return
        }
        guard let planId = today.currentPlanId else { return }
        do {
            let plan = try await session.api.getPlan(kind: .workout, id: planId)
            if let planned = plan.days?.first(where: { $0.id == dayId }) {
                selectedDay = WorkoutDay(
                    id: planned.id,
                    title: planned.title,
                    exercises: planned.exercises.map {
                        WorkoutExercise(id: $0.id, catalogKey: $0.catalogKey, name: $0.name,
                                        sets: $0.sets, reps: $0.reps, weight: $0.weight,
                                        restSeconds: $0.restSeconds)
                    }
                )
            }
            let date = weekDateKey(for: weekday.weekday, localDate: today.localDate, timezone: today.timezone)
            if date > today.localDate {
                selectedState = "scheduled"
            } else {
                let page = try await session.api.getWorkoutActivities()
                let activity = page.items.first {
                    guard let stamp = $0.completedAt else { return false }
                    return localDateKey(stamp, timezone: today.timezone) == date &&
                        $0.planName == today.currentPlan?.title
                }
                if let activity {
                    selectedActivityId = activity.id
                    selectedState = activity.exercisesPerformed == activity.totalExercises ? "completed" : "partial"
                } else {
                    selectedState = "notCompleted"
                }
            }
        } catch {
            selectionError = error.localizedDescription
        }
    }

    func prescription(_ exercise: WorkoutExercise, completed: Bool) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(exercise.name).font(.headline)
                Spacer()
                if completed { Image(systemName: "checkmark.circle.fill").foregroundColor(.green).accessibilityLabel("Registrado") }
            }
            HStack(spacing: 12) {
                if let sets = exercise.sets { Text("\(sets) séries") }
                if let reps = exercise.reps { Text("\(reps) reps") }
                if let weight = exercise.weight, !weight.isEmpty { Text(weight) }
            }.font(.subheadline).foregroundColor(.secondary)
            if let rest = exercise.restSeconds { Text("Descanso: \(rest) s").font(.caption).foregroundColor(.secondary) }
            if let notes = exercise.notes, !notes.isEmpty { Text(notes).font(.footnote).foregroundColor(.secondary) }
        }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
    }

    func weekdayIndex(for date: String) -> Int? {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = timeZone
        guard let parsed = formatter.date(from: date) else { return nil }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        return (calendar.component(.weekday, from: parsed) + 5) % 7
    }

    func weekDateKey(for weekday: Int, localDate: String, timezone: String) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone(identifier: timezone) ?? timeZone
        guard let parsed = formatter.date(from: localDate) else { return localDate }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = formatter.timeZone
        let todayIndex = (calendar.component(.weekday, from: parsed) + 5) % 7
        guard let date = calendar.date(byAdding: .day, value: weekday - todayIndex, to: parsed) else { return localDate }
        return formatter.string(from: date)
    }

    func localDateKey(_ timestamp: String, timezone: String) -> String {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var parsed = iso.date(from: timestamp)
        if parsed == nil {
            iso.formatOptions = [.withInternetDateTime]
            parsed = iso.date(from: timestamp)
        }
        guard let parsed else { return String(timestamp.prefix(10)) }
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone(identifier: timezone) ?? timeZone
        return formatter.string(from: parsed)
    }
}

struct NativeWorkoutScheduledDetailsView: View {
    @Environment(\.dismiss) var dismiss
    let day: WorkoutDay
    let status: String

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Label(status == "notCompleted" ? "Não concluído" : "Treino previsto",
                          systemImage: status == "notCompleted" ? "minus.circle" : "calendar")
                        .font(.caption.bold()).foregroundColor(status == "notCompleted" ? .secondary : .fitBlue)
                    Text(day.title).font(.title2.bold())
                    Text("\(day.exercises.count) exercícios").font(.subheadline).foregroundColor(.secondary)
                    ForEach(day.exercises) { exercise in
                        VStack(alignment: .leading, spacing: 10) {
                            Text(exercise.name).font(.headline)
                            HStack(spacing: 12) {
                                if let sets = exercise.sets { Text("\(sets) séries") }
                                if let reps = exercise.reps { Text("\(reps) reps") }
                                if let weight = exercise.weight, !weight.isEmpty { Text(weight) }
                            }.font(.subheadline).foregroundColor(.secondary)
                            if let rest = exercise.restSeconds {
                                Text("Descanso: \(rest) s").font(.caption).foregroundColor(.secondary)
                            }
                        }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                    }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle("Detalhes do treino").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .navigationBarLeading) { Button("Fechar") { dismiss() } } }
        }
    }
}
struct NativeWorkoutHistoryView: View {
    @Environment(NativeSession.self) var session
    let timezone: String?
    @State var items: [WorkoutActivity] = []
    @State var offset = 0
    @State var hasMore = true
    @State var loaded = false
    @State var loading = false
    @State var refreshPending = false
    @State var error: String?

    var groups: [(date: String, items: [WorkoutActivity])] {
        var result: [(date: String, items: [WorkoutActivity])] = []
        for item in items {
            let label = workoutDateLabel(item.completedAt ?? item.startedAt, timezone: timezone)
            if result.last?.date == label { result[result.count - 1].items.append(item) }
            else { result.append((label, [item])) }
        }
        return result
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if loaded, items.isEmpty { Text("Você ainda não tem treinos registrados.").foregroundColor(.secondary) }
                ForEach(groups, id: \.date) { group in
                    Text(group.date).font(.headline)
                    ForEach(group.items) { item in
                        NavigationLink { NativeWorkoutActivityView(id: item.id) } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                Text(item.workoutName).font(.headline).foregroundColor(.primary)
                                Text("\(item.exercisesPerformed)/\(item.totalExercises) exercícios · \(item.durationSeconds / 60) min")
                                    .font(.subheadline).foregroundColor(.secondary)
                                Text(item.planName).font(.caption).foregroundColor(.secondary)
                            }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        }
                    }
                }
                if let error { Text(error).foregroundColor(.red) }
                if loading { ProgressView().frame(maxWidth: .infinity) }
                else if hasMore {
                    Button(error == nil ? "Carregar mais treinos" : "Tentar novamente") { Task { await load() } }
                        .frame(maxWidth: .infinity).buttonStyle(.bordered)
                }
            }.padding(20)
        }
        .background(Color.fitBackground.ignoresSafeArea()).navigationTitle("Histórico")
        .task { if !loaded { await load() } }
        .onFitNotification(.nativeWorkoutChanged) { _ in
            Task { await load(refresh: true) }
        }
    }

    func load(refresh: Bool = false) async {
        guard !loading else {
            if refresh { refreshPending = true }
            return
        }
        loading = true
        error = nil
        do {
            let page = try await session.api.getWorkoutActivities(offset: refresh ? 0 : offset)
            if refresh { items = page.items }
            else {
                let known = Set(items.map(\.id))
                items.append(contentsOf: page.items.filter { !known.contains($0.id) })
            }
            offset = page.offset + page.items.count
            hasMore = page.hasMore
            loaded = true
        } catch { if !isNativeRequestCancellation(error) { self.error = error.localizedDescription } }
        loading = false
        if refreshPending {
            refreshPending = false
            await load(refresh: true)
        }
    }
}

struct NativeWorkoutActivityView: View {
    @Environment(NativeSession.self) var session
    @Environment(\.dismiss) var dismiss
    @State var confirmDeletion = false
    @State var deleting = false
    @State var showShare = false
    let id: Int
    @State var activity: WorkoutActivitySummary?
    @State var error: String?
    @State var loading = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if loading { ProgressView("Carregando registro…").frame(maxWidth: .infinity) }
                if let error {
                    Text(error).foregroundColor(.red)
                    Button("Tentar novamente") { Task { await load() } }
                }
                if let activity {
                    Label("Treino concluído", systemImage: "checkmark.circle.fill")
                        .font(.caption.weight(.bold)).foregroundColor(.green)
                    Text(activity.workoutName).font(.title2.bold())
                    Text("\(activity.exercisesPerformed) exercícios feitos · \(activity.setsPerformed + activity.exercises.reduce(0) { $0 + ($1.completionMode == "planned" ? ($1.setsPlanned ?? $1.plannedPrescription?.sets ?? 0) : 0) }) séries · \(activity.durationSeconds / 60) min")
                        .foregroundColor(.secondary)
                    if let volume = activity.volumeTotalKg {
                        Text("Volume: \(volume, specifier: "%.1f") kg").font(.subheadline)
                    }
                    Button { showShare = true } label: {
                        Label("Compartilhar treino", systemImage: "square.and.arrow.up")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(FitPrimaryButtonStyle())
                    .disabled(deleting || activity.exercises.isEmpty)
                    ForEach(activity.exercises) { exercise in
                        VStack(alignment: .leading, spacing: 12) {
                            Text(exercise.name).font(.headline)
                            if exercise.completionMode == "planned", let prescription = exercise.plannedPrescription {
                                Text("Conforme o plano · \(prescription.sets.map(String.init) ?? "—") séries · \(prescription.reps ?? "—")")
                                    .font(.footnote).foregroundColor(.secondary)
                            } else if exercise.sets.isEmpty {
                                Text("Exercício registrado sem detalhes de séries.").font(.footnote).foregroundColor(.secondary)
                            }
                            ForEach(exercise.sets) { set in
                                HStack {
                                    Text("\(set.setOrder). \(set.repetitions) reps")
                                    Spacer()
                                    if let load = set.loadKg { Text("\(load, specifier: "%.1f") kg") }
                                    else { Text("Carga não informada").foregroundColor(.secondary) }
                                }.font(.subheadline)
                                if set.isWarmup { Text("Aquecimento").font(.caption).foregroundColor(.secondary) }
                            }
                        }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                    }
                }
            }.padding(20)
        }.background(Color.fitBackground.ignoresSafeArea()).navigationTitle("Treino registrado")
            .toolbar {
                if activity != nil {
                    Button(role: .destructive) { confirmDeletion = true } label: {
                        Label("Excluir registro", systemImage: "trash")
                    }.disabled(deleting)
                }
            }
            .alert("Excluir este treino registrado?", isPresented: $confirmDeletion) {
                Button("Cancelar", role: .cancel) { }
                Button("Excluir registro", role: .destructive) { Task { await delete() } }
            } message: {
                Text("O registro e suas séries serão excluídos, e seus recordes serão recalculados. O plano de treino será mantido.")
            }
            .overlay { if deleting { ProgressView("Excluindo registro…").padding(20).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16)) } }
            .fullScreenCover(isPresented: $showShare) {
                if let activity {
                    let minutes = max(0, activity.durationSeconds) / 60
                    NativeWorkoutShareView(
                        summary: activity,
                        duration: minutes >= 60 ? "\(minutes / 60)h \(minutes % 60)min" : "\(minutes) min"
                    )
                }
            }
            .task { if activity == nil { await load() } }
    }

    func delete() async {
        guard !deleting else { return }
        deleting = true
        defer { deleting = false }
        do {
            try await session.api.deleteWorkoutActivity(id: id)
            NotificationCenter.default.post(name: .nativeWorkoutChanged, object: nil)
            dismiss()
        } catch { self.error = error.localizedDescription }
    }

    func load() async {
        guard !loading else { return }
        loading = true
        error = nil
        defer { loading = false }
        do { activity = try await session.api.getWorkoutActivity(id: id).activity }
        catch { if !isNativeRequestCancellation(error) { self.error = error.localizedDescription } }
    }
}

func workoutStateTitle(_ state: String) -> String {
    switch state {
    case "scheduled": return "Programado para hoje"
    case "active": return "Treino em andamento"
    case "completed": return "Treino registrado"
    case "partial": return "Treino registrado parcialmente"
    case "rest": return "Dia de descanso"
    case "unconfigured": return "Plano ainda não configurado"
    default: return "Treino"
    }
}

func workoutDateLabel(_ timestamp: String, timezone: String?) -> String {
    let parser = ISO8601DateFormatter()
    let value = timestamp.hasSuffix("Z") || timestamp.contains("+") ? timestamp : timestamp + "Z"
    parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    var date = parser.date(from: value)
    if date == nil {
        parser.formatOptions = [.withInternetDateTime]
        date = parser.date(from: value)
    }
    guard let date else { return String(timestamp.prefix(10)) }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "pt_BR")
    formatter.timeZone = timezone.flatMap(TimeZone.init(identifier:)) ?? .current
    formatter.dateFormat = "d 'de' MMMM 'de' yyyy"
    return formatter.string(from: date)
}

extension Notification.Name {
    static let nativeWorkoutChanged = Notification.Name("fitTrackerDataDidChange")
}
