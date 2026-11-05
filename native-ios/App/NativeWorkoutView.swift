import SwiftUI
import FitTrackerCore

struct NativeTodayWorkoutCard: View {
    @EnvironmentObject private var session: NativeSession
    @EnvironmentObject private var tabData: NativeTabDataStore
    @State private var showingWorkout = false
    @State private var showingGenerator = false
    @State private var showingPremium = false
    @State private var showingActionsPicker = false
    @State private var showingRepeatConfirmation = false
    @State private var previousWorkout: PreviousWorkout?
    @State private var showingCalisthenicsConfirmation = false
    @State private var showingCalisthenicsFirstDay = false
    @State private var showingCalisthenicsFlow = false
    @State private var preparedCalisthenics: HomeWorkoutSelection?
    @State private var calisthenicsPlan: NativePlan?
    @State private var actionBusy = false
    @State private var actionError: String?
    @State private var actionMessage: String?
    @State private var selectedWorkout: HomeWorkoutSelection?
    @State private var showingSelectedWorkout = false
    @State private var repeatKey = UUID().uuidString
    @State private var calisthenicsKey = UUID().uuidString
    private var today: WorkoutToday? { tabData.workoutToday }

    var body: some View {
        Button {
            if today == nil, tabData.workoutError != nil { Task { await tabData.loadWorkout(force: true) } }
            else if today?.state == "unconfigured" { showingGenerator = true }
            else { showingWorkout = true }
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                Text(L("TREINO DE HOJE"))
                    .font(.caption.weight(.bold)).foregroundColor(FitTrackerTheme.electricBlue)
                Text(today?.state == "unconfigured" ? L("Crie seu primeiro treino") : today?.currentDay?.title ?? workoutStateTitle(today?.state ?? ""))
                    .font(FitTrackerTheme.cardTitle).foregroundColor(.white).fixedSize(horizontal: false, vertical: true)
                if let today {
                    if today.state == "unconfigured" {
                        Text(L("Um plano feito para seu objetivo e sua rotina."))
                            .font(.subheadline).foregroundColor(Color.white.opacity(0.72))
                    } else {
                        HStack(alignment: .top, spacing: 12) {
                            if let day = today.currentDay {
                                Label(L("\(day.exercises.count) exercícios"), systemImage: "calendar")
                            }
                            Label(workoutStateTitle(today.state), systemImage: "clock")
                        }
                        .font(.caption).foregroundColor(Color(red: 0.66, green: 0.81, blue: 0.96))
                        .fixedSize(horizontal: false, vertical: true)
                    }
                    if today.currentDay != nil || today.state == "unconfigured" {
                        HStack(spacing: 9) {
                            Text(today.state == "unconfigured" ? L("Montar meu treino") : today.state == "active" ? L("Continuar treino") : L("Ver treino"))
                            Image(systemName: "arrow.right")
                        }
                        .fitPrimarySurface(compact: true)
                        .padding(.top, 4)
                    }
                }
                if tabData.workoutLoading && today == nil { ProgressView() }
                if tabData.workoutError != nil {
                    Text(today == nil ? L("Seu treino não carregou agora. Toque para tentar novamente.") : L("Não foi possível atualizar agora. Seu último treino consultado continua aqui."))
                        .font(.caption).foregroundColor(Color.white.opacity(0.75))
                }
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
        .overlay(alignment: .topTrailing) {
            if let today, today.state != "unconfigured" {
                Menu {
                    if today.currentDay != nil, today.state == "scheduled" {
                        Button(L("Marcar como concluído"), systemImage: "checkmark.circle") { showingRepeatConfirmation = true }
                        Button(L("Substituir por calistenia"), systemImage: "figure.strengthtraining.traditional") { showingCalisthenicsConfirmation = true }
                    }
                    Button(L("Iniciar treino diferente"), systemImage: "arrow.triangle.swap") { showingActionsPicker = true }
                } label: {
                    Image(systemName: "ellipsis").font(.headline).frame(width: 44, height: 44)
                        .background(.black.opacity(0.35), in: Circle())
                }
                .foregroundColor(.white).padding(8).disabled(actionBusy)
                .accessibilityLabel(L("Opções do treino"))
            }
        }
        .accessibilityHint(today == nil && tabData.workoutError != nil ? L("Tentar carregar seu treino novamente") : L("Abrir seu treino"))
        .sheet(isPresented: $showingRepeatConfirmation) { repeatWorkoutSheet }
        .alert(L("Calistenia para hoje"), isPresented: $showingCalisthenicsConfirmation) {
            Button(L("Cancelar"), role: .cancel) { }
            Button(L("Preparar treino")) { Task { await beginCalisthenics() } }
        } message: { Text(L("Vamos adaptar o treino para usar apenas peso corporal, priorizando o foco de hoje. A alteração vale somente para esta sessão.")) }
        .sheet(isPresented: $showingCalisthenicsFirstDay) {
            NavigationView {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        Text(L("Por qual treino quer começar?")).font(.title2.bold())
                        Text(L("Escolha o primeiro treino para organizar a sequência da semana."))
                            .font(.subheadline).foregroundColor(.secondary)
                        ForEach(calisthenicsPlan?.days ?? []) { planned in
                            Button {
                                Task { await selectCalisthenicsFirstDay(planned) }
                            } label: {
                                HStack {
                                    Text(planned.title).font(.headline).foregroundColor(.primary)
                                    Spacer()
                                    Image(systemName: "chevron.right").foregroundColor(.fitBlue)
                                }.padding(18).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                            }.buttonStyle(.plain).disabled(actionBusy || planned.exercises.isEmpty)
                        }
                        if actionBusy { ProgressView() }
                    }.padding(20)
                }.background(Color.fitBackground.ignoresSafeArea())
                    .navigationTitle(L("Primeiro treino")).navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Cancelar")) { showingCalisthenicsFirstDay = false } } }
            }.navigationViewStyle(.stack).interactiveDismissDisabled(actionBusy)
        }
        .alert(L("Treino"), isPresented: Binding(get: { actionError != nil || actionMessage != nil }, set: { if !$0 { actionError = nil; actionMessage = nil } })) {
            Button(L("OK"), role: .cancel) { actionError = nil; actionMessage = nil }
        } message: { Text(actionError ?? actionMessage ?? "") }
        .sheet(isPresented: $showingActionsPicker, onDismiss: {
            if selectedWorkout != nil { showingSelectedWorkout = true }
        }) { HomeWorkoutPicker { selectedWorkout = $0; showingActionsPicker = false } }
        .fullScreenCover(isPresented: $showingSelectedWorkout, onDismiss: {
            selectedWorkout = nil
            Task { await tabData.loadWorkout(force: true) }
        }) {
            if let selectedWorkout { NativeWorkoutExecutionView(planId: selectedWorkout.planId, day: selectedWorkout.day) }
        }
        .fullScreenCover(isPresented: $showingCalisthenicsFlow, onDismiss: {
            preparedCalisthenics = nil
            Task { await tabData.loadWorkout(force: true) }
        }) {
            if let preparedCalisthenics {
                NativeWorkoutExecutionView(planId: preparedCalisthenics.planId, day: preparedCalisthenics.day)
            } else {
                CalisthenicsPreparationView()
            }
        }
        .task { await tabData.loadWorkout() }
        .onReceive(NotificationCenter.default.publisher(for: .nativeWorkoutChanged)) { _ in Task { await tabData.loadWorkout(force: true) } }
        .sheet(isPresented: $showingGenerator, onDismiss: { Task { await tabData.loadWorkout(force: true) } }) { PlanGeneratorView(kind: .workout, firstPlan: true) }
        .sheet(isPresented: $showingPremium) { NavigationView { NativeSubscriptionView(surface: "workout_plans") }.navigationViewStyle(.stack) }
        .fullScreenCover(isPresented: $showingWorkout, onDismiss: { Task { await tabData.loadWorkout(force: true) } }) {
            if let today = tabData.workoutToday, let planId = today.currentPlanId, let day = today.currentDay,
               ["scheduled", "active"].contains(today.state) {
                NativeWorkoutExecutionView(planId: planId, day: day)
            } else { NativeWorkoutView(presented: true) }
        }
    }

    private var repeatWorkoutSheet: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(L("Concluir treino de hoje?")).font(.title2.bold())
                    Text(L("Confira as séries da última sessão. Elas serão repetidas no registro de hoje."))
                        .font(.subheadline).foregroundColor(.secondary)
                    if actionBusy && previousWorkout == nil { ProgressView() }
                    if let previousWorkout {
                        if previousWorkout.available {
                            ForEach(Array(previousWorkout.exercises.enumerated()), id: \.offset) { _, exercise in
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(exercise.name).font(.headline)
                                    ForEach(Array(exercise.sets.enumerated()), id: \.offset) { index, set in
                                        Text(L("Série \(index + 1): \(set.repetitions) repetições") + (set.loadKg.map { " · \($0.formatted()) kg" } ?? " · " + L("carga não informada")) + (set.isWarmup ? " · " + L("aquecimento") : ""))
                                            .font(.caption).foregroundColor(.secondary)
                                    }
                                }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
                                    .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                            }
                            Button(L("Confirmar conclusão")) { Task { await repeatLastWorkout() } }
                                .buttonStyle(FitPrimaryButtonStyle()).disabled(actionBusy)
                        } else {
                            Text(L("O último treino não tem séries registradas para todos os exercícios. Registre um treino completo antes de usar esta opção."))
                                .font(.subheadline).foregroundColor(.secondary)
                        }
                    }
                    if let actionError { Text(actionError).font(.footnote).foregroundColor(.red) }
                }.padding(20)
            }.background(Color.fitBackground.ignoresSafeArea())
                .navigationTitle(L("Último treino")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { showingRepeatConfirmation = false } } }
                .task { await loadPreviousWorkout() }
        }.navigationViewStyle(.stack)
    }

    private func loadPreviousWorkout() async {
        guard let planId = today?.currentPlanId, let day = today?.currentDay, !actionBusy else { return }
        actionBusy = true; previousWorkout = nil; actionError = nil
        defer { actionBusy = false }
        do { previousWorkout = try await session.api.getPreviousWorkout(planId: planId, dayId: day.id) }
        catch { actionError = RequestFailure.message(error, fallback: L("Não foi possível carregar o último treino.")) }
    }

    private func repeatLastWorkout() async {
        guard let planId = today?.currentPlanId, let day = today?.currentDay, !actionBusy else { return }
        actionBusy = true; defer { actionBusy = false }
        do {
            _ = try await session.api.repeatLastWorkout(planId: planId, dayId: day.id, idempotencyKey: repeatKey)
            repeatKey = UUID().uuidString
            await tabData.loadWorkout(force: true)
            showingRepeatConfirmation = false
            actionMessage = L("Treino concluído com as séries da última sessão.")
        } catch { actionError = RequestFailure.message(error, fallback: L("Não foi possível concluir o treino. Tente novamente.")) }
    }

    private func beginCalisthenics() async {
        guard let planId = today?.currentPlanId, let day = today?.currentDay, !actionBusy else { return }
        actionBusy = true
        do {
            let plan = try await session.api.getPlan(kind: .workout, id: planId)
            actionBusy = false
            if plan.hasStarted == false { calisthenicsPlan = plan; showingCalisthenicsFirstDay = true }
            else { await prepareCalisthenics(planId: planId, day: day) }
        } catch {
            actionBusy = false
            actionError = RequestFailure.message(error, fallback: L("Não foi possível consultar seu plano."))
        }
    }

    private func selectCalisthenicsFirstDay(_ planned: PlanWorkoutDay) async {
        guard let plan = calisthenicsPlan, !actionBusy else { return }
        actionBusy = true
        do {
            _ = try await session.api.setWorkoutStartDay(planId: plan.id, dayId: planned.id)
            let day = WorkoutDay(id: planned.id, title: planned.title, exercises: planned.exercises.map {
                WorkoutExercise(id: $0.id, catalogKey: $0.catalogKey, name: $0.name, sets: $0.sets, reps: $0.reps,
                                weight: $0.weight, restSeconds: $0.restSeconds)
            })
            showingCalisthenicsFirstDay = false
            actionBusy = false
            await prepareCalisthenics(planId: plan.id, day: day)
        } catch {
            actionBusy = false
            showingCalisthenicsFirstDay = false
            actionError = RequestFailure.message(error, fallback: L("Não foi possível configurar o primeiro treino."))
        }
    }

    private func prepareCalisthenics(planId: Int, day: WorkoutDay) async {
        guard !actionBusy else { return }
        actionBusy = true
        showingCalisthenicsFlow = true
        await Task.yield()
        defer { actionBusy = false }
        do {
            _ = try await session.api.prepareCalisthenics(planId: planId, dayId: day.id, idempotencyKey: calisthenicsKey)
            calisthenicsKey = UUID().uuidString
            preparedCalisthenics = HomeWorkoutSelection(planId: planId, day: day)
        } catch {
            showingCalisthenicsFlow = false
            actionError = RequestFailure.message(error, fallback: L("Não foi possível preparar o treino de calistenia. Tente novamente."))
        }
    }

    private var workoutImageName: String? {
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

private struct CalisthenicsPreparationView: View {
    var body: some View {
        ZStack {
            Color.fitBackground.ignoresSafeArea()
            VStack(spacing: 20) {
                Image(systemName: "figure.strengthtraining.traditional")
                    .font(.system(size: 40, weight: .medium))
                    .foregroundColor(.fitBlue)
                    .frame(width: 88, height: 88)
                    .background(Color.fitBlue.opacity(0.14), in: Circle())
                ProgressView().controlSize(.large).tint(.fitBlue)
                VStack(spacing: 8) {
                    Text(L("Preparando seu treino de calistenia"))
                        .font(.title3.bold()).multilineTextAlignment(.center)
                    Text(L("Estamos adaptando os exercícios para usar apenas o peso do corpo."))
                        .font(.subheadline).foregroundColor(.secondary).multilineTextAlignment(.center)
                }
            }
            .padding(32)
            .frame(maxWidth: 360)
        }
        .interactiveDismissDisabled()
    }
}

private struct HomeWorkoutSelection {
    let planId: Int
    let day: WorkoutDay
}

private struct HomeWorkoutPicker: View {
    @EnvironmentObject private var session: NativeSession
    @State private var plans: [NativePlan] = []
    @State private var loading = false
    @State private var error: String?
    @State private var candidate: HomeWorkoutSelection?
    @State private var showChoice = false
    let onSelect: (HomeWorkoutSelection) -> Void

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(L("Qual treino você quer fazer hoje?")).font(.title2.bold())
                    Text(L("Escolha um treino de qualquer um dos seus planos."))
                        .font(.subheadline).foregroundColor(.secondary)
                    if loading { ProgressView().frame(maxWidth: .infinity) }
                    if let error {
                        NativeRecoveryCard(title: L("Vamos buscar seus treinos"), message: error, actionTitle: L("Tentar novamente")) {
                            Task { await load() }
                        }
                    }
                    ForEach(plans) { plan in
                        Text(plan.title).font(.headline).foregroundColor(.fitBlue).padding(.top, 8)
                        ForEach(plan.days ?? []) { planned in
                            Button {
                                candidate = HomeWorkoutSelection(planId: plan.id, day: workoutDay(planned))
                                showChoice = true
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 5) {
                                        Text(planned.title).font(.headline).foregroundColor(.primary)
                                        Text(L("\(planned.exercises.count) exercícios")).font(.caption).foregroundColor(.secondary)
                                    }
                                    Spacer()
                                    Image(systemName: "chevron.right").foregroundColor(.fitBlue)
                                }.padding(18).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                            }.buttonStyle(.plain).disabled(planned.exercises.isEmpty || loading)
                        }
                    }
                    if !loading && error == nil && plans.isEmpty { Text(L("Você ainda não tem planos de treino.")) }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(L("Escolher treino")).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Cancelar")) { dismiss() } } }
            .confirmationDialog(L("Definir este treino como padrão para este dia da semana?"), isPresented: $showChoice, titleVisibility: .visible) {
                Button(L("Definir como padrão e iniciar")) { Task { await select(makeDefault: true) } }
                Button(L("Iniciar somente hoje")) { Task { await select(makeDefault: false) } }
                Button(L("Cancelar"), role: .cancel) { candidate = nil }
            } message: { Text(L("Somente hoje mantém sua programação atual.")) }
            .task { await load() }
        }.navigationViewStyle(.stack)
    }

    @Environment(\.dismiss) private var dismiss

    private func workoutDay(_ day: PlanWorkoutDay) -> WorkoutDay {
        WorkoutDay(id: day.id, title: day.title, exercises: day.exercises.map {
            WorkoutExercise(id: $0.id, catalogKey: $0.catalogKey, name: $0.name, sets: $0.sets, reps: $0.reps,
                            weight: $0.weight, restSeconds: $0.restSeconds)
        })
    }

    private func load() async {
        guard !loading else { return }
        loading = true; error = nil
        defer { loading = false }
        do {
            var summaries: [NativePlan] = []
            while true {
                let page = try await session.api.getPlans(kind: .workout, limit: 30, offset: summaries.count)
                summaries.append(contentsOf: page)
                if page.count < 30 { break }
            }
            var loaded: [NativePlan] = []
            for plan in summaries { loaded.append(try await session.api.getPlan(kind: .workout, id: plan.id)) }
            plans = loaded
        } catch { self.error = RequestFailure.message(error, fallback: L("Não foi possível carregar os planos.")) }
    }

    private func select(makeDefault: Bool) async {
        guard let candidate, !loading else { return }
        if makeDefault {
            loading = true
            defer { loading = false }
            do { try await session.api.setWorkoutWeekdayDefault(planId: candidate.planId, dayId: candidate.day.id) }
            catch { self.error = RequestFailure.message(error, fallback: L("Não foi possível atualizar sua programação.")); return }
        }
        onSelect(candidate)
    }
}

