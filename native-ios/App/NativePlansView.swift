import SwiftUI
import UserNotifications
import FitTrackerCore

struct NativePlansView: View {
    let kind: NativePlanKind
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    @State private var plans: [NativePlan] = []
    @State private var loading = false
    @State private var loaded = false
    @State private var failedLoadReset = true
    @State private var failedPlan: NativePlan?
    @State private var hasMore = true
    @State private var error: String?
    @State private var generating = false
    @State private var creatingManually = false
    @State private var importingWorkout = false
    @State private var selected: NativePlan?
    @State private var planToDelete: NativePlan?
    @State private var deleting = false
    @State private var deletionError: String?
    @State private var deletionMessage: String?

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(L("Sua biblioteca")).font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                        Text(kind == .workout ? L("Seus planos de treino") : L("Seus planos alimentares")).font(.title2.bold())
                        Text(plans.isEmpty ? L("Comece com um plano para sua rotina. Você confere tudo antes de usar.") : L("O plano atual continua em uso até você revisar e confirmar uma alternativa."))
                            .font(.subheadline).foregroundColor(.secondary)
                    }
                    Button { generating = true } label: {
                        Label(plans.isEmpty ? L("Criar meu primeiro plano") : kind == .workout ? L("Criar treino") : L("Gerar outro plano"), systemImage: "sparkles")
                            .font(.headline).frame(maxWidth: .infinity).padding(16)
                            .background(Color.fitBlue.opacity(0.16), in: RoundedRectangle(cornerRadius: 18))
                    }.buttonStyle(.plain)
                    Button(L("Já tenho um plano · adicionar manualmente")) { creatingManually = true }.fitGlassButton().frame(maxWidth: .infinity)
                    if kind == .workout {
                        Button { importingWorkout = true } label: { Label(L("Importar treino de imagem ou texto"), systemImage: "doc.text.viewfinder") }
                            .fitGlassButton().frame(maxWidth: .infinity)
                    }
                    if let error = error {
                        NativeRecoveryCard(title: failedPlan == nil ? L("Sua biblioteca continua aqui") : L("Vamos abrir seu plano?"), message: error,
                                           actionTitle: L("Tentar novamente")) {
                            Task { if let failedPlan { await open(failedPlan) } else { await load(reset: failedLoadReset) } }
                        }
                    }
                    if !plans.isEmpty {
                        Text(L("Planos salvos")).font(.headline).padding(.top, 4)
                        ForEach(plans) { plan in
                            VStack(spacing: 0) {
                                Button { Task { await open(plan) } } label: { planCard(plan) }
                                    .buttonStyle(.plain)
                                Button(role: .destructive) { deletionError = nil; planToDelete = plan } label: {
                                    Label(L("Excluir plano"), systemImage: "trash")
                                        .font(.subheadline).frame(maxWidth: .infinity, minHeight: 44)
                                }.buttonStyle(.plain).foregroundColor(.red)
                                    .accessibilityLabel(L("Excluir plano \(plan.title)"))
                            }.disabled(loading || deleting)
                                .background(plan.isCurrent == true ? Color.fitBlue.opacity(0.13) : Color.fitSurface,
                                            in: RoundedRectangle(cornerRadius: 20))
                                .overlay(RoundedRectangle(cornerRadius: 20).stroke(plan.isCurrent == true ? Color.fitBlue.opacity(0.35) : Color.white.opacity(0.06), lineWidth: 1))
                        }
                    }
                    if deleting { ProgressView(L("Excluindo plano…")).frame(maxWidth: .infinity) }
                    if let deletionError { Text(deletionError).font(.subheadline).foregroundColor(.orange) }
                    if let deletionMessage { Label(deletionMessage, systemImage: "checkmark.circle.fill").font(.subheadline).foregroundColor(.green) }
                    if loaded && plans.isEmpty && !loading && error == nil {
                        NativeRecoveryCard(title: L("Seu primeiro plano começa aqui"), message: L("Responda algumas perguntas para criar seu plano. Se já recebeu um plano, você também pode adicioná-lo manualmente."),
                                           systemImage: kind == .workout ? "dumbbell" : "fork.knife")
                    }
                    if loading { ProgressView().frame(maxWidth: .infinity).padding() }
                    if hasMore && !plans.isEmpty {
                        Button(L("Carregar mais")) { Task { await load(reset: false) } }.disabled(loading)
                            .frame(maxWidth: .infinity).padding(.vertical, 8)
                    }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(kind.title)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { dismiss() } } }
            .onReceive(NotificationCenter.default.publisher(for: Notification.Name("fitTrackerNavigate"))) { _ in dismiss() }
            .refreshable { await load(reset: true) }
            .task { await load(reset: true) }
            .sheet(isPresented: $creatingManually, onDismiss: { Task { await load(reset: true) } }) { NativeManualPlanView(kind: kind) }
            .sheet(isPresented: $importingWorkout, onDismiss: { Task { await load(reset: true) } }) { NativeWorkoutImportView() }
            .sheet(isPresented: $generating, onDismiss: { Task { await load(reset: true) } }) { PlanGeneratorView(kind: kind, firstPlan: plans.isEmpty) }
            .sheet(item: $selected, onDismiss: { Task { await load(reset: true) } }) { NativePlanDetailView(kind: kind, initialPlan: $0) }
            .confirmationDialog(L("Excluir plano?"), isPresented: Binding(get: { planToDelete != nil }, set: { if !$0 { planToDelete = nil } }), titleVisibility: .visible, presenting: planToDelete) { plan in
                Button(L("Excluir plano"), role: .destructive) { Task { await delete(plan) } }
                Button(L("Cancelar"), role: .cancel) { planToDelete = nil }
            } message: { plan in
                Text(L("\(plan.title) será removido dos seus planos\(plan.isCurrent == true ? L(" e deixará de ser o plano atual") : ""). Seus registros no histórico serão preservados. Esta ação não pode ser desfeita."))
            }
        }.navigationViewStyle(.stack)
    }
    private func planCard(_ plan: NativePlan) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label(plan.isCurrent == true ? L("Em uso") : L("Plano salvo"),
                      systemImage: plan.isCurrent == true ? "checkmark.circle.fill" : "square.stack.3d.up")
                    .font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                Spacer()
                Image(systemName: "arrow.up.right").font(.caption.weight(.semibold)).foregroundColor(.secondary)
            }
            Text(plan.title).font(.headline).foregroundColor(.primary)
            if let description = plan.description { Text(description).font(.subheadline).foregroundColor(.secondary).lineLimit(3) }
            HStack(spacing: 14) {
                if let count = kind == .workout ? plan.daysCount : plan.mealsCount {
                    Label(L("\(count) \(kind == .workout ? L("dias") : L("refeições"))"), systemImage: kind == .workout ? "calendar" : "fork.knife")
                }
                if kind == .workout, let exerciseCount = plan.days?.reduce(0, { $0 + $1.exercises.count }) {
                    Label(L("\(exerciseCount) exercícios"), systemImage: "dumbbell")
                }
            }.font(.caption).foregroundColor(.secondary)
        }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
    }
    private func load(reset: Bool) async {
        guard !loading && !deleting else { return }; loading = true; error = nil; failedPlan = nil; failedLoadReset = reset
        defer { loading = false }
        do {
            let page = try await session.api.getPlans(kind: kind, offset: reset ? 0 : plans.count)
            plans = reset ? page : plans + page
            hasMore = page.count == 30
            loaded = true
        } catch { if !isNativeRequestCancellation(error) { self.error = RequestFailure.message(error, fallback: L("Seus planos não carregaram agora. Tente novamente; os planos já exibidos continuam disponíveis.")) } }
    }
    private func open(_ plan: NativePlan) async {
        guard !loading && !deleting else { return }; loading = true; error = nil
        defer { loading = false }
        do { selected = try await session.api.getPlan(kind: kind, id: plan.id); failedPlan = nil }
        catch { if !isNativeRequestCancellation(error) { failedPlan = plan; self.error = RequestFailure.message(error, fallback: L("Não foi possível abrir este plano agora. Tente novamente.")) } }
    }
    private func delete(_ plan: NativePlan) async {
        guard !loading && !deleting else { return }; deleting = true; deletionError = nil; deletionMessage = nil
        defer { deleting = false }
        do {
            deletionMessage = try await session.api.deletePlan(kind: kind, id: plan.id)
            plans.removeAll { $0.id == plan.id }
            NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
        } catch { deletionError = RequestFailure.message(error, fallback: L("Não foi possível excluir o plano. Ele continua na sua biblioteca; tente novamente.")) }
    }
}

struct NativePlanDetailView: View {
    let kind: NativePlanKind
    @State private var plan: NativePlan
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    @State private var weekdays: Set<Int> = []
    @State private var confirming = false
    @State private var busy = false
    @State private var error: String?
    @State private var message: String?
    @State private var editingMeal: DietMealAlternative?
    @State private var editingExercise: PlanWorkoutExercise?
    @State private var selectedDay: PlanWorkoutDay?
    @State private var expandedDays: Set<Int> = []
    @State private var showingActivationOptions = false
    @State private var adjustingWithAI = false
    @State private var adjustmentDayId: Int?
    @State private var premiumAfterActivation = false
    @State private var unlockingWorkout = false
    @State private var activated = false
    @State private var confirmingDeletion = false

