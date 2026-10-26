import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
#if !os(Android)
import UIKit
#endif
import FitTrackerCore

struct NativeWorkoutExecutionView: View {
    @Environment(NativeSession.self) var account
    @Environment(\.dismiss) var dismiss
    let planId: Int
    let day: WorkoutDay
    @State var ownerId: UUID?
    @State var execution: WorkoutExecutionSession?
    @State var local = WorkoutLocalDraft()
    @State var index = 0
    @State var loading = false
    @State var loaded = false
    @State var sessionConfirmed = false
    @State var error: String?
    @State var showingRecorder = false
    @State var showingAlternatives = false
    @State var alternatives: [WorkoutReplacementOption] = []
    @State var finishConfirmation = false
    @State var cancelConfirmation = false
    @State var summary: WorkoutActivitySummary?
    @Environment(\.accessibilityReduceMotion) var reduceMotion
    @State var drag = CGSize.zero
    @State var transitioning = false
    @State var syncing = false
    @State var finishRequested = false
    @State var alternativesLoading = false
    @State var alternativesError: String?
    @State var alternativeCache: [Int: [WorkoutReplacementOption]] = [:]

    var completedIds: Set<Int> { local.completedIds(onServer: execution?.completedExerciseIds ?? []) }
    var exercise: WorkoutExercise? { day.exercises.indices.contains(index) ? day.exercises[index] : nil }
    var pending: Bool { !local.operationQueue.isEmpty }
    var storageKey: String? {
        guard let ownerId, let execution else { return nil }
        return WorkoutExecutionSyncCoordinator.key(ownerId: ownerId, sessionId: execution.id)
    }
    var syncMessage: String? {
        guard let storageKey, pending else { return nil }
        return WorkoutExecutionSyncCoordinator.shared.failure(for: storageKey)
            ?? "Treino salvo neste aparelho. Sincronizando seus registros…"
    }

    var body: some View {
        Group {
            executionBody
        }
    }

