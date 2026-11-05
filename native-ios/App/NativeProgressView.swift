import SwiftUI
import FitTrackerCore

struct NativeProgressView: View {
    @EnvironmentObject private var tabData: NativeTabDataStore
    @State private var section = 0
    @State private var refreshID = 0
    @State private var selectedDay: ConsistencyDay?
    @State private var showMeasurement = false
    @State private var detailsDay: ConsistencyDay?

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    Picker(L("Área do progresso"), selection: $section) {
                        Text(L("Resumo")).tag(0)
                        Text(L("Corpo")).tag(1)
                        Text(L("Conquistas")).tag(2)
                        Text(L("Cargas")).tag(3)
                    }.pickerStyle(.segmented)
                    NavigationLink(destination: NativeWorkoutHistoryView(timezone: tabData.workoutToday?.timezone)) {
                        Label(L("Registro de atividades"), systemImage: "clock.arrow.circlepath")
                            .font(.subheadline.weight(.semibold))
                    }
                    VStack(spacing: 0) {
                        NativeAchievementsSection(refreshID: refreshID)
                            .frame(height: section == 2 ? nil : 0).clipped()
                            .opacity(section == 2 ? 1 : 0).allowsHitTesting(section == 2).accessibilityHidden(section != 2)
                        NativeExerciseProgressSection(refreshID: refreshID)
                            .frame(height: section == 3 ? nil : 0).clipped()
                            .opacity(section == 3 ? 1 : 0).allowsHitTesting(section == 3).accessibilityHidden(section != 3)
                        NativeBodyProgressSection(refreshID: refreshID)
                            .frame(height: section == 1 ? nil : 0).clipped()
                            .opacity(section == 1 ? 1 : 0).allowsHitTesting(section == 1).accessibilityHidden(section != 1)
                    }
                    if section == 0 {
                        if tabData.progressLoading && tabData.progressOverview == nil { ProgressView(L("Carregando progresso…")).frame(maxWidth: .infinity) }
                        if let error = tabData.progressError {
                            NativeRecoveryCard(title: L("Vamos atualizar seu progresso?"), message: error, actionTitle: L("Tentar novamente")) { Task { await load(force: true) } }
                        }
                        if let overview = tabData.progressOverview {
                            if let gamification = tabData.gamification ?? overview.gamification {
                                NativeGamificationProgressCard(summary: gamification) { section = 2 }
                            }
                            weekly(overview.weekly.current)
                            consistency(overview.consistency)
                            if let fetchedAt = tabData.progressFetchedAt {
                                Text(L("Consultado às \(fetchedAt.formatted(date: .omitted, time: .shortened))"))
                                    .font(.caption).foregroundColor(.secondary)
                            } else {
                                Text(L("Dados anteriores · atualização pendente")).font(.caption).foregroundColor(.secondary)
                            }
                        }
                    }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea()).navigationTitle(L("Progresso"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button(L("Registrar medidas")) { showMeasurement = true } }
            .sheet(isPresented: $showMeasurement) { NativeMeasurementEditor() }
            .sheet(item: $detailsDay) { NativeProgressDayView(date: $0.date) }
            .refreshable { if section == 0 { await load(force: true) } else { refreshID += 1 } }
            .task(id: section) {
                if section == 0 {
                    await load()
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: Notification.Name("fitTrackerDataDidChange"))) { _ in
                refreshID += 1
                Task { await load(force: true) }
            }
        }.navigationViewStyle(.stack)
    }

    private func weekly(_ current: WeeklyProgressCurrent) -> some View {
        VStack(alignment: .leading, spacing: 15) {
            Label(L("Sua semana"), systemImage: "calendar").font(.headline)
            Text("\(progressDate(current.weekStart)) — \(progressDate(current.weekEnd))")
                .font(.caption).foregroundColor(.secondary)
            HStack(alignment: .firstTextBaseline) {
                Text("\(current.completed)").font(.system(size: 46, weight: .bold, design: .rounded))
                Text(L("treinos registrados")).foregroundColor(.secondary)
            }
            if let target = current.target {
                ProgressView(value: min(Double(current.completed), Double(target)), total: Double(max(1, target))).tint(.fitBlue)
                Text(current.fulfilled ? L("Meta de \(target) treinos atingida") : L("Meta: \(target) treinos nesta semana"))
                    .font(.subheadline)
            } else {
                Text(L("Você ainda não definiu uma meta semanal.")).font(.subheadline).foregroundColor(.secondary)
            }
            if current.completed == 0 {
                Button(L("Começar meu treino")) { NotificationCenter.default.post(name: Notification.Name("fitTrackerNavigate"), object: nil, userInfo: ["tab": "workout"]) }.fitGlassButton(prominent: true).frame(minHeight: 44)
                Button(L("Registrar meu peso")) { showMeasurement = true }.frame(minHeight: 44)
            }
            if current.streak > 0 {
                Label(L("\(current.streak) semanas seguidas cumprindo a meta"), systemImage: "flame")
                    .font(.subheadline).foregroundColor(.orange)
            }
        }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 22))
    }

    private func consistency(_ summary: ConsistencySummary) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(L("Constância nos últimos 28 dias")).font(.headline)
            HStack(spacing: 18) {
                Label(L("Treino"), systemImage: "circle.fill").foregroundColor(.fitBlue)
                Label(L("Dieta registrada"), systemImage: "circle.fill").foregroundColor(.green)
            }.font(.caption)
            if summary.days.isEmpty {
                Text(L("Seus registros de treino e alimentação vão preencher este calendário, um dia de cada vez.")).font(.subheadline).foregroundColor(.secondary)
            }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 7), spacing: 12) {
                ForEach(Array(summary.days.suffix(28))) { day in
                    Button { selectedDay = day } label: {
                        VStack(spacing: 7) {
                            Text(String(day.date.suffix(2))).font(.caption).foregroundColor(.primary)
                            HStack(spacing: 4) {
                                Circle().fill(day.workout ? Color.fitBlue : Color.secondary.opacity(0.22))
                                Circle().fill(day.dietTracked ? Color.green : Color.secondary.opacity(0.22))
                            }.frame(width: 22, height: 7)
                        }.padding(.vertical, 8).frame(maxWidth: .infinity)
                            .background(selectedDay?.id == day.id ? Color.fitBlue.opacity(0.18) : .clear, in: RoundedRectangle(cornerRadius: 10))
                    }.buttonStyle(.plain)
                        .accessibilityLabel(L("\(progressDate(day.date)): \(day.workout ? L("treino registrado") : L("sem treino registrado")), \(day.dietTracked ? L("dieta registrada") : L("sem dieta registrada"))"))
                }
            }
            if let day = selectedDay {
                Text(L("\(progressDate(day.date)): \(day.workout ? L("treino registrado") : L("sem treino registrado")) · \(day.dietTracked ? L("alimentação registrada") : L("sem alimentação registrada"))"))
                    .font(.footnote).foregroundColor(.secondary)
                Button(L("Ver detalhes")) { detailsDay = day }.fitGlassButton(prominent: true)
            }
            Text(L("Registrar alimentação indica acompanhamento; não significa que o plano foi seguido."))
                .font(.caption).foregroundColor(.secondary)
        }.padding(20).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 22))
    }

    private func load(force: Bool = false) async {
        await tabData.loadProgress(force: force)
        guard let overview = tabData.progressOverview else { return }
        if let selected = selectedDay {
            selectedDay = overview.consistency.days.first { $0.id == selected.id }
        }
    }
}

