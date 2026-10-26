import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
import FitTrackerCore

struct NativeProgressView: View {
    @Environment(NativeTabDataStore.self) var tabData
    @State var section = 0
    @State var refreshID = 0
    @State var selectedDay: ConsistencyDay?
    @State var showMeasurement = false
    @State var detailsDay: ConsistencyDay?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    Picker("Área do progresso", selection: $section) {
                        Text("Resumo").tag(0)
                        Text("Corpo").tag(1)
                        Text("Conquistas").tag(2)
                        Text("Cargas").tag(3)
                    }.pickerStyle(.segmented)
                    NavigationLink(destination: NativeWorkoutHistoryView(timezone: tabData.workoutToday?.timezone)) {
                        Label("Registro de atividades", systemImage: "clock.arrow.circlepath")
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
                        if tabData.progressLoading && tabData.progressOverview == nil { ProgressView("Carregando progresso…").frame(maxWidth: .infinity) }
                        if let error = tabData.progressError {
                            Text(error).foregroundColor(.red)
                            Button("Tentar novamente") { Task { await load(force: true) } }
                        }
                        if let overview = tabData.progressOverview {
                            weekly(overview.weekly.current)
                            consistency(overview.consistency)
                            if let fetchedAt = tabData.progressFetchedAt {
                                Text("Consultado às \(fetchedAt.formatted(date: .omitted, time: .shortened))")
                                    .font(.caption).foregroundColor(.secondary)
                            } else {
                                Text("Dados anteriores · atualização pendente").font(.caption).foregroundColor(.secondary)
                            }
                        }
                    }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea()).navigationTitle("Progresso")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("Registrar medidas") { showMeasurement = true } }
            .sheet(isPresented: $showMeasurement) { NativeMeasurementEditor() }
            .sheet(item: $detailsDay) { NativeProgressDayView(date: $0.date) }
            .refreshable { if section == 0 { await load(force: true) } else { refreshID += 1 } }
            .task(id: section) {
                if section == 0 {
                    await load()
                }
            }
            .onFitNotification(Notification.Name("fitTrackerDataDidChange")) { _ in
                refreshID += 1
                Task { await load(force: true) }
            }
        }
    }

    func weekly(_ current: WeeklyProgressCurrent) -> some View {
        VStack(alignment: .leading, spacing: 15) {
            Label("Sua semana", systemImage: "calendar").font(.headline)
            Text("\(progressDate(current.weekStart)) — \(progressDate(current.weekEnd))")
                .font(.caption).foregroundColor(.secondary)
            HStack(alignment: .firstTextBaseline) {
                Text("\(current.completed)").font(.system(size: 46, weight: .bold, design: .rounded))
                Text("treinos registrados").foregroundColor(.secondary)
            }
            if let target = current.target {
                ProgressView(value: min(Double(current.completed), Double(target)), total: Double(max(1, target))).tint(.fitBlue)
                Text(current.fulfilled ? "Meta de \(target) treinos atingida" : "Meta: \(target) treinos nesta semana")
                    .font(.subheadline)
            } else {
                Text("Você ainda não definiu uma meta semanal.").font(.subheadline).foregroundColor(.secondary)
            }
            if current.streak > 0 {
                Label("\(current.streak) semanas seguidas cumprindo a meta", systemImage: "flame")
                    .font(.subheadline).foregroundColor(.orange)
            }
        }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 22))
    }

    func consistency(_ summary: ConsistencySummary) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Constância nos últimos 28 dias").font(.headline)
            HStack(spacing: 18) {
                Label("Treino", systemImage: "circle.fill").foregroundColor(.fitBlue)
                Label("Dieta registrada", systemImage: "circle.fill").foregroundColor(.green)
            }.font(.caption)
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
                        .accessibilityLabel("\(progressDate(day.date)): \(day.workout ? "treino registrado" : "sem treino registrado"), \(day.dietTracked ? "dieta registrada" : "sem dieta registrada")")
                }
            }
            if let day = selectedDay {
                Text("\(progressDate(day.date)): \(day.workout ? "treino registrado" : "sem treino registrado") · \(day.dietTracked ? "alimentação registrada" : "sem alimentação registrada")")
                    .font(.footnote).foregroundColor(.secondary)
                Button("Ver detalhes") { detailsDay = day }.buttonStyle(.borderedProminent)
            }
            Text("Registrar alimentação indica acompanhamento; não significa que o plano foi seguido.")
                .font(.caption).foregroundColor(.secondary)
        }.padding(20).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 22))
    }

    func load(force: Bool = false) async {
        await tabData.loadProgress(force: force)
        guard let overview = tabData.progressOverview else { return }
        if let selected = selectedDay {
            selectedDay = overview.consistency.days.first { $0.id == selected.id }
        }
    }
}

