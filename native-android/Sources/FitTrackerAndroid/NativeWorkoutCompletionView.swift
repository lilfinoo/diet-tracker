import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
#if !os(Android)
import UIKit
#endif
import FitTrackerCore

struct NativeWorkoutCompletionView: View {
    @Environment(\.accessibilityReduceMotion) var reduceMotion
    let summary: WorkoutActivitySummary
    let onClose: () -> Void
    var syncMessage: String? = nil

    @State var celebrating = false
    @State var didCelebrate = false
    @State var showShare = false

    var duration: String {
        let minutes = max(0, summary.durationSeconds) / 60
        return minutes >= 60 ? "\(minutes / 60)h \(minutes % 60)min" : "\(minutes) min"
    }

    var body: some View {
        ZStack {
            Color(red: 0.025, green: 0.045, blue: 0.075).ignoresSafeArea()
            ScrollView {
                VStack(spacing: 22) {
                    Image(systemName: "checkmark")
                        .font(.system(size: 33, weight: .bold))
                        .foregroundColor(.white)
                        .frame(width: 74, height: 74)
                        .background(LinearGradient(colors: [Color.blue, Color.cyan.opacity(0.75)], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 25))
                        .shadow(color: .blue.opacity(0.45), radius: 24)
                        .rotationEffect(.degrees(celebrating && !reduceMotion ? 360 : 0))
                        .animation(reduceMotion ? nil : .spring(response: 0.75, dampingFraction: 0.62), value: celebrating)

                    VStack(spacing: 8) {
                        Text("TREINO FINALIZADO").font(.caption.weight(.bold)).tracking(2).foregroundColor(.cyan)
                        Text("Você fez acontecer.").font(.system(size: 30, weight: .bold, design: .rounded)).foregroundColor(.white)
                        Text("Agora é hora de recuperar.").font(.subheadline).foregroundColor(.white.opacity(0.62))
                    }

                    if let syncMessage {
                        Label(syncMessage, systemImage: "arrow.triangle.2.circlepath")
                            .font(.footnote).foregroundColor(.cyan)
                            .padding(12).frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.blue.opacity(0.10), in: RoundedRectangle(cornerRadius: 12))
                    }

                    VStack(alignment: .leading, spacing: 5) {
                        Text(summary.workoutName).font(.title2.bold()).foregroundColor(.white)
                        Text(summary.planName).font(.subheadline).foregroundColor(.white.opacity(0.58))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(20)
                    .background(LinearGradient(colors: [Color(red: 0.10, green: 0.21, blue: 0.34), Color(red: 0.055, green: 0.11, blue: 0.19)], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 20))
                    .overlay(RoundedRectangle(cornerRadius: 20).stroke(Color.blue.opacity(0.42), lineWidth: 1))

                    HStack(spacing: 0) {
                        stat("◷", duration, "Duração")
                        stat("✓", "\(summary.exercisesPerformed)", "Exercícios")
                        stat("≋", "\(summary.setsPerformed + summary.exercises.reduce(0) { $0 + ($1.completionMode == "planned" ? ($1.setsPlanned ?? $1.plannedPrescription?.sets ?? 0) : 0) })", "Séries")
                    }
                    if let volume = summary.volumeTotalKg {
                        HStack {
                            Text("Volume registrado").foregroundColor(.white.opacity(0.65))
                            Spacer()
                            Text("\(volume.formatted(.number.precision(.fractionLength(0...1)))) kg").fontWeight(.bold).foregroundColor(.cyan)
                        }
                        .font(.subheadline).padding(15)
                        .background(Color.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 14))
                    }

                    DisclosureGroup("Ver exercícios e séries") {
                        VStack(alignment: .leading, spacing: 16) {
                            ForEach(summary.exercises) { exercise in
                                VStack(alignment: .leading, spacing: 7) {
                                    Text(exercise.name).font(.subheadline.bold()).foregroundColor(.white)
                                    if exercise.completionMode == "planned", let prescription = exercise.plannedPrescription {
                                        Text("Conforme o plano · \(prescription.sets.map(String.init) ?? "—") séries · \(prescription.reps ?? "—")")
                                            .font(.caption).foregroundColor(.white.opacity(0.62))
                                    } else if exercise.sets.isEmpty {
                                        Text("Concluído sem detalhes de séries.").font(.caption).foregroundColor(.white.opacity(0.55))
                                    } else {
                                        ForEach(exercise.sets) { set in
                                            HStack(spacing: 4) {
                                                Text("Série \(set.setOrder)")
                                                Text("· \(set.repetitions) reps")
                                                if let load = set.loadKg { Text("· \(load.formatted(.number.precision(.fractionLength(0...1)))) kg") }
                                                if set.isWarmup { Text("· aquecimento") }
                                            }.font(.caption).foregroundColor(.white.opacity(0.62))
                                        }
                                    }
                                }
                                if exercise.id != summary.exercises.last?.id { Divider().overlay(Color.white.opacity(0.1)) }
                            }
                        }.padding(.top, 12)
                    }
                    .font(.subheadline.weight(.semibold)).foregroundColor(.white.opacity(0.82))
                    .tint(.cyan)

                    Button { showShare = true } label: {
                        Label("Compartilhar treino", systemImage: "square.and.arrow.up")
                            .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 15)
                    }
                    .buttonStyle(.borderedProminent).tint(Color.blue)
                    .disabled(summary.exercises.isEmpty)

                    Button("Voltar para Treino", action: onClose)
                        .font(.subheadline.weight(.medium)).foregroundColor(.white.opacity(0.65)).padding(.bottom, 12)
                }
                .padding(.horizontal, 22).padding(.top, 34)
            }
            if celebrating && !reduceMotion { WorkoutConfetti().allowsHitTesting(false).transition(.opacity) }
        }
        .preferredColorScheme(.dark)
        .fullScreenCover(isPresented: $showShare) {
            NativeWorkoutShareView(summary: summary, duration: duration)
        }
        .onAppear {
            guard !reduceMotion, !didCelebrate else { return }
            didCelebrate = true
            celebrating = true
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.4) { celebrating = false }
        }
    }

    func stat(_ symbol: String, _ value: String, _ label: String) -> some View {
        VStack(spacing: 7) {
            Text(symbol).font(.title3).foregroundColor(.cyan)
            Text(value).font(.system(size: 21, weight: .bold, design: .rounded)).foregroundColor(.white)
            Text(label).font(.caption2).foregroundColor(.white.opacity(0.56))
        }.frame(maxWidth: .infinity).padding(.vertical, 6)
    }
}