private struct NativeBodyProgressSection: View {
    @EnvironmentObject private var session: NativeSession
    let refreshID: Int
    @State private var summary: BodyProgressSummary?
    @State private var metric = BodyMetric.weight
    @State private var series: BodyMetricSeries?
    @State private var seriesCache: [BodyMetric: BodyMetricSeries] = [:]
    @State private var cachedRefreshID = -1
    @State private var error: String?
    @State private var loading = false
    @State private var displayedMetric: BodyMetric?
    @State private var requestID = UUID()
    @State private var showingMeasurement = false
    @State private var showingHistory = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Picker(L("Medida corporal"), selection: $metric) {
                ForEach(BodyMetric.allCases, id: \.self) { Text($0.displayName).tag($0) }
            }.pickerStyle(.menu)
            if let value = summary?.metrics[metric.rawValue]?.latest {
                Text("\(value.value, specifier: "%.1f") \(metric.unit)")
                    .font(.system(size: 38, weight: .bold, design: .rounded))
                Text(L("Registrado em \(progressDate(value.date))")).font(.caption).foregroundColor(.secondary)
                if let change = summary?.metrics[metric.rawValue]?.change {
                    Text(L("Variação desde o registro anterior: \(change > 0 ? "+" : "")\(change, specifier: "%.1f") \(metric == .bodyFat ? "p.p." : metric.unit)"))
                        .font(.subheadline).foregroundColor(.secondary)
                }
            } else if summary != nil && !loading && error == nil {
                NativeRecoveryCard(title: L("Seu ponto de partida"), message: L("Registre sua primeira medida de \(metric.displayName.lowercased()) para acompanhar as mudanças ao longo do tempo."), systemImage: "ruler", actionTitle: L("Registrar medida")) { showingMeasurement = true }
            }
            if loading { ProgressView(L("Carregando histórico…")) }
            if let error {
                NativeRecoveryCard(title: L("Seu histórico merece continuar"), message: error, actionTitle: L("Tentar novamente")) { Task { await load(metric) } }
            }
            if let series, !series.points.isEmpty {
                NativeBodyChart(points: series.points, unit: metric.unit)
                DisclosureGroup(L("Registros de \(metric.displayName.lowercased())")) {
                    ForEach(Array(series.points.enumerated().reversed()), id: \.offset) { entry in
                        HStack {
                            Text(progressDate(entry.element.date))
                            Spacer()
                            Text("\(entry.element.value, specifier: "%.1f") \(metric.unit)")
                        }.font(.subheadline).padding(.vertical, 7)
                    }
                }
            }
            Button(L("Ver e editar registros")) { showingHistory = true }.frame(minHeight: 44)
        }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 22))
            .task(id: metric.rawValue + String(refreshID)) { await load(metric) }
            .sheet(isPresented: $showingMeasurement) { NativeMeasurementEditor() }
            .sheet(isPresented: $showingHistory) { NativeMeasurementHistoryView() }
    }

    private func load(_ requestedMetric: BodyMetric) async {
        if cachedRefreshID != refreshID { seriesCache = [:]; cachedRefreshID = refreshID }
        if let cached = seriesCache[requestedMetric] { series = cached; displayedMetric = requestedMetric; error = nil; loading = false; return }
        let id = UUID()
        requestID = id
        loading = true
        error = nil
        if displayedMetric != requestedMetric { series = nil }
        defer { if requestID == id { loading = false } }
        do {
            async let summaryResult = session.api.getBodyProgressSummary()
            async let seriesResult = session.api.getBodyMetricSeries(metric: requestedMetric)
            let (bodySummary, result) = try await (summaryResult, seriesResult)
            guard requestID == id, metric == requestedMetric, !Task.isCancelled else { return }
            summary = bodySummary
            seriesCache[requestedMetric] = result
            series = result
            displayedMetric = requestedMetric
        } catch {
            guard requestID == id, metric == requestedMetric, !Task.isCancelled, !isNativeRequestCancellation(error) else { return }
            self.error = RequestFailure.message(error, fallback: L("Suas medidas não carregaram agora. Os registros já exibidos continuam aqui; tente atualizar novamente."))
        }
    }
}