struct NativeBodyProgressSection: View {
    @Environment(NativeSession.self) var session
    let refreshID: Int
    @State var summary: BodyProgressSummary?
    @State var metric = BodyMetric.weight
    @State var series: BodyMetricSeries?
    @State var seriesCache: [BodyMetric: BodyMetricSeries] = [:]
    @State var cachedRefreshID = -1
    @State var error: String?
    @State var loading = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Picker("Medida corporal", selection: $metric) {
                ForEach(BodyMetric.allCases, id: \.self) { Text($0.displayName).tag($0) }
            }.pickerStyle(.menu)
            if let value = summary?.metrics[metric.rawValue]?.latest {
                Text("\(value.value, specifier: "%.1f") \(metric.unit)")
                    .font(.system(size: 38, weight: .bold, design: .rounded))
                Text("Registrado em \(progressDate(value.date))").font(.caption).foregroundColor(.secondary)
                if let change = summary?.metrics[metric.rawValue]?.change {
                    Text("Variação desde o registro anterior: \(change > 0 ? "+" : "")\(change, specifier: "%.1f") \(metric == .bodyFat ? "p.p." : metric.unit)")
                        .font(.subheadline).foregroundColor(.secondary)
                }
            } else { Text("Nenhum registro de \(metric.displayName.lowercased()) ainda.").foregroundColor(.secondary) }
            if loading { ProgressView("Carregando histórico…") }
            if let error {
                Text(error).foregroundColor(.red)
                Button("Tentar novamente") { Task { await load(metric) } }
            }
            if let series, !series.points.isEmpty {
                NativeBodyChart(points: series.points, unit: metric.unit)
                DisclosureGroup("Registros de \(metric.displayName.lowercased())") {
                    ForEach(Array(series.points.enumerated().reversed()), id: \.offset) { entry in
                        HStack {
                            Text(progressDate(entry.element.date))
                            Spacer()
                            Text("\(entry.element.value, specifier: "%.1f") \(metric.unit)")
                        }.font(.subheadline).padding(.vertical, 7)
                    }
                }
            }
        }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 22))
            .task(id: metric.rawValue + String(refreshID)) { await load(metric) }
    }

    func load(_ requestedMetric: BodyMetric) async {
        if cachedRefreshID != refreshID { seriesCache = [:]; cachedRefreshID = refreshID }
        if let cached = seriesCache[requestedMetric] { series = cached; return }
        loading = true
        error = nil
        series = nil
        do {
            async let summaryResult = session.api.getBodyProgressSummary()
            async let seriesResult = session.api.getBodyMetricSeries(metric: requestedMetric)
            let (bodySummary, result) = try await (summaryResult, seriesResult)
            guard metric == requestedMetric, !Task.isCancelled else { loading = false; return }
            summary = bodySummary
            seriesCache[requestedMetric] = result
            series = result
            loading = false
        } catch {
            loading = false
            guard metric == requestedMetric, !Task.isCancelled, !isNativeRequestCancellation(error) else { return }
            self.error = error.localizedDescription
        }
    }
}

struct NativeBodyChart: View {
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
                .font(.caption).foregroundColor(.secondary).accessibilityHidden(true)
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
            }.font(.caption).foregroundColor(.secondary).accessibilityHidden(true)
        }.accessibilityLabel(Text("De \(progressDate(points.first?.date ?? "")) a \(progressDate(points.last?.date ?? "")): \(minimum, specifier: "%.1f") a \(maximum, specifier: "%.1f") \(unit)"))
    }
}

