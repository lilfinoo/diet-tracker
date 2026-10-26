import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
import FitTrackerCore

struct NativePlansView: View {
    let kind: NativePlanKind
    @Environment(NativeSession.self) var session
    @Environment(\.dismiss) var dismiss
    @State var plans: [NativePlan] = []
    @State var loading = false
    @State var hasMore = true
    @State var error: String?
    @State var generating = false
    @State var creatingManually = false
    @State var importingWorkout = false
    @State var selected: NativePlan?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Sua biblioteca").font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                        Text(kind == .workout ? "Seus planos de treino" : "Seus planos alimentares").font(.title2.bold())
                        Text("O plano atual continua em uso até você revisar e confirmar uma alternativa.")
                            .font(.subheadline).foregroundColor(.secondary)
                    }
                    Button { generating = true } label: {
                        Label("Gerar outro plano", systemImage: "sparkles")
                            .font(.headline).frame(maxWidth: .infinity).padding(16)
                            .background(Color.fitBlue.opacity(0.16), in: RoundedRectangle(cornerRadius: 18))
                    }.buttonStyle(.plain)
                    Button("Montar sem IA") { creatingManually = true }.buttonStyle(.bordered).frame(maxWidth: .infinity)
                    if kind == .workout {
                        Button("Importar treino por texto") { importingWorkout = true }.buttonStyle(.bordered).frame(maxWidth: .infinity)
                    }
                    if let error = error {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(error).foregroundColor(.red)
                            Button("Tentar novamente") { Task { await load(reset: plans.isEmpty) } }
                        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                    }
                    if !plans.isEmpty {
                        Text("Planos salvos").font(.headline).padding(.top, 4)
                        ForEach(plans) { plan in
                            Button { Task { await open(plan) } } label: { planCard(plan) }
                                .buttonStyle(.plain).disabled(loading)
                        }
                    }
                    if plans.isEmpty && !loading { Text("Nenhum plano salvo.").foregroundColor(.secondary).padding(.vertical, 12) }
                    if loading { ProgressView().frame(maxWidth: .infinity).padding() }
                    if hasMore && !plans.isEmpty {
                        Button("Carregar mais") { Task { await load(reset: false) } }.disabled(loading)
                            .frame(maxWidth: .infinity).padding(.vertical, 8)
                    }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(kind.title)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() } } }
            .refreshable { await load(reset: true) }
            .task { await load(reset: true) }
            .sheet(isPresented: $importingWorkout, onDismiss: { Task { await load(reset: true) } }) { NativeWorkoutTextImportView() }
            .sheet(isPresented: $creatingManually, onDismiss: { Task { await load(reset: true) } }) { NativeManualPlanView(kind: kind) }
            .sheet(isPresented: $generating, onDismiss: { Task { await load(reset: true) } }) { PlanGeneratorView(kind: kind) }
            .sheet(item: $selected, onDismiss: { Task { await load(reset: true) } }) { NativePlanDetailView(kind: kind, initialPlan: $0) }
        }
    }
    func planCard(_ plan: NativePlan) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label(plan.isCurrent == true ? "Em uso" : "Plano salvo",
                      systemImage: plan.isCurrent == true ? "checkmark.circle.fill" : "square.stack.3d.up")
                    .font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                Spacer()
                Image(systemName: "arrow.up.right").font(.caption.weight(.semibold)).foregroundColor(.secondary)
            }
            Text(plan.title).font(.headline).foregroundColor(.primary)
            if let description = plan.description { Text(description).font(.subheadline).foregroundColor(.secondary).lineLimit(3) }
            HStack(spacing: 14) {
                if let count = kind == .workout ? plan.daysCount : plan.mealsCount {
                    Label("\(count) \(kind == .workout ? "dias" : "refeições")", systemImage: kind == .workout ? "calendar" : "fork.knife")
                }
                if kind == .workout, let exerciseCount = plan.days?.reduce(0, { $0 + $1.exercises.count }) {
                    Label("\(exerciseCount) exercícios", systemImage: "dumbbell")
                }
            }.font(.caption).foregroundColor(.secondary)
        }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
            .background(plan.isCurrent == true ? Color.fitBlue.opacity(0.13) : Color.fitSurface,
                        in: RoundedRectangle(cornerRadius: 20))
            .overlay(RoundedRectangle(cornerRadius: 20).stroke(plan.isCurrent == true ? Color.fitBlue.opacity(0.35) : Color.white.opacity(0.06), lineWidth: 1))
    }
    func load(reset: Bool) async {
        guard !loading else { return }; loading = true; error = nil
        defer { loading = false }
        do {
            let page = try await session.api.getPlans(kind: kind, offset: reset ? 0 : plans.count)
            plans = reset ? page : plans + page
            hasMore = page.count == 30
        } catch is CancellationError { } catch { self.error = error.localizedDescription }
    }
    func open(_ plan: NativePlan) async {
        guard !loading else { return }; loading = true; error = nil
        defer { loading = false }
        do { selected = try await session.api.getPlan(kind: kind, id: plan.id) }
        catch { self.error = error.localizedDescription }
    }
}

struct NativePlanDetailView: View {
    let kind: NativePlanKind
    @State var plan: NativePlan
    @Environment(NativeSession.self) var session
    @Environment(\.dismiss) var dismiss
    @State var weekdays: Set<Int> = []
    @State var confirming = false
    @State var confirmingDeletion = false
    @State var busy = false
    @State var error: String?
    @State var message: String?
    @State var editingMeal: DietMealAlternative?
    @State var editingExercise: PlanWorkoutExercise?
    @State var selectedDay: PlanWorkoutDay?
    @State var expandedDays: Set<Int> = []
    @State var showingActivationOptions = false
    @State var adjustingWithAI = false
    @State var adjustmentDayId: Int?
    @State var premiumAfterActivation = false