private struct NativeBodyChart: View {
    let points: [BodyMetricPoint]
    let unit: String

    var body: some View {
        let dates = points.map { progressDay($0.date)?.timeIntervalSince1970 ?? 0 }
        let firstDate = dates.min() ?? 0
        let dateRange = max(1, (dates.max() ?? firstDate) - firstDate)
        let minimum = points.map(\.value).min() ?? 0
        let maximum = points.map(\.value).max() ?? 0
        let plotMinimum = maximum == minimum ? minimum - 0.5 : minimum
        let valueRange = max(1, maximum - minimum)
        VStack(alignment: .leading, spacing: 9) {
            Text("\(minimum, specifier: "%.1f") – \(maximum, specifier: "%.1f") \(unit)")
                .font(.caption).foregroundColor(.secondary)
            GeometryReader { geometry in
                Path { path in
                    for (index, point) in points.enumerated() {
                        let position = CGPoint(x: 6 + (dates[index] - firstDate) / dateRange * (geometry.size.width - 12),
                                               y: 6 + (1 - (point.value - plotMinimum) / valueRange) * (geometry.size.height - 12))
                        if index == 0 { path.move(to: position) } else { path.addLine(to: position) }
                    }
                }.stroke(Color.fitBlue, style: StrokeStyle(lineWidth: 3, lineCap: .round, lineJoin: .round))
                ForEach(Array(points.enumerated()), id: \.offset) { entry in
                    Circle().fill(Color.fitBlue).frame(width: 7, height: 7)
                        .position(x: 6 + (dates[entry.offset] - firstDate) / dateRange * (geometry.size.width - 12),
                                  y: 6 + (1 - (entry.element.value - plotMinimum) / valueRange) * (geometry.size.height - 12))
                }
            }.frame(height: 130).accessibilityHidden(true)
            HStack {
                Text(progressDate(points.first?.date ?? ""))
                Spacer()
                if points.count > 1 { Text(progressDate(points.last?.date ?? "")) }
            }.font(.caption).foregroundColor(.secondary)
        }.accessibilityElement(children: .combine)
    }
}

private struct NativeAchievementsSection: View {
    @EnvironmentObject private var session: NativeSession
    let refreshID: Int
    @State private var items: [ProgressAchievement] = []
    @State private var loading = false
    @State private var loadedRefreshID: Int?
    @State private var error: String?
    @State private var filter = "Todas"
    private let filters = ["Todas", "Obtidas", "Próximas", "Treino", "Recordes", "Meta", "Consistência", "Alimentação", "Hidratação", "Sequência", "Presença", "Coleções"]