    var executionBody: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if loading && !finishRequested { ProgressView().padding(8) }
                if let error {
                    VStack(spacing: 8) {
                        Text(error).font(.footnote).foregroundColor(.red)
                        Button(pending ? "Verificar e tentar novamente" : "Atualizar sessão") {
                            Task { await reconcileAndRetry() }
                        }.disabled(loading || syncing)
                    }.padding(14)
                }
                if let summary {
                    NativeWorkoutCompletionView(summary: summary, onClose: { dismiss() }, syncMessage: syncMessage)
                } else if let exercise {
                    player(exercise)
                } else if loaded {
                    Spacer()
                    Text("Este dia não tem exercícios.").foregroundColor(.secondary)
                    Spacer()
                }
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(day.title).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) { Button("Fechar") { persist(); changed(); dismiss() }.disabled(loading) }
                ToolbarItem(placement: .navigationBarTrailing) {
                    if execution != nil, summary == nil {
                        Menu {
                            Button("Finalizar treino") { finishConfirmation = true }
                            Button("Cancelar treino", role: .destructive) { cancelConfirmation = true }.disabled(pending)
                        } label: { Image(systemName: "ellipsis.circle").accessibilityLabel("Opções do treino") }
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
            .alert("Finalizar este treino?", isPresented: $finishConfirmation) {
                Button("Continuar treinando", role: .cancel) { }
                Button("Finalizar") { Task { await finish() } }
            } message: {
                Text("\(completedIds.count) de \(day.exercises.count) exercícios concluídos. Exercícios pendentes e séries em rascunho não entrarão no histórico. Revise antes de finalizar.")
            }
            .alert("Cancelar e apagar este treino?", isPresented: $cancelConfirmation) {
                Button("Continuar treinando", role: .cancel) { }
                Button("Apagar treino", role: .destructive) { Task { await cancel() } }
            } message: { Text("Os exercícios e séries desta sessão serão apagados. O plano será mantido.") }
            .task { ownerId = account.user?.id; await load() }
            .task(id: index) { await prefetchMedia() }
            .onFitNotification(WorkoutExecutionSyncCoordinator.changed) { notification in
                guard let key = notification.object as? String, key == storageKey else { return }
                refreshSyncState()
            }
        }.interactiveDismissDisabled(loading)
    }

    func player(_ exercise: WorkoutExercise) -> some View {
        let completed = completedIds.contains(exercise.id)
        let neighbor = index + (drag.width > 0 ? -1 : 1)
        return VStack(spacing: 12) {
            HStack {
                Text("EXERCÍCIO \(index + 1) / \(day.exercises.count)").font(.caption2.weight(.semibold))
                Spacer()
                Text("\(completedIds.count) concluídos").font(.caption2).foregroundColor(.secondary)
                if execution != nil, !completed {
                    Menu {
                        Button("Trocar neste treino") { Task { await loadAlternatives() } }
                        Button("Restaurar exercício original") { Task { await replace(with: nil) } }
                    } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
                    .disabled(loading || !sessionConfirmed)
                }
            }
            HStack(spacing: 5) {
                ForEach(day.exercises) { item in
                    Capsule().fill(completedIds.contains(item.id) ? Color.green : item.id == exercise.id ? Color.fitBlue : Color.secondary.opacity(0.2)).frame(height: 3)
                }
            }
            GeometryReader { geometry in
                ZStack {
                    if day.exercises.indices.contains(neighbor) {
                        exerciseCard(day.exercises[neighbor]).scaleEffect(0.97).offset(y: 8).accessibilityHidden(true)
                    } else {
                        VStack(spacing: 16) {
                            Image(systemName: "checkmark.circle.fill").font(.system(size: 48)).foregroundColor(.green)
                            Text("Último exercício").font(.title2.bold())
                            Text("Seu resumo vem a seguir.").foregroundColor(.secondary)
                        }.frame(maxWidth: .infinity, maxHeight: .infinity)
                            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 24)).accessibilityHidden(true)
                    }
                    exerciseCard(exercise)
                        .offset(drag)
                        .rotationEffect(.degrees(reduceMotion ? 0 : Double(drag.width / 25)))
                        .overlay(alignment: .topLeading) {
                            if abs(drag.width) > 25 || drag.height < -25 {
                                Text(drag.height < -abs(drag.width) ? "REGISTRAR SÉRIE" : drag.width < 0 ? "CONCLUIR" : "VOLTAR")
                                    .font(.headline).foregroundColor(drag.width < 0 ? .green : .fitBlue)
                                    .padding(12).background(Color.fitBackground.opacity(0.9), in: RoundedRectangle(cornerRadius: 12)).padding(18)
                            }
                        }
                        .gesture(DragGesture(minimumDistance: 15)
                            .onChanged { value in
                                guard !loading, !transitioning, execution != nil, sessionConfirmed else { return }
                                if !reduceMotion { drag = value.translation }
                            }
                            .onEnded { value in
                                guard !loading, !transitioning, execution != nil, sessionConfirmed else { snapCard(); return }
                                let x = value.translation.width, y = value.translation.height
                                if y < -65, abs(y) > abs(x) * 1.3, !completed {
                                    snapCard(); showingRecorder = true
                                } else if abs(x) > 85, abs(x) > abs(y) * 1.3 {
                                    if x < 0 { Task { await completeAndAdvance() } }
                                    else if index > 0 { Task { await animateMove(-1, width: geometry.size.width) } }
                                    else { snapCard() }
                                } else { snapCard() }
                            })
                }
            }.padding(.bottom, 8)
            HStack {
                Text("← Concluir"); Spacer(); Text("↑ Registrar série"); Spacer(); Text("Voltar →")
            }.font(.caption2).foregroundColor(.secondary)
            if let rest = local.restUntil { NativeRestTimer(until: rest) { local.restUntil = nil; persist() } }
            if execution == nil {
                Button { Task { await start() } } label: {
                    Label("Iniciar treino", systemImage: "play.fill")
                        .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 12)
                }
                .buttonStyle(.borderedProminent).tint(Color(red: 0, green: 0.82, blue: 0.69))
                .disabled(loading || !sessionConfirmed)
            } else {
                HStack(spacing: 12) {
                    Button { Task { await animateMove(-1) } } label: { Image(systemName: "arrow.uturn.backward").frame(width: 30, height: 32) }
                        .buttonStyle(.bordered).disabled(index == 0 || transitioning)
                        .accessibilityLabel("Exercício anterior")
                    Button { showingRecorder = true } label: {
                        Label("Registrar série", systemImage: "chevron.up").frame(maxWidth: .infinity).padding(.vertical, 8)
                    }.buttonStyle(.bordered).disabled(loading || transitioning || completed || !sessionConfirmed)
                    Button { Task { await completeAndAdvance() } } label: {
                        Image(systemName: completed ? "arrow.right" : "checkmark").frame(width: 30, height: 32)
                    }.buttonStyle(.borderedProminent).disabled(loading || transitioning || !sessionConfirmed)
                        .accessibilityLabel(completed ? "Próximo exercício" : "Concluir e avançar")
                }
                if workingRows(for: exercise).count == 1, let count = prescriptionCount(exercise), count > 1 {
                    Text("Ao concluir, os valores da série registrada serão usados nas \(count) séries.")
                        .font(.caption2).foregroundColor(.secondary).multilineTextAlignment(.center)
                }
            }
        }.padding(.horizontal, 18).padding(.top, 8).padding(.bottom, 16)
    }

    func exerciseCard(_ exercise: WorkoutExercise) -> some View {
        let override = effectiveOverride(for: exercise)
        return VStack(spacing: 0) {
            NativeExerciseAnimation(catalogKey: override?.catalogKey ?? exercise.catalogKey, showsPlaybackControls: false)
                .id(override?.catalogKey ?? exercise.catalogKey ?? String(exercise.id))
                .frame(maxWidth: .infinity, maxHeight: .infinity).background(Color.white)
            VStack(alignment: .leading, spacing: 14) {
                Text(completedIds.contains(exercise.id) ? "✓ EXERCÍCIO CONCLUÍDO" : "TÉCNICA ANTES DA CARGA")
                    .font(.system(size: 9, weight: .semibold)).foregroundColor(.secondary)
                Text(override?.name ?? exercise.name).font(.title2.bold()).fixedSize(horizontal: false, vertical: true)
                HStack {
                    if let sets = override?.sets ?? exercise.sets { prescriptionValue("\(sets)", label: "séries") }
                    if let reps = override?.reps ?? exercise.reps { prescriptionValue(reps, label: "repetições") }
                    if let rest = override?.restSeconds ?? exercise.restSeconds { prescriptionValue("\(rest)s", label: "descanso") }
                }
            }.padding(20).frame(maxWidth: .infinity, alignment: .leading).background(Color.fitSurface)
        }.clipShape(RoundedRectangle(cornerRadius: 24))
    }

    func prescriptionValue(_ value: String, label: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(value).font(.headline)
            Text(label).font(.caption2).foregroundColor(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }

    func prescriptionCount(_ exercise: WorkoutExercise) -> Int? {
        effectiveOverride(for: exercise)?.sets ?? exercise.sets
    }

    func workingRows(for exercise: WorkoutExercise) -> [WorkoutDraftSet] {
        rows(for: exercise).filter { !$0.isWarmup && !$0.repetitions.isEmpty }
    }

    func snapCard() {
        withAnimation(reduceMotion ? nil : .spring(response: 0.32, dampingFraction: 0.8)) { drag = .zero }
    }

    func animateMove(_ direction: Int, width: CGFloat = 390) async {
        guard !transitioning else { return }
        transitioning = true
        withAnimation(reduceMotion ? nil : .easeIn(duration: 0.2)) {
            drag = CGSize(width: CGFloat(direction) * -width * 1.4, height: 0)
        }
        if !reduceMotion { try? await Task.sleep(nanoseconds: 200_000_000) }
        guard summary == nil else { transitioning = false; drag = .zero; return }
        move(direction)
        if direction < 0, let exercise, completedIds.contains(exercise.id) {
            finishRequested = false
            enqueue(WorkoutPendingOperation(kind: .reopen, exerciseId: exercise.id))
        }
        drag = .zero
        transitioning = false
    }

    func prefetchMedia() async {
        let keys = day.exercises.compactMap { item in
            effectiveOverride(for: item)?.catalogKey ?? item.catalogKey
        }
        await NativeWorkoutMediaCache.shared.prefetch(keys: keys)
    }

    var replacementSheet: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Escolha uma alternativa para este treino.").font(.subheadline).foregroundColor(.secondary)
                    if alternativesLoading { ProgressView("Buscando alternativas…").frame(maxWidth: .infinity).padding() }
                    if let alternativesError {
                        Text(alternativesError).font(.footnote).foregroundColor(.red)
                        Button("Tentar novamente") { Task { await loadAlternatives() } }
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
                                        Text("\(sets) séries · \(reps) reps").font(.caption).foregroundColor(.secondary)
                                    }
                                    Text("Escolher").font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                                }.frame(maxWidth: .infinity, alignment: .leading)
                            }.padding(12).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 20))
                        }.buttonStyle(.plain)
                    }
                }.padding(18)
            }.background(Color.fitBackground.ignoresSafeArea()).navigationTitle("Trocar exercício").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { showingAlternatives = false } } }
        }
    }

    func rows(for exercise: WorkoutExercise) -> [WorkoutDraftSet] {
        if let rows = local.sets[String(exercise.id)] { return rows }
        if let rows = execution?.draftSets[String(exercise.id)], !rows.isEmpty { return rows }
        let count = effectiveOverride(for: exercise)?.sets ?? exercise.sets ?? 1
        return Array(repeating: WorkoutDraftSet(), count: max(1, min(20, count)))
    }

    func effectiveOverride(for exercise: WorkoutExercise) -> WorkoutExerciseOverride? {
        if let operation = local.operationQueue.last(where: { $0.kind == .replace && $0.exerciseId == exercise.id }) {
            guard let key = operation.catalogKey else { return nil }
            return WorkoutExerciseOverride(workoutExerciseId: exercise.id, catalogKey: key,
                name: operation.replacementName ?? exercise.name, sets: operation.replacementSets ?? exercise.sets,
                reps: operation.replacementReps ?? exercise.reps, restSeconds: exercise.restSeconds)
        }
        return execution?.overrides.first { $0.workoutExerciseId == exercise.id }
    }

    func persist() {
        guard let storageKey else { return }
        // The coordinator may have acknowledged writes since this view's last update.
        local.operations = WorkoutExecutionSyncCoordinator.shared.draft(for: storageKey).operationQueue
        local.cachedSession = execution
        WorkoutExecutionSyncCoordinator.shared.save(local, for: storageKey)
    }

    func clearLocal() {
        if let storageKey { UserDefaults.standard.removeObject(forKey: storageKey) }
        local = WorkoutLocalDraft()
    }

    func changed() { NotificationCenter.default.post(name: .nativeWorkoutChanged, object: nil) }

    func enqueue(_ operation: WorkoutPendingOperation) {
        guard let storageKey, let ownerId, account.user?.id == ownerId else { return }
        persist()
        WorkoutExecutionSyncCoordinator.shared.enqueue(operation, for: storageKey, api: account.api,
            ownerId: ownerId, stillOwner: { account.user?.id })
        refreshSyncState()
    }

    func refreshSyncState() {
        guard let storageKey, account.user?.id == ownerId else { return }
        let coordinator = WorkoutExecutionSyncCoordinator.shared
        local = coordinator.draft(for: storageKey)
        execution = coordinator.latestSession(for: storageKey) ?? local.cachedSession ?? execution
        error = coordinator.failure(for: storageKey)
        syncing = coordinator.isSyncing(storageKey)
        if let confirmed = coordinator.latestSummary(for: storageKey) { summary = confirmed }
        else if local.finishedAt != nil { summary = localSummary() }
    }

    func restoreLocal() {
        guard let ownerId else { return }
        let prefix = "fittracker.native.workout.\(ownerId)."
        let coordinator = WorkoutExecutionSyncCoordinator.shared
        for key in UserDefaults.standard.dictionaryRepresentation().keys where key.hasPrefix(prefix) {
            let draft = coordinator.draft(for: key)
            guard draft.planId == planId, draft.dayId == day.id, let cached = draft.cachedSession,
                  draft.finishedAt == nil || !draft.operationQueue.isEmpty else { continue }
            execution = cached; local = draft; sessionConfirmed = true; loaded = true
            index = day.exercises.firstIndex { $0.id == draft.activeExerciseId } ?? 0
            if draft.finishedAt != nil { summary = localSummary() }
            coordinator.retry(key: key, ownerId: ownerId, sessionId: cached.id, api: account.api,
                              stillOwner: { account.user?.id })
            break
        }
    }

    func load() async {
        guard !loading, account.user?.id == ownerId else { return }
        restoreLocal()
        if execution != nil { return }
        loading = true; error = nil
        defer { loading = false }
        do {
            let record = try await account.api.getWorkoutExecutionSession(planId: planId, dayId: day.id)
            guard account.user?.id == ownerId else { return }
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
        } catch { self.error = error.localizedDescription }
    }

    func start() async {
        guard !loading, account.user?.id == ownerId else { return }
        loading = true; error = nil
        defer { loading = false }
        do {
            let created = try await account.api.startWorkout(planId: planId, dayId: day.id)
            guard account.user?.id == ownerId else { return }
            execution = created
            guard execution?.workoutPlanId == planId, execution?.workoutDayId == day.id else { throw APIError.invalidResponse }
            local = WorkoutLocalDraft(); local.planId = planId; local.dayId = day.id; local.startedAt = Date(); sessionConfirmed = true; persist(); changed()
        } catch { self.error = error.localizedDescription; sessionConfirmed = false }
    }

    func move(_ direction: Int) {
        let next = index + direction
        if day.exercises.indices.contains(next) { index = next; local.activeExerciseId = day.exercises[next].id; persist() }
        else if direction > 0, !finishRequested { finishConfirmation = true }
    }

    func completeAndAdvance() async {
        guard execution != nil, let exercise, !loading, !transitioning, sessionConfirmed,
              account.user?.id == ownerId else { snapCard(); return }
        if completedIds.contains(exercise.id) { await animateMove(1); return }
        do {
            let sets = try workoutPerformedSets(rows(for: exercise))
            local.completedSets = local.completedSets ?? [:]
            local.completedSets?[String(exercise.id)] = sets
            local.restUntil = nil
            enqueue(WorkoutPendingOperation(kind: .complete, exerciseId: exercise.id,
                sets: sets, completionMode: sets.isEmpty ? "planned" : nil))
            if index == day.exercises.count - 1, completedIds.count == day.exercises.count { await finish() }
            else { await animateMove(1) }
        } catch { self.error = error.localizedDescription; snapCard(); showingRecorder = true }
    }

    func reconcileAndRetry() async {
        guard let storageKey, let ownerId, let execution else { await load(); return }
        WorkoutExecutionSyncCoordinator.shared.retry(key: storageKey, ownerId: ownerId,
            sessionId: execution.id, api: account.api, stillOwner: { account.user?.id })
    }

    func finish() async {
        guard execution != nil, !loading, local.finishedAt == nil, account.user?.id == ownerId else { return }
        local.finishedAt = Date()
        finishRequested = true
        summary = localSummary()
        enqueue(WorkoutPendingOperation(kind: .finish))
    }

    func localSummary() -> WorkoutActivitySummary? {
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
            durationSeconds: max(0, Int((local.finishedAt ?? Date()).timeIntervalSince(local.startedAt ?? Date()))),
            exercisesPerformed: performed.count, totalExercises: day.exercises.count, setsPerformed: sets.count,
            volumeTotalKg: !sets.isEmpty && sets.allSatisfy { $0.loadKg != nil }
                ? sets.reduce(0) { $0 + Double($1.repetitions) * ($1.loadKg ?? 0) } : nil, exercises: performed)
    }

    func loadAlternatives() async {
        guard let execution, let exercise, !alternativesLoading, account.user?.id == ownerId else { return }
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
            if alternatives.isEmpty { alternativesError = result.message ?? "Nenhuma alternativa disponível." }
            else { Task { await NativeWorkoutMediaCache.shared.prefetch(keys: alternatives.map(\.catalogKey)) } }
        } catch { alternativesError = error.localizedDescription }
    }

    func replace(with key: String?) async {
        guard execution != nil, let exercise, !loading, account.user?.id == ownerId else { return }
        let option = alternatives.first { $0.catalogKey == key }
        enqueue(WorkoutPendingOperation(kind: .replace, exerciseId: exercise.id, catalogKey: key,
            replacementName: option?.name, replacementSets: option?.sets, replacementReps: option?.reps))
    }

    func cancel() async {
        guard let execution, !loading, !pending, account.user?.id == ownerId else { return }
        loading = true; error = nil
        defer { loading = false }
        do {
            try await account.api.cancelWorkout(sessionId: execution.id)
            clearLocal(); changed(); dismiss()
        } catch { self.error = error.localizedDescription; sessionConfirmed = false }
    }
}