    init(kind: NativePlanKind, initialPlan: NativePlan, generatedPreview: Bool = false) {
        self.kind = kind; _plan = State(initialValue: initialPlan)
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 10) {
                        if plan.isCurrent == true { Label("Plano atual", systemImage: "checkmark.circle.fill").font(.caption.weight(.semibold)).foregroundColor(.fitBlue) }
                        Text(plan.title).font(.title2.bold())
                        if let description = plan.description { Text(description).font(.subheadline).foregroundColor(.secondary) }
                        HStack(spacing: 14) {
                            if kind == .workout, let count = plan.daysCount { Label("\(count) dias/semana", systemImage: "calendar") }
                            if kind == .diet, let count = plan.mealsCount { Label("\(count) refeições", systemImage: "fork.knife") }
                        }.font(.caption).foregroundColor(.secondary)
                    }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 20))
                    if let error = error { Text(error).foregroundColor(.red) }
                    if let message = message { Text(message).foregroundColor(.green) }
                    if kind == .diet {
                        ForEach(plan.meals ?? []) { meal in
                            VStack(alignment: .leading, spacing: 10) {
                                Text(meal.mealType.uppercased()).font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                                Text(meal.description).font(.body)
                                if let kcal = meal.calories { Label("\(Int(kcal)) kcal", systemImage: "flame").font(.caption).foregroundColor(.secondary) }
                                Button("Editar refeição") { editingMeal = meal }.disabled(busy)
                            }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        }
                    }
                    if kind == .workout {
                        Button { adjustmentDayId = nil; if session.hasPremium { adjustingWithAI = true } else { premiumAfterActivation = true } } label: { Label("Ajustar plano com IA", systemImage: "sparkles").frame(maxWidth: .infinity).padding(14) }.buttonStyle(.bordered)
                        Text("Escolha seu treino").font(.headline).padding(.top, 4)
                        Text("Abra um dia para conferir os exercícios e iniciar o treino.").font(.subheadline).foregroundColor(.secondary)
                        ForEach(plan.days ?? []) { day in
                            workoutDayCard(day)
                        }
                    }
                    if plan.isCurrent != true { activationSection }
                    Button(role: .destructive) { confirmingDeletion = true } label: {
                        Label("Excluir plano", systemImage: "trash").frame(maxWidth: .infinity, minHeight: 44)
                    }.disabled(busy)

                }.padding(20)
            }.background(Color.fitBackground.ignoresSafeArea())
                .navigationTitle("Revisar plano")
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() }.disabled(busy) } }
                .confirmationDialog("Usar este plano?", isPresented: $confirming, titleVisibility: .visible) {
                    Button("Confirmar") { Task { await activate() } }
                } message: {
                    Text(kind == .diet
                         ? "Esta será sua dieta atual. Suas refeições já registradas continuam no histórico."
                         : "Este será seu plano de treino atual. Seus treinos já registrados continuam no histórico.")
                }
                .confirmationDialog("Excluir plano?", isPresented: $confirmingDeletion, titleVisibility: .visible) {
                    Button("Excluir plano", role: .destructive) { Task { await delete() } }
                    Button("Cancelar", role: .cancel) { }
                } message: {
                    Text("O plano será removido da sua biblioteca. Seus registros anteriores continuam no histórico.")
                }
                .sheet(isPresented: $premiumAfterActivation) { NavigationStack { NativeSubscriptionView() } }
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
        }
    }
    func workoutDayCard(_ day: PlanWorkoutDay) -> some View {
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
                        Text("\(day.exercises.count) exercícios").font(.caption).foregroundColor(.secondary)
                    }
                    Spacer()
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down").font(.caption.bold()).foregroundColor(.secondary)
                }
            }.buttonStyle(.plain)
            if isExpanded {
                ForEach(day.exercises) { exercise in
                    HStack(alignment: .top, spacing: 12) {
                        Circle().fill(Color.fitBlue.opacity(0.55)).frame(width: 6, height: 6).padding(.top, 6)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(exercise.name).font(.subheadline.weight(.semibold))
                            Text("\(exercise.sets ?? 0) séries · \(exercise.reps ?? "—") repetições · \(exercise.restSeconds ?? 0) s descanso")
                                .font(.caption).foregroundColor(.secondary)
                            Button("Editar exercício") { editingExercise = exercise }.font(.caption).disabled(busy)
                        }
                        Spacer(minLength: 0)
                    }.padding(.vertical, 5)
                }
                Button { adjustmentDayId = day.id; if session.hasPremium { adjustingWithAI = true } else { premiumAfterActivation = true } } label: { Label("Ajustar este treino com IA", systemImage: "sparkles") }.font(.subheadline)
                Button {
                    selectedDay = day
                } label: {
                    Label("Iniciar treino", systemImage: "play.fill").frame(maxWidth: .infinity).padding(13)
                }.buttonStyle(.borderedProminent).disabled(day.exercises.isEmpty)
            }
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
    }
    @ViewBuilder var activationSection: some View {
        if kind == .diet {
            Button("Definir como plano atual") { confirming = true }
                .buttonStyle(.borderedProminent).frame(maxWidth: .infinity).disabled(busy)
        } else if showingActivationOptions {
            VStack(alignment: .leading, spacing: 12) {
                Text("Dias da semana").font(.headline)
                Text("Escolha um dia para cada treino do plano.").font(.subheadline).foregroundColor(.secondary)
                ForEach(0..<7) { index in
                    Toggle(weekdayNames[index], isOn: Binding(get: { weekdays.contains(index) }, set: { if $0 { weekdays.insert(index) } else { weekdays.remove(index) } }))
                }
                Button("Confirmar plano e agenda") { confirming = true }
                    .buttonStyle(.borderedProminent).frame(maxWidth: .infinity)
                    .disabled(busy || weekdays.count != (plan.days?.count ?? 0))
            }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
        } else {
            Button("Usar este plano") { showingActivationOptions = true }
                .buttonStyle(.borderedProminent).frame(maxWidth: .infinity)
        }
        if busy { ProgressView().frame(maxWidth: .infinity) }
    }
    var weekdayNames: [String] { ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"] }
    func delete() async {
        guard !busy, let owner = session.user?.id else { return }
        busy = true; error = nil
        defer { busy = false }
        do {
            _ = try await session.api.deletePlan(kind: kind, id: plan.id)
            guard session.user?.id == owner else { return }
            NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
            dismiss()
        } catch { if !isNativeRequestCancellation(error) { self.error = error.localizedDescription } }
    }

    func activate() async {
        guard !busy else { return }; busy = true; error = nil; message = nil
        defer { busy = false }
        do {
            let response = try await session.api.activatePlan(kind: kind, id: plan.id, weekdays: weekdays.sorted())
            NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
            message = response.message + (response.effectiveFrom.map { " Início: \($0)." } ?? "")
            plan = try await session.api.getPlan(kind: kind, id: plan.id)
            try? await session.refreshFreeAccess()

        } catch { self.error = error.localizedDescription }
    }
    func refresh() async {
        do { plan = try await session.api.getPlan(kind: kind, id: plan.id) }
        catch { self.error = error.localizedDescription }
    }
    func workoutDay(from day: PlanWorkoutDay) -> WorkoutDay {
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
    @Environment(NativeSession.self) var session
    @Environment(\.dismiss) var dismiss
    @State var creatingManually = false
    @State var diet = DietPlanPreferences()
    @State var workout = WorkoutPlanPreferences()
    @State var allergies = ""
    @State var intolerances = ""
    @State var disliked = ""
    @State var preferred = ""
    @State var busy = false
    @State var error: String?
    @State var generated: NativePlan?
    @State var reviewingPlan: NativePlan?
    @State var jobId: UUID?
    @State var monitoringJob: UUID?
    @State var showingGeneration = false
    @State var equipment = "full_gym"
    @State var step = 0
    @State var routine = ""
    @State var prepStyle = "mixed"
    @State var showingPremium = false
    @State var requestingConsent = false
    @State var consentVersion: String?
    @State var generationStarted: Date?
    @State var takingLonger = false
    @State var generationKey = UUID().uuidString
    @Bindable var backgroundPlans = NativePlanBackground.shared

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                HStack {
                    if step > 0 && jobId == nil && generated == nil && !showingGeneration {
                        Button { step -= 1 } label: { Image(systemName: "chevron.left") }
                    }
                    Spacer()
                    Text(firstPlan ? (kind == .diet ? "Sua primeira dieta" : "Seu primeiro treino") : (kind == .diet ? "Nova dieta" : "Novo treino")).font(.headline)
                    Spacer()
                    Button("Fechar") { dismiss() }.disabled(busy)
                }.padding(.horizontal, 20).padding(.vertical, 14)
                if generated == nil && jobId == nil && !showingGeneration {
                    ProgressView(value: Double(min(step + 1, totalSteps)), total: Double(totalSteps)).tint(.fitBlue).padding(.horizontal, 20)
                }
                if showingGeneration {
                    generationScreen
                } else {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 18) {
                            if generated == nil && jobId == nil { Button("Prefiro montar sem IA") { creatingManually = true }.buttonStyle(.bordered) }
                            if let error { Text(error).font(.footnote).foregroundColor(.red) }
                            if let generated {
                                Text("Plano pronto para revisar").font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                                Text("Confira antes de trocar o plano atual.").font(.title2.bold())
                                Button("Ver meu plano") { reviewingPlan = generated }.buttonStyle(.borderedProminent)
                            } else if jobId != nil {
                                Text("Seu plano está sendo preparado.").font(.title2.bold())
                                Text("Seu pedido está guardado. Retome para conferir o resultado, sem gerar outro plano.").foregroundColor(.secondary)
                            } else if step == totalSteps {
                                review
                            } else {
                                question
                            }
                        }.padding(20)
                    }
                    if generated == nil {
                        Button(jobId != nil ? "Retomar meu plano" : step == totalSteps ? (firstPlan ? "Gerar meu plano" : "Gerar alternativa") : "Continuar") {
                            if jobId != nil || step == totalSteps { Task { await generate() } } else { step += 1 }
                        }
                        .buttonStyle(.borderedProminent).frame(maxWidth: .infinity).padding(.horizontal, 20).padding(.bottom, 18)
                        .disabled(busy || (step < totalSteps && jobId == nil && !canContinue))
                    }
                }
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationBarHidden(true)
                .onAppear {
                    if let owner = session.user?.id, let key = backgroundPlans.requestKey(owner: owner, kind: kind) { generationKey = key }
                    if jobId == nil, generated == nil, let key = pendingJobKey,
                       let saved = UserDefaults.standard.string(forKey: key), let id = UUID(uuidString: saved) {
                        jobId = id
                        showingGeneration = true
                        monitoringJob = id
                    }
                    guard step == 0, let goal = session.profile?.profile?.goal else { return }
                    let normalized = goal.lowercased()
                    diet.goal = normalized.contains("ganhar") ? "muscle_gain" : normalized.contains("perder") ? "fat_loss" : normalized.contains("saude") || normalized.contains("saúde") ? "general_health" : "maintenance"
                    workout.goal = normalized.contains("perder") ? "fat_loss" : normalized.contains("ganhar") ? "hypertrophy" : "conditioning"
                    if firstPlan { step = 1 }
                }
                .task(id: monitoringJob) {
                    if let id = monitoringJob { await monitorGeneration(id: id) }
                }
                .onDisappear { monitoringJob = nil }
                .onChange(of: backgroundPlans.completed.keys.sorted { $0.uuidString < $1.uuidString }) { _ in
                    let results = backgroundPlans.completed
                    if let id = jobId, let plan = results[id] { receiveGeneratedPlan(plan) }
                }
                .onChange(of: backgroundPlans.failures.keys.sorted { $0.uuidString < $1.uuidString }) { _ in
                    let failures = backgroundPlans.failures
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
                .sheet(isPresented: $showingPremium) { NavigationStack { NativeSubscriptionView() } }
                .sheet(isPresented: $creatingManually) { NativeManualPlanView(kind: kind) }
                .sheet(isPresented: $requestingConsent) { consentSheet }
        }.interactiveDismissDisabled(busy)
    }
    var totalSteps: Int { kind == .diet ? 8 : 6 }
    var canContinue: Bool {
        if kind == .diet {
            switch step { case 0: return !diet.goal.isEmpty; case 1: return !diet.dietPattern.isEmpty; case 2: return (1...7).contains(diet.mealsPerDay); default: return true }
        }
        switch step {
        case 0: return !workout.goal.isEmpty
        case 1: return !workout.experienceLevel.isEmpty
        case 2: return (1...7).contains(workout.daysPerWeek)
        case 3: return [20, 30, 45, 60, 75, 90].contains(workout.sessionDuration)
        default: return true
        }
    }
    @ViewBuilder var question: some View {
        if kind == .diet { dietQuestion } else { workoutQuestion }
    }
    @ViewBuilder var dietQuestion: some View {
        switch step {
        case 0: choiceQuestion("Qual é seu objetivo?", options: [("Manter peso","maintenance"),("Perder gordura","fat_loss"),("Ganhar massa","muscle_gain"),("Saúde geral","general_health")], selection: $diet.goal)
        case 1: choiceQuestion("Como você se alimenta?", options: [("Onívora","omnivore"),("Vegetariana","vegetarian"),("Vegana","vegan"),("Pescetariana","pescatarian")], selection: $diet.dietPattern)
        case 2: mealsPerDayQuestion
        case 3:
            Text("Como é o seu dia?").font(.title2.bold())
            Text("Informe os horários para encaixar a dieta na sua rotina.").foregroundColor(.secondary)
            Stepper("\(diet.trainingDaysPerWeek) dias de treino", value: $diet.trainingDaysPerWeek, in: 0...7)
            TextEditor(text: $routine).frame(minHeight: 110).padding(8).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14)).overlay(alignment: .topLeading) { if routine.isEmpty { Text("Ex.: acordo às 6h, almoço às 12h, treino às 19h e durmo às 23h.").foregroundColor(.secondary).padding(16).allowsHitTesting(false) } }
        case 4: choiceQuestion("Qual orçamento combina com você?", options: [("Econômico","economical"),("Moderado","moderate"),("Flexível","flexible")], selection: $diet.budget)
        case 5: choiceQuestion("Como prefere suas refeições?", options: [("Práticas e rápidas","quick"),("Um pouco de cada","mixed"),("Mais elaboradas","elaborate")], selection: $prepStyle)
        case 6:
            Text("O que sua dieta precisa respeitar?").font(.title2.bold())
            Text("Conte o que não pode entrar e o que você gosta de comer. Todos os campos são opcionais.")
                .font(.subheadline).foregroundColor(.secondary)
            dietPreferenceField("Alergias", example: "Ex.: amendoim, frutos do mar", text: $allergies)
            dietPreferenceField("Intolerâncias", example: "Ex.: lactose", text: $intolerances)
            if session.hasPremium {
            dietPreferenceField("Alimentos a evitar", example: "Ex.: fígado, berinjela", text: $disliked)
            dietPreferenceField("Alimentos que você gosta", example: "Ex.: arroz, ovos, banana", text: $preferred)
            } else { Button("Preferências alimentares · Premium") { showingPremium = true } }
            Text("Separe os alimentos por vírgula. Seus favoritos serão considerados junto com suas restrições.")
                .font(.caption).foregroundColor(.secondary)
        default:
            Text("Como quer avançar até seu objetivo?").font(.title2.bold())
            Text(diet.goal == "maintenance" || diet.goal == "general_health"
                 ? "Para manter o peso ou cuidar da saúde, as duas opções mantêm a mesma meta de calorias."
                 : "Essa escolha define o ajuste de calorias do plano, sem prometer um prazo para o resultado.")
                .font(.subheadline).foregroundColor(.secondary)
            ForEach([("Gradualmente", "Ajuste menor nas calorias para avançar aos poucos.", "conservative"),
                     ("Um pouco mais rápido", "Ajuste um pouco maior nas calorias para avançar mais rápido.", "moderate")], id: \.2) { option in
                Button { diet.changePace = option.2 } label: {
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(option.0).font(.headline)
                            Text(option.1).font(.subheadline).foregroundColor(.secondary)
                        }
                        Spacer(minLength: 0)
                        Image(systemName: diet.changePace == option.2 ? "checkmark.circle.fill" : "circle")
                            .foregroundColor(diet.changePace == option.2 ? .fitBlue : .secondary)
                    }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                        .background(diet.changePace == option.2 ? Color.fitBlue.opacity(0.2) : Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                }.buttonStyle(.plain)
            }
            TextField("Observações", text: $diet.notes).textFieldStyle(.roundedBorder)
        }
    }
    @ViewBuilder var workoutQuestion: some View {
        switch step {
        case 0: choiceQuestion("O que você quer conquistar?", options: [("Hipertrofia","hypertrophy"),("Força","strength"),("Condicionamento","conditioning"),("Perder gordura","fat_loss"),("Mobilidade","mobility")], selection: $workout.goal)
        case 1: choiceQuestion("Qual sua experiência?", options: [("Iniciante","beginner"),("Intermediário","intermediate"),("Avançado","advanced")], selection: $workout.experienceLevel)
        case 2: numberQuestion("Quantos dias por semana?", value: $workout.daysPerWeek, range: 1...7, suffix: "dias")
        case 3: numberQuestion("Quanto tempo por treino?", value: $workout.sessionDuration, values: [20,30,45,60,75,90], suffix: "minutos")
        case 4: choiceQuestion("Onde você treina?", options: [("Academia completa","full_gym"),("Halteres","dumbbell"),("Peso corporal","bodyweight")], selection: $equipment)
        default:
            Text("O que precisamos respeitar?").font(.title2.bold())
            TextField("Limitações", text: $workout.limitations).textFieldStyle(.roundedBorder)
            if session.hasPremium {
            TextField("Prioridades", text: $workout.priorities).textFieldStyle(.roundedBorder)
            TextField("Exercícios a evitar", text: $workout.avoidExercises).textFieldStyle(.roundedBorder)
            } else { Button("Regiões prioritárias e exercícios a evitar · Premium") { showingPremium = true } }
        }
    }
    var review: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Vamos revisar?").font(.title2.bold())
            Text("Confira suas escolhas antes de gerar.").foregroundColor(.secondary)
            if kind == .diet {
                reviewRow("Objetivo", display(diet.goal, values: ["maintenance": "Manter peso", "fat_loss": "Perder gordura", "muscle_gain": "Ganhar massa", "general_health": "Saúde geral"]))
                reviewRow("Alimentação", display(diet.dietPattern, values: ["omnivore": "Onívora", "vegetarian": "Vegetariana", "vegan": "Vegana", "pescatarian": "Pescetariana"]))
                reviewRow("Refeições", "\(diet.mealsPerDay) por dia")
                reviewRow("Treinos", "\(diet.trainingDaysPerWeek) dias por semana")
                reviewRow("Rotina", routine.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Não informada" : routine)
                reviewRow("Orçamento", display(diet.budget, values: ["economical": "Econômico", "moderate": "Moderado", "flexible": "Flexível"]))
                reviewRow("Preparo", prepStyleLabel)
                reviewRow("Avanço até o objetivo", display(diet.changePace, values: ["conservative": "Gradualmente", "moderate": "Um pouco mais rápido"]))
                reviewRow("Alergias", listText(allergies))
                reviewRow("Intolerâncias", listText(intolerances))
                reviewRow("A evitar", listText(disliked))
                reviewRow("Favoritos", preferred.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Não informados" : preferred)
                reviewRow("Observações", diet.notes.isEmpty ? "Nenhuma" : diet.notes)
            } else {
                reviewRow("Objetivo", display(workout.goal, values: ["hypertrophy": "Hipertrofia", "strength": "Força", "conditioning": "Condicionamento", "fat_loss": "Perder gordura", "mobility": "Mobilidade"]))
                reviewRow("Experiência", display(workout.experienceLevel, values: ["beginner": "Iniciante", "intermediate": "Intermediário", "advanced": "Avançado"]))
                reviewRow("Frequência", "\(workout.daysPerWeek) dias")
                reviewRow("Duração", "\(workout.sessionDuration) minutos")
                reviewRow("Equipamentos", display(equipment, values: ["full_gym": "Academia completa", "dumbbell": "Halteres", "bodyweight": "Peso corporal"]))
                reviewRow("Limitações", workout.limitations.isEmpty ? "Nenhuma" : workout.limitations)
                reviewRow("Prioridades", workout.priorities.isEmpty ? "Nenhuma" : workout.priorities)
                reviewRow("Exercícios a evitar", workout.avoidExercises.isEmpty ? "Nenhum" : workout.avoidExercises)
            }
            Text("O plano atual só muda depois que você revisar e confirmar a alternativa.").font(.footnote).foregroundColor(.secondary).padding(.top, 10)
        }
    }
    func reviewRow(_ title: String, _ value: String) -> some View { HStack { Text(title).foregroundColor(.secondary); Spacer(); Text(value).multilineTextAlignment(.trailing).lineLimit(2) }.padding(.vertical, 8) }
    var prepStyleLabel: String { prepStyle == "quick" ? "Práticas e rápidas" : prepStyle == "elaborate" ? "Mais elaboradas" : "Um pouco de cada" }
    func display(_ value: String, values: [String: String]) -> String { values[value] ?? value }
    func listText(_ value: String) -> String { value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Nenhuma" : value }
    func choiceQuestion(_ title: String, options: [(String,String)], selection: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 14) { Text(title).font(.title2.bold()); ForEach(options, id: \.1) { option in Button { selection.wrappedValue = option.1 } label: { HStack { Text(option.0); Spacer(); if selection.wrappedValue == option.1 { Image(systemName: "checkmark.circle.fill").foregroundColor(.fitBlue) } else { Image(systemName: "circle").foregroundColor(.secondary) } }.padding(16).frame(maxWidth: .infinity, alignment: .leading).background(selection.wrappedValue == option.1 ? Color.fitBlue.opacity(0.2) : Color.fitSurface, in: RoundedRectangle(cornerRadius: 16)) }.buttonStyle(.plain) } }
    }
    func numberQuestion(_ title: String, value: Binding<Int>, range: ClosedRange<Int>, suffix: String) -> some View { VStack(alignment: .leading, spacing: 14) { Text(title).font(.title2.bold()); Stepper("\(value.wrappedValue) \(suffix)", value: value, in: range).padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16)) } }
    var mealsPerDayQuestion: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Quantas refeições por dia?").font(.title2.bold())
            Text("Escolha a quantidade que combina com sua rotina.").font(.subheadline).foregroundColor(.secondary)
            VStack(spacing: 16) {
                Button { diet.mealsPerDay += 1 } label: {
                    Image(systemName: "plus").font(.title2.bold()).frame(width: 100, height: 64)
                }
                .buttonStyle(.plain).foregroundColor(.white)
                .background(Color.fitBlue, in: RoundedRectangle(cornerRadius: 20))
                .disabled(diet.mealsPerDay >= 7).opacity(diet.mealsPerDay >= 7 ? 0.35 : 1)
                .accessibilityLabel("Adicionar uma refeição")
                VStack(spacing: 2) {
                    Text("\(diet.mealsPerDay)").font(.system(size: 88, weight: .bold, design: .monospaced)).accessibilityHidden(true)
                    Text(diet.mealsPerDay == 1 ? "refeição por dia" : "refeições por dia").font(.headline).foregroundColor(.secondary).accessibilityHidden(true)
                }
                .accessibilityLabel(Text("\(diet.mealsPerDay) \(diet.mealsPerDay == 1 ? "refeição por dia" : "refeições por dia")"))
                Button { diet.mealsPerDay -= 1 } label: {
                    Image(systemName: "minus").font(.title2.bold()).frame(width: 100, height: 64)
                }
                .buttonStyle(.plain).foregroundColor(.fitBlue)
                .background(Color.fitBlue.opacity(0.16), in: RoundedRectangle(cornerRadius: 20))
                .disabled(diet.mealsPerDay <= 1).opacity(diet.mealsPerDay <= 1 ? 0.35 : 1)
                .accessibilityLabel("Remover uma refeição")
            }.frame(maxWidth: .infinity).padding(.vertical, 24)
            Text("De 1 a 7 refeições, distribuídas conforme os horários que você informar.")
                .font(.footnote).foregroundColor(.secondary)
        }
    }
    func dietPreferenceField(_ title: String, example: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.subheadline.weight(.semibold))
            TextField("", text: text, prompt: Text(example).foregroundColor(.white.opacity(0.6)))
                .textFieldStyle(.plain).foregroundColor(.white)
                .padding(14)
                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.white.opacity(0.16), lineWidth: 1))
                .accessibilityLabel(Text(title))
        }
    }
    func numberQuestion(_ title: String, value: Binding<Int>, values: [Int], suffix: String) -> some View { VStack(alignment: .leading, spacing: 14) { Text(title).font(.title2.bold()); LazyVGrid(columns: [GridItem(.adaptive(minimum: 70))], spacing: 10) { ForEach(values, id: \.self) { item in Button("\(item)") { value.wrappedValue = item }.frame(maxWidth: .infinity).padding(14).background(value.wrappedValue == item ? Color.fitBlue.opacity(0.25) : Color.fitSurface, in: RoundedRectangle(cornerRadius: 12)) } }; Text(suffix).font(.footnote).foregroundColor(.secondary) } }
    func picker(_ title: String, value: Binding<String>, options: [(String,String)]) -> some View {
        Picker(title, selection: value) { ForEach(options, id: \.0) { Text($0.1).tag($0.0) } }
    }
    var pendingJobKey: String? {
        guard let account = session.user?.id else { return nil }
        return "fitTracker.pendingPlan.\(account.uuidString).\(kind == .diet ? "diet" : "workout")"
    }
    func storeJob(_ id: UUID?) {
        jobId = id
        guard let key = pendingJobKey else { return }
        if let id {
            UserDefaults.standard.set(id.uuidString, forKey: key)
            backgroundPlans.track(id: id, kind: kind, owner: session.user?.id, api: session.api)
        }
        else { UserDefaults.standard.removeObject(forKey: key) }
    }
    func leaveGeneration() {
        monitoringJob = nil
        showingGeneration = false
    }
    func receiveGeneratedPlan(_ plan: NativePlan) {
        storeJob(nil)
        monitoringJob = nil
        generated = plan
        showingGeneration = false
        reviewingPlan = plan
    }
    func generate() async {
        guard !busy else { return }
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
                requestingConsent = true
                return
            }
            var preferences = diet
            preferences.allergies = split(allergies); preferences.intolerances = split(intolerances); preferences.dislikedFoods = split(disliked); preferences.preferredFoods = split(preferred)
            preferences.prepMinutes = prepStyle == "quick" ? 15 : prepStyle == "elaborate" ? 60 : 30
            if !routine.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                preferences.notes = "Rotina e horários: \(routine)\(diet.notes.isEmpty ? "" : " · \(diet.notes)")"
            }
            if !session.hasPremium { preferences.dislikedFoods = []; preferences.preferredFoods = [] }
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
                } else { self.error = error.localizedDescription }
            } else { self.error = error.localizedDescription }
        }
    }
    func monitorGeneration(id: UUID) async {
        backgroundPlans.track(id: id, kind: kind, owner: session.user?.id, api: session.api)
    }
    var generationScreen: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 0) {
                    Spacer(minLength: 28)
                    if error == nil {
                        NativePlanPreparationAnimation(kind: kind)
                            .frame(width: 260, height: 260)
                        Text(takingLonger ? "Está demorando mais que o esperado." : kind == .diet ? "Preparando sua dieta." : "Montando seu treino.")
                            .font(.system(size: 29, weight: .bold)).multilineTextAlignment(.center).padding(.top, 20)
                        Text(takingLonger && jobId != nil
                             ? "Seu pedido está salvo e continua sendo preparado. Você pode sair desta tela e conferir o plano quando estiver pronto."
                             : kind == .diet
                             ? "Combinando seus gostos, sua rotina e seu objetivo em um plano feito para você."
                             : "Organizando os exercícios para seu objetivo, seu nível e os dias que você tem disponíveis.")
                            .font(.subheadline).foregroundColor(.secondary).multilineTextAlignment(.center)
                            .padding(.top, 14).frame(maxWidth: 300)
                        HStack(spacing: 9) {
                            ProgressView().scaleEffect(0.75).tint(Color(red: 0.31, green: 0.86, blue: 0.75)).accessibilityHidden(true)
                            Text("Seu plano está ganhando forma").font(.caption).foregroundColor(.secondary).accessibilityHidden(true)
                        }.padding(.top, 28).accessibilityLabel(Text("Seu plano está ganhando forma"))
                    } else {
                        Image(systemName: "exclamationmark.circle").font(.system(size: 54, weight: .light))
                            .foregroundColor(.orange).padding(.bottom, 28)
                        Text("Vamos tentar de novo?").font(.title2.bold()).multilineTextAlignment(.center)
                        Text(error ?? "").font(.subheadline).foregroundColor(.secondary)
                            .multilineTextAlignment(.center).padding(.top, 14)
                        if jobId != nil {
                            Button("Retomar meu plano") { error = nil; monitoringJob = jobId }
                                .buttonStyle(.borderedProminent).padding(.top, 24)
                        }
                    }
                    Spacer(minLength: 32)
                    Text(takingLonger && jobId != nil && backgroundPlans.notificationsAvailable
                         ? "Avisaremos quando seu plano estiver pronto. Você pode continuar usando o app."
                         : jobId != nil
                         ? "Você pode voltar às suas escolhas. Seu plano continua sendo preparado."
                         : "Você poderá conferir tudo antes de usar o plano.")
                        .font(.caption).foregroundColor(.secondary).multilineTextAlignment(.center)
                        .frame(maxWidth: 270).padding(.bottom, 16)
                    Button("Voltar às escolhas") { leaveGeneration() }
                        .font(.subheadline).disabled(busy).padding(.bottom, 24)
                    if takingLonger, jobId != nil {
                        Button("Continuar usando o app") { dismiss() }
                            .buttonStyle(.borderedProminent).padding(.bottom, 24)
                    }
                }.padding(.horizontal, 24).frame(maxWidth: .infinity)
                    .frame(minHeight: geometry.size.height)
            }
        }
    }
    var consentSheet: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text("Um plano personalizado com IA").font(.title2.bold())
                    Text("Para gerar seu plano, precisamos da sua autorização para enviar ao Google Gemini e, se ele falhar, à OpenAI os dados de perfil, alimentação e treino necessários. Você pode revogar essa autorização no Perfil.")
                    Button("Autorizar e gerar meu plano") {
                        guard let version = consentVersion else { return }
                        requestingConsent = false
                        Task {
                            do { _ = try await session.api.updateConsent(granted: true, version: version); await generate() }
                            catch { self.error = error.localizedDescription }
                        }
                    }.buttonStyle(.borderedProminent)
                    Button("Agora não") { requestingConsent = false }
                }.padding(24)
            }.background(Color.fitBackground.ignoresSafeArea()).navigationTitle("Autorização de IA")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { requestingConsent = false } } }
        }
    }
    func split(_ text: String) -> [String] { text.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty } }
}

