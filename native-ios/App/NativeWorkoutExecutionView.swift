import SwiftUI
import UIKit
import FitTrackerCore

struct NativeWorkoutExecutionView: View {
    @EnvironmentObject private var account: NativeSession
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let planId: Int
    @State private var day: WorkoutDay
    @State private var firstPlan: NativePlan?
    @State private var showingFirstDay = false
    @State private var ownerId: UUID?
    @State private var execution: WorkoutExecutionSession?
    @State private var local = WorkoutLocalDraft()
    @State private var index = 0
    @State private var loading = false
    @State private var loaded = false
    @State private var localStorageKey: String?
    @State private var sessionConfirmed = false
    @State private var error: String?
    @State private var showingRecorder = false
    @State private var showingAlternatives = false
    @State private var showingWorkoutPremium = false
    @State private var alternatives: [WorkoutReplacementOption] = []
    @State private var finishConfirmation = false
    @State private var finishMinutes = ""
    @State private var longOpenSession = false
    @State private var finishError: String?
    @State private var cancelConfirmation = false
    @State private var summary: WorkoutActivitySummary?
    @State private var syncing = false
    @State private var finishRequested = false
    @State private var alternativesLoading = false
    @State private var alternativesError: String?
    @State private var cancellationNeedsCheck = false
    @State private var sessionEnded = false
    @State private var alternativeCache: [Int: [WorkoutReplacementOption]] = [:]
    @State private var cardOffset: CGFloat = 0
    @State private var cardAnimating = false

    init(planId: Int, day: WorkoutDay) {
        self.planId = planId
        _day = State(initialValue: day)
    }

    private var completedIds: Set<Int> { local.completedIds(onServer: execution?.completedExerciseIds ?? []) }
    private var exercise: WorkoutExercise? { day.exercises.indices.contains(index) ? day.exercises[index] : nil }
    private var pending: Bool { !local.operationQueue.isEmpty }
    private var storageKey: String? {
        guard let ownerId, let execution else { return nil }
        return localStorageKey ?? WorkoutExecutionSyncCoordinator.key(ownerId: ownerId, sessionId: execution.id)
    }
    private var syncMessage: String? {
        guard let storageKey, pending || (execution?.id ?? 0) < 0 else { return nil }
        return WorkoutExecutionSyncCoordinator.shared.failure(for: storageKey)
            ?? L("Treino salvo neste iPhone. Sincronizando seus registros…")
    }

    var body: some View {
        Group {
            executionBody
        }
        .modifier(NativeAchievementPresenter())
    }