struct NativeWorkoutExerciseRecorder: View {
    @Environment(\.dismiss) var dismiss
    let exercise: WorkoutExercise
    let override: WorkoutExerciseOverride?
    let initialRows: [WorkoutDraftSet]
    let restUntil: Date?
    let onDraft: ([WorkoutDraftSet], Date?) -> Void
    @State var rows: [WorkoutDraftSet] = []
    @State var selected = 0
    @State var load = ""
    @State var repetitions = ""
    @State var warmup = false
    @State var confirmed = false
    @State var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    HStack {
                        Text("SÉRIE \(selected + 1) DE \(max(rows.count, 1))").font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                        Spacer()
                        Menu("Revisar séries") {
                            ForEach(rows.indices, id: \.self) { i in
                                Button("Série \(i + 1)\(rows[i].completed ? " · concluída" : "")") { select(i) }
                            }
                            if rows.count < 20 { Button("Adicionar série") { rows.append(WorkoutDraftSet()); select(rows.count - 1) } }
                        }.font(.caption)
                    }
                    Text(override?.name ?? exercise.name).font(.title2.bold())
                    if let reps = override?.reps ?? exercise.reps {
                        Text("Referência: \(reps) reps · \(override?.restSeconds ?? exercise.restSeconds ?? 60)s de descanso")
                            .font(.subheadline).foregroundColor(.secondary)
                    }
                    HStack(spacing: 14) {
                        entry("Carga · kg", text: $load, decimal: true)
                        entry("Repetições", text: $repetitions, decimal: false)
                    }
                    Toggle("Série de aquecimento", isOn: $warmup).font(.subheadline)
                    if let error { Text(error).font(.footnote).foregroundColor(.red) }
                    Button { confirm() } label: {
                        Label("Concluir série", systemImage: "checkmark").frame(maxWidth: .infinity).padding(.vertical, 10)
                    }.buttonStyle(.borderedProminent)
                    Text("Você volta ao exercício e o descanso começa. Uma única série de trabalho registrada será repetida nas séries previstas ao concluir o exercício; aquecimentos não são repetidos.")
                        .font(.footnote).foregroundColor(.secondary)
                }.padding(22)
            }.background(Color.fitBackground.ignoresSafeArea())
                .navigationTitle("Registrar série").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { saveDraft(); dismiss() } } }
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
        }
    }

    func entry(_ label: String, text: Binding<String>, decimal: Bool) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(label).font(.caption).foregroundColor(.secondary)
            TextField("—", text: text).keyboardType(decimal ? .decimalPad : .numberPad).font(.title.bold()).padding(16)
                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 15)).accessibilityLabel(Text(label))
        }
    }

    func select(_ i: Int) {
        if rows.indices.contains(selected) { saveFields() }
        selected = i
        load = rows[i].loadKg; repetitions = rows[i].repetitions; warmup = rows[i].isWarmup
        if load.isEmpty, repetitions.isEmpty, i > 0 {
            load = rows[i - 1].loadKg; repetitions = rows[i - 1].repetitions
        }
    }

    func saveFields() {
        guard rows.indices.contains(selected) else { return }
        if selected > 0, rows[selected].loadKg.isEmpty, rows[selected].repetitions.isEmpty,
           load == rows[selected - 1].loadKg, repetitions == rows[selected - 1].repetitions, !warmup { return }
        rows[selected].loadKg = load; rows[selected].repetitions = repetitions; rows[selected].isWarmup = warmup
    }

    func saveDraft() { saveFields(); if !rows.isEmpty { onDraft(rows, restUntil) } }

    func confirm() {
        do {
            let row = WorkoutDraftSet(loadKg: load, repetitions: repetitions, isWarmup: warmup, completed: true)
            _ = try row.performedSet()
            rows[selected] = row
            confirmed = true
            onDraft(rows, Date().addingTimeInterval(Double(override?.restSeconds ?? exercise.restSeconds ?? 60)))
            dismiss()
        } catch { self.error = error.localizedDescription }
    }
}