struct WorkoutConfetti: View {
    let colors: [Color] = [.cyan, .blue, .white.opacity(0.9), Color(red: 0.55, green: 0.78, blue: 1)]
    @State var falling = false

    var body: some View {
        GeometryReader { proxy in
            ForEach(0..<28, id: \.self) { index in
                RoundedRectangle(cornerRadius: 2)
                    .fill(colors[index % colors.count])
                    .frame(width: index.isMultiple(of: 3) ? 5 : 3, height: 9)
                    .position(x: proxy.size.width * CGFloat((index * 37) % 100) / 100,
                              y: falling ? proxy.size.height + 20 : -20)
                    .rotationEffect(.degrees(falling ? Double(index * 73) : 0))
                    .opacity(falling ? 0 : 0.85)
                    .animation(.easeIn(duration: 1.7 + Double(index % 6) * 0.12).delay(Double(index % 8) * 0.045), value: falling)
            }
        }
        .ignoresSafeArea()
        .onAppear { falling = true }
    }
}

struct NativeWorkoutShareView: View {
    @Environment(\.dismiss) var dismiss
    let summary: WorkoutActivitySummary
    let duration: String

    @State var selectedExerciseId: Int
    @State var photo: NativePhoto?
    @State var showingPhotoPicker = false
    @State var shareError: String?
    @State var preparingShare = false
    #if !os(Android)
    @State var shareImage: NativePhoto?
    #endif

    init(summary: WorkoutActivitySummary, duration: String) {
        self.summary = summary
        self.duration = duration
        _selectedExerciseId = State(initialValue: summary.exercises.first?.id ?? 0)
    }