@MainActor
struct NativeWorkoutView: View {
    var presented = false
    @Environment(\.dismiss) private var dismiss
    @Environment(\.timeZone) private var timeZone
    @EnvironmentObject private var session: NativeSession
    @EnvironmentObject private var tabData: NativeTabDataStore
    @State private var showPlans = false
    @State private var showingGenerator = false
    @State private var showingWorkout = false
    @State private var selectedWeekday: Int?
    @State private var selectedDay: WorkoutDay?
    @State private var selectedActivityId: Int?
    @State private var selectedState: String?
    @State private var selectionError: String?
    @State private var selectionLoading = false
    @State private var selectionRequestID = UUID()
    @State private var showingWorkoutPicker = false
    @State private var alternateDay: WorkoutDay?
    @State private var pickerPlan: NativePlan?
    @State private var pickerError: String?
    @State private var pickerLoading = false

    private var today: WorkoutToday? { tabData.workoutToday }
    private var loading: Bool { tabData.workoutLoading }
    private var error: String? { selectionError ?? tabData.workoutError }
    private var localWeekday: Int { weekdayIndex(for: today?.localDate ?? "") ?? 0 }
    private var day: WorkoutDay? {
        guard let selectedWeekday else { return today?.currentDay }
        return selectedWeekday == localWeekday ? today?.currentDay : selectedDay
    }
    private var state: String { selectedState ?? today?.state ?? "" }
    private var title: String { day?.title ?? (state == "rest" ? L("Dia de descanso") : today?.currentPlan?.title ?? L("Seu treino")) }

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if loading && today == nil { workoutSkeleton }
                    if let error {
                        NativeRecoveryCard(title: L("Seu treino continua por aqui"), message: error, actionTitle: L("Tentar novamente")) {
                            Task {
                                if selectionError != nil, let weekday = today?.week.first(where: { $0.weekday == selectedWeekday }) { await select(weekday) }
                                else { await tabData.loadWorkout(force: true) }
                            }
                        }
                    }
                    if selectionLoading && day == nil { workoutSkeleton }
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
                                    .accessibilityLabel(L("\(weekday.label): \(weekday.dayTitle ?? L("Descanso"))"))
                                }
                            }
                        }

                        if today.currentPlanId != nil {
                            Button {
                                alternateDay = nil
                                showingWorkoutPicker = true
                            } label: {
                                HStack(spacing: 12) {
                                    Image(systemName: "arrow.triangle.swap")
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(L("Escolher outro treino")).font(.subheadline.weight(.semibold))
                                        Text(today.state == "active" ? L("Finalize o treino em andamento para começar outro.") : L("Treine qualquer dia do seu plano hoje."))
                                            .font(.caption).foregroundColor(.secondary)
                                    }
                                    Spacer()
                                    Image(systemName: "chevron.right").font(.caption.bold())
                                }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                                    .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                                    .contentShape(Rectangle())
                            }.buttonStyle(.plain).disabled(today.state == "active")
                        }
                        if let day {
                            workoutStack(day)
                            Text(L("Exercícios do plano")).font(.headline)
                            if day.exercises.isEmpty {
                                NativeRecoveryCard(title: L("Vamos completar este treino?"), message: L("Este dia ainda não tem exercícios. Abra seus planos para revisar a rotina antes de começar."), systemImage: "dumbbell", actionTitle: L("Ver meus planos")) { showPlans = true }
                            }
                            ForEach(day.exercises) { exercise in
                                prescription(exercise, completed: state == "completed" ||
                                    (today.session ?? today.completedSession)?.completedExerciseIds.contains(exercise.id) == true)
                            }
                        } else if !selectionLoading && selectionError == nil && (selectedWeekday != nil || today.state == "rest") {
                            VStack(alignment: .leading, spacing: 8) {
                                Text(L("Dia de descanso")).font(.headline)
                                if selectedWeekday == nil, let next = today.nextDay {
                                    Text(L("Próximo treino: \(next.title)")).font(.subheadline).foregroundColor(.secondary)
                                }
                            }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        } else if today.state == "unconfigured" {
                            VStack(alignment: .leading, spacing: 12) {
                                Text(L("Seu primeiro treino começa aqui")).font(.headline)
                                Text(L("Conte seu objetivo e veja um plano feito para você.")).font(.subheadline).foregroundColor(.secondary)
                                Button(L("Criar meu treino")) { showingGenerator = true }.fitGlassButton(prominent: true)
                            }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        }
                    }
                    NavigationLink {
                        NativeWorkoutHistoryView(timezone: today?.timezone)
                    } label: {
                        HStack {
                            Label(L("Histórico de treinos"), systemImage: "clock.arrow.circlepath")
                            Spacer()
                            Image(systemName: "chevron.right").font(.caption)
                        }.padding(18).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                    }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(L("Treino"))
            .sheet(isPresented: $showPlans, onDismiss: { Task { await tabData.loadWorkout(force: true) } }) { NativePlansView(kind: .workout) }
            .sheet(isPresented: $showingGenerator, onDismiss: { Task { await tabData.loadWorkout(force: true) } }) { PlanGeneratorView(kind: .workout, firstPlan: true) }
            .sheet(isPresented: $showingWorkoutPicker, onDismiss: {
                if alternateDay != nil { showingWorkout = true }
            }) { workoutPicker }
            .fullScreenCover(isPresented: $showingWorkout, onDismiss: {
                alternateDay = nil
                Task { await tabData.loadWorkout(force: true) }
            }) {
                if let alternateDay, let planId = today?.currentPlanId {
                    NativeWorkoutExecutionView(planId: planId, day: alternateDay)
                } else if let selectedActivityId, state == "completed" || state == "partial" {
                    NavigationView {
                        NativeWorkoutActivityView(id: selectedActivityId)
                            .toolbar { ToolbarItem(placement: .navigationBarLeading) {
                                Button(L("Fechar")) { showingWorkout = false }
                            } }
                    }.navigationViewStyle(.stack)
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
                ToolbarItem(placement: .navigationBarTrailing) { Button(L("Planos")) { showPlans = true } }
                ToolbarItem(placement: .navigationBarLeading) { if presented { Button(L("Fechar")) { dismiss() } } }
            }
            .onReceive(NotificationCenter.default.publisher(for: .nativeWorkoutChanged)) { _ in Task { await tabData.loadWorkout(force: true) } }
            .refreshable { await tabData.loadWorkout(force: true) }
            .onChange(of: tabData.workoutVersion) { _ in
                guard let selectedWeekday, let weekday = today?.week.first(where: { $0.weekday == selectedWeekday }) else { return }
                Task { await select(weekday) }
            }
            .task(id: day?.exercises.compactMap(\.catalogKey) ?? []) {
                guard !presented, let exercises = day?.exercises else { return }
                await NativeWorkoutMediaCache.shared.prefetch(keys: exercises.compactMap(\.catalogKey))
            }
            .task(id: "\(today?.currentPlanId ?? 0):\(tabData.workoutVersion)") {
                guard let planId = today?.currentPlanId else { return }
                _ = try? await tabData.workoutWeek.loadPlan(id: planId)
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
        }.navigationViewStyle(.stack)
    }

    private var workoutPicker: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(L("Qual treino você quer fazer hoje?")).font(.title2.bold())
                    Text(L("Escolha um treino do seu plano e comece agora. Sua agenda semanal continua igual."))
                        .font(.subheadline).foregroundColor(.secondary)
                    if let pickerError {
                        NativeRecoveryCard(title: L("Vamos buscar seus treinos"), message: pickerError, actionTitle: L("Tentar novamente")) {
                            Task { await loadPickerPlan() }
                        }
                    }
                    if pickerLoading && pickerPlan == nil { ProgressView().frame(maxWidth: .infinity) }
                    ForEach(pickerPlan?.days ?? []) { planned in
                        Button {
                            guard let plan = pickerPlan, let day = plannedDay(planned.id, in: plan) else { return }
                            alternateDay = day
                            showingWorkoutPicker = false
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "dumbbell.fill").foregroundColor(.fitBlue)
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(planned.title).font(.headline).foregroundColor(.primary)
                                    Text(L("\(planned.exercises.count) exercícios")).font(.caption).foregroundColor(.secondary)
                                    Text(planned.exercises.prefix(3).map(\.name).joined(separator: " · "))
                                        .font(.caption).foregroundColor(.secondary).lineLimit(2)
                                }
                                Spacer(minLength: 0)
                                Image(systemName: "play.circle.fill").font(.title2).foregroundColor(.fitBlue)
                            }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                                .contentShape(Rectangle())
                        }.buttonStyle(.plain).disabled(planned.exercises.isEmpty)
                            .accessibilityHint(L("Iniciar este treino hoje"))
                    }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(L("Escolher treino")).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Cancelar")) { showingWorkoutPicker = false } } }
            .task { await loadPickerPlan() }
        }.navigationViewStyle(.stack)
    }

    private func loadPickerPlan() async {
        guard let planId = today?.currentPlanId, !pickerLoading else { return }
        pickerPlan = tabData.workoutWeek.cachedPlan(id: planId)
        pickerError = nil
        pickerLoading = true
        defer { pickerLoading = false }
        do { pickerPlan = try await tabData.workoutWeek.loadPlan(id: planId) }
        catch {
            if !isNativeRequestCancellation(error) {
                pickerError = RequestFailure.message(error, fallback: L("Não foi possível carregar os treinos. Tente novamente."))
            }
        }
    }

    private func workoutStack(_ day: WorkoutDay) -> some View {
        let status = state == "completed" ? L("Treino concluído") :
            state == "partial" ? L("Treino concluído parcialmente") :
            state == "active" ? L("Treino em andamento") :
            state == "scheduled" ? L("Treino previsto") :
            state == "notCompleted" ? L("Não concluído") :
            state == "checking" ? L("Consultando status…") :
            state == "unknown" ? L("Status indisponível") : workoutStateTitle(state)
        return ZStack(alignment: .topLeading) {
            RoundedRectangle(cornerRadius: 22).fill(Color.fitSurface.opacity(0.45))
                .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.fitBlue.opacity(0.12), lineWidth: 1))
                .frame(height: 278).offset(x: 16, y: 16)
            RoundedRectangle(cornerRadius: 22).fill(Color.fitSurface.opacity(0.75))
                .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.fitBlue.opacity(0.18), lineWidth: 1))
                .frame(height: 278).offset(x: 8, y: 8)
            Button {
                alternateDay = nil
                showingWorkout = true
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
                            Text(L("\(day.exercises.count) exercícios · \(status)"))
                                .font(.caption).foregroundColor(state == "completed" || state == "partial" ? .green : .secondary)
                            Text(day.title).font(.headline).foregroundColor(.primary).lineLimit(2)
                            Text(L("Ver detalhes do treino →")).font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
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
            .accessibilityHint(state == "completed" || state == "partial" ? L("Ver treino concluído e cargas registradas") : L("Abrir treino"))
        }
        .padding(.trailing, 16).padding(.bottom, 16)
    }

    private var workoutSkeleton: some View {
        VStack(alignment: .leading, spacing: 20) {
            RoundedRectangle(cornerRadius: 22).fill(Color.fitSurface).frame(height: 278)
            ForEach(0..<3) { _ in
                VStack(alignment: .leading, spacing: 12) {
                    RoundedRectangle(cornerRadius: 6).fill(Color.white.opacity(0.08)).frame(height: 18)
                    RoundedRectangle(cornerRadius: 6).fill(Color.white.opacity(0.05)).frame(width: 180, height: 12)
                }.padding(20).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
            }
        }.accessibilityElement(children: .ignore).accessibilityLabel(L("Carregando treino"))
    }

    private func select(_ weekday: WorkoutWeekday) async {
        let requestID = UUID()
        selectionRequestID = requestID
        selectedWeekday = weekday.weekday
        selectedDay = nil
        selectedActivityId = nil
        selectedState = nil
        selectionError = nil
        selectionLoading = false
        guard let today else { return }
        guard let dayId = weekday.dayId else { selectedState = "rest"; return }
        if weekday.weekday == localWeekday, let currentDay = today.currentDay, currentDay.id == dayId {
            selectedDay = currentDay
            selectedState = today.state
            selectedActivityId = today.completedSession?.id
            return
        }
        guard let planId = weekday.planId ?? today.currentPlanId else { return }
        let cache = tabData.workoutWeek
        let generation = cache.generation
        let date = weekDateKey(for: weekday.weekday, localDate: today.localDate, timezone: today.timezone)
        if let plan = cache.cachedPlan(id: planId) { selectedDay = plannedDay(dayId, in: plan) }
        selectedState = date > today.localDate ? "scheduled" : "checking"
        selectionLoading = selectedDay == nil
        defer { if selectionRequestID == requestID { selectionLoading = false } }
        do {
            let plan = try await cache.loadPlan(id: planId)
            guard selectionRequestID == requestID, cache.generation == generation, !Task.isCancelled else { return }
            guard let nextDay = plannedDay(dayId, in: plan) else { throw APIError.invalidResponse }
            selectedDay = nextDay
            selectionLoading = false
            if date <= today.localDate {
                let page = try await cache.loadActivities()
                guard selectionRequestID == requestID, cache.generation == generation, !Task.isCancelled else { return }
                let activity = page.items.first {
                    guard let stamp = $0.completedAt else { return false }
                    return localDateKey(stamp, timezone: today.timezone) == date && $0.planName == today.currentPlan?.title
                }
                if let activity {
                    selectedActivityId = activity.id
                    selectedState = activity.exercisesPerformed == activity.totalExercises ? "completed" : "partial"
                } else { selectedState = "notCompleted" }
            }
        } catch {
            guard selectionRequestID == requestID, cache.generation == generation, !isNativeRequestCancellation(error) else { return }
            selectedState = "unknown"
            selectionError = RequestFailure.message(error, fallback: L("Não foi possível consultar este dia. Tente novamente; seu treino não foi alterado."))
        }
    }

    private func plannedDay(_ id: Int, in plan: NativePlan) -> WorkoutDay? {
        guard let planned = plan.days?.first(where: { $0.id == id }) else { return nil }
        return WorkoutDay(id: planned.id, title: planned.title, exercises: planned.exercises.map {
            WorkoutExercise(id: $0.id, catalogKey: $0.catalogKey, name: $0.name, sets: $0.sets, reps: $0.reps,
                            weight: $0.weight, restSeconds: $0.restSeconds)
        })
    }

    private func prescription(_ exercise: WorkoutExercise, completed: Bool) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(exercise.name).font(.headline)
                Spacer()
                if completed { Image(systemName: "checkmark.circle.fill").foregroundColor(.green).accessibilityLabel(L("Registrado")) }
            }
            HStack(spacing: 12) {
                if let sets = exercise.sets { Text(L("\(sets) séries")) }
                if let reps = exercise.reps { Text("\(reps) reps") }
                if let weight = exercise.weight, !weight.isEmpty { Text(weight) }
            }.font(.subheadline).foregroundColor(.secondary)
            if let rest = exercise.restSeconds { Text(L("Descanso: \(rest) s")).font(.caption).foregroundColor(.secondary) }
            if let notes = exercise.notes, !notes.isEmpty { Text(notes).font(.footnote).foregroundColor(.secondary) }
        }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
    }

    private func weekdayIndex(for date: String) -> Int? {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = timeZone
        guard let parsed = formatter.date(from: date) else { return nil }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        return (calendar.component(.weekday, from: parsed) + 5) % 7
    }

    private func weekDateKey(for weekday: Int, localDate: String, timezone: String) -> String {
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

    private func localDateKey(_ timestamp: String, timezone: String) -> String {
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

private struct NativeWorkoutScheduledDetailsView: View {
    @Environment(\.dismiss) private var dismiss
    let day: WorkoutDay
    let status: String

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Label(status == "notCompleted" ? L("Não concluído") : L("Treino previsto"),
                          systemImage: status == "notCompleted" ? "minus.circle" : "calendar")
                        .font(.caption.bold()).foregroundColor(status == "notCompleted" ? .secondary : .fitBlue)
                    Text(day.title).font(.title2.bold())
                    Text(L("\(day.exercises.count) exercícios")).font(.subheadline).foregroundColor(.secondary)
                    ForEach(day.exercises) { exercise in
                        VStack(alignment: .leading, spacing: 10) {
                            Text(exercise.name).font(.headline)
                            HStack(spacing: 12) {
                                if let sets = exercise.sets { Text(L("\(sets) séries")) }
                                if let reps = exercise.reps { Text("\(reps) reps") }
                                if let weight = exercise.weight, !weight.isEmpty { Text(weight) }
                            }.font(.subheadline).foregroundColor(.secondary)
                            if let rest = exercise.restSeconds {
                                Text(L("Descanso: \(rest) s")).font(.caption).foregroundColor(.secondary)
                            }
                        }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                    }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(L("Detalhes do treino")).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .navigationBarLeading) { Button(L("Fechar")) { dismiss() } } }
        }.navigationViewStyle(.stack)
    }
}
struct NativeWorkoutHistoryView: View {
    @EnvironmentObject private var session: NativeSession
    let timezone: String?
    @State private var items: [WorkoutActivity] = []
    @State private var offset = 0
    @State private var hasMore = true
    @State private var loaded = false
    @State private var loading = false
    @State private var refreshPending = false
    @State private var error: String?
    @State private var failedRefresh = false