    private var executionBody: some View {
        NavigationView {
            VStack(spacing: 0) {
                if loading && loaded && !finishRequested { ProgressView().padding(8) }
                if let error {
                    NativeRecoveryCard(title: pending ? L("Seu treino continua neste iPhone") : L("Vamos conferir sua sessão?"),
                        message: error, systemImage: pending ? "iphone.and.arrow.forward" : "arrow.clockwise",
                        actionTitle: sessionEnded ? L("Voltar aos treinos") : pending ? L("Verificar e sincronizar") : L("Verificar sessão")) {
                            if sessionEnded { dismiss() }
                            else { Task { await reconcileAndRetry() } }
                        }.disabled(loading || syncing).padding(14)
                }
                if let summary {
                    NativeWorkoutCompletionView(summary: summary, onClose: { dismiss() }, syncMessage: syncMessage)
                } else if let exercise {
                    player(exercise)
                } else if loaded {
                    Spacer()
                    NativeRecoveryCard(title: L("Este dia ainda não tem exercícios"), message: L("Escolha outro dia do plano para começar seu treino."), systemImage: "dumbbell", actionTitle: L("Voltar ao plano")) { dismiss() }.padding(18)
                    Spacer()
                }
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(day.title).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) { Button(L("Fechar")) { persist(); changed(); dismiss() }.disabled(loading) }
                ToolbarItem(placement: .navigationBarTrailing) {
                    if execution != nil, summary == nil {
                        Menu {
                            Button(L("Finalizar treino")) { prepareFinish() }
                            Button(L("Cancelar treino"), role: .destructive) { cancelConfirmation = true }.disabled(pending || (execution?.id ?? 0) < 0)
                        } label: { Image(systemName: "ellipsis.circle").accessibilityLabel(L("Opções do treino")) }
                        .disabled(loading || !sessionConfirmed)
                    }
                }
            }
            .sheet(isPresented: $showingRecorder) {
                if execution != nil, let exercise {
                    NativeWorkoutExerciseRecorder(exercise: exercise, override: effectiveOverride(for: exercise),
                        initialRows: rows(for: exercise), restUntil: local.restUntil,
                        onDraft: { rows, rest in
                            local.sets[String(exercise.id)] = rows
                            local.restUntil = rest
                            persist()
                        })
                }
            }
            .sheet(isPresented: $showingAlternatives) { replacementSheet }
            .sheet(isPresented: $showingWorkoutPremium) {
                NavigationView { NativeSubscriptionView(surface: "workout_plans", workoutUnlock: true) }.navigationViewStyle(.stack)
            }
            .sheet(isPresented: $showingFirstDay) { firstDaySheet }
            .sheet(isPresented: $finishConfirmation) { finishSheet }
            .alert(L("Cancelar e apagar este treino?"), isPresented: $cancelConfirmation) {
                Button(L("Continuar treinando"), role: .cancel) { }
                Button(L("Apagar treino"), role: .destructive) { Task { await cancel() } }
            } message: { Text(L("Os exercícios e séries desta sessão serão apagados. O plano será mantido.")) }
            .task { ownerId = account.user?.id; await load() }
            .task(id: index) { await prefetchMedia() }
            .onReceive(NotificationCenter.default.publisher(for: WorkoutExecutionSyncCoordinator.changed)) { notification in
                guard let key = notification.object as? String, key == storageKey else { return }
                refreshSyncState()
            }

        }.navigationViewStyle(.stack).interactiveDismissDisabled(loading)
    }

    private func player(_ exercise: WorkoutExercise) -> some View {
        let completed = completedIds.contains(exercise.id)
        let draftRows = rows(for: exercise)
        let nextSeries = draftRows.firstIndex { !$0.completed }
        return ScrollViewReader { scroll in
        ScrollView {
            VStack(spacing: 18) {
                HStack {
                    Text(L("Exercício \(index + 1) de \(day.exercises.count)")).font(.subheadline.weight(.semibold))
                    Spacer()
                    if (execution?.id ?? 0) > 0, !completed {
                        Menu {
                            Button(L("Trocar neste treino")) { Task { await loadAlternatives() } }
                            if effectiveOverride(for: exercise) != nil {
                                Button(L("Restaurar exercício original")) { Task { await replace(with: nil) } }
                            }
                        } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
                        .accessibilityLabel(L("Opções deste exercício"))
                        .disabled(loading || !sessionConfirmed)
                    }
                }
                ProgressView(value: Double(completedIds.count), total: Double(max(1, day.exercises.count)))
                    .accessibilityLabel(L("Exercícios concluídos"))
                    .accessibilityValue(L("\(completedIds.count) de \(day.exercises.count)"))
                ZStack {
                    if cardOffset != 0 {
                        let previewIndex = index + (cardOffset < 0 ? 1 : -1)
                        if day.exercises.indices.contains(previewIndex) {
                            exerciseCard(day.exercises[previewIndex])
                                .scaleEffect(0.95)
                                .offset(x: cardOffset < 0 ? 24 : -24)
                                .accessibilityHidden(true)
                        }
                    }
                    exerciseCard(exercise)
                        .offset(x: reduceMotion ? 0 : cardOffset)
                        .rotationEffect(.degrees(reduceMotion ? 0 : Double(cardOffset / 30)))
                        .simultaneousGesture(DragGesture(minimumDistance: 20)
                            .onChanged { value in
                                guard execution != nil, sessionConfirmed, !loading, !cardAnimating else { return }
                                let x = value.translation.width, y = value.translation.height
                                guard abs(x) >= abs(y) * 1.3 else { return }
                                let factor: CGFloat = x > 0 && index == 0 ? 0.16 : 0.55
                                cardOffset = max(-110, min(110, x * factor))
                            }
                            .onEnded { value in
                                guard execution != nil, sessionConfirmed, !loading, !cardAnimating else { return }
                                let x = value.translation.width, y = value.translation.height
                                if abs(x) >= 58, abs(x) >= abs(y) * 1.3, !(x > 0 && index == 0) {
                                    animateCardAdvance(left: x < 0)
                                } else {
                                    withAnimation(reduceMotion ? nil : .spring(response: 0.3, dampingFraction: 0.8)) { cardOffset = 0 }
                                    if y <= -44, abs(y) >= abs(x) * 1.3, !completed { showingRecorder = true }
                                }
                            })
                }
                    .accessibilityHint(L("Arraste para os lados para navegar ou para cima para registrar uma série."))
                if let rest = local.restUntil { NativeRestTimer(until: rest) { local.restUntil = nil; persist() } }
                if execution == nil {
                    Text(L("Veja a demonstração. Quando estiver pronto, inicie e registre uma série de cada vez."))
                        .font(.subheadline).foregroundColor(.secondary)
                    Button { Task { await start() } } label: {
                        Label(L("Iniciar treino"), systemImage: account.hasPremium ? "play.fill" : "lock.fill").frame(maxWidth: .infinity, minHeight: 44)
                    }.fitGlassButton(prominent: true)
                } else {
                    if completed {
                        Label(L("Exercício concluído"), systemImage: "checkmark.circle.fill").foregroundColor(.green)
                        Button(L("Editar séries deste exercício")) {
                            finishRequested = false
                            enqueue(WorkoutPendingOperation(kind: .reopen, exerciseId: exercise.id))
                            showingRecorder = true
                        }.frame(minHeight: 44).disabled(loading || !sessionConfirmed)
                    } else {
                        Button { showingRecorder = true } label: {
                            Label(nextSeries.map { L("Registrar série \($0 + 1) de \(draftRows.count)") } ?? L("Revisar séries"),
                                  systemImage: "plus.circle")
                                .frame(maxWidth: .infinity, minHeight: 44)
                        }.fitGlassButton(prominent: true).disabled(loading || !sessionConfirmed)
                        Text(L("\(draftRows.filter(\.completed).count) de \(draftRows.count) séries registradas"))
                            .font(.subheadline).foregroundColor(.secondary)
                    }
                    Button { Task { await completeAndAdvance() } } label: {
                        Label(completed ? L("Próximo exercício") : L("Concluir exercício"), systemImage: completed ? "arrow.right" : "checkmark")
                            .frame(maxWidth: .infinity, minHeight: 44)
                    }.fitGlassButton().disabled(loading || !sessionConfirmed)
                    if !completed, workingRows(for: exercise).isEmpty {
                        Text(L("Sem séries registradas, a conclusão será salva como feita conforme o plano, sem cargas informadas."))
                            .font(.footnote).foregroundColor(.secondary)
                    }
                    Button { move(-1) } label: {
                        Label(L("Exercício anterior"), systemImage: "arrow.left").frame(minHeight: 44)
                    }.disabled(index == 0)
                }
            }.padding(20).id("exerciseTop")
        }.onChange(of: index) { _ in scroll.scrollTo("exerciseTop", anchor: .top) }
        }
    }

    private func exerciseCard(_ exercise: WorkoutExercise) -> some View {
        let override = effectiveOverride(for: exercise)
        return VStack(spacing: 0) {
            NativeExerciseAnimation(catalogKey: override?.catalogKey ?? exercise.catalogKey, showsPlaybackControls: false)
                .id(override?.catalogKey ?? exercise.catalogKey ?? String(exercise.id))
                .frame(maxWidth: .infinity).frame(height: 220).background(Color.white)
            VStack(alignment: .leading, spacing: 14) {
                Text(completedIds.contains(exercise.id) ? L("✓ EXERCÍCIO CONCLUÍDO") : L("TÉCNICA ANTES DA CARGA"))
                    .font(.caption.weight(.semibold)).foregroundColor(.secondary)
                Text(override?.name ?? exercise.name).font(.title2.bold()).fixedSize(horizontal: false, vertical: true)
                HStack {
                    if let sets = override?.sets ?? exercise.sets { prescriptionValue("\(sets)", label: L("séries")) }
                    if let reps = override?.reps ?? exercise.reps { prescriptionValue(reps, label: L("repetições")) }
                    if let rest = override?.restSeconds ?? exercise.restSeconds { prescriptionValue("\(rest)s", label: "descanso") }
                }
            }.padding(20).frame(maxWidth: .infinity, alignment: .leading).background(Color.fitSurface)
        }.clipShape(RoundedRectangle(cornerRadius: 24))
    }

    private func prescriptionValue(_ value: String, label: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(value).font(.headline)
            Text(label).font(.caption2).foregroundColor(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    private func prescriptionCount(_ exercise: WorkoutExercise) -> Int? {
        effectiveOverride(for: exercise)?.sets ?? exercise.sets
    }

    private func workingRows(for exercise: WorkoutExercise) -> [WorkoutDraftSet] {
        rows(for: exercise).filter { !$0.isWarmup && !$0.repetitions.isEmpty }
    }

    private func prefetchMedia() async {
        let keys = day.exercises.compactMap { item in
            effectiveOverride(for: item)?.catalogKey ?? item.catalogKey
        }
        await NativeWorkoutMediaCache.shared.prefetch(keys: keys)
    }

    private var replacementSheet: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text(L("Escolha uma alternativa para este treino.")).font(.subheadline).foregroundColor(.secondary)
                    if alternativesLoading { ProgressView(L("Buscando alternativas…")).frame(maxWidth: .infinity).padding() }
                    if let alternativesError {
                        NativeRecoveryCard(title: L("Vamos manter seu exercício por enquanto?"), message: alternativesError,
                            systemImage: "arrow.triangle.2.circlepath", actionTitle: L("Buscar alternativas novamente")) { Task { await loadAlternatives() } }
                            .disabled(alternativesLoading)
                    }
                    ForEach(alternatives.prefix(3)) { option in
                        Button { showingAlternatives = false; Task { await replace(with: option.catalogKey) } } label: {
                            HStack(spacing: 14) {
                                NativeExerciseAnimation(catalogKey: option.catalogKey)
                                    .frame(width: 110, height: 120).background(Color.white)
                                    .clipShape(RoundedRectangle(cornerRadius: 14))
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(option.name).font(.headline).foregroundColor(.white)
                                    if let sets = option.sets, let reps = option.reps {
                                        Text(L("\(sets) séries · \(reps) reps")).font(.caption).foregroundColor(.secondary)
                                    }
                                    Text(L("Escolher")).font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                                }.frame(maxWidth: .infinity, alignment: .leading)
                            }.padding(12).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 20))
                        }.buttonStyle(.plain)
                    }
                }.padding(18)
            }.background(Color.fitBackground.ignoresSafeArea()).navigationTitle(L("Trocar exercício")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { showingAlternatives = false } } }
        }.navigationViewStyle(.stack)
    }

    private func rows(for exercise: WorkoutExercise) -> [WorkoutDraftSet] {
        if let rows = local.sets[String(exercise.id)] { return rows }
        if let rows = execution?.draftSets[String(exercise.id)], !rows.isEmpty { return rows }
        let count = effectiveOverride(for: exercise)?.sets ?? exercise.sets ?? 1
        return Array(repeating: WorkoutDraftSet(), count: max(1, min(20, count)))
    }

    private func effectiveOverride(for exercise: WorkoutExercise) -> WorkoutExerciseOverride? {
        if let operation = local.operationQueue.last(where: { $0.kind == .replace && $0.exerciseId == exercise.id }) {
            guard let key = operation.catalogKey else { return nil }
            return WorkoutExerciseOverride(workoutExerciseId: exercise.id, catalogKey: key,
                name: operation.replacementName ?? exercise.name, sets: operation.replacementSets ?? exercise.sets,
                reps: operation.replacementReps ?? exercise.reps, restSeconds: exercise.restSeconds)
        }
        return execution?.overrides.first { $0.workoutExerciseId == exercise.id }
    }

    private func persist() {
        guard let storageKey else { return }
        // The coordinator may have acknowledged writes since this view's last update.
        local.operations = WorkoutExecutionSyncCoordinator.shared.draft(for: storageKey).operationQueue
        local.cachedSession = execution
        WorkoutExecutionSyncCoordinator.shared.save(local, for: storageKey)
    }

    private func clearLocal() {
        if let storageKey { UserDefaults.standard.removeObject(forKey: storageKey) }
        local = WorkoutLocalDraft()
    }

    private func changed() { NotificationCenter.default.post(name: .nativeWorkoutChanged, object: nil) }

    private func enqueue(_ operation: WorkoutPendingOperation) {
        guard let storageKey, let ownerId, account.user?.id == ownerId else { return }
        if operation.kind == .finish { NativeXPEffects.shared.captureAction(key: operation.key) }
        persist()
        WorkoutExecutionSyncCoordinator.shared.enqueue(operation, for: storageKey, api: account.api,
            ownerId: ownerId, stillOwner: { account.user?.id })
        refreshSyncState()
    }

    private func refreshSyncState() {
        guard let storageKey, account.user?.id == ownerId else { return }
        let coordinator = WorkoutExecutionSyncCoordinator.shared
        local = coordinator.draft(for: storageKey)
        execution = coordinator.latestSession(for: storageKey) ?? local.cachedSession ?? execution
        error = coordinator.failure(for: storageKey)
        syncing = coordinator.isSyncing(storageKey)
        if let confirmed = coordinator.latestSummary(for: storageKey) { summary = confirmed }
        else if local.finishedAt != nil { summary = localSummary() }
    }

    private func restoreLocal() {
        guard let ownerId else { return }
        let prefix = "fittracker.native.workout.\(ownerId)."
        let coordinator = WorkoutExecutionSyncCoordinator.shared
        for key in UserDefaults.standard.dictionaryRepresentation().keys where key.hasPrefix(prefix) {
            let draft = coordinator.draft(for: key)
            guard draft.planId == planId, draft.dayId == day.id, let cached = draft.cachedSession,
                  draft.finishedAt == nil || !draft.operationQueue.isEmpty else { continue }
            localStorageKey = key; execution = cached; local = draft; sessionConfirmed = true; loaded = true
            index = day.exercises.firstIndex { $0.id == draft.activeExerciseId } ?? 0
            if draft.finishedAt != nil { summary = localSummary() }
            coordinator.retry(key: key, ownerId: ownerId, sessionId: cached.id, api: account.api,
                              stillOwner: { account.user?.id })
            break
        }
    }

    private func load() async {
        guard !loading, account.user?.id == ownerId else { return }
        restoreLocal()
        if execution != nil { return }
        loading = true; error = nil
        defer { loading = false }
        do {
            let record = try await account.api.getWorkoutExecutionSession(planId: planId, dayId: day.id)
            guard account.user?.id == ownerId, execution == nil else { return }
            if let record {
                guard record.workoutPlanId == planId, record.workoutDayId == day.id, record.completedAt == nil else { throw APIError.invalidResponse }
                execution = record
                if let storageKey { local = WorkoutExecutionSyncCoordinator.shared.draft(for: storageKey) }
                local.planId = planId; local.dayId = day.id
                if local.startedAt == nil, let started = record.startedAt {
                    let formatter = ISO8601DateFormatter()
                    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                    let date = started.hasSuffix("Z") ? started : started + "Z"
                    local.startedAt = formatter.date(from: date)
                    if local.startedAt == nil { local.startedAt = ISO8601DateFormatter().date(from: date) }
                }
                index = day.exercises.firstIndex { $0.id == local.activeExerciseId }
                    ?? day.exercises.firstIndex { !completedIds.contains($0.id) } ?? 0
                persist()
            }
            loaded = true; sessionConfirmed = true
        } catch { if execution == nil && !isNativeRequestCancellation(error) { self.error = RequestFailure.message(error, fallback: L("Não conseguimos conferir sua sessão agora. Tente novamente antes de iniciar.")) } }
    }

    private var firstDaySheet: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(L("Por qual treino quer começar?")).font(.title2.bold())
                    Text(L("Escolha o primeiro treino. A ordem do plano e seus dias de descanso serão preservados."))
                        .font(.subheadline).foregroundColor(.secondary)
                    ForEach(firstPlan?.days ?? []) { planned in
                        Button { Task { await chooseFirstDay(planned) } } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 5) {
                                    Text(planned.title).font(.headline).foregroundColor(.primary)
                                    Text(L("\(planned.exercises.count) exercícios")).font(.caption).foregroundColor(.secondary)
                                }
                                Spacer()
                                Image(systemName: "chevron.right").foregroundColor(.fitBlue)
                            }.padding(18).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        }.buttonStyle(.plain).disabled(loading || planned.exercises.isEmpty)
                    }
                    if loading { ProgressView().frame(maxWidth: .infinity) }
                    if let error { Text(error).font(.footnote).foregroundColor(.red) }
                }.padding(20)
            }.background(Color.fitBackground.ignoresSafeArea())
                .navigationTitle(L("Primeiro treino")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Cancelar")) { showingFirstDay = false } } }
        }.navigationViewStyle(.stack).interactiveDismissDisabled(loading)
    }

    private func chooseFirstDay(_ planned: PlanWorkoutDay) async {
        guard !loading else { return }
        loading = true; error = nil
        do {
            let today = try await account.api.getWorkoutToday()
            _ = try await account.api.setWorkoutStartDay(planId: planId, dayId: planned.id)
            if firstPlan?.isCurrent == false, today.currentPlanId == planId, today.currentDay?.id == day.id,
               planned.id != day.id {
                try await account.api.setWorkoutWeekdayDefault(planId: planId, dayId: planned.id)
            }
            day = WorkoutDay(id: planned.id, title: planned.title, exercises: planned.exercises.map {
                WorkoutExercise(id: $0.id, catalogKey: $0.catalogKey, name: $0.name, sets: $0.sets, reps: $0.reps,
                                weight: $0.weight, restSeconds: $0.restSeconds)
            })
            index = 0
            showingFirstDay = false
            loading = false
            changed()
            await start(firstDayChosen: true)
        } catch {
            loading = false
            self.error = RequestFailure.message(error, fallback: L("Não foi possível configurar o primeiro treino."))
        }
    }

    private func start(firstDayChosen: Bool = false) async {
        guard let ownerId, account.user?.id == ownerId, execution == nil, !loading else { return }
        guard account.hasPremium else { showingWorkoutPremium = true; return }
        loading = true; error = nil
        defer { loading = false }
        if !firstDayChosen {
            do {
                let plan = try await account.api.getPlan(kind: .workout, id: planId)
                if plan.hasStarted == false {
                    firstPlan = plan
                    showingFirstDay = true
                    return
                }
            } catch {
                self.error = RequestFailure.message(error, fallback: L("Não foi possível consultar seu plano. Tente novamente."))
                return
            }
        }
        do { try await account.refreshFreeAccess() }
        catch {
            if !isNativeRequestCancellation(error) {
                self.error = L("Não foi possível confirmar seu Premium. Conecte-se e tente novamente.")
            }
            return
        }
        guard account.user?.id == ownerId, execution == nil else { return }
        guard account.hasPremium else { showingWorkoutPremium = true; return }
        let provisionalId = -Int(Date().timeIntervalSince1970 * 1000)
        localStorageKey = WorkoutExecutionSyncCoordinator.key(ownerId: ownerId, sessionId: provisionalId)
        execution = WorkoutExecutionSession(id: provisionalId, workoutPlanId: planId, workoutDayId: day.id)
        local = WorkoutLocalDraft(); local.planId = planId; local.dayId = day.id; local.startedAt = Date()
        loaded = true; sessionConfirmed = true; error = nil
        persist(); changed()
        if let storageKey {
            WorkoutExecutionSyncCoordinator.shared.retry(key: storageKey, ownerId: ownerId,
                sessionId: provisionalId, api: account.api, stillOwner: { account.user?.id })
        }
    }

    private func move(_ direction: Int) {
        let next = index + direction
        if day.exercises.indices.contains(next) { index = next; local.activeExerciseId = day.exercises[next].id; persist() }
        else if direction > 0, !finishRequested { prepareFinish() }
    }

    private func animateCardAdvance(left: Bool) {
        cardAnimating = true
        withAnimation(reduceMotion ? nil : .easeIn(duration: 0.22)) { cardOffset = left ? -500 : 500 }
        Task { @MainActor in
            if !reduceMotion { try? await Task.sleep(nanoseconds: 220_000_000) }
            if left { await completeAndAdvance() } else { move(-1) }
            cardOffset = 0
            cardAnimating = false
        }
    }

    private func completeAndAdvance() async {
        guard execution != nil, let exercise, !loading, sessionConfirmed,
              account.user?.id == ownerId else { return }
        if completedIds.contains(exercise.id) { move(1); return }
        do {
            let sets = try workoutPerformedSets(rows(for: exercise))
            local.completedSets = local.completedSets ?? [:]
            local.completedSets?[String(exercise.id)] = sets
            local.restUntil = nil
            enqueue(WorkoutPendingOperation(kind: .complete, exerciseId: exercise.id,
                sets: sets, completionMode: sets.isEmpty ? "planned" : nil))
            if index == day.exercises.count - 1, completedIds.count == day.exercises.count { prepareFinish() }
            else { move(1) }
        } catch { self.error = error.localizedDescription; showingRecorder = true }
    }

    private func reconcileAndRetry() async {
        guard !loading, !syncing, account.user?.id == ownerId else { return }
        guard let storageKey, let ownerId, let execution else { await load(); return }
        if pending || execution.id < 0 {
            WorkoutExecutionSyncCoordinator.shared.retry(key: storageKey, ownerId: ownerId,
                sessionId: execution.id, api: account.api, stillOwner: { account.user?.id })
            return
        }
        loading = true; error = nil
        defer { loading = false }
        do {
            let current = try await account.api.getWorkoutExecutionSession(planId: planId, dayId: day.id)
            guard account.user?.id == ownerId else { return }
            guard let current, current.id == execution.id, current.completedAt == nil else {
                sessionConfirmed = false
                sessionEnded = true
                if cancellationNeedsCheck { clearLocal(); changed(); dismiss() }
                else { error = L("Esta sessão não está mais ativa. Seus rascunhos continuam neste iPhone; volte aos treinos para conferir o histórico.") }
                return
            }
            self.execution = current
            sessionConfirmed = true
            cancellationNeedsCheck = false
            persist()
        } catch {
            if !isNativeRequestCancellation(error) { self.error = RequestFailure.message(error, fallback: L("Não conseguimos conferir a sessão agora. Seus rascunhos continuam neste iPhone.")) }
        }
    }

    private var finishSheet: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Image(systemName: "checkmark.seal.fill")
                        .font(.system(size: 30)).foregroundColor(.fitBlue)
                        .frame(width: 64, height: 64)
                        .background(Color.fitBlue.opacity(0.15), in: RoundedRectangle(cornerRadius: 20))
                    VStack(alignment: .leading, spacing: 8) {
                        Text(L("Seu treino está quase concluído")) .font(.title.bold())
                        Text(L("Confira os detalhes antes de salvar.")) .font(.subheadline).foregroundColor(.secondary)
                    }
                    HStack(spacing: 14) {
                        Image(systemName: "dumbbell.fill").foregroundColor(.fitBlue)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(day.title).font(.headline)
                            Text(L("\(completedIds.count) de \(day.exercises.count) exercícios concluídos"))
                                .font(.subheadline).foregroundColor(.secondary)
                        }
                        Spacer()
                    }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 20))
                    VStack(alignment: .leading, spacing: 12) {
                        Text(L("Duração do treino")).font(.headline)
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            TextField(L("Minutos"), text: $finishMinutes)
                                .keyboardType(.numberPad).font(.system(size: 36, weight: .bold, design: .rounded))
                                .accessibilityLabel(L("Duração do treino em minutos"))
                            Text(L("min")).foregroundColor(.secondary).font(.headline)
                        }.padding(18).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 20))
                        Text(L("Inclua o descanso entre séries e desconte pausas longas. Esse tempo ajuda a estimar as calorias."))
                            .font(.footnote).foregroundColor(.secondary)
                        if longOpenSession {
                            Text(L("A sessão ficou aberta por bastante tempo. Informe quantos minutos você treinou."))
                                .font(.footnote).foregroundColor(.orange)
                        }
                    }
                    Text(L("Exercícios pendentes e séries em rascunho não entrarão no histórico."))
                        .font(.footnote).foregroundColor(.secondary)
                    if let finishError { Text(finishError).foregroundColor(.red).font(.footnote) }
                    Button { Task { await finish() } } label: {
                        Label(L("Finalizar treino"), systemImage: "checkmark")
                            .font(.headline).frame(maxWidth: .infinity, minHeight: 54)
                    }.fitGlassButton(prominent: true).disabled(loading)
                    Button(L("Continuar treinando")) { finishConfirmation = false }
                        .font(.subheadline.weight(.semibold)).frame(maxWidth: .infinity, minHeight: 44)
                }.padding(24)
            }.background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(L("Confirmar treino")).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { finishConfirmation = false } } }
        }.navigationViewStyle(.stack)
    }

    private func prepareFinish() {
        guard !finishRequested else { return }
        let elapsed = max(0, Date().timeIntervalSince(local.startedAt ?? Date()))
        longOpenSession = elapsed > 180 * 60
        finishMinutes = longOpenSession ? "" : String(max(1, Int((elapsed / 60).rounded())))
        finishError = nil
        finishConfirmation = true
    }

    private func finish() async {
        guard execution != nil, !loading, local.finishedAt == nil, account.user?.id == ownerId else { return }
        let finishedAt = Date()
        let elapsed = max(0, finishedAt.timeIntervalSince(local.startedAt ?? finishedAt))
        guard let minutes = Int(finishMinutes.trimmingCharacters(in: .whitespacesAndNewlines)),
              minutes > 0, Double(minutes) <= (elapsed + 60) / 60 else {
            finishError = L("Informe os minutos de treino, sem ultrapassar o tempo desde o início da sessão.")
            return
        }
        local.finishedAt = finishedAt
        local.confirmedDurationSeconds = minutes * 60
        finishConfirmation = false
        finishRequested = true
        summary = localSummary()
        enqueue(WorkoutPendingOperation(kind: .finish, durationSeconds: minutes * 60,
            finishedAt: ISO8601DateFormatter().string(from: finishedAt)))
    }

    private func localSummary() -> WorkoutActivitySummary? {
        guard let execution else { return nil }
        let performed = day.exercises.filter { completedIds.contains($0.id) }.map { exercise in
            let override = effectiveOverride(for: exercise)
            let recorded = local.completedSets?[String(exercise.id)]
                ?? (try? workoutPerformedSets(rows(for: exercise))) ?? []
            let sets = recorded.enumerated().map { index, row in
                WorkoutPerformedSet(setOrder: index + 1, repetitions: row.repetitions,
                    loadKg: row.loadKg, isWarmup: row.isWarmup)
            }
            return WorkoutPerformedExercise(exerciseId: exercise.id, name: override?.name ?? exercise.name,
                sets: sets, completionMode: sets.isEmpty ? "planned" : "performed",
                plannedPrescription: sets.isEmpty ? WorkoutPlannedPrescription(sets: prescriptionCount(exercise),
                    reps: override?.reps ?? exercise.reps, restSeconds: override?.restSeconds ?? exercise.restSeconds) : nil,
                setsPlanned: sets.isEmpty ? prescriptionCount(exercise) : nil)
        }
        let sets = performed.flatMap(\.sets)
        return WorkoutActivitySummary(id: execution.id, workoutName: day.title, planName: "",
            durationSeconds: local.confirmedDurationSeconds ?? max(0, Int((local.finishedAt ?? Date()).timeIntervalSince(local.startedAt ?? Date()))),
            exercisesPerformed: performed.count, totalExercises: day.exercises.count, setsPerformed: sets.count,
            volumeTotalKg: !sets.isEmpty && sets.allSatisfy { $0.loadKg != nil }
                ? sets.reduce(0) { $0 + Double($1.repetitions) * ($1.loadKg ?? 0) } : nil, exercises: performed)
    }

    private func loadAlternatives() async {
        guard let execution, execution.id > 0, let exercise, !alternativesLoading, account.user?.id == ownerId else { return }
        showingAlternatives = true
        alternativesError = nil
        alternatives = alternativeCache[exercise.id] ?? []
        if !alternatives.isEmpty { return }
        alternativesLoading = true
        defer { alternativesLoading = false }
        do {
            let result = try await account.api.workoutReplacementOptions(sessionId: execution.id, exerciseId: exercise.id)
            alternatives = Array(result.options.prefix(3))
            alternativeCache[exercise.id] = alternatives
            if alternatives.isEmpty { alternativesError = result.message ?? L("Nenhuma alternativa disponível.") }
            else { Task { await NativeWorkoutMediaCache.shared.prefetch(keys: alternatives.map(\.catalogKey)) } }
        } catch { if !isNativeRequestCancellation(error) { alternativesError = RequestFailure.message(error, fallback: L("As alternativas não carregaram agora. Você pode seguir com o exercício atual.")) } }
    }

    private func replace(with key: String?) async {
        guard execution != nil, let exercise, !loading, account.user?.id == ownerId else { return }
        let option = alternatives.first { $0.catalogKey == key }
        enqueue(WorkoutPendingOperation(kind: .replace, exerciseId: exercise.id, catalogKey: key,
            replacementName: option?.name, replacementSets: option?.sets, replacementReps: option?.reps))
    }

    private func cancel() async {
        guard let execution, !loading, !pending, account.user?.id == ownerId else { return }
        loading = true; error = nil
        cancellationNeedsCheck = true
        defer { loading = false }
        do {
            try await account.api.cancelWorkout(sessionId: execution.id)
            clearLocal(); changed(); dismiss()
        } catch {
            if !isNativeRequestCancellation(error) { self.error = RequestFailure.message(error, fallback: L("Não recebemos a confirmação do cancelamento. Verifique a sessão para saber se ela continua ativa.")) }
            sessionConfirmed = false
        }
    }
}