struct NativeAchievementsSection: View {
    @Environment(NativeSession.self) var session
    let refreshID: Int
    @State var items: [ProgressAchievement] = []
    @State var loading = false
    @State var loadedRefreshID: Int?
    @State var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Suas conquistas").font(.headline)
                Spacer()
                Button { Task { await load() } } label: { Image(systemName: "arrow.clockwise") }.disabled(loading)
            }
            if loading { ProgressView("Carregando conquistas…") }
            if let error {
                Text(error).foregroundColor(.red)
                Button("Tentar novamente") { Task { await load() } }
            }
            ForEach(items) { item in
                VStack(alignment: .leading, spacing: 10) {
                    Label(item.title, systemImage: item.unlocked == nil ? "lock" : "rosette")
                        .font(.headline).foregroundColor(item.unlocked == nil ? .primary : .fitBlue)
                    Text(item.description).font(.subheadline).foregroundColor(.secondary)
                    if let progress = item.progress, item.unlocked == nil {
                        ProgressView(value: Double(progress.current), total: Double(max(1, progress.target))).tint(.fitBlue)
                        Text("\(progress.current) de \(progress.target)").font(.caption).foregroundColor(.secondary)
                    }
                    if let unlocked = item.unlocked {
                        Text("Desbloqueada\(unlocked.unlockedAt.map { " em " + progressDate(String($0.prefix(10))) } ?? "")")
                            .font(.caption).foregroundColor(.fitBlue)
                    }
                }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
            }
        }.task(id: refreshID) { if loadedRefreshID != refreshID { await load() } }
    }

    func load() async {
        guard !loading else { return }
        loading = true
        error = nil
        defer { loading = false }
        do { items = try await session.api.getProgressAchievements().items; loadedRefreshID = refreshID }
        catch { if !isNativeRequestCancellation(error) { self.error = error.localizedDescription } }
    }
}

extension BodyMetric {
    var displayName: String {
        switch self {
        case .weight: return "Peso"
        case .bodyFat: return "Gordura corporal"
        case .waist: return "Cintura"
        case .chest: return "Peito"
        case .arm: return "Braço"
        case .thigh: return "Coxa"
        case .muscleMass: return "Massa muscular"
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

func progressDay(_ value: String) -> Date? {
    let parser = DateFormatter()
    parser.calendar = Calendar(identifier: .gregorian)
    parser.locale = Locale(identifier: "en_US_POSIX")
    parser.timeZone = TimeZone(secondsFromGMT: 0)
    parser.dateFormat = "yyyy-MM-dd"
    return parser.date(from: value)
}

func progressDate(_ value: String) -> String {
    guard let date = progressDay(value) else { return value }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "pt_BR")
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "dd/MM/yyyy"
    return formatter.string(from: date)
}

struct NativeProgressDayView: View {
    @Environment(NativeSession.self) var session
    @Environment(\.dismiss) var dismiss
    let date: String
    @State var diet: DietDayResponse?
    @State var activities: [WorkoutActivity] = []
    @State var dietError: String?
    @State var workoutError: String?
    @State var loadingDiet = false
    @State var loadingWorkout = false
    @State var workoutsLoaded = false
    @State var hasMore = false
    @State var offset = 0

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text(progressDate(date)).font(.title2.bold())
                    Text("Alimentação").font(.headline)
                    if loadingDiet { ProgressView("Carregando refeições…") }
                    if let dietError {
                        Text(dietError).foregroundColor(.red)
                        Button("Tentar refeições novamente") { Task { await loadDiet() } }
                    }
                    if let diet {
                        if diet.entries.isEmpty { Text("Nenhuma refeição registrada nesta data.").foregroundColor(.secondary) }
                        ForEach(diet.entries) { entry in
                            VStack(alignment: .leading, spacing: 8) {
                                Text(entry.mealType).font(.headline)
                                Text(entry.description).font(.subheadline)
                                Text(entry.calories.map { "\(Int($0.rounded())) kcal" } ?? "Calorias não informadas")
                                    .font(.caption).foregroundColor(.secondary)
                            }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        }
                        ForEach(diet.slots.filter { $0.result == "skipped" }) { slot in
                            Label("\(slot.label) · pulada", systemImage: "forward.end")
                                .font(.subheadline).foregroundColor(.secondary)
                        }
                    }
                    Text("Treinos").font(.headline)
                    if loadingWorkout { ProgressView("Carregando treinos…") }
                    if let workoutError {
                        Text(workoutError).foregroundColor(.red)
                        Button("Tentar treinos novamente") { Task { await loadWorkouts() } }
                    }
                    if workoutsLoaded && activities.isEmpty { Text("Nenhum treino registrado nesta data.").foregroundColor(.secondary) }
                    ForEach(activities) { activity in
                        NavigationLink(destination: NativeWorkoutActivityView(id: activity.id)) {
                            HStack {
                                VStack(alignment: .leading, spacing: 7) {
                                    Text(activity.workoutName).font(.headline)
                                    Text("\(activity.exercisesPerformed) exercícios · \(activity.durationSeconds / 60) min")
                                        .font(.subheadline).foregroundColor(.secondary)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                            }.padding(18).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                        }.buttonStyle(.plain)
                    }
                    if hasMore { Button("Carregar mais treinos") { Task { await loadWorkouts() } }.disabled(loadingWorkout) }
                }.padding(20)
            }.background(Color.fitBackground.ignoresSafeArea())
                .navigationTitle("Detalhes do dia").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .navigationBarLeading) { Button("Fechar") { dismiss() } } }
                .onFitNotification(.nativeWorkoutChanged) { _ in
                    activities = []; offset = 0; hasMore = false; workoutsLoaded = false
                    Task { await loadWorkouts() }
                }
                .task {
                    async let meals: Void = loadDiet()
                    async let workouts: Void = loadWorkouts()
                    _ = await (meals, workouts)
                }
        }
    }

    func loadDiet() async {
        guard !loadingDiet else { return }
        loadingDiet = true
        dietError = nil
        defer { loadingDiet = false }
        do { diet = try await session.api.getDietDay(date: date) }
        catch { if !isNativeRequestCancellation(error) { dietError = error.localizedDescription } }
    }

    func loadWorkouts() async {
        guard !loadingWorkout else { return }
        loadingWorkout = true
        workoutError = nil
        defer { loadingWorkout = false }
        do {
            let page = try await session.api.getProgressDayActivities(date: date, offset: offset)
            let known = Set(activities.map(\.id))
            activities.append(contentsOf: page.items.filter { !known.contains($0.id) })
            offset = page.offset + page.items.count
            hasMore = page.hasMore
            workoutsLoaded = true
        } catch { if !isNativeRequestCancellation(error) { workoutError = error.localizedDescription } }
    }
}