struct NativeRestTimer: View {
    let until: Date
    let stop: () -> Void
    @State var now = Date()

    var body: some View {
        let remaining = max(0, Int(ceil(until.timeIntervalSince(now))))
        HStack {
            Label(remaining > 0 ? "Descanso · \(remaining)s" : "Descanso concluído", systemImage: "timer")
                .font(.system(.subheadline, design: .monospaced))
            Spacer()
            Button("Encerrar", action: stop).font(.caption)
        }.padding(12).background(Color.fitBlue.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
        .task(id: until) {
            now = Date()
            while !Task.isCancelled, now < until {
                do { try await Task.sleep(nanoseconds: 1_000_000_000) }
                catch { return }
                now = Date()
            }
        }
    }
}

@MainActor
final class WorkoutExecutionSyncCoordinator {
    static let shared = WorkoutExecutionSyncCoordinator()
    static let changed = Notification.Name("FitTrackerWorkoutExecutionSyncChanged")

    var active = Set<String>()
    var sessions: [String: WorkoutExecutionSession] = [:]
    var summaries: [String: WorkoutActivitySummary] = [:]
    var failures: [String: String] = [:]

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
            guard !draft(for: key).operationQueue.isEmpty,
                  let sessionId = Int(key.dropFirst(prefix.count)) else { continue }
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