struct NativeAchievementToast: View {
    let notice: AchievementUnlockNotice

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "rosette.fill")
                .font(.title2).foregroundColor(.yellow)
                .frame(width: 48, height: 48).background(Color.white.opacity(0.1), in: Circle())
            VStack(alignment: .leading, spacing: 3) {
                Text(L("CONQUISTA DESBLOQUEADA"))
                    .font(.caption2.weight(.bold)).tracking(0.8).foregroundColor(.yellow)
                Text(notice.title).font(.headline).foregroundColor(.white)
                Text("\(NativeLocalization.display(achievementToastTier(notice.tier ?? "bronze"))) · \(notice.description)")
                    .font(.caption).foregroundColor(.white.opacity(0.75)).lineLimit(2)
            }
            Spacer(minLength: 0)
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(red: 0.08, green: 0.12, blue: 0.2), in: RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.yellow.opacity(0.35), lineWidth: 1))
        .shadow(color: .black.opacity(0.25), radius: 16, y: 6)
        .accessibilityElement(children: .combine)
    }
}

private func achievementToastTier(_ tier: String) -> String {
    switch tier {
    case "prata": return "Prata"
    case "ouro": return "Ouro"
    case "platina": return "Platina"
    default: return "Bronze"
    }
}

private struct NativeWorkoutExerciseRecorder: View {
    @Environment(\.dismiss) private var dismiss
    let exercise: WorkoutExercise
    let override: WorkoutExerciseOverride?
    let initialRows: [WorkoutDraftSet]
    let restUntil: Date?
    let onDraft: ([WorkoutDraftSet], Date?) -> Void
    @State private var rows: [WorkoutDraftSet] = []
    @State private var selected = 0
    @State private var load = ""
    @State private var repetitions = ""
    @State private var warmup = false
    @State private var confirmed = false
    @State private var repeatRemaining = false
    @State private var error: String?

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    HStack {
                        Text(L("SÉRIE \(selected + 1) DE \(max(rows.count, 1))")).font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                        Spacer()
                        Menu(L("Revisar séries")) {
                            ForEach(rows.indices, id: \.self) { i in
                                Button(L("Série \(i + 1)\(rows[i].completed ? L(" · concluída") : "")")) { select(i) }
                            }
                            if rows.count < 20 { Button(L("Adicionar série")) { rows.append(WorkoutDraftSet()); select(rows.count - 1) } }
                        }.font(.caption)
                    }
                    Text(override?.name ?? exercise.name).font(.title2.bold())
                    if let reps = override?.reps ?? exercise.reps {
                        Text(L("Referência: \(reps) reps · \(override?.restSeconds ?? exercise.restSeconds ?? 60)s de descanso"))
                            .font(.subheadline).foregroundColor(.secondary)
                    }
                    HStack(spacing: 14) {
                        entry(L("Carga · kg"), text: $load, keyboard: .decimalPad)
                        entry(L("Repetições"), text: $repetitions, keyboard: .numberPad)
                    }
                    Toggle(L("Série de aquecimento"), isOn: $warmup).font(.subheadline)
                        .onChange(of: warmup) { if $0 { repeatRemaining = false } }
                    let remaining = rows.enumerated().filter { $0.offset > selected && $0.element.loadKg.isEmpty && $0.element.repetitions.isEmpty && !$0.element.isWarmup }.count
                    if remaining > 0, !warmup {
                        Toggle(L("Usar estes valores nas próximas \(remaining) séries"), isOn: $repeatRemaining)
                            .font(.subheadline)
                        Text(L("Ative apenas se você já fez essas séries com a mesma carga e repetições."))
                            .font(.footnote).foregroundColor(.secondary)
                    }
                    if let error { Text(NativeLocalization.display(error)).font(.footnote).foregroundColor(.red) }
                    Button { confirm() } label: {
                        Label(L("Concluir série"), systemImage: "checkmark").frame(maxWidth: .infinity).padding(.vertical, 10)
                    }.fitGlassButton(prominent: true)
                    Text(L("Ao salvar, você volta ao exercício e o descanso começa. Cada série fica registrada separadamente."))
                        .font(.footnote).foregroundColor(.secondary)
                }.padding(22)
            }.background(Color.fitBackground.ignoresSafeArea())
                .navigationTitle(L("Registrar série")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { saveDraft(); dismiss() } } }
                .onAppear {
                    guard rows.isEmpty else { return }
                    rows = initialRows.isEmpty ? [WorkoutDraftSet()] : initialRows
                    selected = rows.firstIndex { !$0.completed } ?? max(0, rows.count - 1)
                    load = rows[selected].loadKg; repetitions = rows[selected].repetitions; warmup = rows[selected].isWarmup
                    if load.isEmpty, repetitions.isEmpty, selected > 0 {
                        load = rows[selected - 1].loadKg; repetitions = rows[selected - 1].repetitions
                    }
                }
                .onDisappear { if !confirmed { saveDraft() } }
        }.navigationViewStyle(.stack)
    }

    private func entry(_ label: String, text: Binding<String>, keyboard: UIKeyboardType) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(label).font(.caption).foregroundColor(.secondary)
            TextField("—", text: text).keyboardType(keyboard).font(.title.bold()).padding(16)
                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 15)).accessibilityLabel(label)
        }
    }

    private func select(_ i: Int) {
        if rows.indices.contains(selected) { saveFields() }
        selected = i
        repeatRemaining = false
        load = rows[i].loadKg; repetitions = rows[i].repetitions; warmup = rows[i].isWarmup
        if load.isEmpty, repetitions.isEmpty, i > 0 {
            load = rows[i - 1].loadKg; repetitions = rows[i - 1].repetitions
        }
    }

    private func saveFields() {
        guard rows.indices.contains(selected) else { return }
        if selected > 0, rows[selected].loadKg.isEmpty, rows[selected].repetitions.isEmpty,
           load == rows[selected - 1].loadKg, repetitions == rows[selected - 1].repetitions, !warmup { return }
        rows[selected].loadKg = load; rows[selected].repetitions = repetitions; rows[selected].isWarmup = warmup
    }

    private func saveDraft() { saveFields(); if !rows.isEmpty { onDraft(rows, restUntil) } }

    private func confirm() {
        do {
            let row = WorkoutDraftSet(loadKg: load, repetitions: repetitions, isWarmup: warmup, completed: true)
            _ = try row.performedSet()
            rows[selected] = row
            if repeatRemaining { rows = try workoutRepeatingSet(rows, at: selected) }
            confirmed = true
            onDraft(rows, Date().addingTimeInterval(Double(override?.restSeconds ?? exercise.restSeconds ?? 60)))
            dismiss()
        } catch { self.error = error.localizedDescription }
    }
}