    private var groups: [(date: String, items: [WorkoutActivity])] {
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
                if loaded && items.isEmpty && !loading && error == nil {
                    NativeRecoveryCard(title: L("Sua história de treino começa aqui"), message: L("Conclua um treino para acompanhar suas atividades, séries e cargas neste histórico."), systemImage: "clock.arrow.circlepath")
                }
                ForEach(groups, id: \.date) { group in
                    Text(group.date).font(.headline)
                    ForEach(group.items) { item in
                        NavigationLink { NativeWorkoutActivityView(id: item.id) } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                Text(item.workoutName).font(.headline).foregroundColor(.primary)
                                Text(L("\(item.exercisesPerformed)/\(item.totalExercises) exercícios · \(item.durationSeconds / 60) min"))
                                    .font(.subheadline).foregroundColor(.secondary)
                                Text(item.planName).font(.caption).foregroundColor(.secondary)
                            }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        }
                    }
                }
                if let error {
                    NativeRecoveryCard(title: L("Vamos consultar seu histórico?"), message: error, actionTitle: L("Tentar novamente")) { Task { await load(refresh: failedRefresh) } }
                }
                if loading { ProgressView().frame(maxWidth: .infinity) }
                else if hasMore && error == nil {
                    Button(L("Carregar mais treinos")) { Task { await load() } }
                        .frame(maxWidth: .infinity).fitGlassButton()
                }
            }.padding(20)
        }
        .background(Color.fitBackground.ignoresSafeArea()).navigationTitle(L("Histórico"))
        .task { if !loaded { await load() } }
        .onReceive(NotificationCenter.default.publisher(for: .nativeWorkoutChanged)) { _ in
            Task { await load(refresh: true) }
        }
    }

    private func load(refresh: Bool = false) async {
        guard !loading else {
            if refresh { refreshPending = true }
            return
        }
        loading = true
        error = nil
        failedRefresh = refresh
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
        } catch { if !isNativeRequestCancellation(error) { self.error = RequestFailure.message(error, fallback: L("Seu histórico não carregou agora. Os treinos já exibidos foram mantidos.")) } }
        loading = false
        if refreshPending {
            refreshPending = false
            await load(refresh: true)
        }
    }
}