    init(kind: NativePlanKind, initialPlan: NativePlan, generatedPreview: Bool = false) {
        self.kind = kind; _plan = State(initialValue: initialPlan)
    }
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 10) {
                        if plan.isCurrent == true { Label(L("Plano atual"), systemImage: "checkmark.circle.fill").font(.caption.weight(.semibold)).foregroundColor(.fitBlue) }
                        Text(plan.title).font(.title2.bold())
                        if kind == .workout, plan.source == "template" {
                            Text(L("Plano pronto ajustado à sua rotina")).font(.subheadline).foregroundColor(.fitBlue)
                        }
                        if let description = plan.description { Text(description).font(.subheadline).foregroundColor(.secondary) }
                        HStack(spacing: 14) {
                            if kind == .workout, let count = plan.daysCount { Label(L("\(count) dias/semana"), systemImage: "calendar") }
                            if kind == .diet, let count = plan.mealsCount { Label(L("\(count) refeições"), systemImage: "fork.knife") }
                        }.font(.caption).foregroundColor(.secondary)
                    }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 20))
                    if kind == .diet {
                        ForEach(plan.meals ?? []) { meal in
                            VStack(alignment: .leading, spacing: 10) {
                                Text(meal.mealType.uppercased()).font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                                Text(meal.description).font(.body)
                                if let kcal = meal.calories { Label("\(Int(kcal)) kcal", systemImage: "flame").font(.caption).foregroundColor(.secondary) }
                                Button(L("Editar refeição")) { editingMeal = meal }.disabled(busy)
                            }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        }
                    }
                    if kind == .workout {
                        Button { adjustmentDayId = nil; if session.hasPremium { adjustingWithAI = true } else { premiumAfterActivation = true } } label: { Label(L("Ajustar plano com IA"), systemImage: session.hasPremium ? "sparkles" : "lock.fill").frame(maxWidth: .infinity).padding(14) }.fitGlassButton()
                        Text(L("Escolha seu treino")).font(.headline).padding(.top, 4)
                        Text(L("Toque no cartão para conferir os exercícios. Você pode iniciar qualquer treino hoje, mesmo fora do dia planejado.")).font(.subheadline).foregroundColor(.secondary)
                        ForEach(plan.days ?? []) { day in
                            workoutDayCard(day)
                        }
                    }
                    Button(role: .destructive) { confirmingDeletion = true } label: {
                        Label(L("Excluir plano"), systemImage: "trash").frame(maxWidth: .infinity, minHeight: 44)
                    }.fitGlassButton().disabled(busy)
                }.padding(20)
            }.background(Color.fitBackground.ignoresSafeArea())
                .navigationTitle(activated || plan.isCurrent == true ? L("Seu plano atual") : L("Revisar plano"))
                .navigationBarTitleDisplayMode(.inline)
                .safeAreaInset(edge: .bottom) {
                    VStack(alignment: .leading, spacing: 10) {
                        if let error { Text(NativeLocalization.display(error)).font(.caption).foregroundColor(.orange) }
                        if let message { Label(message, systemImage: "checkmark.circle.fill").font(.subheadline).foregroundColor(.green) }
                        if activated || plan.isCurrent == true {
                            Button(L("Ver meu dia")) {
                                NotificationCenter.default.post(name: Notification.Name("fitTrackerNavigate"), object: nil, userInfo: ["tab": kind == .diet ? "diet" : "workout"])
                            }.fitGlassButton(prominent: true).frame(maxWidth: .infinity)
                        } else { activationSection }
                    }.padding(16).frame(maxWidth: .infinity).fitGlassBar()
                }
                .onReceive(NotificationCenter.default.publisher(for: Notification.Name("fitTrackerNavigate"))) { _ in dismiss() }
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { dismiss() }.disabled(busy) } }
                .confirmationDialog(L("Usar este plano?"), isPresented: $confirming, titleVisibility: .visible) {
                    Button(L("Confirmar")) { Task { await activate() } }
                } message: {
                    Text(kind == .diet
                         ? L("Esta será sua dieta atual. Suas refeições já registradas continuam no histórico.")
                         : L("Este será seu plano de treino atual. Seus treinos já registrados continuam no histórico."))
                }
                .confirmationDialog(L("Excluir plano?"), isPresented: $confirmingDeletion, titleVisibility: .visible) {
                    Button(L("Excluir plano"), role: .destructive) { Task { await delete() } }
                    Button(L("Cancelar"), role: .cancel) { }
                } message: {
                    Text(L("\(plan.title) será removido dos seus planos\(plan.isCurrent == true ? L(" e deixará de ser o plano atual") : ""). Seus registros no histórico serão preservados. Esta ação não pode ser desfeita."))
                }
                .sheet(isPresented: $premiumAfterActivation, onDismiss: { unlockingWorkout = false }) { NavigationView { NativeSubscriptionView(surface: kind == .diet ? "diet_plans" : "workout_plans", workoutUnlock: unlockingWorkout) }.navigationViewStyle(.stack) }
                .sheet(item: $editingMeal) { meal in
                    PlanMealEditor(planId: plan.id, meal: meal) { Task { await refresh() } }
                }
                .sheet(item: $editingExercise) { exercise in
                    PlanExerciseEditor(planId: plan.id, exercise: exercise) { updated in plan = updated; weekdays = [] }
                }
                .sheet(isPresented: $adjustingWithAI) {
                    PlanAIEditor(plan: plan, initialDayId: adjustmentDayId) { updated in plan = updated; expandedDays = []; NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil) }
                }
                .fullScreenCover(item: $selectedDay) { day in
                    NativeWorkoutExecutionView(planId: plan.id, day: workoutDay(from: day))
                }
        }.navigationViewStyle(.stack)
    }
    private func workoutDayCard(_ day: PlanWorkoutDay) -> some View {
        let isExpanded = expandedDays.contains(day.id)
        return VStack(alignment: .leading, spacing: 12) {
            Button {
                if isExpanded { expandedDays.remove(day.id) } else { expandedDays.insert(day.id) }
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "dumbbell.fill").font(.caption.bold()).foregroundColor(.fitBlue)
                        .frame(width: 38, height: 38).background(Color.fitBlue.opacity(0.16), in: Circle())
                    VStack(alignment: .leading, spacing: 4) {
                        Text(day.title).font(.headline).foregroundColor(.primary)
                        Text(L("\(day.exercises.count) exercícios")).font(.caption).foregroundColor(.secondary)
                    }
                    Spacer()
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down").font(.caption.bold()).foregroundColor(.secondary)
                }
                .padding(16).frame(maxWidth: .infinity, minHeight: 76, alignment: .leading)
                .contentShape(Rectangle())
            }.buttonStyle(.plain)
                .accessibilityLabel(day.title)
                .accessibilityValue(isExpanded ? L("Expandido") : L("Recolhido"))
                .accessibilityHint(L("Ver exercícios e iniciar este treino"))
            if isExpanded {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(day.exercises) { exercise in
                        HStack(alignment: .top, spacing: 12) {
                            Circle().fill(Color.fitBlue.opacity(0.55)).frame(width: 6, height: 6).padding(.top, 6)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(exercise.name).font(.subheadline.weight(.semibold))
                                Text(L("\(exercise.sets ?? 0) séries · \(exercise.reps ?? "—") repetições · \(exercise.restSeconds ?? 0) s descanso"))
                                    .font(.caption).foregroundColor(.secondary)
                                Button(L("Editar exercício")) { editingExercise = exercise }.font(.caption).disabled(busy)
                            }
                            Spacer(minLength: 0)
                        }.padding(.vertical, 5)
                    }
                    Button { adjustmentDayId = day.id; if session.hasPremium { adjustingWithAI = true } else { premiumAfterActivation = true } } label: { Label(L("Ajustar este treino com IA"), systemImage: session.hasPremium ? "sparkles" : "lock.fill") }.font(.subheadline)
                    Button {
                        if session.hasPremium { selectedDay = day }
                        else { unlockingWorkout = true; premiumAfterActivation = true }
                    } label: {
                        Label(L("Iniciar treino"), systemImage: session.hasPremium ? "play.fill" : "lock.fill").frame(maxWidth: .infinity).padding(13)
                    }.fitGlassButton(prominent: true).disabled(day.exercises.isEmpty)
                }.padding(.horizontal, 16).padding(.bottom, 16)
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
    }
    @ViewBuilder private var activationSection: some View {
        if kind == .diet {
            Button(L("Definir como plano atual")) { confirming = true }
                .fitGlassButton(prominent: true).frame(maxWidth: .infinity).disabled(busy)
        } else if !session.hasPremium {
            VStack(spacing: 10) {
                Text(L("Com Premium, aplique seu plano e comece a treinar."))
                    .font(.subheadline).foregroundColor(.secondary).frame(maxWidth: .infinity, alignment: .leading)
                Button { unlockingWorkout = true; premiumAfterActivation = true } label: {
                    Label(L("Desbloquear treino com Premium"), systemImage: "lock.fill")
                        .frame(maxWidth: .infinity, minHeight: 44)
                }.fitGlassButton(prominent: true)
            }
        } else if showingActivationOptions {
            VStack(alignment: .leading, spacing: 12) {
                Text(L("Dias da semana")).font(.headline)
                Text(L("Escolha um dia para cada treino do plano.")).font(.subheadline).foregroundColor(.secondary)
                ScrollView {
                    VStack {
                        ForEach(0..<7) { index in
                            Toggle(weekdayNames[index], isOn: Binding(get: { weekdays.contains(index) }, set: { if $0 { weekdays.insert(index) } else { weekdays.remove(index) } }))
                        }
                    }
                }.frame(maxHeight: 190).disabled(busy)
                Text(L("\(weekdays.count) de \(plan.days?.count ?? 0) dias selecionados")).font(.caption).foregroundColor(.secondary)
                Button(L("Confirmar plano e agenda")) { confirming = true }
                    .fitGlassButton(prominent: true).frame(maxWidth: .infinity)
                    .disabled(busy || weekdays.count != (plan.days?.count ?? 0))
            }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
        } else {
            Button(L("Usar este plano")) { showingActivationOptions = true }
                .fitGlassButton(prominent: true).frame(maxWidth: .infinity)
        }
        if busy { ProgressView().frame(maxWidth: .infinity) }
    }
    private var weekdayNames: [String] { [L("Segunda"), L("Terça"), L("Quarta"), L("Quinta"), L("Sexta"), L("Sábado"), L("Domingo")] }
    private func activate() async {
        guard kind != .workout || session.hasPremium else { unlockingWorkout = true; premiumAfterActivation = true; return }
        guard !busy else { return }; busy = true; error = nil; message = nil
        defer { busy = false }
        do {
            let response = try await session.api.activatePlan(kind: kind, id: plan.id, weekdays: weekdays.sorted())
            NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
            activated = true
            message = response.message + (response.effectiveFrom.map { L(" Início: \($0).") } ?? "")
            if let updated = try? await session.api.getPlan(kind: kind, id: plan.id) { plan = updated }
            try? await session.refreshFreeAccess()

        } catch {
            if kind == .workout, case APIError.http(let status, _) = error, status == 403 {
                try? await session.refreshFreeAccess()
                if !session.hasPremium { unlockingWorkout = true; premiumAfterActivation = true; return }
            }
            self.error = RequestFailure.message(error, fallback: L("Não foi possível confirmar esta etapa. Suas escolhas continuam aqui; confira e tente novamente."))
        }
    }
    private func refresh() async {
        do { plan = try await session.api.getPlan(kind: kind, id: plan.id) }
        catch { self.error = RequestFailure.message(error, fallback: L("Não foi possível confirmar esta etapa. Suas escolhas continuam aqui; confira e tente novamente.")) }
    }
    private func delete() async {
        guard !busy else { return }; busy = true; error = nil
        defer { busy = false }
        do {
            _ = try await session.api.deletePlan(kind: kind, id: plan.id)
            NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
            dismiss()
        } catch { self.error = RequestFailure.message(error, fallback: L("Não foi possível excluir o plano. Tente novamente.")) }
    }
    private func workoutDay(from day: PlanWorkoutDay) -> WorkoutDay {
        WorkoutDay(id: day.id, title: day.title, exercises: day.exercises.map { exercise in
            WorkoutExercise(id: exercise.id, catalogKey: exercise.catalogKey, name: exercise.name,
                            sets: exercise.sets, reps: exercise.reps, weight: exercise.weight,
                            restSeconds: exercise.restSeconds)
        })
    }
}