struct NativePlanPreparationAnimation: View {
    let kind: NativePlanKind
    @Environment(\.accessibilityReduceMotion) var reduceMotion
    @State var floating = false
    let mint = Color(red: 0.31, green: 0.86, blue: 0.75)

    var body: some View {
        ZStack {
            Circle().fill(RadialGradient(colors: [mint.opacity(0.16), .clear],
                                        center: .center, startRadius: 20, endRadius: 130))
            Circle().stroke(mint.opacity(0.15), lineWidth: 1).padding(32)
            Image(systemName: kind == .diet ? "fork.knife" : "dumbbell.fill")
                .font(.system(size: 80, weight: .light)).foregroundColor(mint)
                .shadow(color: mint.opacity(0.2), radius: 20)
                .offset(y: floating && !reduceMotion ? -7 : 7)
                .rotationEffect(.degrees(kind == .workout && floating && !reduceMotion ? -5 : 0))
        }
        .animation(reduceMotion ? nil : .easeInOut(duration: 1.8).repeatForever(autoreverses: true), value: floating)
        .onAppear { floating = !reduceMotion }
        .onChange(of: reduceMotion) { value in floating = !value }
        .accessibilityHidden(true)
    }
}

struct PlanMealEditor: View {
    let planId: Int
    let meal: DietMealAlternative
    let onSaved: () -> Void
    @Environment(NativeSession.self) var session
    @Environment(\.dismiss) var dismiss
    @State var description = ""
    @State var calories = ""
    @State var protein = ""
    @State var carbs = ""
    @State var fat = ""
    @State var busy = false
    @State var error: String?
    var body: some View {
        NavigationStack {
            Form {
                Section(meal.mealType) { TextEditor(text: $description).frame(minHeight: 130) }
                Section("Valores nutricionais") {
                    TextField("Calorias (kcal)", text: $calories).keyboardType(.decimalPad)
                    TextField("Proteínas (g)", text: $protein).keyboardType(.decimalPad)
                    TextField("Carboidratos (g)", text: $carbs).keyboardType(.decimalPad)
                    TextField("Gorduras (g)", text: $fat).keyboardType(.decimalPad)
                    Text("Campos vazios preservam o valor anterior.").font(.footnote).foregroundColor(.secondary)
                }
                Section {
                    Text("Ao alterar os alimentos, os valores nutricionais do plano precisam ser revistos.").font(.footnote).foregroundColor(.secondary)
                    if let error = error { Text(error).foregroundColor(.red) }
                    Button("Salvar refeição") { Task { await save() } }.disabled(busy || description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    if busy { ProgressView() }
                }
            }.navigationTitle("Editar refeição")
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancelar") { dismiss() }.disabled(busy) } }
                .onAppear {
                    description = meal.description
                    calories = meal.calories.map(String.init(describing:)) ?? ""
                    protein = meal.protein.map(String.init(describing:)) ?? ""
                    carbs = meal.carbs.map(String.init(describing:)) ?? ""
                    fat = meal.fat.map(String.init(describing:)) ?? ""
                }
        }
    }
    func save() async {
        guard !busy else { return }; busy = true; error = nil
        defer { busy = false }
        do {
            let values = try [calories, protein, carbs, fat].enumerated().map { index, text -> Double? in
                let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
                if cleaned.isEmpty { return nil }
                guard let value = Double(cleaned.replacingOccurrences(of: ",", with: ".")), value.isFinite, value >= 0, value <= (index == 0 ? 20000 : 5000) else {
                    throw APIError.http(status: 400, message: "Revise os valores nutricionais.")
                }
                return value
            }
            try await session.api.editDietPlanMeal(planId: planId, mealId: meal.id, description: description, calories: values[0], protein: values[1], carbs: values[2], fat: values[3])
            onSaved(); dismiss()
        }
        catch { self.error = error.localizedDescription }
    }
}


struct PlanExerciseEditor: View {
    let planId: Int
    let exercise: PlanWorkoutExercise
    let onSaved: (NativePlan) -> Void
    @Environment(NativeSession.self) var session
    @Environment(\.dismiss) var dismiss
    @State var sets = 3
    @State var reps = ""
    @State var weight = ""
    @State var rest = 60
    @State var busy = false
    @State var error: String?
    @State var method = "similar"
    @State var search = ""
    @State var options: [WorkoutReplacementOption] = []
    @State var catalog: [PlanCatalogItem] = []
    @State var selectedKey: String?
    @State var selectedName: String?
    @State var customName = ""
    @State var confirming = false
    var compatibleCatalog: [PlanCatalogItem] {
        let group = catalog.first { $0.key == exercise.catalogKey }?.group ?? catalog.first { item in options.contains(where: { $0.catalogKey == item.key }) }?.group
        return catalog.filter { item in
            (group.map { item.group == $0 } ?? options.contains(where: { $0.catalogKey == item.key })) && (search.isEmpty || item.name.localizedStandardContains(search))
        }
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text(exercise.name).font(.title2.bold())
                    if exercise.catalogKey?.hasPrefix("custom:") == true { TextField("Nome do exercício", text: $customName) }
                    Text("A edição vale para os próximos treinos. Seu histórico é preservado.").font(.subheadline).foregroundColor(.secondary)
                    Picker("Como editar", selection: $method) { Text("Semelhantes").tag("similar"); Text("Catálogo").tag("catalog"); Text("Prescrição").tag("prescription") }.pickerStyle(.segmented)
                    if method == "catalog" { TextField("Pesquisar exercício", text: $search).padding(12).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 12)); Text("Exercícios compatíveis com o padrão de movimento do plano.").font(.caption).foregroundColor(.secondary) }
                    if method == "similar" {
                        ForEach(options) { option in choice(key: option.catalogKey, name: option.name) }
                        if options.isEmpty && !busy { Text("Nenhuma alternativa disponível. Confira o catálogo.").foregroundColor(.secondary) }
                    } else if method == "catalog" {
                        LazyVStack(spacing: 12) { ForEach(compatibleCatalog) { item in choice(key: item.key, name: item.name) } }
                    }
                    VStack(alignment: .leading, spacing: 14) {
                        Text("Prescrição").font(.headline)
                        Stepper("\(sets) séries", value: $sets, in: 1...10)
                        TextField("Repetições", text: $reps)
                        TextField("Carga prescrita", text: $weight)
                        Stepper("\(rest) s descanso", value: $rest, in: 0...600, step: 15)
                    }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                    if let error { Text(error).foregroundColor(.red) }
                    if busy { ProgressView().frame(maxWidth: .infinity) }
                    Button("Revisar alteração") { confirming = true }.buttonStyle(.borderedProminent).disabled(busy || reps.isEmpty)
                }.padding(20)
            }.background(Color.fitBackground.ignoresSafeArea()).navigationTitle("Editar exercício").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancelar") { dismiss() }.disabled(busy) } }
                .task { customName = exercise.name; sets = exercise.sets ?? 3; reps = exercise.reps ?? ""; weight = exercise.weight ?? ""; rest = exercise.restSeconds ?? 60; await load() }
                .sheet(isPresented: $confirming) {
                    NavigationStack {
                        VStack(alignment: .leading, spacing: 20) {
                            Text("Antes").foregroundColor(.secondary); Text(exercise.name).font(.headline)
                            Text("\(exercise.sets ?? 3) × \(exercise.reps ?? "—") · \(exercise.restSeconds ?? 60) s descanso").foregroundColor(.secondary)
                            Text(exercise.weight.flatMap { $0.isEmpty ? nil : $0 } ?? "Sem carga prescrita").font(.subheadline).foregroundColor(.secondary)
                            Divider(); Text("Depois").foregroundColor(.fitBlue); Text(selectedName ?? exercise.name).font(.title3.bold())
                            Text("\(sets) × \(reps) · \(rest) s descanso")
                            Text(weight.isEmpty ? "Sem carga prescrita" : "Carga: \(weight)").font(.subheadline)
                            Text("A alteração será salva no plano ao confirmar.").font(.subheadline).foregroundColor(.secondary)
                            if let error { Text(error).foregroundColor(.red) }
                            Button("Confirmar alteração no plano") { Task { await save() } }.buttonStyle(.borderedProminent).disabled(busy)
                            Spacer()
                        }.padding(20).background(Color.fitBackground.ignoresSafeArea()).navigationTitle("Revisar alteração").navigationBarTitleDisplayMode(.inline)
                            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Voltar") { confirming = false }.disabled(busy) } }
                    }
                }
        }
    }
    func choice(key: String, name: String) -> some View {
        Button { selectedKey = key; selectedName = name } label: {
            HStack(spacing: 12) {
                NativeExerciseAnimation(catalogKey: key).frame(width: 90, height: 80).clipShape(RoundedRectangle(cornerRadius: 12))
                Text(name).font(.subheadline.weight(.semibold)).foregroundColor(.primary).frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: selectedKey == key ? "checkmark.circle.fill" : "circle").foregroundColor(.fitBlue)
            }.padding(12).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain).disabled(busy)
    }
    func load() async {
        busy = true; defer { busy = false }
        do {
            async let alternatives = session.api.getPlanReplacementOptions(planId: planId, exerciseId: exercise.id)
            async let items = session.api.getPlanExerciseCatalog(planId: planId)
            (options, catalog) = try await (alternatives.options, items)
        } catch { self.error = error.localizedDescription }
    }
    func save() async {
        guard !busy else { return }; busy = true; error = nil
        defer { busy = false }
        do {
            let updated = try await session.api.editWorkoutPrescription(planId: planId, exerciseId: exercise.id, catalogKey: selectedKey, sets: sets, reps: reps, weight: weight, restSeconds: rest, name: exercise.catalogKey?.hasPrefix("custom:") == true ? customName : nil)
            NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
            onSaved(updated); confirming = false; dismiss()
        } catch { self.error = error.localizedDescription }
    }
}