private struct NativeRestTimer: View {
    let until: Date
    let stop: () -> Void
    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let remaining = max(0, Int(ceil(until.timeIntervalSince(context.date))))
            HStack {
                Label(remaining > 0 ? L("Descanso · \(remaining)s") : L("Descanso concluído"), systemImage: "timer")
                    .font(.subheadline.monospacedDigit())
                Spacer()
                Button(L("Encerrar"), action: stop).font(.subheadline).frame(minHeight: 44)
            }.padding(12).background(Color.fitBlue.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
        }
    }
}

@MainActor
final class WorkoutExecutionSyncCoordinator {
    static let shared = WorkoutExecutionSyncCoordinator()
    static let changed = Notification.Name("FitTrackerWorkoutExecutionSyncChanged")

    private var active = Set<String>()
    private var sessions: [String: WorkoutExecutionSession] = [:]
    private var summaries: [String: WorkoutActivitySummary] = [:]
    private var failures: [String: String] = [:]

    static func key(ownerId: UUID, sessionId: Int) -> String {
        "fittracker.native.workout.\(ownerId).\(sessionId)"
    }

    func draft(for key: String) -> WorkoutLocalDraft {
        guard let data = UserDefaults.standard.data(forKey: key),
              var draft = try? JSONDecoder().decode(WorkoutLocalDraft.self, from: data) else { return WorkoutLocalDraft() }
        if draft.operations == nil {
            draft.operationQueue = draft.operationQueue
            if let migrated = try? JSONEncoder().encode(draft) { UserDefaults.standard.set(migrated, forKey: key) }
        }
        return draft
    }