struct NativeExerciseProgressSection: View {
    @Environment(NativeSession.self) var session
    let refreshID: Int
    @State var options: [ExerciseProgressOption] = []
    @State var selectedKey = ""
    @State var search = ""
    @State var mode = 0
    @State var histories: [String: NativeExerciseHistorySnapshot] = [:]
    @State var optionsError: String?
    @State var loading = false
    @State var loadedRefreshID: Int?

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Picker("Visualização das cargas", selection: $mode) {
                Text("Evolução").tag(0)
                Text("PRs").tag(1)
            }.pickerStyle(.segmented)
            NativePersonalRecordsSection(refreshID: refreshID)
                .frame(height: mode == 1 ? nil : 0).clipped()
                .opacity(mode == 1 ? 1 : 0).allowsHitTesting(mode == 1).accessibilityHidden(mode != 1)
            if mode == 0 {
            Text("Evolução de cargas").font(.title2.bold())
            Text("Compare o mesmo exercício ao longo dos seus treinos registrados.")
                .font(.subheadline).foregroundColor(.secondary)
            if loading { ProgressView("Carregando exercícios…") }
            if let optionsError {
                Text(optionsError).foregroundColor(.red)
                Button("Tentar novamente") { Task { await loadOptions() } }
            }
            if !options.isEmpty {
                TextField("Pesquisar exercício pelo nome", text: $search)
                    .textFieldStyle(.roundedBorder).autocorrectionDisabled()
                let filtered = options.filter { search.isEmpty || $0.name.localizedStandardContains(search) }
                if !search.isEmpty {
                    if filtered.isEmpty { Text("Nenhum exercício encontrado.").foregroundColor(.secondary) }
                    ForEach(filtered) { option in
                        Button { selectedKey = option.key; search = "" } label: {
                            HStack { Text(option.name); Spacer(); if selectedKey == option.key { Image(systemName: "checkmark") } }
                        }.padding(.vertical, 8)
                    }
                } else {
                    Picker("Exercício", selection: $selectedKey) {
                        ForEach(options) { Text($0.name).tag($0.key) }
                    }.pickerStyle(.menu)
                }
                NativeExerciseHistory(key: selectedKey, refreshID: refreshID, histories: $histories)
                    .id(selectedKey)
            } else if !loading && optionsError == nil {
                Text("Seus exercícios aparecerão depois que você registrar um treino.").foregroundColor(.secondary)
            }
            }
        }.task(id: refreshID) {
            if loadedRefreshID != refreshID { histories = [:]; await loadOptions() }
        }
    }

    func loadOptions() async {
        guard !loading else { return }
        loading = true
        optionsError = nil
        defer { loading = false }
        do {
            options = try await session.api.getExerciseProgressOptions().items
            loadedRefreshID = refreshID
            if !options.contains(where: { $0.key == selectedKey }) { selectedKey = options.first?.key ?? "" }
        } catch { if !isNativeRequestCancellation(error) { optionsError = error.localizedDescription } }
    }
}