struct PlanAIEditor: View {
    let plan: NativePlan
    let initialDayId: Int?
    let onSaved: (NativePlan) -> Void
    @Environment(NativeSession.self) var session
    @Environment(\.dismiss) var dismiss
    @State var feedback = ""
    @State var wholePlan = false
    @State var changes: [PlanExerciseChange] = []
    @State var revision = ""
    @State var proposalPlan: NativePlan?
    @State var busy = false
    @State var error: String?
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text(changes.isEmpty ? "O que quer mudar?" : "Confira antes de salvar.").font(.title2.bold())
                    if changes.isEmpty {
                        if initialDayId != nil { Toggle("Ajustar o plano inteiro", isOn: $wholePlan) }
                        Text("Descreva sua preferência ou os equipamentos disponíveis.").foregroundColor(.secondary)
                        TextEditor(text: $feedback).frame(minHeight: 140).padding(10).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                        Text("A IA sugere trocas compatíveis e ajustes de séries e repetições. Você aprova a proposta antes de salvar.").font(.subheadline).foregroundColor(.secondary)
                        Button("Ver proposta de alteração") { Task { await suggest() } }.buttonStyle(.borderedProminent).disabled(busy || feedback.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    } else {
                        ForEach(changes) { change in
                            VStack(alignment: .leading, spacing: 10) {
                                if let before = (proposalPlan ?? plan).days?.flatMap(\.exercises).first(where: { $0.id == change.exerciseId }) {
                                    Text("Antes").font(.caption).foregroundColor(.secondary)
                                    Text(before.name).font(.headline)
                                    Text("\(before.sets ?? 3) × \(before.reps ?? "—") · \(before.restSeconds ?? 60) s").font(.subheadline).foregroundColor(.secondary)
                                    Text(before.weight.flatMap { $0.isEmpty ? nil : $0 } ?? "Sem carga prescrita").font(.subheadline).foregroundColor(.secondary)
                                }
                                Divider(); Text("Depois").font(.caption).foregroundColor(.fitBlue)
                                Text(change.name).font(.headline)
                                Text("\(change.sets) × \(change.reps) · \(change.restSeconds) s")
                                Text(change.weight.flatMap { $0.isEmpty ? nil : $0 } ?? "Sem carga prescrita").font(.subheadline)
                            }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        }
                        Button("Refinar meu pedido") { changes = [] }.disabled(busy)
                        Button("Confirmar alteração no plano") { Task { await apply() } }.buttonStyle(.borderedProminent).disabled(busy)
                    }
                    if busy { ProgressView().frame(maxWidth: .infinity) }
                    if let error { Text(error).foregroundColor(.red) }
                }.padding(20)
            }.background(Color.fitBackground.ignoresSafeArea()).navigationTitle("Ajustar com IA").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() }.disabled(busy) } }
        }
    }
    func suggest() async {
        guard !busy else { return }; busy = true; error = nil; defer { busy = false }
        do { let proposal = try await session.api.suggestPlanChanges(planId: plan.id, feedback: feedback, dayId: wholePlan ? nil : initialDayId); changes = proposal.changes; revision = proposal.revision; proposalPlan = proposal.plan }
        catch { self.error = error.localizedDescription }
    }
    func apply() async {
        guard !busy else { return }; busy = true; error = nil; defer { busy = false }
        do { let updated = try await session.api.applyPlanChanges(planId: plan.id, changes: changes, revision: revision); onSaved(updated); dismiss() }
        catch { self.error = error.localizedDescription }
    }
}