    private var visibleItems: [ProgressAchievement] {
        switch filter {
        case "Obtidas": return items.filter { $0.unlocked != nil }
        case "Próximas": return items.filter { $0.unlocked == nil && ($0.progress?.current ?? 0) > 0 }
        case "Treino": return items.filter { $0.category == "treino" }
        case "Recordes": return items.filter { $0.category == "recorde" }
        case "Meta": return items.filter { $0.category == "meta" }
        case "Consistência": return items.filter { $0.category == "consistencia" }
        case "Alimentação": return items.filter { $0.category == "alimentacao" }
        case "Hidratação": return items.filter { $0.category == "hidratacao" }
        case "Sequência": return items.filter { $0.category == "sequencia" }
        case "Presença": return items.filter { $0.category == "presenca" }
        case "Coleções": return items.filter { $0.category == "colecao" }
        default: return items
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(L("Suas conquistas")).font(.headline)
                Spacer()
                Text(L("\(items.filter { $0.unlocked != nil }.count) de \(items.count)"))
                    .font(.caption.weight(.semibold)).foregroundColor(.secondary)
                Button { Task { await load() } } label: { Image(systemName: "arrow.clockwise") }.disabled(loading)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(filters, id: \.self) { value in
                        Button { filter = value } label: {
                            Text(NativeLocalization.display(value)).font(.caption.weight(.semibold)).padding(.horizontal, 12).padding(.vertical, 9)
                                .background(filter == value ? Color.fitBlue.opacity(0.22) : Color.fitSurface, in: Capsule())
                        }.buttonStyle(.plain).accessibilityAddTraits(filter == value ? .isSelected : [])
                    }
                }
            }
            if loading { ProgressView(L("Carregando conquistas…")) }
            if let error {
                NativeRecoveryCard(title: L("Suas conquistas continuam aqui"), message: error, actionTitle: L("Tentar novamente")) { Task { await load() } }
            }
            if loadedRefreshID != nil && items.isEmpty && !loading && error == nil {
                NativeRecoveryCard(title: L("Cada registro conta"), message: L("Suas conquistas aparecerão conforme você registrar sua rotina. Continue no seu ritmo."), systemImage: "rosette", actionTitle: L("Ir para alimentação")) {
                    NotificationCenter.default.post(name: Notification.Name("fitTrackerNavigate"), object: nil, userInfo: ["tab": "diet"])
                }
            }
            ForEach(visibleItems) { item in
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Image(systemName: item.unlocked == nil ? "lock.fill" : "rosette")
                            .font(.title3).foregroundColor(achievementTierColor(item.tier ?? "bronze"))
                            .frame(width: 42, height: 42).background(achievementTierColor(item.tier ?? "bronze").opacity(0.14), in: Circle())
                        VStack(alignment: .leading, spacing: 3) {
                            Text(item.title).font(.headline).foregroundColor(item.unlocked == nil ? .primary : .fitBlue)
                        Text("\(NativeLocalization.display(achievementTierName(item.tier ?? "bronze"))) · \(NativeLocalization.display(achievementCategoryName(item.category ?? "colecao")))")
                                .font(.caption).foregroundColor(achievementTierColor(item.tier ?? "bronze"))
                        }
                    }
                    Text(item.description).font(.subheadline).foregroundColor(.secondary)
                    if let progress = item.progress, item.unlocked == nil {
                        ProgressView(value: Double(progress.current), total: Double(max(1, progress.target))).tint(.fitBlue)
                        Text("\(progress.current) \(L("de")) \(progress.target)").font(.caption).foregroundColor(.secondary)
                    }
                    if let unlocked = item.unlocked {
                        Text(L("Desbloqueada\(unlocked.unlockedAt.map { L(" em ") + progressDate(String($0.prefix(10))) } ?? "")"))
                            .font(.caption).foregroundColor(.fitBlue)
                    }
                }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
            }
        }.task(id: refreshID) { if loadedRefreshID != refreshID { await load() } }
    }

    private func load() async {
        guard !loading else { return }
        loading = true
        error = nil
        defer { loading = false }
        do { items = try await session.api.getProgressAchievements().items; loadedRefreshID = refreshID }
        catch { if !isNativeRequestCancellation(error) { self.error = RequestFailure.message(error, fallback: L("Não foi possível consultar suas conquistas agora. Tente novamente.")) } }
    }
}

private extension BodyMetric {
    var displayName: String {
        switch self {
        case .weight: return L("Peso")
        case .bodyFat: return L("Gordura corporal")
        case .waist: return L("Cintura")
        case .chest: return L("Peito")
        case .arm: return L("Braço")
        case .thigh: return L("Coxa")
        case .muscleMass: return L("Massa muscular")
        }
    }
    var unit: String {
        switch self {
        case .weight, .muscleMass: return "kg"
        case .bodyFat: return "%"
        default: return "cm"
        }
    }
}

private func progressDay(_ value: String) -> Date? {
    let parser = DateFormatter()
    parser.calendar = Calendar(identifier: .gregorian)
    parser.locale = Locale(identifier: "en_US_POSIX")
    parser.timeZone = TimeZone(secondsFromGMT: 0)
    parser.dateFormat = "yyyy-MM-dd"
    return parser.date(from: value)
}

private func progressDate(_ value: String) -> String {
    guard let date = progressDay(value) else { return value }
    let formatter = DateFormatter()
    formatter.locale = NativeLocalization.locale
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "dd/MM/yyyy"
    return formatter.string(from: date)
}