struct PlanGeneratorView: View {
    let kind: NativePlanKind
    var firstPlan = false
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    @State private var creatingManually = false
    @State private var diet = DietPlanPreferences()
    @State private var workout = WorkoutPlanPreferences()
    @State private var allergies = ""
    @State private var intolerances = ""
    @State private var disliked = ""
    @State private var preferred = ""
    @State private var busy = false
    @State private var error: String?
    @State private var generated: NativePlan?
    @State private var reviewingPlan: NativePlan?
    @State private var jobId: UUID?
    @State private var monitoringJob: UUID?
    @State private var showingGeneration = false
    @State private var equipment = "full_gym"
    @State private var step = 0
    @State private var routine = ""
    @State private var prepStyle = "mixed"
    @State private var showingPremium = false
    @State private var requestingConsent = false
    @State private var consentVersion: String?
    @State private var generationStarted: Date?
    @State private var takingLonger = false
    @State private var generationKey = UUID().uuidString
    @State private var showingQuestions = false
    @State private var conditionsLoading = false
    @State private var conditionsLoaded = false
    @State private var conditionsError: String?
    @State private var consentAccepted = false
    @State private var consentForGeneration = false
    @State private var completingProfile = false
    @State private var didLoadDraft = false
    @State private var setupOwner: UUID?
    @State private var restoredDraft = false
    private let draftStore = PlanSetupDraftStore()
    @ObservedObject private var backgroundPlans = NativePlanBackground.shared

    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                HStack {
                    if showingQuestions && step > 0 && jobId == nil && generated == nil && !showingGeneration {
                        Button { step -= 1 } label: { Image(systemName: "chevron.left") }
                    }
                    Spacer()
                    Text(firstPlan ? (kind == .diet ? L("Sua primeira dieta") : L("Seu primeiro treino")) : (kind == .diet ? L("Nova dieta") : L("Novo treino"))).font(.headline)
                    Spacer()
                    Button(L("Fechar")) { dismiss() }.disabled(busy)
                }.padding(.horizontal, 20).padding(.vertical, 14)
                if showingQuestions && generated == nil && jobId == nil && !showingGeneration {
                    Text(step == totalSteps ? L("Confira seu plano antes de criar") : L("Etapa \(step + 1) de \(totalSteps) · \(stepTitle)"))
                        .font(.caption).foregroundColor(.secondary).padding(.bottom, 8)
                    ProgressView(value: Double(min(step + 1, totalSteps)), total: Double(totalSteps)).tint(.fitBlue).padding(.horizontal, 20)
                }
                if showingGeneration {
                    generationScreen
                } else {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 18) {
                            if showingQuestions && generated == nil && jobId == nil { Button(L("Montar manualmente")) { creatingManually = true }.fitGlassButton() }
                            if let error { Text(NativeLocalization.display(error)).font(.footnote).foregroundColor(.red) }
                            if let generated {
                                Text(L("Plano pronto para revisar")).font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                                Text(L("Confira antes de trocar o plano atual.")).font(.title2.bold())
                                Button(L("Ver meu plano")) { reviewingPlan = generated }.fitGlassButton(prominent: true)
                            } else if jobId != nil {
                                Text(L("Seu plano está sendo preparado.")).font(.title2.bold())
                                Text(L("Seu pedido está guardado. Retome para conferir o resultado, sem gerar outro plano.")).foregroundColor(.secondary)
                            } else if !showingQuestions {
                                conditionsView
                            } else if step == totalSteps {
                                review
                            } else {
                                question
                            }
                        }.padding(20)
                    }
                    if generated == nil && (showingQuestions || jobId != nil) {
                        VStack(spacing: 8) {
                            if offersDietPremium {
                                Button { showingPremium = true } label: {
                                    Label(L("Personalizar com Premium"), systemImage: "sparkles")
                                        .frame(maxWidth: .infinity, minHeight: 44)
                                }.fitGlassButton(prominent: true)
                                Button(L("Continuar no gratuito")) { advanceSetup() }
                                    .font(.footnote).foregroundColor(.secondary).frame(minHeight: 44)
                            } else {
                                Button(jobId != nil ? L("Retomar meu plano") : step == totalSteps ? (kind == .workout ? L("Criar treino") : firstPlan ? L("Gerar meu plano") : L("Gerar alternativa")) : L("Continuar")) {
                                    advanceSetup()
                                }.fitGlassButton(prominent: true).frame(maxWidth: .infinity, minHeight: 44)
                            }
                        }.padding(.horizontal, 20).padding(.bottom, 12)
                            .disabled(busy || (step < totalSteps && jobId == nil && !canContinue))
                    }
                }
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationBarHidden(true)
                .task {
                    restoreSetup()
                    if jobId == nil && generated == nil { await loadConditions() }
                }
                .onChange(of: setupDraft) { _ in persistSetup() }
                .onReceive(NotificationCenter.default.publisher(for: Notification.Name("fitTrackerNavigate"))) { _ in dismiss() }
                .task(id: monitoringJob) {
                    if let id = monitoringJob { await monitorGeneration(id: id) }
                }
                .onDisappear { monitoringJob = nil; persistSetup() }
                .onReceive(backgroundPlans.$completed) { results in
                    if let id = jobId, let plan = results[id] { receiveGeneratedPlan(plan) }
                }
                .onReceive(backgroundPlans.$failures) { failures in
                    if let id = jobId, let message = failures[id] {
                        error = message; storeJob(nil); monitoringJob = nil
                        generationKey = UUID().uuidString
                    }
                }
                .task(id: showingGeneration) {
                    guard showingGeneration else { return }
                    let elapsed = generationStarted.map { Date().timeIntervalSince($0) } ?? 0
                    do { try await Task.sleep(nanoseconds: UInt64(max(0, 60 - elapsed)) * 1_000_000_000) }
                    catch { return }
                    takingLonger = true
                }
                .sheet(item: $reviewingPlan) { NativePlanDetailView(kind: kind, initialPlan: $0, generatedPreview: true) }
                .sheet(isPresented: $showingPremium, onDismiss: { Task { await loadConditions() } }) { NavigationView { NativeSubscriptionView(surface: kind == .diet ? "diet_plans" : "workout_plans") }.navigationViewStyle(.stack) }
                .sheet(isPresented: $creatingManually) { NativeManualPlanView(kind: kind) }
                .sheet(isPresented: $requestingConsent) { consentSheet }
                .sheet(isPresented: $completingProfile) {
                    NativePlanProfileSetupView {
                        completingProfile = false
                        if !restoredDraft { applyProfileGoal() }
                        Task { await loadConditions() }
                    }
                }
        }.navigationViewStyle(.stack).interactiveDismissDisabled(busy)
    }
    private var offersDietPremium: Bool {
        kind == .diet && !session.hasPremium && jobId == nil && (1...totalSteps).contains(step)
    }
    private func advanceSetup() {
        if jobId != nil || step == totalSteps { Task { await generate() } }
        else { step += 1 }
    }
    private var dietRequestPreferences: DietPlanPreferences {
        var preferences = diet
        preferences.allergies = split(allergies); preferences.intolerances = split(intolerances)
        preferences.dislikedFoods = split(disliked); preferences.preferredFoods = split(preferred)
        preferences.prepMinutes = prepStyle == "quick" ? 15 : prepStyle == "elaborate" ? 60 : 30
        if !routine.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            preferences.notes = L("Rotina e horários: \(routine)\(diet.notes.isEmpty ? "" : " · \(diet.notes)")")
        }
        return preferences.forGeneration(hasPremium: session.hasPremium)
    }
    private var totalSteps: Int { 3 }
    private var stepTitle: String {
        [L("Seu objetivo"), L("Sua rotina"), L("Suas preferências")][min(step, 2)]
    }
    private var canContinue: Bool {
        if kind == .diet { return !diet.goal.isEmpty && !diet.dietPattern.isEmpty && (1...7).contains(diet.mealsPerDay) }
        return !workout.goal.isEmpty && !workout.experienceLevel.isEmpty && (1...7).contains(workout.daysPerWeek)
    }
    private var remainingPlans: Int? { session.freeAccess?.remainingPlans(for: kind) }
    private var canStart: Bool {
        conditionsLoaded && !conditionsLoading && session.profile?.profileComplete == true && consentAccepted &&
        (session.hasPremium || (remainingPlans ?? 0) > 0)
    }
    private var conditionsView: some View {
        VStack(alignment: .leading, spacing: 18) {
            Image(systemName: kind == .diet ? "fork.knife.circle.fill" : "dumbbell.fill")
                .font(.system(size: 42)).foregroundColor(.fitBlue).accessibilityHidden(true)
            Text(restoredDraft ? L("Vamos continuar seu plano?") : L("Um plano que cabe na sua rotina"))
                .font(.title2.bold())
            Text(L("São 3 etapas. Suas escolhas ficam salvas neste aparelho para você continuar depois."))
                .font(.subheadline).foregroundColor(.secondary)
            if conditionsLoading { ProgressView(L("Conferindo seu acesso…")) }
            if let conditionsError {
                NativeRecoveryCard(title: L("Vamos conferir seu acesso?"), message: conditionsError, actionTitle: L("Tentar novamente")) {
                    Task { await loadConditions() }
                }
            }
            if conditionsLoaded {
                VStack(alignment: .leading, spacing: 10) {
                    Label(session.hasPremium ? L("Criação de planos incluída no Premium") : L("\(remainingPlans ?? 0) planos gratuitos disponíveis"), systemImage: "sparkles")
                        .font(.headline)
                    Text(session.hasPremium ? L("Você revisa o resultado antes de definir seu plano atual.") : L("Criar este plano usa 1 opção gratuita. Não há cobrança automática. Adicionar um plano manualmente continua grátis."))
                        .font(.caption).foregroundColor(.secondary)
                }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                if !session.hasPremium && remainingPlans == 0 {
                    Button(L("Conhecer o Premium")) { showingPremium = true }.fitGlassButton(prominent: true)
                } else if session.profile?.profileComplete != true {
                    NativeRecoveryCard(title: L("Primeiro, um pouco sobre você"), message: L("Seu objetivo e suas medidas ajudam a preparar um plano adequado. Seu diário já pode ser usado sem esta etapa."), systemImage: "person.crop.circle", actionTitle: L("Completar perfil para meu plano")) { completingProfile = true }
                } else if !consentAccepted {
                    Text(L("A criação pode usar IA. Confira quais dados são necessários e autorize antes de começar."))
                        .font(.subheadline).foregroundColor(.secondary)
                    Button(L("Conferir e autorizar IA")) { consentForGeneration = false; requestingConsent = true }.fitGlassButton(prominent: true)
                }
                if canStart {
                    Button(restoredDraft ? L("Continuar configuração") : L("Começar meu plano")) { showingQuestions = true }
                        .fitGlassButton(prominent: true).frame(maxWidth: .infinity)
                }
            }
            Button(L("Já tenho um plano · adicionar manualmente")) { creatingManually = true }
                .fitGlassButton().frame(minHeight: 44)
        }
    }

    private var setupDraft: PlanSetupDraft {
        var draft = PlanSetupDraft()
        draft.step = step; draft.diet = diet; draft.workout = workout
        draft.allergies = allergies; draft.intolerances = intolerances
        draft.disliked = disliked; draft.preferred = preferred
        draft.routine = routine; draft.prepStyle = prepStyle; draft.equipment = equipment
        draft.requestKey = generationKey
        return draft
    }
    private func restoreSetup() {
        guard !didLoadDraft, let owner = session.user?.id else { return }
        setupOwner = owner
        defer { didLoadDraft = true }
        do {
            if let draft = try draftStore.load(owner: owner, kind: kind) {
                step = min(max(draft.step, 0), totalSteps); diet = draft.diet; workout = draft.workout
                allergies = draft.allergies; intolerances = draft.intolerances
                disliked = draft.disliked; preferred = draft.preferred
                routine = draft.routine; prepStyle = draft.prepStyle; equipment = draft.equipment
                generationKey = draft.requestKey; restoredDraft = true
            } else { applyProfileGoal() }
        } catch { self.error = L("Não conseguimos recuperar suas escolhas. Você pode preencher o plano novamente.") }
        if let key = backgroundPlans.requestKey(owner: owner, kind: kind) { generationKey = key }
        if jobId == nil, generated == nil, let key = pendingJobKey,
           let saved = UserDefaults.standard.string(forKey: key), let id = UUID(uuidString: saved) {
            jobId = id; showingGeneration = true; monitoringJob = id
        }
    }
    private func applyProfileGoal() {
        guard let goal = session.profile?.profile?.goal else { return }
        let normalized = goal.lowercased()
        diet.goal = normalized.contains("ganhar") ? "muscle_gain" : normalized.contains("perder") ? "fat_loss" : normalized.contains("saude") || normalized.contains("saúde") ? "general_health" : "maintenance"
        workout.goal = normalized.contains("perder") ? "fat_loss" : normalized.contains("ganhar") ? "hypertrophy" : "conditioning"
    }
    private func persistSetup() {
        guard didLoadDraft, generated == nil, showingQuestions || restoredDraft || jobId != nil,
              let owner = setupOwner, session.user?.id == owner else { return }
        do { try draftStore.save(setupDraft, owner: owner, kind: kind) }
        catch { self.error = L("Não conseguimos guardar suas escolhas neste aparelho. Mantenha esta tela aberta para continuar.") }
    }
    private func loadConditions() async {
        guard !conditionsLoading, let owner = session.user?.id else { return }
        conditionsLoading = true; conditionsLoaded = false; conditionsError = nil
        defer { conditionsLoading = false }
        do {
            try await session.refreshFreeAccess()
            if session.profile == nil { try await session.refreshProfile() }
            let consent = try await session.api.consentStatus()
            guard session.user?.id == owner else { return }
            consentAccepted = consent.ai.accepted
            consentVersion = consent.versions.ai.version
            conditionsLoaded = true
        } catch {
            if !isNativeRequestCancellation(error) {
                conditionsError = RequestFailure.message(error, fallback: L("Seu acesso não carregou agora. Suas escolhas continuam neste aparelho."))
            }
        }
    }
    @ViewBuilder private var question: some View {
        if kind == .diet { dietQuestion } else { workoutQuestion }
    }
    @ViewBuilder private var dietQuestion: some View {
        switch step {
        case 0:
            choiceQuestion(L("Qual é seu objetivo?"), options: [(L("Manter peso"),"maintenance"),(L("Perder gordura"),"fat_loss"),(L("Ganhar massa"),"muscle_gain"),(L("Saúde geral"),"general_health")], selection: $diet.goal)
            choiceQuestion(L("Como você se alimenta?"), options: [(L("Onívora"),"omnivore"),(L("Vegetariana"),"vegetarian"),(L("Vegana"),"vegan"),(L("Pescetariana"),"pescatarian")], selection: $diet.dietPattern)
            numberQuestion(L("Quantas refeições por dia?"), value: $diet.mealsPerDay, range: 1...7, suffix: L("refeições por dia"))
        case 1:
            Text(L("Como é o seu dia?")).font(.title2.bold())
            Stepper(L("\(diet.trainingDaysPerWeek) dias de treino por semana"), value: $diet.trainingDaysPerWeek, in: 0...7)
            if !session.hasPremium { dietPremiumPitch }
            VStack(alignment: .leading, spacing: 18) {
                dietPremiumLabel(L("Rotina e horários"))
                Text(L("Encaixe suas refeições nos horários de trabalho, sono e treino.")).font(.subheadline).foregroundColor(.secondary)
                TextEditor(text: session.hasPremium ? $routine : .constant("")).frame(minHeight: 100).padding(8)
                    .background(Color.fitBackground, in: RoundedRectangle(cornerRadius: 14))
                    .accessibilityLabel(L("Rotina e horários, opcional"))
                    .overlay(alignment: .topLeading) {
                        if routine.isEmpty || !session.hasPremium {
                            Text(L("Ex.: acordo às 6h, almoço às 12h, treino às 19h e durmo às 23h."))
                                .font(.subheadline).foregroundColor(.secondary).padding(16).allowsHitTesting(false)
                        }
                    }
                    .disabled(!session.hasPremium)
                dietPremiumLabel(L("Orçamento e preparo"))
                VStack(alignment: .leading, spacing: 18) {
                    choiceQuestion(L("Seu orçamento"), options: [(L("Econômico"),"economical"),(L("Moderado"),"moderate"),(L("Flexível"),"flexible")], selection: session.hasPremium ? $diet.budget : .constant("moderate"))
                    choiceQuestion(L("Como prefere suas refeições?"), options: [(L("Práticas e rápidas"),"quick"),(L("Um pouco de cada"),"mixed"),(L("Mais elaboradas"),"elaborate")], selection: session.hasPremium ? $prepStyle : .constant("mixed"))
                }.disabled(!session.hasPremium)
            }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
            if !session.hasPremium {
                Text(L("No gratuito, usamos orçamento moderado e preparo de até 30 minutos. Suas alergias e intolerâncias continuam sendo respeitadas."))
                    .font(.caption).foregroundColor(.secondary)
            }
        default:
            Text(L("O que sua dieta precisa respeitar?")).font(.title2.bold())
            Text(L("Informe alergias e intolerâncias, se houver. Esses campos estão disponíveis para todos.")).font(.subheadline).foregroundColor(.secondary)
            dietPreferenceField(L("Alergias"), example: L("Ex.: amendoim, frutos do mar"), text: $allergies)
            dietPreferenceField(L("Intolerâncias"), example: L("Ex.: lactose"), text: $intolerances)
            Text(L("Separe os alimentos por vírgula. Se não houver restrições, deixe em branco.")).font(.caption).foregroundColor(.secondary)
            VStack(alignment: .leading, spacing: 16) {
                Label(L("Preferências alimentares · Premium"), systemImage: session.hasPremium ? "slider.horizontal.3" : "lock.fill").font(.headline)
                dietPreferenceField(L("Alimentos a evitar"), example: L("Ex.: fígado, berinjela"), text: session.hasPremium ? $disliked : .constant(""))
                    .disabled(!session.hasPremium)
                dietPreferenceField(L("Alimentos que você gosta"), example: L("Ex.: arroz, ovos, banana"), text: session.hasPremium ? $preferred : .constant(""))
                    .disabled(!session.hasPremium)
                Text(L("Inclua seus alimentos preferidos e evite os que não gosta na dieta gerada por IA."))
                    .font(.subheadline).foregroundColor(.secondary)
            }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
            VStack(alignment: .leading, spacing: 16) {
                dietPremiumLabel(L("Observações"))
                VStack(alignment: .leading, spacing: 16) {
                    dietPreferenceField(L("Observações"), example: L("Algo mais sobre sua alimentação"), text: session.hasPremium ? $diet.notes : .constant(""))
                        .disabled(!session.hasPremium)
                }
            }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
            if diet.goal == "fat_loss" || diet.goal == "muscle_gain" {
                VStack(alignment: .leading, spacing: 16) {
                    dietPremiumLabel(L("Ritmo do plano"))
                    choiceQuestion(L("Como quer avançar?"), options: [(L("Gradualmente · ajuste menor"),"conservative"),(L("Um pouco mais rápido · ajuste maior"),"moderate")], selection: session.hasPremium ? $diet.changePace : .constant("conservative"))
                        .disabled(!session.hasPremium)
                    Text(L("Essa escolha ajusta as calorias do plano, sem prometer um prazo para o resultado.")).font(.caption).foregroundColor(.secondary)
                }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
            }
            if !session.hasPremium { dietPremiumPitch }
        }
    }
    private func dietPremiumLabel(_ title: String) -> some View {
        HStack {
            Text(title).font(.headline)
            Spacer()
            Label(L("Premium"), systemImage: session.hasPremium ? "checkmark.seal.fill" : "lock.fill")
                .font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
        }
    }
    private var dietPremiumPitch: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(L("Uma dieta com a sua cara"), systemImage: "sparkles").font(.title3.bold())
            Text(L("Com Premium, seu plano considera seus horários, orçamento, preparo e alimentos preferidos. Mais escolhas para encaixar a alimentação na sua vida."))
                .font(.subheadline).foregroundColor(.secondary)
            Label(L("Desbloqueie as opções marcadas com cadeado"), systemImage: "lock.fill")
                .font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
        }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.fitBlue.opacity(0.12), in: RoundedRectangle(cornerRadius: 18))
            .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.fitBlue.opacity(0.3)))
    }
    @ViewBuilder private var workoutQuestion: some View {
        switch step {
        case 0:
            choiceQuestion(L("O que você quer conquistar?"), options: [(L("Hipertrofia"),"hypertrophy"),(L("Força"),"strength"),(L("Condicionamento"),"conditioning"),(L("Perder gordura"),"fat_loss"),(L("Mobilidade"),"mobility")], selection: $workout.goal)
            choiceQuestion(L("Qual sua experiência?"), options: [(L("Iniciante"),"beginner"),(L("Intermediário"),"intermediate"),(L("Avançado"),"advanced")], selection: $workout.experienceLevel)
        case 1:
            numberQuestion(L("Quantos dias por semana?"), value: $workout.daysPerWeek, range: 1...7, suffix: L("dias"))
            numberQuestion(L("Quanto tempo por treino?"), value: $workout.sessionDuration, values: [20,30,45,60,75,90], suffix: L("minutos"))
            choiceQuestion(L("Onde você treina?"), options: [(L("Academia completa"),"full_gym"),(L("Halteres"),"dumbbell"),(L("Peso corporal"),"bodyweight")], selection: $equipment)
        default:
            Text(L("O que precisamos respeitar?")).font(.title2.bold())
            Text(L("Conte limitações que precisam ser consideradas. Se não houver, pode continuar.")).font(.subheadline).foregroundColor(.secondary)
            dietPreferenceField(L("Limitações"), example: L("Ex.: evitar impacto nos joelhos"), text: $workout.limitations)
            VStack(alignment: .leading, spacing: 16) {
                Label(L("Personalização do treino · Premium"), systemImage: session.hasPremium ? "slider.horizontal.3" : "lock.fill").font(.headline)
                dietPreferenceField(L("Músculos para priorizar"), example: L("Ex.: costas e glúteos"), text: $workout.priorities)
                    .disabled(!session.hasPremium)
                dietPreferenceField(L("Exercícios a evitar"), example: L("Ex.: corrida"), text: $workout.avoidExercises)
                    .disabled(!session.hasPremium)
                Label(L("Depois de criar seu treino, peça mudanças por texto em Ajustar plano com IA. Revise a proposta antes de confirmar."), systemImage: session.hasPremium ? "sparkles" : "lock.fill")
                    .font(.subheadline).foregroundColor(.secondary)
                if !session.hasPremium { Button(L("Ver Premium")) { showingPremium = true }.fitGlassButton() }
            }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
        }
    }
    private var review: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(L("Vamos revisar?")).font(.title2.bold())
            Text(kind == .workout ? L("Confira suas escolhas antes de criar seu treino.") : L("Confira suas escolhas antes de gerar.")).foregroundColor(.secondary)
            HStack {
                ForEach(0..<totalSteps, id: \.self) { index in
                    Button([L("Objetivo"), L("Rotina"), L("Preferências")][index]) { step = index }
                        .font(.caption).frame(maxWidth: .infinity, minHeight: 44)
                }
            }.fitGlassButton()
            if kind == .diet {
                let preferences = dietRequestPreferences
                reviewRow(L("Objetivo"), display(diet.goal, values: ["maintenance": L("Manter peso"), "fat_loss": L("Perder gordura"), "muscle_gain": L("Ganhar massa"), "general_health": L("Saúde geral")]))
                reviewRow(L("Alimentação"), display(diet.dietPattern, values: ["omnivore": L("Onívora"), "vegetarian": L("Vegetariana"), "vegan": L("Vegana"), "pescatarian": L("Pescetariana")]))
                reviewRow(L("Refeições"), L("\(diet.mealsPerDay) por dia"))
                reviewRow(L("Treinos"), L("\(diet.trainingDaysPerWeek) dias por semana"))
                reviewRow(L("Rotina"), !session.hasPremium ? L("Premium") : routine.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? L("Não informada") : routine)
                reviewRow(L("Orçamento"), display(preferences.budget, values: ["economical": L("Econômico"), "moderate": L("Moderado"), "flexible": L("Flexível")]))
                reviewRow(L("Preparo"), session.hasPremium ? prepStyleLabel : L("Até 30 minutos"))
                reviewRow(L("Avanço até o objetivo"), display(preferences.changePace, values: ["conservative": L("Gradualmente"), "moderate": L("Um pouco mais rápido")]))
                reviewRow(L("Alergias"), listText(allergies))
                reviewRow(L("Intolerâncias"), listText(intolerances))
                reviewRow(L("A evitar"), session.hasPremium ? listText(disliked) : L("Premium"))
                reviewRow(L("Favoritos"), !session.hasPremium ? L("Premium") : preferred.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? L("Não informados") : preferred)
                reviewRow(L("Observações"), !session.hasPremium ? L("Premium") : diet.notes.isEmpty ? L("Nenhuma") : diet.notes)
            } else {
                reviewRow(L("Objetivo"), display(workout.goal, values: ["hypertrophy": L("Hipertrofia"), "strength": L("Força"), "conditioning": L("Condicionamento"), "fat_loss": L("Perder gordura"), "mobility": L("Mobilidade")]))
                reviewRow(L("Experiência"), display(workout.experienceLevel, values: ["beginner": L("Iniciante"), "intermediate": L("Intermediário"), "advanced": L("Avançado")]))
                reviewRow(L("Frequência"), L("\(workout.daysPerWeek) dias"))
                reviewRow(L("Duração"), L("\(workout.sessionDuration) minutos"))
                reviewRow(L("Equipamentos"), display(equipment, values: ["full_gym": L("Academia completa"), "dumbbell": L("Halteres"), "bodyweight": L("Peso corporal")]))
                reviewRow(L("Limitações"), workout.limitations.isEmpty ? L("Nenhuma") : workout.limitations)
                reviewRow(L("Prioridades"), workout.priorities.isEmpty ? L("Nenhuma") : workout.priorities)
                reviewRow(L("Exercícios a evitar"), workout.avoidExercises.isEmpty ? L("Nenhum") : workout.avoidExercises)
            }
            Text(L("O plano atual só muda depois que você revisar e confirmar a alternativa.")).font(.footnote).foregroundColor(.secondary).padding(.top, 10)
        }
    }
    private func reviewRow(_ title: String, _ value: String) -> some View { HStack { Text(title).foregroundColor(.secondary); Spacer(); Text(value).multilineTextAlignment(.trailing).lineLimit(2) }.padding(.vertical, 8) }
    private var prepStyleLabel: String { prepStyle == "quick" ? L("Práticas e rápidas") : prepStyle == "elaborate" ? L("Mais elaboradas") : L("Um pouco de cada") }
    private func display(_ value: String, values: [String: String]) -> String { values[value] ?? value }
    private func listText(_ value: String) -> String { value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? L("Nenhuma") : value }
    private func choiceQuestion(_ title: String, options: [(String,String)], selection: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 14) { Text(title).font(.title2.bold()); ForEach(options, id: \.1) { option in Button { selection.wrappedValue = option.1 } label: { HStack { Text(option.0); Spacer(); if selection.wrappedValue == option.1 { Image(systemName: "checkmark.circle.fill").foregroundColor(.fitBlue) } else { Image(systemName: "circle").foregroundColor(.secondary) } }.padding(16).frame(maxWidth: .infinity, alignment: .leading).background(selection.wrappedValue == option.1 ? Color.fitBlue.opacity(0.2) : Color.fitSurface, in: RoundedRectangle(cornerRadius: 16)) }.buttonStyle(.plain) } }
    }
    private func numberQuestion(_ title: String, value: Binding<Int>, range: ClosedRange<Int>, suffix: String) -> some View { VStack(alignment: .leading, spacing: 14) { Text(title).font(.title2.bold()); Stepper("\(value.wrappedValue) \(suffix)", value: value, in: range).padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16)) } }
    private func dietPreferenceField(_ title: String, example: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.subheadline.weight(.semibold))
            TextField("", text: text, prompt: Text(example).foregroundColor(.white.opacity(0.6)))
                .textFieldStyle(.plain).foregroundColor(.white)
                .padding(14)
                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.white.opacity(0.16), lineWidth: 1))
                .accessibilityLabel(title)
        }
    }
    private func numberQuestion(_ title: String, value: Binding<Int>, values: [Int], suffix: String) -> some View { VStack(alignment: .leading, spacing: 14) { Text(title).font(.title2.bold()); LazyVGrid(columns: [GridItem(.adaptive(minimum: 70))], spacing: 10) { ForEach(values, id: \.self) { item in Button("\(item)") { value.wrappedValue = item }.frame(maxWidth: .infinity).padding(14).background(value.wrappedValue == item ? Color.fitBlue.opacity(0.25) : Color.fitSurface, in: RoundedRectangle(cornerRadius: 12)) } }; Text(suffix).font(.footnote).foregroundColor(.secondary) } }
    private func picker(_ title: String, value: Binding<String>, options: [(String,String)]) -> some View {
        Picker(title, selection: value) { ForEach(options, id: \.0) { Text($0.1).tag($0.0) } }
    }
    private var pendingJobKey: String? {
        guard let account = session.user?.id else { return nil }
        return "fitTracker.pendingPlan.\(account.uuidString).\(kind == .diet ? "diet" : "workout")"
    }
    private func storeJob(_ id: UUID?) {
        jobId = id
        guard let key = pendingJobKey else { return }
        if let id {
            UserDefaults.standard.set(id.uuidString, forKey: key)
            backgroundPlans.track(id: id, kind: kind, owner: session.user?.id, api: session.api)
        }
        else { UserDefaults.standard.removeObject(forKey: key) }
    }
    private func leaveGeneration() {
        monitoringJob = nil
        showingGeneration = false
    }
    private func receiveGeneratedPlan(_ plan: NativePlan) {
        if let owner = setupOwner, session.user?.id == owner { draftStore.clear(owner: owner, kind: kind) }
        storeJob(nil)
        monitoringJob = nil
        generated = plan
        showingGeneration = false
        reviewingPlan = plan
    }
    private func generate() async {
        guard !busy else { return }
        NativeXPEffects.shared.captureAction(key: generationKey)
        error = nil
        showingGeneration = true
        generationStarted = Date()
        takingLonger = false
        if let jobId {
            monitoringJob = jobId
            return
        }
        let account = session.user?.id
        busy = true
        defer { busy = false }
        do {
            try await session.refreshFreeAccess()
            if let access = session.freeAccess, !access.premium, access.remainingPlans(for: kind) == 0 {
                showingGeneration = false
                showingPremium = true
                return
            }
            let consent = try await session.api.consentStatus()
            if !consent.ai.accepted {
                showingGeneration = false
                consentVersion = consent.versions.ai.version
                consentForGeneration = true
                requestingConsent = true
                return
            }
            let preferences = dietRequestPreferences
            var workoutPreferences = workout
            if !session.hasPremium { workoutPreferences.priorities = ""; workoutPreferences.avoidExercises = "" }
            workoutPreferences.equipment = [equipment]
            let capabilities = try? await session.api.planBackgroundStatus()
            if capabilities?.planBackgroundEnabled == true {
                await backgroundPlans.prepareNotifications(api: session.api, owner: account,
                    enabled: capabilities?.pushEnabled == true)
            }
            if capabilities?.planBackgroundEnabled == true, let account {
                backgroundPlans.beginRequest(owner: account, kind: kind, key: generationKey)
            }
            let response: PlanGenerationResponse
            if kind == .diet { response = try await session.api.generateDietPlan(preferences,
                background: capabilities?.planBackgroundEnabled == true, idempotencyKey: generationKey) }
            else { response = try await session.api.generateWorkoutPlan(workoutPreferences,
                background: capabilities?.planBackgroundEnabled == true, idempotencyKey: generationKey) }
            guard session.user?.id == account else { showingGeneration = false; return }
            switch response {
            case .plan(let plan): receiveGeneratedPlan(plan)
            case .queued(let id): storeJob(id); monitoringJob = id
            }
        } catch {
            if Task.isCancelled || (error as? URLError)?.code == .cancelled { showingGeneration = false; return }
            if case APIError.http(let status, _) = error, status == 403 {
                try? await session.refreshFreeAccess()
                if let access = session.freeAccess, !access.premium, access.remainingPlans(for: kind) == 0 {
                    showingGeneration = false
                    showingPremium = true
                } else { self.error = RequestFailure.message(error, fallback: L("Não foi possível confirmar esta etapa. Suas escolhas continuam aqui; confira e tente novamente.")) }
            } else { self.error = RequestFailure.message(error, fallback: L("Não foi possível confirmar esta etapa. Suas escolhas continuam aqui; confira e tente novamente.")) }
        }
    }
    private func monitorGeneration(id: UUID) async {
        backgroundPlans.track(id: id, kind: kind, owner: session.user?.id, api: session.api)
    }
    private var generationScreen: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 0) {
                    Spacer(minLength: 28)
                    if error == nil {
                        NativePlanPreparationAnimation(kind: kind)
                            .frame(width: 260, height: 260)
                        Text(takingLonger ? L("Está demorando mais que o esperado.") : kind == .diet ? L("Preparando sua dieta.") : L("Montando seu treino."))
                            .font(.system(size: 29, weight: .bold)).multilineTextAlignment(.center).padding(.top, 20)
                        Text(takingLonger && jobId != nil
                             ? L("Seu pedido está salvo e continua sendo preparado. Você pode sair desta tela e conferir o plano quando estiver pronto.")
                             : kind == .diet
                             ? L("Combinando seus gostos, sua rotina e seu objetivo em um plano feito para você.")
                             : L("Organizando os exercícios para seu objetivo, seu nível e os dias que você tem disponíveis."))
                            .font(.subheadline).foregroundColor(.secondary).multilineTextAlignment(.center)
                            .padding(.top, 14).frame(maxWidth: 300)
                        HStack(spacing: 9) {
                            ProgressView().scaleEffect(0.75).tint(Color(red: 0.31, green: 0.86, blue: 0.75))
                            Text(L("Seu plano está ganhando forma")).font(.caption).foregroundColor(.secondary)
                        }.padding(.top, 28).accessibilityElement(children: .combine)
                    } else {
                        Image(systemName: "exclamationmark.circle").font(.system(size: 54, weight: .light))
                            .foregroundColor(.orange).padding(.bottom, 28)
                        Text(L("Vamos tentar de novo?")).font(.title2.bold()).multilineTextAlignment(.center)
                        Text(error ?? "").font(.subheadline).foregroundColor(.secondary)
                            .multilineTextAlignment(.center).padding(.top, 14)
                        if jobId != nil {
                            Button(L("Retomar meu plano")) { error = nil; monitoringJob = jobId }
                                .fitGlassButton(prominent: true).padding(.top, 24)
                        }
                    }
                    Spacer(minLength: 32)
                    Text(takingLonger && jobId != nil && backgroundPlans.notificationsAvailable
                         ? L("Avisaremos quando seu plano estiver pronto. Você pode continuar usando o app.")
                         : jobId != nil
                         ? L("Você pode voltar às suas escolhas. Seu plano continua sendo preparado.")
                         : L("Você poderá conferir tudo antes de usar o plano."))
                        .font(.caption).foregroundColor(.secondary).multilineTextAlignment(.center)
                        .frame(maxWidth: 270).padding(.bottom, 16)
                    Button(L("Voltar às escolhas")) { leaveGeneration() }
                        .font(.subheadline).disabled(busy).padding(.bottom, 24)
                    if takingLonger, jobId != nil {
                        Button(L("Continuar usando o app")) { dismiss() }
                            .fitGlassButton(prominent: true).padding(.bottom, 24)
                    }
                }.padding(.horizontal, 24).frame(maxWidth: .infinity)
                    .frame(minHeight: geometry.size.height)
            }
        }
    }
    private var consentSheet: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text(kind == .workout ? L("Seu treino, conforme sua rotina") : L("Um plano personalizado com IA")).font(.title2.bold())
                    Text(kind == .workout ? L("Quando suas escolhas forem compatíveis, selecionaremos um plano pronto. Se precisar de IA, enviaremos ao Google Gemini e, se ele falhar, à OpenAI os dados de perfil e treino necessários, com sua autorização. Você pode revogá-la no Perfil.") : L("Para gerar seu plano, precisamos da sua autorização para enviar ao Google Gemini e, se ele falhar, à OpenAI os dados de perfil, alimentação e treino necessários. Você pode revogar essa autorização no Perfil."))
                    Button(consentForGeneration ? L("Autorizar e criar plano") : L("Autorizar e continuar")) {
                        guard let version = consentVersion else { return }
                        requestingConsent = false
                        Task {
                            do {
                                _ = try await session.api.updateConsent(granted: true, version: version)
                                consentAccepted = true
                                if consentForGeneration { await generate() }
                            }
                            catch { self.error = RequestFailure.message(error, fallback: L("Não foi possível confirmar esta etapa. Suas escolhas continuam aqui; confira e tente novamente.")) }
                        }
                    }.fitGlassButton(prominent: true)
                    Button(L("Agora não")) { requestingConsent = false }
                }.padding(24)
            }.background(Color.fitBackground.ignoresSafeArea()).navigationTitle(L("Autorização de IA"))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { requestingConsent = false } } }
        }.navigationViewStyle(.stack)
    }
    private func split(_ text: String) -> [String] { text.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty } }
}