struct NativeExerciseHistorySnapshot {
    let refreshID: Int
    let items: [ExerciseProgressSession]
    let maxLoad: Double?
    let offset: Int
    let hasMore: Bool
}

struct NativeExerciseHistory: View {
    @Environment(NativeSession.self) var session
    @Environment(\.timeZone) var timezone
    let key: String
    let refreshID: Int
    @Binding var histories: [String: NativeExerciseHistorySnapshot]
    @State var items: [ExerciseProgressSession] = []
    @State var maxLoad: Double?
    @State var offset = 0
    @State var hasMore = false
    @State var loading = false
    @State var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if let maxLoad {
                Text("\(maxLoad, specifier: "%.1f") kg").font(.system(size: 38, weight: .bold, design: .rounded))
                Text("Maior carga registrada em uma série de trabalho").font(.caption).foregroundColor(.secondary)
            }
            if loading { ProgressView("Carregando sessões…") }
            if let error {
                Text(error).foregroundColor(.red)
                Button("Tentar novamente") { Task { await load() } }
            }
            if !items.isEmpty {
                Text("Melhor carga por sessão").font(.headline)
                let points = items.reversed().compactMap { item -> BodyMetricPoint? in
                    guard let load = item.bestWorkingLoad else { return nil }
                    return BodyMetricPoint(date: localDate(item), value: load)
                }
                if points.isEmpty {
                    Text("Nenhuma carga válida de trabalho informada nestas sessões.").foregroundColor(.secondary)
                } else { NativeBodyChart(points: points, unit: "kg") }
                Text("Aquecimentos e cargas não informadas ficam fora do gráfico. Ele mostra apenas as sessões carregadas.")
                    .font(.caption).foregroundColor(.secondary)
                ForEach(items) { item in
                    DisclosureGroup {
                        ForEach(Array(item.sets.enumerated()), id: \.offset) { row in
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Série \(row.offset + 1) · \(row.element.repetitions) reps")
                                    Text(row.element.isWarmup ? "Aquecimento" : "Trabalho").font(.caption).foregroundColor(.secondary)
                                }
                                Spacer()
                                if let load = row.element.loadKg { Text("\(load, specifier: "%.1f") kg") }
                                else { Text("Não informada").foregroundColor(.secondary) }
                            }.font(.subheadline).padding(.vertical, 6)
                        }
                        if item.sets.isEmpty { Text("Sem detalhes de séries.").foregroundColor(.secondary) }
                        NavigationLink("Ver treino completo", destination: NativeWorkoutActivityView(id: item.sessionId))
                            .padding(.top, 8)
                    } label: {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(progressDate(localDate(item)))
                            if let load = item.bestWorkingLoad { Text("Melhor carga: \(load, specifier: "%.1f") kg").font(.caption).foregroundColor(.secondary) }
                            else { Text("Sem carga de trabalho informada").font(.caption).foregroundColor(.secondary) }
                        }
                    }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                }
                if hasMore { Button("Carregar sessões anteriores") { Task { await load() } }.disabled(loading) }
            }
        }.task(id: refreshID) { await load(reset: true) }
    }

    func localDate(_ item: ExerciseProgressSession) -> String {
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

    func load(reset: Bool = false) async {
        guard !key.isEmpty, !loading else { return }
        loading = true
        error = nil
        defer { loading = false }
        if reset {
            if let cached = histories[key], cached.refreshID == refreshID {
                items = cached.items; maxLoad = cached.maxLoad
                offset = cached.offset; hasMore = cached.hasMore
                return
            }
            offset = 0; items = []; maxLoad = nil; hasMore = false
        }
        do {
            let result = try await session.api.getExerciseProgress(key: key, offset: offset)
            guard !Task.isCancelled else { return }
            let known = Set(items.map(\.id))
            items.append(contentsOf: result.sessions.items.filter { !known.contains($0.id) })
            maxLoad = result.maxLoadKg
            offset = result.sessions.offset + result.sessions.items.count
            hasMore = result.sessions.hasMore
            histories[key] = NativeExerciseHistorySnapshot(refreshID: refreshID, items: items, maxLoad: maxLoad, offset: offset, hasMore: hasMore)
        } catch { if !isNativeRequestCancellation(error) { self.error = error.localizedDescription } }
    }
}