    var selectedExercise: WorkoutPerformedExercise? {
        summary.exercises.first { $0.id == selectedExerciseId } ?? summary.exercises.first
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    GeometryReader { proxy in
                        WorkoutShareCard(summary: summary, exercise: selectedExercise, duration: duration, photo: photo)
                            .scaleEffect(proxy.size.width / 360, anchor: .topLeading)
                            .frame(width: 360, height: 640, alignment: .topLeading)
                            .frame(width: proxy.size.width, height: proxy.size.height, alignment: .topLeading)
                    }
                    .aspectRatio(9 / 16, contentMode: .fit)
                    .clipShape(RoundedRectangle(cornerRadius: 20))
                    .padding(.horizontal, 28)

                    HStack(spacing: 10) {
                        Button { showingPhotoPicker = true } label: {
                            Label(photo == nil ? "Adicionar foto" : "Trocar foto", systemImage: "photo")
                                .frame(maxWidth: .infinity).padding(.vertical, 12)
                        }.buttonStyle(.bordered)
                        if photo != nil {
                            Button("Remover") { photo = nil }.buttonStyle(.bordered)
                        }
                    }

                    VStack(alignment: .leading, spacing: 9) {
                        Text("EXERCÍCIO EM DESTAQUE").font(.caption.bold()).tracking(1).foregroundColor(.secondary)
                        Picker("Exercício em destaque", selection: $selectedExerciseId) {
                            ForEach(summary.exercises) { exercise in Text(exercise.name).tag(exercise.id) }
                        }.pickerStyle(.menu).frame(maxWidth: .infinity, alignment: .leading)
                    }.frame(maxWidth: .infinity, alignment: .leading)

                    Text("O total considera os \(summary.exercisesPerformed) exercícios do treino. A foto permanece no aparelho até você compartilhar.")
                        .font(.caption).foregroundColor(.secondary).frame(maxWidth: .infinity, alignment: .leading)

                    Button(action: prepareShare) {
                        Label("Compartilhar", systemImage: "square.and.arrow.up")
                            .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 14)
                    }.buttonStyle(.borderedProminent).disabled(selectedExercise == nil || preparingShare)
                }.padding(20)
            }
            .background(Color(red: 0.025, green: 0.045, blue: 0.075).ignoresSafeArea())
            .navigationTitle("Compartilhar treino")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() } } }
            .sheet(isPresented: $showingPhotoPicker) {
                NativePhotoPicker(photo: $photo)
            }
            #if !os(Android)
            .sheet(item: $shareImage) { image in NativePhotoActivitySheet(photo: image) }
            #endif
            .alert("Não foi possível compartilhar", isPresented: Binding(get: { shareError != nil }, set: { if !$0 { shareError = nil } })) {
                Button("OK") { shareError = nil }
            } message: { Text(shareError ?? "") }
        }.preferredColorScheme(.dark)
    }

    func prepareShare() {
        guard let exercise = selectedExercise else { return }
        preparingShare = true
        Task { @MainActor in
            defer { preparingShare = false }
            guard let image = renderShareCard(summary: summary, exercise: exercise, duration: duration, photo: photo) else {
                shareError = "Não foi possível preparar a imagem do treino. Tente novamente."
                return
            }
            #if os(Android)
            do { try shareNativePhoto(image) }
            catch { shareError = error.localizedDescription }
            #else
            shareImage = image
            #endif
        }
    }
}

struct WorkoutShareCard: View {
    let summary: WorkoutActivitySummary
    let exercise: WorkoutPerformedExercise?
    let duration: String
    let photo: NativePhoto?

    var loads: [Double] { exercise?.sets.compactMap(\.loadKg) ?? [] }
    var distinctLoads: Set<Double> { Set(loads) }
    var distinctReps: Set<Int> { Set(exercise?.sets.map(\.repetitions) ?? []) }
    var loadText: String {
        guard !distinctLoads.isEmpty else { return "—" }
        guard loads.count == (exercise?.sets.count ?? 0) else { return "—" }
        guard distinctLoads.count == 1 else { return "Varia" }
        return (distinctLoads.first ?? 0).formatted(.number.precision(.fractionLength(0...1)))
    }
    var repsText: String {
        guard !distinctReps.isEmpty else { return exercise?.plannedPrescription?.reps ?? "—" }
        return distinctReps.count > 1 ? "Varia" : "\(distinctReps.first ?? 0)"
    }