struct NativeManualPlanView: View {
    let kind: NativePlanKind
    let imported: WorkoutTextImport?
    @Environment(NativeSession.self) var session
    @Environment(\.dismiss) var dismiss
    @State var title = ""
    @State var days = [ManualPlanDay()]
    @State var meals = [ManualPlanMeal()]
    @State var catalog: [PlanCatalogItem] = []
    @State var search = ""
    @State var catalogTarget: UUID?
    @State var saved: NativePlan?
    @State var busy = false
    @State var error: String?
    @State var importedMissingRest: Set<UUID> = []
    @State var importReviewed = false

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
            _title = State(initialValue: "Meu treino importado")
            _days = State(initialValue: importedDays)
            _importedMissingRest = State(initialValue: missingRest)
        }
    }

    var valid: Bool {
        (imported == nil || importReviewed) && !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && (kind == .workout
            ? !days.isEmpty && days.allSatisfy { !$0.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !$0.exercises.isEmpty && $0.exercises.allSatisfy { !$0.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !$0.reps.isEmpty && $0.sets > 0 && !importedMissingRest.contains($0.id) } }
            : !meals.isEmpty && meals.allSatisfy { !$0.description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty })
    }
    var body: some View {
        NavigationStack {
            Form {
                if let imported {
                    Section("Confira a importação") {
                        Text("Revise os nomes, séries, repetições, cargas e descansos. Nada foi salvo.")
                        if !imported.warnings.isEmpty {
                            DisclosureGroup("Pontos para conferir") {
                                ForEach(Array(imported.warnings.enumerated()), id: \.offset) { _, warning in Text(warning).font(.caption).foregroundColor(.orange) }
                            }
                        }
                        DisclosureGroup("Texto original completo") { Text(imported.sourceText).font(.caption) }
                    }
                }
                Section("Seu plano") { TextField("Nome do plano", text: $title) }
                if kind == .workout {
                    ForEach($days) { $day in
                        Section {
                            TextField("Nome do dia", text: $day.title)
                            ForEach($day.exercises) { $exercise in
                                VStack(alignment: .leading, spacing: 12) {
                                    TextField("Nome ou descrição do exercício", text: $exercise.name)
                                        .onChange(of: exercise.name) { name in
                                            if let key = exercise.catalogKey, catalog.first(where: { $0.key == key })?.name != name { exercise.catalogKey = nil }
                                        }
                                    if let key = exercise.catalogKey {
                                        NativeExerciseAnimation(catalogKey: key).frame(height: 100)
                                    } else { Color.clear.frame(height: 80).overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.secondary.opacity(0.2))) }
                                    Button("Escolher do catálogo") { search = ""; catalogTarget = exercise.id }
                                    Stepper(exercise.sets == 0 ? "Séries não informadas · defina" : "\(exercise.sets) séries", value: $exercise.sets, in: (exercise.sets == 0 ? 0 : 1)...10)
                                    TextField("Repetições", text: $exercise.reps)
                                    TextField("Carga (opcional)", text: $exercise.weight)
                                    Stepper("\(exercise.restSeconds) s descanso", value: $exercise.restSeconds, in: 0...600, step: 15)
                                        .onChange(of: exercise.restSeconds) { _ in importedMissingRest.remove(exercise.id) }
                                    if importedMissingRest.contains(exercise.id) {
                                        Text("Descanso não informado: ajuste acima ou confirme sem descanso.").font(.caption).foregroundColor(.orange)
                                        Button("Confirmar sem descanso") { exercise.restSeconds = 0; importedMissingRest.remove(exercise.id) }
                                    }
                                    Button("Remover exercício", role: .destructive) { day.exercises.removeAll { $0.id == exercise.id } }
                                }.padding(.vertical, 8)
                            }
                            Button("Adicionar exercício") { day.exercises.append(ManualPlanExercise()) }
                            Button("Remover dia", role: .destructive) { days.removeAll { $0.id == day.id } }
                        }
                    }
                    Button("Adicionar dia") { var day = ManualPlanDay(); day.title = "Treino \(days.count + 1)"; days.append(day) }.disabled(days.count >= 7)
                } else {
                    ForEach($meals) { $meal in
                        Section("Refeição") {
                            Picker("Variação", selection: $meal.dayOfWeek) { ForEach(["Dia 1", "Dia 2", "Dia 3"], id: \.self) { Text($0) } }
                            Picker("Refeição", selection: $meal.mealType) { ForEach(["Café da manhã", "Lanche da manhã", "Almoço", "Lanche da tarde", "Jantar", "Ceia"], id: \.self) { Text($0) } }
                            TextField("Alimentos e quantidades", text: $meal.description)
                            TextField("Calorias (kcal)", value: $meal.calories, format: .number).keyboardType(.decimalPad)
                            TextField("Proteínas (g)", value: $meal.protein, format: .number).keyboardType(.decimalPad)
                            TextField("Carboidratos (g)", value: $meal.carbs, format: .number).keyboardType(.decimalPad)
                            TextField("Gorduras (g)", value: $meal.fat, format: .number).keyboardType(.decimalPad)
                            Button("Remover refeição", role: .destructive) { meals.removeAll { $0.id == meal.id } }
                        }
                    }
                    Button("Adicionar refeição") { meals.append(ManualPlanMeal()) }
                }
                Section {
                    if let error { Text(error).foregroundColor(.red) }
                    if busy { ProgressView() }
                    if imported != nil {
                        Toggle("Conferi os exercícios e os valores importados", isOn: $importReviewed)
                    }
                    Button("Salvar e revisar plano") { Task { await save() } }.disabled(busy || !valid)
                }
            }.navigationTitle("Montar sem IA")
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() }.disabled(busy) } }
                .task { if kind == .workout { do { catalog = try await session.api.getManualExerciseCatalog() } catch { self.error = "Não foi possível carregar o catálogo. Você pode descrever seus exercícios." } } }
                .sheet(isPresented: Binding(get: { catalogTarget != nil }, set: { if !$0 { catalogTarget = nil } })) {
                    NavigationStack {
                        List(catalog.filter { search.isEmpty || $0.name.localizedStandardContains(search) }) { item in
                            Button(item.name) {
                                for d in days.indices { if let e = days[d].exercises.firstIndex(where: { $0.id == catalogTarget }) { days[d].exercises[e].name = item.name; days[d].exercises[e].catalogKey = item.key } }
                                catalogTarget = nil
                            }
                        }.searchable(text: $search).navigationTitle("Catálogo")
                            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { catalogTarget = nil } } }
                    }
                }
                .sheet(item: $saved, onDismiss: { dismiss() }) { NativePlanDetailView(kind: kind, initialPlan: $0) }
        }
    }
    func save() async {
        guard valid, !busy else { return }; busy = true; error = nil; defer { busy = false }
        do {
            if kind == .workout { saved = try await session.api.createManualWorkout(title: title, days: days) }
            else { saved = try await session.api.createManualDiet(title: title, meals: meals) }
            NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
        } catch { self.error = error.localizedDescription }
    }
}