private struct NativePlanPreparationAnimation: View {
    let kind: NativePlanKind
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private let mint = Color(red: 0.31, green: 0.86, blue: 0.75)

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: reduceMotion)) { timeline in
            Canvas { context, size in
                var drawing = context
                drawing.scaleBy(x: size.width / 280, y: size.height / 280)
                let time = reduceMotion ? 0 : timeline.date.timeIntervalSinceReferenceDate
                let wave = reduceMotion ? 0 : sin(time * 2 * .pi / 3.8)
                drawing.fill(Path(ellipseIn: CGRect(x: 34, y: 34, width: 212, height: 212)),
                             with: .radialGradient(Gradient(colors: [mint.opacity(0.1), .clear]),
                                                   center: CGPoint(x: 140, y: 140), startRadius: 0, endRadius: 110))
                drawing.fill(Path(ellipseIn: CGRect(x: 60, y: 216, width: 160, height: 20)), with: .color(.black.opacity(0.25)))
                if kind == .diet { drawBowl(in: drawing, time: time, wave: wave) }
                else { drawDumbbell(in: drawing, wave: wave) }
            }
        }.accessibilityHidden(true)
    }
    private func drawBowl(in context: GraphicsContext, time: Double, wave: Double) {
        for index in 0..<3 {
            let x = 118.0 + Double(index) * 24
            let lift = reduceMotion ? 0 : sin(time * 2 * .pi / 2.8 - Double(index) * 0.8) * 5
            var steam = Path()
            steam.move(to: CGPoint(x: x, y: 114 + lift))
            steam.addCurve(to: CGPoint(x: x, y: 76 + lift),
                           control1: CGPoint(x: x - 13, y: 99 + lift), control2: CGPoint(x: x + 12, y: 93 + lift))
            context.stroke(steam, with: .color(mint.opacity(0.35 + (wave + 1) * 0.13)),
                           style: StrokeStyle(lineWidth: 3, lineCap: .round))
        }
        if !reduceMotion {
            for index in 0..<3 {
                let phase = (time / 3.8 + Double(index) / 3).truncatingRemainder(dividingBy: 1)
                if phase > 0.16 && phase < 0.55 {
                    let x = [103.0, 159.0, 139.0][index]
                    let y = 60 + (phase - 0.16) * 210
                    rounded(in: context, rect: CGRect(x: x, y: y, width: 11, height: 11), radius: 3,
                            color: [Color.orange, mint, Color.yellow][index].opacity(0.9))
                }
            }
        }
        var spoon = context
        spoon.translateBy(x: 211, y: 140)
        spoon.rotate(by: .degrees(wave * 6))
        spoon.translateBy(x: -211, y: -140)
        var handle = Path()
        handle.move(to: CGPoint(x: 205, y: 136)); handle.addLine(to: CGPoint(x: 227, y: 78))
        spoon.stroke(handle, with: .color(Color(red: 0.74, green: 0.83, blue: 0.91)), style: StrokeStyle(lineWidth: 8, lineCap: .round))
        spoon.fill(Path(ellipseIn: CGRect(x: 187, y: 130, width: 26, height: 40)), with: .color(Color(red: 0.55, green: 0.7, blue: 0.81)))
        var bowl = Path()
        bowl.move(to: CGPoint(x: 65, y: 153)); bowl.addLine(to: CGPoint(x: 215, y: 153))
        bowl.addCurve(to: CGPoint(x: 140, y: 222), control1: CGPoint(x: 213, y: 189), control2: CGPoint(x: 190, y: 222))
        bowl.addCurve(to: CGPoint(x: 65, y: 153), control1: CGPoint(x: 90, y: 222), control2: CGPoint(x: 67, y: 189))
        bowl.closeSubpath()
        context.fill(bowl, with: .linearGradient(Gradient(colors: [mint, Color(red: 0.14, green: 0.61, blue: 0.57)]),
                                                 startPoint: CGPoint(x: 65, y: 153), endPoint: CGPoint(x: 215, y: 222)))
        context.fill(Path(ellipseIn: CGRect(x: 65, y: 130, width: 150, height: 46)), with: .color(Color(red: 0.62, green: 0.93, blue: 0.86)))
        context.fill(Path(ellipseIn: CGRect(x: 74, y: 134, width: 132, height: 34)),
                     with: .linearGradient(Gradient(colors: [Color(red: 1, green: 0.89, blue: 0.62), Color(red: 0.9, green: 0.67, blue: 0.34)]),
                                           startPoint: CGPoint(x: 140, y: 134), endPoint: CGPoint(x: 140, y: 168)))
        var shine = Path()
        shine.move(to: CGPoint(x: 77, y: 174)); shine.addQuadCurve(to: CGPoint(x: 116, y: 204), control: CGPoint(x: 94, y: 199))
        context.stroke(shine, with: .color(.white.opacity(0.38)), style: StrokeStyle(lineWidth: 5, lineCap: .round))
        var leaf = Path()
        leaf.move(to: CGPoint(x: 132, y: 148))
        leaf.addQuadCurve(to: CGPoint(x: 103, y: 137), control: CGPoint(x: 122, y: 124))
        leaf.addQuadCurve(to: CGPoint(x: 132, y: 148), control: CGPoint(x: 107, y: 157))
        leaf.addQuadCurve(to: CGPoint(x: 165, y: 136), control: CGPoint(x: 149, y: 122))
        leaf.addQuadCurve(to: CGPoint(x: 132, y: 148), control: CGPoint(x: 159, y: 157))
        context.fill(leaf, with: .color(Color(red: 0.22, green: 0.62, blue: 0.47)))
        rounded(in: context, rect: CGRect(x: 164, y: 153, width: 11, height: 6), radius: 2, color: .orange.opacity(0.75))
        rounded(in: context, rect: CGRect(x: 112, y: 154, width: 8, height: 6), radius: 2, color: Color(red: 0.97, green: 0.93, blue: 0.79))
    }
    private func drawDumbbell(in context: GraphicsContext, wave: Double) {
        for point in [CGPoint(x: 61, y: 100), CGPoint(x: 212, y: 181)] {
            var spark = Path()
            spark.move(to: CGPoint(x: point.x - 7, y: point.y)); spark.addLine(to: CGPoint(x: point.x + 7, y: point.y))
            spark.move(to: CGPoint(x: point.x, y: point.y - 7)); spark.addLine(to: CGPoint(x: point.x, y: point.y + 7))
            context.stroke(spark, with: .color(mint.opacity(0.5 + wave * 0.2)), style: StrokeStyle(lineWidth: 3, lineCap: .round))
        }
        var weights = context
        weights.translateBy(x: 140, y: 149 - wave * 11)
        weights.rotate(by: .degrees(wave * 7))
        weights.translateBy(x: -140, y: -149)
        let steel = Color(red: 0.79, green: 0.9, blue: 0.93)
        rounded(in: weights, rect: CGRect(x: 80, y: 139, width: 120, height: 18), radius: 9, color: steel)
        for x in stride(from: 119.0, through: 164.0, by: 9) {
            var grip = Path(); grip.move(to: CGPoint(x: x, y: 142)); grip.addLine(to: CGPoint(x: x, y: 154))
            weights.stroke(grip, with: .color(Color(red: 0.48, green: 0.68, blue: 0.75)), lineWidth: 2)
        }
        for x in [70.0, 180.0] {
            weights.fill(Path(roundedRect: CGRect(x: x, y: 105, width: 30, height: 86), cornerRadius: 11),
                         with: .linearGradient(Gradient(colors: [Color(red: 0.47, green: 0.68, blue: 1), .fitBlue]),
                                               startPoint: CGPoint(x: x, y: 105), endPoint: CGPoint(x: x + 30, y: 191)))
            var shine = Path(); shine.move(to: CGPoint(x: x + 9, y: 120)); shine.addLine(to: CGPoint(x: x + 9, y: 173))
            weights.stroke(shine, with: .color(.white.opacity(0.5)), style: StrokeStyle(lineWidth: 4, lineCap: .round))
        }
        for x in [49.0, 206.0] { rounded(in: weights, rect: CGRect(x: x, y: 118, width: 25, height: 60), radius: 9, color: Color(red: 0.36, green: 0.61, blue: 0.94)) }
        for x in [41.0, 230.0] { rounded(in: weights, rect: CGRect(x: x, y: 139, width: 9, height: 18), radius: 4, color: steel) }
    }
    private func rounded(in context: GraphicsContext, rect: CGRect, radius: CGFloat, color: Color) {
        context.fill(Path(roundedRect: rect, cornerRadius: radius), with: .color(color))
    }
}