    var body: some View {
        GeometryReader { proxy in
            ZStack {
                if let photo {
                    NativePhotoPreview(photo: photo).scaledToFill().frame(width: proxy.size.width, height: proxy.size.height).clipped()
                    LinearGradient(colors: [.clear, .black.opacity(0.3)], startPoint: .top, endPoint: .bottom)
                        .frame(height: proxy.size.height / 3).frame(maxHeight: .infinity, alignment: .bottom)
                } else {
                    Color(red: 0.025, green: 0.045, blue: 0.075)
                    Circle().fill(Color.blue.opacity(0.30)).frame(width: 290).blur(radius: 65).offset(x: 110, y: -150)
                }
                VStack(alignment: .leading, spacing: 10) {
                    HStack(alignment: .top, spacing: 10) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(summary.workoutName).font(.system(size: 27, weight: .heavy, design: .rounded)).lineLimit(1).minimumScaleFactor(0.65)
                            Text("\(duration) · \(summary.exercisesPerformed) \(summary.exercisesPerformed == 1 ? "exercício feito" : "exercícios feitos")")
                                .font(.system(size: 10, weight: .semibold)).tracking(0.45).foregroundColor(.white.opacity(0.8)).lineLimit(1)
                        }
                        Spacer(minLength: 0)
                        Image("FitTrackerLogo", bundle: .module).resizable().scaledToFit().frame(width: 26, height: 26)
                    }
                    Rectangle().fill(Color.white.opacity(0.18)).frame(height: 0.5)
                    Text(exercise?.name ?? "Treino").font(.system(size: 17, weight: .bold, design: .rounded)).lineLimit(2).minimumScaleFactor(0.7)
                    HStack(spacing: 0) {
                        metric("CARGA", loadText, loadText == "—" || loadText == "Varia" ? "" : "kg")
                        metric("SÉRIES", exercise?.sets.isEmpty == false ? "\(exercise?.sets.count ?? 0)" : exercise?.plannedPrescription?.sets.map(String.init) ?? "—", "")
                        metric("REPS", repsText, "")
                    }
                }
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .frame(height: proxy.size.height / 3 - 24, alignment: .center)
                .background(Color(red: 0.015, green: 0.035, blue: 0.065).opacity(photo == nil ? 0.94 : 0.68), in: RoundedRectangle(cornerRadius: 15))
                .overlay(RoundedRectangle(cornerRadius: 15).stroke(Color.cyan.opacity(0.8), lineWidth: 1))
                .padding(.horizontal, 15)
                .padding(.bottom, 12)
                .frame(maxHeight: .infinity, alignment: .bottom)
            }.clipped()
        }
    }

    func metric(_ title: String, _ value: String, _ unit: String) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title).font(.system(size: 8, weight: .bold)).tracking(0.7).foregroundColor(.white.opacity(0.62))
            HStack(alignment: .firstTextBaseline, spacing: 2) {
                Text(value).font(.system(size: 24, weight: .bold, design: .rounded)).lineLimit(1).minimumScaleFactor(0.7)
                if !unit.isEmpty { Text(unit).font(.system(size: 8)).foregroundColor(.white.opacity(0.75)) }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

@MainActor
func renderShareCard(summary: WorkoutActivitySummary, exercise: WorkoutPerformedExercise, duration: String, photo: NativePhoto?) -> NativePhoto? {
    #if os(Android)
    let card = WorkoutShareCard(summary: summary, exercise: exercise, duration: duration, photo: photo)
    guard let logoURL = Bundle.module.url(forResource: "FitTrackerLogo", withExtension: "png"),
          let logo = try? Data(contentsOf: logoURL) else { return nil }
    let sets = exercise.sets.isEmpty ? exercise.plannedPrescription?.sets.map(String.init) ?? "—" : "\(exercise.sets.count)"
    let caption = "\(duration) · \(summary.exercisesPerformed) \(summary.exercisesPerformed == 1 ? "exercício feito" : "exercícios feitos")"
    guard let path = renderAndroidWorkoutCard(photo?.data.base64EncodedString() ?? "", logo.base64EncodedString(), summary.workoutName, caption,
                                             exercise.name, card.loadText, sets, card.repsText) else { return nil }
    return try? NativePhoto(url: URL(fileURLWithPath: path))
    #else
    let designSize = CGSize(width: 360, height: 640)
    let outputSize = CGSize(width: 1080, height: 1920)
    let card = WorkoutShareCard(summary: summary, exercise: exercise, duration: duration, photo: photo)
        .environment(\.colorScheme, .dark).foregroundColor(.white)
        .frame(width: designSize.width, height: designSize.height)
    let controller = UIHostingController(rootView: card)
    controller.view.bounds = CGRect(origin: .zero, size: designSize)
    controller.view.frame = CGRect(origin: .zero, size: designSize)
    controller.view.backgroundColor = .clear
    controller.view.setNeedsLayout()
    controller.view.layoutIfNeeded()
    let format = UIGraphicsImageRendererFormat()
    format.scale = 1
    let renderer = UIGraphicsImageRenderer(size: outputSize, format: format)
    let image = renderer.image { context in
        context.cgContext.scaleBy(x: 3, y: 3)
        controller.view.layer.render(in: context.cgContext)
    }
    return image.pngData().flatMap { try? NativePhoto(data: $0) }
    #endif
}

#if SKIP
// Match the approved 360 × 640 share card at a 3× export resolution.
func renderAndroidWorkoutCard(_ photo: String, _ logo: String, _ workout: String, _ caption: String,
                              _ exercise: String, _ load: String, _ sets: String, _ reps: String) -> String? {
    NativeWorkoutPlatform.render(photo: photo, logo: logo, workout: workout, caption: caption, exercise: exercise, load: load, sets: sets, reps: reps)
}
#endif