    func save(_ draft: WorkoutLocalDraft, for key: String) {
        guard let data = try? JSONEncoder().encode(draft) else { return }
        UserDefaults.standard.set(data, forKey: key)
        NotificationCenter.default.post(name: Self.changed, object: key)
    }

    func enqueue(_ operation: WorkoutPendingOperation, for key: String, api: FitTrackerAPI,
                 ownerId: UUID, stillOwner: @escaping @MainActor () -> UUID?) {
        var draft = self.draft(for: key)
        var queue = draft.operationQueue
        queue.append(operation)
        draft.operationQueue = queue
        save(draft, for: key)
        failures[key] = nil
        Task { await flush(key: key, sessionId: Int(key.split(separator: ".").last ?? "") ?? 0,
                           ownerId: ownerId, api: api, stillOwner: stillOwner) }
    }

    func latestSession(for key: String) -> WorkoutExecutionSession? { sessions[key] }
    func latestSummary(for key: String) -> WorkoutActivitySummary? { summaries[key] }
    func failure(for key: String) -> String? { failures[key] }
    func isSyncing(_ key: String) -> Bool { active.contains(key) }

    func resumePending(ownerId: UUID, api: FitTrackerAPI, stillOwner: @escaping @MainActor () -> UUID?) {
        let prefix = "fittracker.native.workout.\(ownerId)."
        for key in UserDefaults.standard.dictionaryRepresentation().keys where key.hasPrefix(prefix) {
            guard let sessionId = Int(key.dropFirst(prefix.count)),
                  !draft(for: key).operationQueue.isEmpty || sessionId < 0 && (draft(for: key).cachedSession?.id ?? 0) < 0 else { continue }
            Task { await flush(key: key, sessionId: sessionId, ownerId: ownerId,
                               api: api, stillOwner: stillOwner) }
        }
    }