private struct NativeProgressDayView: View {
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    let date: String
    @State private var diet: DietDayResponse?
    @State private var activities: [WorkoutActivity] = []
    @State private var dietError: String?
    @State private var workoutError: String?
    @State private var loadingDiet = false
    @State private var loadingWorkout = false
    @State private var workoutsLoaded = false
    @State private var workoutRefreshPending = false
    @State private var failedWorkoutReset = false
    @State private var hasMore = false
    @State private var offset = 0

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text(progressDate(date)).font(.title2.bold())
                    Text(L("Alimentação")).font(.headline)
                    if loadingDiet { ProgressView(L("Carregando refeições…")) }
                    if let dietError {
                        NativeRecoveryCard(title: L("Vamos consultar suas refeições?"), message: dietError, actionTitle: L("Tentar novamente")) { Task { await loadDiet() } }
                    }
                    if let diet {
                        if diet.entries.isEmpty && dietError == nil && !loadingDiet { NativeRecoveryCard(title: L("Um dia sem refeições registradas"), message: L("Não há registros nesta data. Você pode consultar outro dia ou adicionar uma refeição pela aba Dieta."), systemImage: "fork.knife") }
                        ForEach(diet.entries) { entry in
                            VStack(alignment: .leading, spacing: 8) {
                                Text(entry.mealType).font(.headline)
                                Text(entry.description).font(.subheadline)
                                Text(entry.calories.map { "\(Int($0.rounded())) kcal" } ?? L("Calorias não informadas"))
                                    .font(.caption).foregroundColor(.secondary)
                            }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        }
                        ForEach(diet.slots.filter { $0.result == "skipped" }) { slot in
                            Label(L("\(slot.label) · pulada"), systemImage: "forward.end")
                                .font(.subheadline).foregroundColor(.secondary)
                        }
                    }
                    Text(L("Treinos")).font(.headline)
                    if loadingWorkout { ProgressView(L("Carregando treinos…")) }
                    if let workoutError {
                        NativeRecoveryCard(title: L("Vamos consultar seus treinos?"), message: workoutError, actionTitle: L("Tentar novamente")) { Task { await loadWorkouts(reset: failedWorkoutReset) } }
                    }
                    if workoutsLoaded && activities.isEmpty && workoutError == nil && !loadingWorkout { NativeRecoveryCard(title: L("Sem treino registrado neste dia"), message: L("Descansos também fazem parte da rotina. Seus próximos registros aparecerão aqui."), systemImage: "calendar") }
                    ForEach(activities) { activity in
                        NavigationLink(destination: NativeWorkoutActivityView(id: activity.id)) {
                            HStack {
                                VStack(alignment: .leading, spacing: 7) {
                                    Text(activity.workoutName).font(.headline)
                                    Text(L("\(activity.exercisesPerformed) exercícios · \(activity.durationSeconds / 60) min"))
                                        .font(.subheadline).foregroundColor(.secondary)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                            }.padding(18).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        }.buttonStyle(.plain)
                    }
                    if hasMore { Button(L("Carregar mais treinos")) { Task { await loadWorkouts() } }.disabled(loadingWorkout) }
                }.padding(20)
            }.background(Color.fitBackground.ignoresSafeArea())
                .navigationTitle(L("Detalhes do dia")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .navigationBarLeading) { Button(L("Fechar")) { dismiss() } } }
                .onReceive(NotificationCenter.default.publisher(for: .nativeWorkoutChanged)) { _ in
                    Task { await loadWorkouts(reset: true) }
                }
                .task {
                    async let meals: Void = loadDiet()
                    async let workouts: Void = loadWorkouts()
                    _ = await (meals, workouts)
                }
        }.navigationViewStyle(.stack)
    }

    private func loadDiet() async {
        guard !loadingDiet else { return }
        loadingDiet = true
        dietError = nil
        defer { loadingDiet = false }
        do { diet = try await session.api.getDietDay(date: date) }
        catch { if !isNativeRequestCancellation(error) { dietError = RequestFailure.message(error, fallback: L("As refeições desta data não carregaram agora. Tente novamente.")) } }
    }

    private func loadWorkouts(reset: Bool = false) async {
        guard !loadingWorkout else { if reset { workoutRefreshPending = true }; return }
        loadingWorkout = true
        workoutError = nil
        failedWorkoutReset = reset
        do {
            let page = try await session.api.getProgressDayActivities(date: date, offset: reset ? 0 : offset)
            if reset { activities = page.items }
            else {
                let known = Set(activities.map(\.id))
                activities.append(contentsOf: page.items.filter { !known.contains($0.id) })
            }
            offset = page.offset + page.items.count
            hasMore = page.hasMore
            workoutsLoaded = true
        } catch { if !isNativeRequestCancellation(error) { workoutError = RequestFailure.message(error, fallback: L("Os treinos desta data não carregaram agora. Tente novamente.")) } }
        loadingWorkout = false
        if workoutRefreshPending { workoutRefreshPending = false; await loadWorkouts(reset: true) }
    }
}