struct NativeWorkoutActivityView: View {
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    @State private var confirmDeletion = false
    @State private var deleting = false
    @State private var showShare = false
    let id: Int
    @State private var activity: WorkoutActivitySummary?
    @State private var error: String?
    @State private var loading = false
    @State private var deletionFailed = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if loading { ProgressView(L("Carregando registro…")).frame(maxWidth: .infinity) }
                if let error {
                    NativeRecoveryCard(title: deletionFailed ? L("Seu registro continua disponível") : L("Vamos abrir seu treino?"), message: error,
                                       actionTitle: deletionFailed ? L("Conferir registro") : L("Tentar novamente")) { Task { await load() } }
                }
                if let activity {
                    Label(L("Treino concluído"), systemImage: "checkmark.circle.fill")
                        .font(.caption.weight(.bold)).foregroundColor(.green)
                    Text(activity.workoutName).font(.title2.bold())
                    Text(L("\(activity.exercisesPerformed) exercícios feitos · \(activity.setsPerformed + activity.exercises.reduce(0) { $0 + ($1.completionMode == "planned" ? ($1.setsPlanned ?? $1.plannedPrescription?.sets ?? 0) : 0) }) séries · \(activity.durationSeconds / 60) min"))
                        .foregroundColor(.secondary)
                    if let volume = activity.volumeTotalKg {
                        Text(L("Volume: \(volume, specifier: "%.1f") kg")).font(.subheadline)
                    }
                    Button { showShare = true } label: {
                        Label(L("Compartilhar treino"), systemImage: "square.and.arrow.up")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(FitPrimaryButtonStyle())
                    .disabled(deleting || activity.exercises.isEmpty)
                    ForEach(activity.exercises) { exercise in
                        VStack(alignment: .leading, spacing: 12) {
                            Text(exercise.name).font(.headline)
                            if exercise.completionMode == "planned", let prescription = exercise.plannedPrescription {
                                Text(L("Conforme o plano · \(prescription.sets.map(String.init) ?? "—") séries · \(prescription.reps ?? "—")"))
                                    .font(.footnote).foregroundColor(.secondary)
                            } else if exercise.sets.isEmpty {
                                Text(L("Exercício registrado sem detalhes de séries.")).font(.footnote).foregroundColor(.secondary)
                            }
                            ForEach(exercise.sets) { set in
                                HStack {
                                    Text("\(set.setOrder). \(set.repetitions) reps")
                                    Spacer()
                                    if let load = set.loadKg { Text("\(load, specifier: "%.1f") kg") }
                                    else { Text(L("Carga não informada")).foregroundColor(.secondary) }
                                }.font(.subheadline)
                                if set.isWarmup { Text(L("Aquecimento")).font(.caption).foregroundColor(.secondary) }
                            }
                        }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                    }
                }
            }.padding(20)
        }.background(Color.fitBackground.ignoresSafeArea()).navigationTitle(L("Treino registrado"))
            .toolbar {
                if activity != nil {
                    Button(role: .destructive) { confirmDeletion = true } label: {
                        Label(L("Excluir registro"), systemImage: "trash")
                    }.disabled(deleting)
                }
            }
            .alert(L("Excluir este treino registrado?"), isPresented: $confirmDeletion) {
                Button(L("Cancelar"), role: .cancel) { }
                Button(L("Excluir registro"), role: .destructive) { Task { await delete() } }
            } message: {
                Text(L("O registro e suas séries serão excluídos, e seus recordes serão recalculados. O plano de treino será mantido."))
            }
            .overlay { if deleting { ProgressView(L("Excluindo registro…")).padding(20).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16)) } }
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

    private func delete() async {
        guard !deleting else { return }
        deleting = true
        error = nil
        deletionFailed = false
        defer { deleting = false }
        do {
            try await session.api.deleteWorkoutActivity(id: id)
            NotificationCenter.default.post(name: .nativeWorkoutChanged, object: nil)
            dismiss()
        } catch { if !isNativeRequestCancellation(error) { deletionFailed = true; self.error = RequestFailure.message(error, fallback: L("Não foi possível confirmar a exclusão. Confira o registro antes de tentar excluí-lo novamente.")) } }
    }

    private func load() async {
        guard !loading else { return }
        loading = true
        error = nil
        deletionFailed = false
        defer { loading = false }
        do { activity = try await session.api.getWorkoutActivity(id: id).activity }
        catch { if !isNativeRequestCancellation(error) { self.error = RequestFailure.message(error, fallback: L("Este treino não carregou agora. Tente novamente.")) } }
    }
}

private func workoutStateTitle(_ state: String) -> String {
    switch state {
    case "scheduled": return L("Programado para hoje")
    case "active": return L("Treino em andamento")
    case "completed": return L("Treino registrado")
    case "partial": return L("Treino registrado parcialmente")
    case "rest": return L("Dia de descanso")
    case "unconfigured": return L("Plano ainda não configurado")
    default: return L("Treino")
    }
}

private func workoutDateLabel(_ timestamp: String, timezone: String?) -> String {
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
    formatter.locale = NativeLocalization.locale
    formatter.timeZone = timezone.flatMap(TimeZone.init(identifier:)) ?? .current
    formatter.dateStyle = .long
    return formatter.string(from: date)
}

extension Notification.Name {
    static let nativeWorkoutChanged = Notification.Name("fitTrackerDataDidChange")
}