    func retry(key: String, ownerId: UUID, sessionId: Int, api: FitTrackerAPI,
               stillOwner: @escaping @MainActor () -> UUID?) {
        failures[key] = nil
        Task { await flush(key: key, sessionId: sessionId, ownerId: ownerId,
                           api: api, stillOwner: stillOwner) }
    }

    private func flush(key: String, sessionId: Int, ownerId: UUID, api: FitTrackerAPI,
                       stillOwner: @escaping @MainActor () -> UUID?) async {
        guard sessionId != 0, !active.contains(key), stillOwner() == ownerId else { return }
        active.insert(key)
        var serverChanged = false
        NotificationCenter.default.post(name: Self.changed, object: key)
        defer {
            active.remove(key)
            NotificationCenter.default.post(name: Self.changed, object: key)
            if serverChanged, stillOwner() == ownerId {
                NotificationCenter.default.post(name: .nativeWorkoutChanged, object: nil)
            }
        }
        var serverSessionId = draft(for: key).cachedSession?.id ?? sessionId
        if serverSessionId < 0 {
            do {
                let saved = draft(for: key)
                guard let planId = saved.planId, let dayId = saved.dayId else { throw APIError.invalidResponse }
                let session = try await api.startWorkout(planId: planId, dayId: dayId)
                guard stillOwner() == ownerId, session.workoutPlanId == planId,
                      session.workoutDayId == dayId else { return }
                serverSessionId = session.id
                sessions[key] = session
                var current = draft(for: key)
                current.cachedSession = session
                save(current, for: key)
                failures[key] = nil
                serverChanged = true
            } catch {
                failures[key] = Self.failureMessage(error)
                NotificationCenter.default.post(name: Self.changed, object: key)
                return
            }
        }
        while let operation = draft(for: key).operationQueue.first, stillOwner() == ownerId {
            var attempt = 0
            while stillOwner() == ownerId {
                do {
                    switch operation.kind {
                    case .complete:
                        guard let exerciseId = operation.exerciseId else { throw APIError.invalidResponse }
                        sessions[key] = try await api.completeWorkoutExercise(sessionId: serverSessionId,
                            exerciseId: exerciseId, sets: operation.sets ?? [],
                            completionMode: operation.completionMode, idempotencyKey: operation.key)
                    case .reopen:
                        guard let exerciseId = operation.exerciseId else { throw APIError.invalidResponse }
                        sessions[key] = try await api.undoWorkoutExercise(sessionId: serverSessionId,
                            exerciseId: exerciseId, idempotencyKey: operation.key)
                    case .replace:
                        guard let exerciseId = operation.exerciseId else { throw APIError.invalidResponse }
                        try await api.replaceWorkoutExercise(sessionId: serverSessionId,
                            exerciseId: exerciseId, catalogKey: operation.catalogKey,
                            idempotencyKey: operation.key)
                        if let planId = draft(for: key).planId, let dayId = draft(for: key).dayId {
                            sessions[key] = try await api.getWorkoutExecutionSession(planId: planId, dayId: dayId)
                        }
                    case .finish:
                        let result = try await api.finishWorkout(sessionId: serverSessionId, idempotencyKey: operation.key,
                            durationSeconds: operation.durationSeconds, finishedAt: operation.finishedAt)
                        sessions[key] = result.session
                        summaries[key] = result.summary
                    }
                    guard stillOwner() == ownerId else { return }
                    var current = draft(for: key)
                    current.cachedSession = sessions[key] ?? current.cachedSession
                    var queue = current.operationQueue
                    if queue.first?.key == operation.key { queue.removeFirst(); current.operationQueue = queue; save(current, for: key) }
                    failures[key] = nil
                    serverChanged = true
                    break
                } catch {
                    guard stillOwner() == ownerId else { return }
                    attempt += 1
                    if attempt <= 3, Self.transient(error) {
                        try? await Task.sleep(nanoseconds: UInt64(attempt) * 700_000_000)
                        continue
                    }
                    failures[key] = Self.failureMessage(error)
                    NotificationCenter.default.post(name: Self.changed, object: key)
                    return
                }
            }
        }
    }