private struct PlanMealEditor: View {
    let planId: Int
    let meal: DietMealAlternative
    let onSaved: () -> Void
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    @State private var description = ""
    @State private var calories = ""
    @State private var protein = ""
    @State private var carbs = ""
    @State private var fat = ""
    @State private var busy = false
    @State private var error: String?
    var body: some View {
        NavigationView {
            Form {
                Section(meal.mealType) { TextEditor(text: $description).frame(minHeight: 130) }
                Section(L("Valores nutricionais")) {
                    TextField(L("Calorias (kcal)"), text: $calories).keyboardType(.decimalPad)
                    TextField(L("Proteínas (g)"), text: $protein).keyboardType(.decimalPad)
                    TextField(L("Carboidratos (g)"), text: $carbs).keyboardType(.decimalPad)
                    TextField(L("Gorduras (g)"), text: $fat).keyboardType(.decimalPad)
                    Text(L("Campos vazios preservam o valor anterior.")).font(.footnote).foregroundColor(.secondary)
                }
                Section {
                    Text(L("Ao alterar os alimentos, os valores nutricionais do plano precisam ser revistos.")).font(.footnote).foregroundColor(.secondary)
                    if let error = error { NativeRecoveryCard(title: L("Vamos continuar de onde parou?"), message: error) }
                    Button(L("Salvar refeição")) { Task { await save() } }.disabled(busy || description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    if busy { ProgressView() }
                }
            }.navigationTitle(L("Editar refeição"))
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Cancelar")) { dismiss() }.disabled(busy) } }
                .onAppear {
                    description = meal.description
                    calories = meal.calories.map(String.init(describing:)) ?? ""
                    protein = meal.protein.map(String.init(describing:)) ?? ""
                    carbs = meal.carbs.map(String.init(describing:)) ?? ""
                    fat = meal.fat.map(String.init(describing:)) ?? ""
                }
        }.navigationViewStyle(.stack)
    }
    private func save() async {
        guard !busy else { return }; busy = true; error = nil
        defer { busy = false }
        do {
            let values = try [calories, protein, carbs, fat].enumerated().map { index, text -> Double? in
                let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
                if cleaned.isEmpty { return nil }
                guard let value = Double(cleaned.replacingOccurrences(of: ",", with: ".")), value.isFinite, value >= 0, value <= (index == 0 ? 20000 : 5000) else {
                    throw APIError.http(status: 400, message: L("Revise os valores nutricionais."))
                }
                return value
            }
            try await session.api.editDietPlanMeal(planId: planId, mealId: meal.id, description: description, calories: values[0], protein: values[1], carbs: values[2], fat: values[3])
            onSaved(); dismiss()
        }
        catch { self.error = RequestFailure.message(error, fallback: L("Não foi possível confirmar esta etapa. Suas escolhas continuam aqui; confira e tente novamente.")) }
    }
}


private struct PlanExerciseEditor: View {
    let planId: Int
    let exercise: PlanWorkoutExercise
    let onSaved: (NativePlan) -> Void
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    @State private var sets = 3
    @State private var reps = ""
    @State private var weight = ""
    @State private var rest = 60
    @State private var busy = false
    @State private var error: String?
    @State private var method = "similar"
    @State private var search = ""
    @State private var options: [WorkoutReplacementOption] = []
    @State private var optionsLoadError: String?
    @State private var catalog: [PlanCatalogItem] = []
    @State private var selectedKey: String?
    @State private var selectedName: String?
    @State private var customName = ""
    @State private var confirming = false
    private var compatibleCatalog: [PlanCatalogItem] {
        let group = catalog.first { $0.key == exercise.catalogKey }?.group ?? catalog.first { item in options.contains(where: { $0.catalogKey == item.key }) }?.group
        return catalog.filter { item in
            (group.map { item.group == $0 } ?? options.contains(where: { $0.catalogKey == item.key })) && (search.isEmpty || item.name.localizedStandardContains(search))
        }
    }
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text(exercise.name).font(.title2.bold())
                    if exercise.catalogKey?.hasPrefix("custom:") == true { TextField(L("Nome do exercício"), text: $customName) }
                    Text(L("A edição vale para os próximos treinos. Seu histórico é preservado.")).font(.subheadline).foregroundColor(.secondary)
                    Picker(L("Como editar"), selection: $method) { Text(L("Semelhantes")).tag("similar"); Text(L("Catálogo")).tag("catalog"); Text(L("Prescrição")).tag("prescription") }.pickerStyle(.segmented)
                    if method == "catalog" { TextField(L("Pesquisar exercício"), text: $search).padding(12).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 12)); Text(L("Exercícios compatíveis com o padrão de movimento do plano.")).font(.caption).foregroundColor(.secondary) }
                    if let optionsLoadError {
                        NativeRecoveryCard(title: L("Vamos procurar suas alternativas?"), message: optionsLoadError, actionTitle: L("Tentar novamente")) { Task { await load() } }
                    }
                    if method == "similar" {
                        ForEach(options) { option in choice(key: option.catalogKey, name: option.name) }
                        if options.isEmpty && !busy && optionsLoadError == nil {
                            NativeRecoveryCard(title: L("Vamos procurar outra opção?"), message: L("Não há alternativas semelhantes para este exercício agora. Você pode conferir o catálogo ou ajustar a prescrição."), systemImage: "magnifyingglass", actionTitle: L("Conferir catálogo")) { method = "catalog" }
                        }
                    } else if method == "catalog" {
                        LazyVStack(spacing: 12) { ForEach(compatibleCatalog) { item in choice(key: item.key, name: item.name) } }
                        if compatibleCatalog.isEmpty && !busy && optionsLoadError == nil {
                            NativeRecoveryCard(title: search.isEmpty ? L("Sem opções compatíveis por enquanto") : L("Vamos tentar outro nome?"), message: search.isEmpty ? L("Você pode manter o exercício e ajustar suas séries, repetições e carga.") : L("Nenhum exercício corresponde à busca. Tente um nome mais curto."), systemImage: "magnifyingglass", actionTitle: search.isEmpty ? L("Ajustar prescrição") : L("Limpar busca")) { if search.isEmpty { method = "prescription" } else { search = "" } }
                        }
                    }
                    VStack(alignment: .leading, spacing: 14) {
                        Text(L("Prescrição")).font(.headline)
                        Stepper(L("\(sets) séries"), value: $sets, in: 1...10)
                        TextField(L("Repetições"), text: $reps)
                        TextField(L("Carga prescrita"), text: $weight)
                        Stepper(L("\(rest) s descanso"), value: $rest, in: 0...600, step: 15)
                    }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                    if let error { NativeRecoveryCard(title: L("Suas escolhas continuam aqui"), message: error) }
                    if busy { ProgressView().frame(maxWidth: .infinity) }
                    Button(L("Revisar alteração")) { confirming = true }.fitGlassButton(prominent: true).disabled(busy || reps.isEmpty)
                }.padding(20)
            }.background(Color.fitBackground.ignoresSafeArea()).navigationTitle(L("Editar exercício")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Cancelar")) { dismiss() }.disabled(busy) } }
                .task { customName = exercise.name; sets = exercise.sets ?? 3; reps = exercise.reps ?? ""; weight = exercise.weight ?? ""; rest = exercise.restSeconds ?? 60; await load() }
                .sheet(isPresented: $confirming) {
                    NavigationView {
                        VStack(alignment: .leading, spacing: 20) {
                            Text(L("Antes")).foregroundColor(.secondary); Text(exercise.name).font(.headline)
                            Text(L("\(exercise.sets ?? 3) × \(exercise.reps ?? "—") · \(exercise.restSeconds ?? 60) s descanso")).foregroundColor(.secondary)
                            Text(exercise.weight.flatMap { $0.isEmpty ? nil : $0 } ?? L("Sem carga prescrita")).font(.subheadline).foregroundColor(.secondary)
                            Divider(); Text(L("Depois")).foregroundColor(.fitBlue); Text(selectedName ?? exercise.name).font(.title3.bold())
                            Text(L("\(sets) × \(reps) · \(rest) s descanso"))
                            Text(weight.isEmpty ? L("Sem carga prescrita") : L("Carga: \(weight)")).font(.subheadline)
                            Text(L("A alteração será salva no plano ao confirmar.")).font(.subheadline).foregroundColor(.secondary)
                            if let error { NativeRecoveryCard(title: L("Suas escolhas continuam aqui"), message: error) }
                            Button(L("Confirmar alteração no plano")) { Task { await save() } }.fitGlassButton(prominent: true).disabled(busy)
                            Spacer()
                        }.padding(20).background(Color.fitBackground.ignoresSafeArea()).navigationTitle(L("Revisar alteração")).navigationBarTitleDisplayMode(.inline)
                            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Voltar")) { confirming = false }.disabled(busy) } }
                    }.navigationViewStyle(.stack)
                }
        }.navigationViewStyle(.stack)
    }
    private func choice(key: String, name: String) -> some View {
        Button { selectedKey = key; selectedName = name } label: {
            HStack(spacing: 12) {
                NativeExerciseAnimation(catalogKey: key).frame(width: 90, height: 80).clipShape(RoundedRectangle(cornerRadius: 12))
                Text(name).font(.subheadline.weight(.semibold)).foregroundColor(.primary).frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: selectedKey == key ? "checkmark.circle.fill" : "circle").foregroundColor(.fitBlue)
            }.padding(12).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain).disabled(busy)
    }
    private func load() async {
        guard !busy else { return }
        busy = true; optionsLoadError = nil; defer { busy = false }
        do {
            async let alternatives = session.api.getPlanReplacementOptions(planId: planId, exerciseId: exercise.id)
            async let items = session.api.getPlanExerciseCatalog(planId: planId)
            (options, catalog) = try await (alternatives.options, items)
        } catch { if !isNativeRequestCancellation(error) { optionsLoadError = RequestFailure.message(error, fallback: L("As alternativas não carregaram agora. Você pode ajustar a prescrição ou tentar novamente.")) } }
    }
    private func save() async {
        guard !busy else { return }; busy = true; error = nil
        defer { busy = false }
        do {
            let updated = try await session.api.editWorkoutPrescription(planId: planId, exerciseId: exercise.id, catalogKey: selectedKey, sets: sets, reps: reps, weight: weight, restSeconds: rest, name: exercise.catalogKey?.hasPrefix("custom:") == true ? customName : nil)
            NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
            onSaved(updated); confirming = false; dismiss()
        } catch { self.error = RequestFailure.message(error, fallback: L("Não foi possível confirmar esta etapa. Suas escolhas continuam aqui; confira e tente novamente.")) }
    }
}