    func flush(key: String, sessionId: Int, ownerId: UUID, api: FitTrackerAPI,
                       stillOwner: @escaping @MainActor () -> UUID?) async {
        guard sessionId > 0, !active.contains(key), stillOwner() == ownerId else { return }
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
        while let operation = draft(for: key).operationQueue.first, stillOwner() == ownerId {
            var attempt = 0
            while stillOwner() == ownerId {
                do {
                    switch operation.kind {
                    case .complete:
                        guard let exerciseId = operation.exerciseId else { throw APIError.invalidResponse }
                        sessions[key] = try await api.completeWorkoutExercise(sessionId: sessionId,
                            exerciseId: exerciseId, sets: operation.sets ?? [],
                            completionMode: operation.completionMode, idempotencyKey: operation.key)
                    case .reopen:
                        guard let exerciseId = operation.exerciseId else { throw APIError.invalidResponse }
                        sessions[key] = try await api.undoWorkoutExercise(sessionId: sessionId,
                            exerciseId: exerciseId, idempotencyKey: operation.key)
                    case .replace:
                        guard let exerciseId = operation.exerciseId else { throw APIError.invalidResponse }
                        try await api.replaceWorkoutExercise(sessionId: sessionId,
                            exerciseId: exerciseId, catalogKey: operation.catalogKey,
                            idempotencyKey: operation.key)
                        if let planId = draft(for: key).planId, let dayId = draft(for: key).dayId {
                            sessions[key] = try await api.getWorkoutExecutionSession(planId: planId, dayId: dayId)
                        }
                    case .finish:
                        let result = try await api.finishWorkout(sessionId: sessionId, idempotencyKey: operation.key)
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

    static func transient(_ error: Error) -> Bool {
        if error is URLError { return true }
        if case APIError.http(let status, _) = error { return status == 429 || status >= 500 }
        return false
    }

    static func failureMessage(_ error: Error) -> String {
        if case APIError.http(let status, _) = error, status == 401 || status == 403 {
            return "Entre novamente para sincronizar o treino. Os registros continuam neste aparelho."
        }
        if case APIError.http(let status, _) = error, status == 409 {
            return "O treino mudou no servidor. Confira a sessão antes de reenviar."
        }
        return "Não foi possível sincronizar o treino. Seus registros continuam neste aparelho. \(error.localizedDescription)"
    }
}