private struct NativeExerciseProgressSection: View {
    @EnvironmentObject private var session: NativeSession
    let refreshID: Int
    @State private var options: [ExerciseProgressOption] = []
    @State private var selectedKey = ""
    @State private var search = ""
    @State private var mode = 0
    @State private var histories: [String: NativeExerciseHistorySnapshot] = [:]
    @State private var optionsError: String?
    @State private var loading = false
    @State private var loadedRefreshID: Int?

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Picker(L("Visualização das cargas"), selection: $mode) {
                Text(L("Evolução")).tag(0)
                Text(L("Recordes")).tag(1)
            }.pickerStyle(.segmented)
            NativePersonalRecordsSection(refreshID: refreshID)
                .frame(height: mode == 1 ? nil : 0).clipped()
                .opacity(mode == 1 ? 1 : 0).allowsHitTesting(mode == 1).accessibilityHidden(mode != 1)
            if mode == 0 {
            Text(L("Evolução de cargas")).font(.title2.bold())
            Text(L("Compare o mesmo exercício ao longo dos seus treinos registrados."))
                .font(.subheadline).foregroundColor(.secondary)
            if loading { ProgressView(L("Carregando exercícios…")) }
            if let optionsError {
                NativeRecoveryCard(title: L("Vamos buscar seus exercícios?"), message: optionsError, actionTitle: L("Tentar novamente")) { Task { await loadOptions() } }
            }
            if !options.isEmpty {
                TextField(L("Pesquisar exercício pelo nome"), text: $search)
                    .textFieldStyle(.roundedBorder).autocorrectionDisabled()
                let filtered = options.filter { search.isEmpty || $0.name.localizedStandardContains(search) }
                if !search.isEmpty {
                    if filtered.isEmpty { NativeRecoveryCard(title: L("Vamos tentar outro nome?"), message: L("Nenhum exercício corresponde à busca. Tente um nome mais curto."), systemImage: "magnifyingglass", actionTitle: L("Limpar busca")) { search = "" } }
                    ForEach(filtered) { option in
                        Button { selectedKey = option.key; search = "" } label: {
                            HStack { Text(option.name); Spacer(); if selectedKey == option.key { Image(systemName: "checkmark") } }
                        }.padding(.vertical, 8)
                    }
                } else {
                    Picker(L("Exercício"), selection: $selectedKey) {
                        ForEach(options) { Text($0.name).tag($0.key) }
                    }.pickerStyle(.menu)
                }
                NativeExerciseHistory(key: selectedKey, refreshID: refreshID, histories: $histories)
                    .id(selectedKey)
            } else if loadedRefreshID != nil && !loading && optionsError == nil {
                NativeRecoveryCard(title: L("Sua evolução começa com um treino"), message: L("Registre séries e cargas na aba Treino. Depois, compare aqui o que mudou em cada exercício."), systemImage: "chart.line.uptrend.xyaxis", actionTitle: L("Ir para treino")) {
                    NotificationCenter.default.post(name: Notification.Name("fitTrackerNavigate"), object: nil, userInfo: ["tab": "workout"])
                }
            }
            }
        }.task(id: refreshID) {
            if loadedRefreshID != refreshID { await loadOptions() }
        }
    }

    private func loadOptions() async {
        guard !loading else { return }
        loading = true
        optionsError = nil
        defer { loading = false }
        do {
            options = try await session.api.getExerciseProgressOptions().items
            loadedRefreshID = refreshID
            if !options.contains(where: { $0.key == selectedKey }) { selectedKey = options.first?.key ?? "" }
        } catch { if !isNativeRequestCancellation(error) { optionsError = RequestFailure.message(error, fallback: L("Seus exercícios não carregaram agora. Tente novamente.")) } }
    }
}

private struct NativeExerciseHistorySnapshot {
    let refreshID: Int
    let items: [ExerciseProgressSession]
    let maxLoad: Double?
    let offset: Int
    let hasMore: Bool
}

private struct NativeExerciseHistory: View {
    @EnvironmentObject private var session: NativeSession
    @Environment(\.timeZone) private var timezone
    let key: String
    let refreshID: Int
    @Binding var histories: [String: NativeExerciseHistorySnapshot]
    @State private var items: [ExerciseProgressSession] = []
    @State private var maxLoad: Double?
    @State private var offset = 0
    @State private var hasMore = false
    @State private var loading = false
    @State private var error: String?
    @State private var loaded = false
    @State private var failedReset = true
    @State private var requestID = UUID()

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if let maxLoad {
                Text("\(maxLoad, specifier: "%.1f") kg").font(.system(size: 38, weight: .bold, design: .rounded))
                Text(L("Maior carga registrada em uma série de trabalho")).font(.caption).foregroundColor(.secondary)
            }
            if loading { ProgressView(L("Carregando sessões…")) }
            if let error {
                NativeRecoveryCard(title: L("Sua evolução continua aqui"), message: error, actionTitle: L("Tentar novamente")) { Task { await load(reset: failedReset) } }
            }
            if loaded && items.isEmpty && !loading && error == nil {
                NativeRecoveryCard(title: L("Um novo ponto de partida"), message: L("Ainda não há sessões registradas para este exercício. Registre suas séries no próximo treino para acompanhar a evolução."), systemImage: "dumbbell", actionTitle: L("Ir para treino")) {
                    NotificationCenter.default.post(name: Notification.Name("fitTrackerNavigate"), object: nil, userInfo: ["tab": "workout"])
                }
            }
            if !items.isEmpty {
                Text(L("Melhor carga por sessão")).font(.headline)
                let points = items.reversed().compactMap { item -> BodyMetricPoint? in
                    guard let load = item.bestWorkingLoad else { return nil }
                    return BodyMetricPoint(date: localDate(item), value: load)
                }
                if points.isEmpty {
                    Text(L("Nenhuma carga válida de trabalho informada nestas sessões.")).foregroundColor(.secondary)
                } else { NativeBodyChart(points: points, unit: "kg") }
                Text(L("Aquecimentos e cargas não informadas ficam fora do gráfico. Ele mostra apenas as sessões carregadas."))
                    .font(.caption).foregroundColor(.secondary)
                ForEach(items) { item in
                    DisclosureGroup {
                        ForEach(Array(item.sets.enumerated()), id: \.offset) { row in
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(L("Série \(row.offset + 1) · \(row.element.repetitions) reps"))
                                    Text(row.element.isWarmup ? L("Aquecimento") : L("Trabalho")).font(.caption).foregroundColor(.secondary)
                                }
                                Spacer()
                                if let load = row.element.loadKg { Text("\(load, specifier: "%.1f") kg") }
                                else { Text(L("Não informada")).foregroundColor(.secondary) }
                            }.font(.subheadline).padding(.vertical, 6)
                        }
                        if item.sets.isEmpty { Text(L("Sem detalhes de séries.")).foregroundColor(.secondary) }
                        NavigationLink(L("Ver treino completo"), destination: NativeWorkoutActivityView(id: item.sessionId))
                            .padding(.top, 8)
                    } label: {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(progressDate(localDate(item)))
                            if let load = item.bestWorkingLoad { Text(L("Melhor carga: \(load, specifier: "%.1f") kg")).font(.caption).foregroundColor(.secondary) }
                            else { Text(L("Sem carga de trabalho informada")).font(.caption).foregroundColor(.secondary) }
                        }
                    }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                }
                if hasMore { Button(L("Carregar sessões anteriores")) { Task { await load() } }.disabled(loading) }
            }
        }.task(id: refreshID) { await load(reset: true) }
    }

    private func localDate(_ item: ExerciseProgressSession) -> String {
        if let local = item.localDate { return local }
        let parser = ISO8601DateFormatter()
        let text = item.completedAt.hasSuffix("Z") || item.completedAt.contains("+") ? item.completedAt : item.completedAt + "Z"
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var date = parser.date(from: text)
        if date == nil { parser.formatOptions = [.withInternetDateTime]; date = parser.date(from: text) }
        guard let date else { return String(item.completedAt.prefix(10)) }
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = timezone
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    private func load(reset: Bool = false) async {
        guard !key.isEmpty, reset || !loading else { return }
        let id = UUID()
        requestID = id
        loading = true
        error = nil
        failedReset = reset
        defer { if requestID == id { loading = false } }
        if reset, let cached = histories[key] {
            items = cached.items; maxLoad = cached.maxLoad
            offset = cached.offset; hasMore = cached.hasMore; loaded = true
            if cached.refreshID == refreshID { return }
        }
        do {
            let result = try await session.api.getExerciseProgress(key: key, offset: reset ? 0 : offset)
            guard requestID == id, !Task.isCancelled else { return }
            if reset { items = result.sessions.items }
            else {
                let known = Set(items.map(\.id))
                items.append(contentsOf: result.sessions.items.filter { !known.contains($0.id) })
            }
            maxLoad = result.maxLoadKg
            offset = result.sessions.offset + result.sessions.items.count
            hasMore = result.sessions.hasMore
            loaded = true
            histories[key] = NativeExerciseHistorySnapshot(refreshID: refreshID, items: items, maxLoad: maxLoad, offset: offset, hasMore: hasMore)
        } catch { if requestID == id, !isNativeRequestCancellation(error) { self.error = RequestFailure.message(error, fallback: L("As sessões não carregaram agora. As que já estavam disponíveis continuam aqui.")) } }
    }
}