private struct PlanAIEditor: View {
    let plan: NativePlan
    let initialDayId: Int?
    let onSaved: (NativePlan) -> Void
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    @State private var feedback = ""
    @State private var wholePlan = false
    @State private var changes: [PlanExerciseChange] = []
    @State private var revision = ""
    @State private var proposalPlan: NativePlan?
    @State private var busy = false
    @State private var error: String?
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text(changes.isEmpty ? L("O que quer mudar?") : L("Confira antes de salvar.")).font(.title2.bold())
                    if changes.isEmpty {
                        if initialDayId != nil { Toggle(L("Ajustar o plano inteiro"), isOn: $wholePlan) }
                        Text(L("Descreva sua preferência ou os equipamentos disponíveis.")).foregroundColor(.secondary)
                        TextEditor(text: $feedback).frame(minHeight: 140).padding(10).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                        Text(L("A IA sugere trocas compatíveis e ajustes de séries e repetições. Você aprova a proposta antes de salvar.")).font(.subheadline).foregroundColor(.secondary)
                        Button(L("Ver proposta de alteração")) { Task { await suggest() } }.fitGlassButton(prominent: true).disabled(busy || feedback.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    } else {
                        ForEach(changes) { change in
                            VStack(alignment: .leading, spacing: 10) {
                                if let before = (proposalPlan ?? plan).days?.flatMap(\.exercises).first(where: { $0.id == change.exerciseId }) {
                                    Text(L("Antes")).font(.caption).foregroundColor(.secondary)
                                    Text(before.name).font(.headline)
                                    Text("\(before.sets ?? 3) × \(before.reps ?? "—") · \(before.restSeconds ?? 60) s").font(.subheadline).foregroundColor(.secondary)
                                    Text(before.weight.flatMap { $0.isEmpty ? nil : $0 } ?? L("Sem carga prescrita")).font(.subheadline).foregroundColor(.secondary)
                                }
                                Divider(); Text(L("Depois")).font(.caption).foregroundColor(.fitBlue)
                                Text(change.name).font(.headline)
                                Text("\(change.sets) × \(change.reps) · \(change.restSeconds) s")
                                Text(change.weight.flatMap { $0.isEmpty ? nil : $0 } ?? L("Sem carga prescrita")).font(.subheadline)
                            }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        }
                        Button(L("Refinar meu pedido")) { changes = [] }.disabled(busy)
                        Button(L("Confirmar alteração no plano")) { Task { await apply() } }.fitGlassButton(prominent: true).disabled(busy)
                    }
                    if busy { ProgressView().frame(maxWidth: .infinity) }
                    if let error { NativeRecoveryCard(title: L("Suas escolhas continuam aqui"), message: error) }
                }.padding(20)
            }.background(Color.fitBackground.ignoresSafeArea()).navigationTitle(L("Ajustar com IA")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { dismiss() }.disabled(busy) } }
        }.navigationViewStyle(.stack)
    }
    private func suggest() async {
        guard !busy else { return }; busy = true; error = nil; defer { busy = false }
        do { let proposal = try await session.api.suggestPlanChanges(planId: plan.id, feedback: feedback, dayId: wholePlan ? nil : initialDayId); changes = proposal.changes; revision = proposal.revision; proposalPlan = proposal.plan }
        catch { self.error = RequestFailure.message(error, fallback: L("Não foi possível confirmar esta etapa. Suas escolhas continuam aqui; confira e tente novamente.")) }
    }
    private func apply() async {
        guard !busy else { return }; busy = true; error = nil; defer { busy = false }
        do { let updated = try await session.api.applyPlanChanges(planId: plan.id, changes: changes, revision: revision); onSaved(updated); dismiss() }
        catch { self.error = RequestFailure.message(error, fallback: L("Não foi possível confirmar esta etapa. Suas escolhas continuam aqui; confira e tente novamente.")) }
    }
}