    private static func transient(_ error: Error) -> Bool {
        if error is URLError { return true }
        if case APIError.http(let status, _) = error { return status == 429 || status >= 500 }
        return false
    }

    private static func failureMessage(_ error: Error) -> String {
        if case APIError.http(let status, _) = error, status == 401 || status == 403 {
            return L("Entre novamente para sincronizar o treino. Os registros continuam neste iPhone.")
        }
        if case APIError.http(let status, _) = error, status == 409 {
            return L("O treino mudou no servidor. Confira a sessão antes de reenviar.")
        }
        return L("Seus registros continuam neste iPhone. ") + RequestFailure.message(error, fallback: L("Não conseguimos sincronizar agora. Tente novamente em instantes."))
    }
}

struct NativeAchievementPresenter: ViewModifier {
    @EnvironmentObject private var session: NativeSession
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var notices: [AchievementUnlockNotice] = []

    func body(content: Content) -> some View {
        content
            .overlay(alignment: .top) {
                if let notice = notices.first {
                    NativeAchievementToast(notice: notice)
                        .padding(.horizontal, 16).padding(.top, 8)
                        .transition(reduceMotion ? .opacity : .move(edge: .top).combined(with: .opacity))
                        .zIndex(1)
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: FitTrackerAPI.achievementUnlocked).receive(on: DispatchQueue.main)) { notification in
                guard session.user != nil, let notice = notification.object as? AchievementUnlockNotice,
                      !notices.contains(where: { $0.id == notice.id }) else { return }
                withAnimation(reduceMotion ? nil : .spring(response: 0.35, dampingFraction: 0.8)) {
                    notices.append(notice)
                }
            }
            .onChange(of: session.user?.id) { _ in notices.removeAll() }
            .task(id: notices.first?.id) {
                guard let notice = notices.first else { return }
                UIAccessibility.post(notification: .announcement, argument: "\(L("Conquista desbloqueada")): \(notice.title)")
                do { try await Task.sleep(nanoseconds: 4_000_000_000) } catch { return }
                guard notices.first?.id == notice.id else { return }
                withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) { notices.removeFirst() }
            }
    }
}