private struct NativeGamificationProgressCard: View {
    let summary: GamificationSummary
    let action: () -> Void
    private let columns = Array(repeating: GridItem(.flexible(), spacing: 5), count: 7)

    var body: some View {
        Button(action: action) {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 12) {
                Image(systemName: "rosette")
                    .font(.title2).foregroundColor(.fitBlue)
                    .frame(width: 48, height: 48).background(Color.fitBlue.opacity(0.14), in: Circle())
                VStack(alignment: .leading, spacing: 3) {
                    Text(L("Sua jornada")).font(.headline)
                    NativeXPLevelLabel(summary: summary).font(.subheadline).foregroundColor(.fitBlue)
                }
                Spacer()
                Text(L("\(summary.totalXp) XP")).font(.caption.weight(.semibold)).foregroundColor(.secondary)
            }
            NativeXPProgressBar(summary: summary, showsNextLevel: true)
            HStack(spacing: 12) {
                Label("\(summary.currentStreak) \(L("dias seguidos"))", systemImage: "flame.fill").foregroundColor(.orange)
                Spacer(minLength: 0)
                Text("\(L("Recorde")): \(summary.bestStreak) \(L("dias"))").foregroundColor(.secondary)
            }.font(.subheadline.weight(.semibold))
            LazyVGrid(columns: columns, spacing: 8) {
                ForEach(summary.days) { day in
                    Circle().fill(day.qualified ? Color.fitBlue : Color.secondary.opacity(0.18))
                        .frame(width: 15, height: 15)
                        .accessibilityLabel("\(day.date): \(NativeLocalization.display(day.qualified ? "dia ativo" : "sem registro"))")
                }
            }.accessibilityElement(children: .contain).accessibilityLabel(L("Constância nos últimos 28 dias"))
            HStack(spacing: 6) {
                Image(systemName: "shield.fill").foregroundColor(.cyan)
                Text("\(summary.availableProtections) \(L("pausas protegidas disponíveis"))")
                    .font(.caption).foregroundColor(.secondary)
            }
        }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 20))
        }.buttonStyle(.plain)
            .accessibilityHint(L("Abre a aba Conquistas"))
    }
}

private func achievementTierColor(_ tier: String) -> Color {
    switch tier {
    case "prata": return Color(white: 0.75)
    case "ouro": return .yellow
    case "platina": return .cyan
    default: return .orange
    }
}

private func achievementTierName(_ tier: String) -> String {
    switch tier {
    case "prata": return "Prata"
    case "ouro": return "Ouro"
    case "platina": return "Platina"
    default: return "Bronze"
    }
}

private func achievementCategoryName(_ category: String) -> String {
    switch category {
    case "treino": return "Treino"
    case "recorde": return "Recordes"
    case "meta": return "Meta"
    case "consistencia": return "Consistência"
    case "alimentacao": return "Alimentação"
    case "hidratacao": return "Hidratação"
    case "sequencia": return "Sequência"
    case "presenca": return "Presença"
    default: return "Coleções"
    }
}