struct NativeManualPlanView: View {
    let kind: NativePlanKind
    let imported: WorkoutTextImport?
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var days = [ManualPlanDay()]
    @State private var meals = [ManualPlanMeal()]
    @State private var catalog: [PlanCatalogItem] = []
    @State private var search = ""
    @State private var catalogLoading = false
    @State private var catalogError: String?
    @State private var catalogTarget: UUID?
    @State private var saved: NativePlan?
    @State private var busy = false
    @State private var error: String?
    @State private var importedMissingRest: Set<UUID> = []
    @State private var importReviewed = false

    init(kind: NativePlanKind, imported: WorkoutTextImport? = nil) {
        self.kind = kind; self.imported = imported
        if let imported {
            var missingRest: Set<UUID> = []
            let importedDays = imported.days.map { source -> ManualPlanDay in
                var day = ManualPlanDay(); day.title = source.title
                day.exercises = source.exercises.map { item in
                    var exercise = ManualPlanExercise()
                    exercise.name = item.name; exercise.sets = item.sets ?? 0; exercise.reps = item.reps
                    exercise.weight = item.weight; exercise.restSeconds = item.restSeconds ?? 0
                    if item.restSeconds == nil { missingRest.insert(exercise.id) }
                    return exercise
                }
                return day
            }
            _title = State(initialValue: L("Meu treino importado"))
            _days = State(initialValue: importedDays)
            _importedMissingRest = State(initialValue: missingRest)
        }
    }
    private var valid: Bool {
        (imported == nil || importReviewed) && !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && (kind == .workout
            ? !days.isEmpty && days.allSatisfy { !$0.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !$0.exercises.isEmpty && $0.exercises.allSatisfy { !$0.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !$0.reps.isEmpty && $0.sets > 0 && !importedMissingRest.contains($0.id) } }
            : !meals.isEmpty && meals.allSatisfy { !$0.description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty })
    }
    var body: some View {
        NavigationView {
            Form {
                if let imported {
                    Section(L("Confira a importação")) {
                        Text(L("Revise os nomes, séries, repetições, cargas e descansos. A leitura pode conter erros; nada foi salvo.")).font(.subheadline)
                        if !imported.warnings.isEmpty {
                            DisclosureGroup(L("\(imported.warnings.count) pontos precisam de conferência")) {
                                ForEach(Array(imported.warnings.enumerated()), id: \.offset) { _, warning in Text(warning).font(.caption).foregroundColor(.orange) }
                            }
                        }
                        DisclosureGroup(L("Texto original completo")) { Text(imported.sourceText).font(.caption).textSelection(.enabled) }
                    }
                }
                Section(L("Seu plano")) { TextField(L("Nome do plano"), text: $title) }
                if kind == .workout {
                    ForEach($days) { $day in
                        Section {
                            TextField(L("Nome do dia"), text: $day.title)
                            ForEach($day.exercises) { $exercise in
                                VStack(alignment: .leading, spacing: 12) {
                                    TextField(L("Nome ou descrição do exercício"), text: $exercise.name)
                                        .onChange(of: exercise.name) { name in
                                            if let key = exercise.catalogKey, catalog.first(where: { $0.key == key })?.name != name { exercise.catalogKey = nil }
                                        }
                                    if let key = exercise.catalogKey {
                                        NativeExerciseAnimation(catalogKey: key).frame(height: 100)
                                    } else { Color.clear.frame(height: 80).overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.secondary.opacity(0.2))) }
                                    Button(L("Escolher do catálogo")) { search = ""; catalogTarget = exercise.id }
                                    Stepper(exercise.sets == 0 ? L("Séries não informadas · defina") : L("\(exercise.sets) séries"), value: $exercise.sets, in: (exercise.sets == 0 ? 0 : 1)...10)
                                    TextField(L("Repetições"), text: $exercise.reps)
                                    TextField(L("Carga (opcional)"), text: $exercise.weight)
                                    Stepper(L("\(exercise.restSeconds) s descanso"), value: $exercise.restSeconds, in: 0...600, step: 15)
                                        .onChange(of: exercise.restSeconds) { _ in importedMissingRest.remove(exercise.id) }
                                    if importedMissingRest.contains(exercise.id) {
                                        Text(L("Descanso não informado: ajuste acima ou confirme sem descanso.")).font(.caption).foregroundColor(.orange)
                                        Button(L("Confirmar sem descanso")) { exercise.restSeconds = 0; importedMissingRest.remove(exercise.id) }
                                    }
                                    Button(L("Remover exercício"), role: .destructive) { day.exercises.removeAll { $0.id == exercise.id } }
                                }.padding(.vertical, 8)
                            }
                            Button(L("Adicionar exercício")) { day.exercises.append(ManualPlanExercise()) }
                            Button(L("Remover dia"), role: .destructive) { days.removeAll { $0.id == day.id } }
                        }
                    }
                    Button(L("Adicionar dia")) { var day = ManualPlanDay(); day.title = L("Treino \(days.count + 1)"); days.append(day) }.disabled(days.count >= 7)
                } else {
                    ForEach($meals) { $meal in
                        Section(L("Refeição")) {
                            Picker(L("Variação"), selection: $meal.dayOfWeek) { ForEach(["Dia 1", "Dia 2", "Dia 3"], id: \.self) { Text($0) } }
                            Picker(L("Refeição"), selection: $meal.mealType) { ForEach(["Café da manhã", "Lanche da manhã", "Almoço", "Lanche da tarde", "Jantar", "Ceia"], id: \.self) { Text($0) } }
                            TextField(L("Alimentos e quantidades"), text: $meal.description)
                            TextField(L("Calorias (kcal)"), value: $meal.calories, format: .number).keyboardType(.decimalPad)
                            TextField(L("Proteínas (g)"), value: $meal.protein, format: .number).keyboardType(.decimalPad)
                            TextField(L("Carboidratos (g)"), value: $meal.carbs, format: .number).keyboardType(.decimalPad)
                            TextField(L("Gorduras (g)"), value: $meal.fat, format: .number).keyboardType(.decimalPad)
                            Button(L("Remover refeição"), role: .destructive) { meals.removeAll { $0.id == meal.id } }
                        }
                    }
                    Button(L("Adicionar refeição")) { meals.append(ManualPlanMeal()) }
                }
                Section {
                    if imported != nil { Toggle(L("Conferi o texto original e revisei todos os exercícios"), isOn: $importReviewed) }
                    if let error { NativeRecoveryCard(title: L("Suas escolhas continuam aqui"), message: error) }
                    if busy { ProgressView() }
                    Button(imported == nil ? L("Salvar e revisar plano") : L("Salvar plano revisado")) { Task { await save() } }.disabled(busy || !valid)
                }
            }.navigationTitle(imported == nil ? L("Adicionar meu plano") : L("Revisar importação"))
                .onReceive(NotificationCenter.default.publisher(for: Notification.Name("fitTrackerNavigate"))) { _ in dismiss() }
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { dismiss() }.disabled(busy) } }
                .task { if kind == .workout { await loadCatalog() } }
                .sheet(isPresented: Binding(get: { catalogTarget != nil }, set: { if !$0 { catalogTarget = nil } })) {
                    NavigationView {
                        List {
                            if catalogLoading { ProgressView(L("Carregando catálogo…")) }
                            if let catalogError {
                                NativeRecoveryCard(title: L("Você pode seguir com seu plano"), message: catalogError, actionTitle: L("Tentar carregar catálogo")) { Task { await loadCatalog() } }
                            }
                            let filtered = catalog.filter { search.isEmpty || $0.name.localizedStandardContains(search) }
                            if filtered.isEmpty && !catalogLoading && catalogError == nil {
                                NativeRecoveryCard(title: search.isEmpty ? L("Seu exercício também pode ser descrito") : L("Vamos tentar outro nome?"), message: search.isEmpty ? L("O catálogo está vazio agora. Volte ao plano e escreva o nome do seu exercício.") : L("Nenhum exercício corresponde à busca. Tente um nome mais curto."), systemImage: "magnifyingglass", actionTitle: search.isEmpty ? L("Voltar ao plano") : L("Limpar busca")) { if search.isEmpty { catalogTarget = nil } else { search = "" } }
                            }
                            ForEach(filtered) { item in
                                Button(item.name) {
                                    for d in days.indices { if let e = days[d].exercises.firstIndex(where: { $0.id == catalogTarget }) { days[d].exercises[e].name = item.name; days[d].exercises[e].catalogKey = item.key } }
                                    catalogTarget = nil
                                }
                            }
                        }.searchable(text: $search).navigationTitle(L("Catálogo"))
                            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { catalogTarget = nil } } }
                    }.navigationViewStyle(.stack)
                }
                .sheet(item: $saved, onDismiss: { dismiss() }) { NativePlanDetailView(kind: kind, initialPlan: $0) }
        }.navigationViewStyle(.stack)
    }
    private func loadCatalog() async {
        guard !catalogLoading else { return }
        catalogLoading = true; catalogError = nil
        defer { catalogLoading = false }
        do { catalog = try await session.api.getManualExerciseCatalog() }
        catch { if !isNativeRequestCancellation(error) { catalogError = RequestFailure.message(error, fallback: L("Não foi possível carregar o catálogo. Volte ao plano e descreva seus exercícios, ou tente novamente.")) } }
    }
    private func save() async {
        guard valid, !busy else { return }; busy = true; error = nil; defer { busy = false }
        do {
            if kind == .workout { saved = try await session.api.createManualWorkout(title: title, days: days) }
            else { saved = try await session.api.createManualDiet(title: title, meals: meals) }
            NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
        } catch { self.error = RequestFailure.message(error, fallback: L("Não foi possível confirmar esta etapa. Suas escolhas continuam aqui; confira e tente novamente.")) }
    }
}