struct NativePersonalRecordsSection: View {
    @Environment(NativeSession.self) var session
    let refreshID: Int
    @State var items: [PersonalRecord] = []
    @State var offset = 0
    @State var hasMore = false
    @State var loading = false
    @State var error: String?
    @State var search = ""
    @State var requestID = UUID()

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("Seus recordes pessoais", systemImage: "trophy.fill")
                .font(.title2.bold()).foregroundColor(.yellow)
            Text("Conquistas registradas nas suas séries de trabalho.")
                .font(.subheadline).foregroundColor(.secondary)
            HStack {
                Image(systemName: "magnifyingglass").foregroundColor(.secondary)
                TextField("Buscar exercício", text: $search).autocorrectionDisabled()
            }.padding(12).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 12))
            if loading && items.isEmpty { ProgressView("Carregando recordes…") }
            if let error {
                Text(error).foregroundColor(.red)
                Button("Tentar novamente") { Task { await load() } }
            }
            if !loading && items.isEmpty && error == nil {
                Text(search.isEmpty ? "Registre as cargas e repetições dos seus treinos para acompanhar seus PRs." : "Nenhum recorde encontrado para este exercício.")
                    .foregroundColor(.secondary)
            }
            ForEach(items) { record in
                VStack(alignment: .leading, spacing: 10) {
                    Text(record.exerciseName).font(.headline)
                    Text(recordTitle(record)).font(.subheadline.weight(.semibold)).foregroundColor(.secondary)
                    Text(recordValue(record)).font(.system(size: 30, weight: .bold, design: .rounded))
                        .foregroundColor(.yellow)
                    Text(progressDate(String(record.achievedAt.prefix(10))))
                        .font(.caption).foregroundColor(.secondary)
                    if let id = record.workoutSessionId {
                        NavigationLink("Ver treino", destination: NativeWorkoutActivityView(id: id))
                    }
                }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                    .background(LinearGradient(colors: [Color(red: 0.19, green: 0.16, blue: 0.11), Color(red: 0.075, green: 0.12, blue: 0.19)], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 20))
                    .overlay(RoundedRectangle(cornerRadius: 20).stroke(Color.yellow.opacity(0.25), lineWidth: 1))
            }
            if hasMore { Button("Carregar mais recordes") { Task { await load() } }.disabled(loading) }
        }.task(id: "\(refreshID):\(search)") {
            if !search.isEmpty { try? await Task.sleep(nanoseconds: 300_000_000) }
            guard !Task.isCancelled else { return }
            await load(reset: true)
        }.onChange(of: search) { _ in
            requestID = UUID()
            items = []
            hasMore = false
            loading = true
            error = nil
        }
    }

    func recordTitle(_ record: PersonalRecord) -> String {
        switch record.metricType {
        case "max_load": return "Maior carga"
        case "estimated_1rm": return "1RM estimado"
        case "reps_at_load":
            let load = record.loadKg.map { " · \($0.formatted(.number.precision(.fractionLength(0...1)))) kg" } ?? ""
            return "Mais repetições\(load)"
        default: return "Recorde"
        }
    }

    func recordValue(_ record: PersonalRecord) -> String {
        let value = record.newValue.formatted(.number.precision(.fractionLength(0...1)))
        return "\(value) \(record.metricType == "reps_at_load" ? "reps" : "kg")"
    }

    func load(reset: Bool = false) async {
        guard reset || !loading else { return }
        let id = UUID()
        requestID = id
        loading = true
        error = nil
        defer { if requestID == id { loading = false } }
        if reset { offset = 0; items = []; hasMore = false }
        do {
            let page = try await session.api.getPersonalRecords(offset: offset, search: search.trimmingCharacters(in: .whitespacesAndNewlines))
            guard requestID == id, !Task.isCancelled else { return }
            if reset { items = page.items }
            else {
                let known = Set(items.map(\.id))
                items.append(contentsOf: page.items.filter { !known.contains($0.id) })
            }
            offset = page.offset + page.items.count
            hasMore = page.items.count == page.limit
        } catch { if requestID == id, !isNativeRequestCancellation(error) { self.error = error.localizedDescription } }
    }
}