private struct NativePersonalRecordsSection: View {
    @EnvironmentObject private var session: NativeSession
    let refreshID: Int
    @State private var items: [PersonalRecord] = []
    @State private var offset = 0
    @State private var hasMore = false
    @State private var loading = false
    @State private var error: String?
    @State private var search = ""
    @State private var loaded = false
    @State private var failedReset = true
    @State private var requestID = UUID()

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label(L("Seus recordes pessoais"), systemImage: "trophy.fill")
                .font(.title2.bold()).foregroundColor(.yellow)
            Text(L("Conquistas registradas nas suas séries de trabalho."))
                .font(.subheadline).foregroundColor(.secondary)
            HStack {
                Image(systemName: "magnifyingglass").foregroundColor(.secondary)
                TextField(L("Buscar exercício"), text: $search).autocorrectionDisabled()
            }.padding(12).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 12))
            if loading && items.isEmpty { ProgressView(L("Carregando recordes…")) }
            if let error {
                NativeRecoveryCard(title: L("Vamos consultar seus recordes?"), message: error, actionTitle: L("Tentar novamente")) { Task { await load(reset: failedReset) } }
            }
            if loaded && !loading && items.isEmpty && error == nil {
                NativeRecoveryCard(title: search.isEmpty ? L("Seus próximos recordes começam no treino") : L("Vamos tentar outra busca?"), message: search.isEmpty ? L("Registre cargas e repetições nas séries de trabalho. Seus recordes aparecerão aqui quando acontecerem.") : L("Nenhum recorde corresponde ao nome pesquisado. Tente um nome mais curto."), systemImage: search.isEmpty ? "trophy" : "magnifyingglass", actionTitle: search.isEmpty ? L("Ir para treino") : L("Limpar busca")) {
                    if search.isEmpty { NotificationCenter.default.post(name: Notification.Name("fitTrackerNavigate"), object: nil, userInfo: ["tab": "workout"]) }
                    else { search = "" }
                }
            }
            ForEach(items) { record in
                VStack(alignment: .leading, spacing: 10) {
                    Text(record.exerciseName).font(.headline)
                    Text(recordTitle(record)).font(.subheadline.weight(.semibold)).foregroundColor(.secondary)
                    if record.metricType == "estimated_1rm" {
                        Text(L("Estimativa calculada a partir das suas séries; não é uma carga testada.")).font(.caption).foregroundColor(.secondary)
                    }
                    Text(recordValue(record)).font(.system(size: 30, weight: .bold, design: .rounded))
                        .foregroundColor(.yellow)
                    Text(progressDate(String(record.achievedAt.prefix(10))))
                        .font(.caption).foregroundColor(.secondary)
                    if let id = record.workoutSessionId {
                        NavigationLink(L("Ver treino"), destination: NativeWorkoutActivityView(id: id))
                    }
                }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                    .background(LinearGradient(colors: [Color(red: 0.19, green: 0.16, blue: 0.11), Color(red: 0.075, green: 0.12, blue: 0.19)], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 20))
                    .overlay(RoundedRectangle(cornerRadius: 20).stroke(Color.yellow.opacity(0.25), lineWidth: 1))
            }
            if hasMore { Button(L("Carregar mais recordes")) { Task { await load() } }.disabled(loading) }
        }.task(id: "\(refreshID):\(search)") {
            if !search.isEmpty { try? await Task.sleep(nanoseconds: 300_000_000) }
            guard !Task.isCancelled else { return }
            await load(reset: true)
        }.onChange(of: search) { _ in
            requestID = UUID()
            items = []
            hasMore = false
            loaded = false
            loading = true
            error = nil
        }
    }

    private func recordTitle(_ record: PersonalRecord) -> String {
        switch record.metricType {
        case "max_load": return L("Maior carga")
        case "estimated_1rm": return L("Carga máxima estimada para 1 repetição")
        case "reps_at_load":
            let load = record.loadKg.map { " · \($0.formatted(.number.precision(.fractionLength(0...1)))) kg" } ?? ""
            return L("Mais repetições\(load)")
        default: return L("Recorde")
        }
    }

    private func recordValue(_ record: PersonalRecord) -> String {
        let value = record.newValue.formatted(.number.precision(.fractionLength(0...1)))
        return "\(value) \(record.metricType == "reps_at_load" ? "reps" : "kg")"
    }

    private func load(reset: Bool = false) async {
        guard reset || !loading else { return }
        let id = UUID()
        requestID = id
        loading = true
        error = nil
        defer { if requestID == id { loading = false } }
        failedReset = reset
        do {
            let page = try await session.api.getPersonalRecords(offset: reset ? 0 : offset, search: search.trimmingCharacters(in: .whitespacesAndNewlines))
            guard requestID == id, !Task.isCancelled else { return }
            if reset { items = page.items }
            else {
                let known = Set(items.map(\.id))
                items.append(contentsOf: page.items.filter { !known.contains($0.id) })
            }
            offset = page.offset + page.items.count
            hasMore = page.items.count == page.limit
            loaded = true
        } catch { if requestID == id, !isNativeRequestCancellation(error) { self.error = RequestFailure.message(error, fallback: L("Seus recordes não carregaram agora. Os registros já exibidos foram mantidos.")) } }
    }
}
