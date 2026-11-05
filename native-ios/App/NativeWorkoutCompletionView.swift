import PhotosUI
import SwiftUI
import UIKit
import FitTrackerCore

struct NativeWorkoutCompletionView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let summary: WorkoutActivitySummary
    let onClose: () -> Void
    var syncMessage: String? = nil

    @State private var celebrating = false
    @State private var didCelebrate = false
    @State private var showShare = false

    private var duration: String {
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
                        Text(L("TREINO FINALIZADO")).font(.caption.weight(.bold)).tracking(2).foregroundColor(.cyan)
                        Text(L("Você fez acontecer.")).font(.system(size: 30, weight: .bold, design: .rounded)).foregroundColor(.white)
                        Text(L("Agora é hora de recuperar.")).font(.subheadline).foregroundColor(.white.opacity(0.62))
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
                        stat("◷", duration, L("Duração"))
                        stat("✓", "\(summary.exercisesPerformed)", L("Exercícios"))
                        stat("≋", "\(summary.setsPerformed + summary.exercises.reduce(0) { $0 + ($1.completionMode == "planned" ? ($1.setsPlanned ?? $1.plannedPrescription?.sets ?? 0) : 0) })", L("Séries"))
                    }
                    if let calories = summary.energyEstimate?.activeKcal {
                        VStack(alignment: .leading, spacing: 7) {
                            Label(L("≈\(Int((calories / 10).rounded()) * 10) kcal ativas · estimativa"), systemImage: "flame.fill")
                                .font(.headline).foregroundColor(.orange)
                            Text(L("Estimativa pelo seu peso, duração confirmada e tipo de treino. Representa o gasto acima do repouso e pode variar conforme seu esforço."))
                                .font(.footnote).foregroundColor(.white.opacity(0.62))
                        }.frame(maxWidth: .infinity, alignment: .leading).padding(15)
                            .background(Color.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 14))
                    } else if summary.energyEstimate?.reason == "missing_weight" {
                        Text(L("Atualize seu peso no perfil para estimar as calorias dos próximos treinos."))
                            .font(.footnote).foregroundColor(.white.opacity(0.62))
                    } else if summary.energyEstimate?.reason != nil {
                        Text(L("Não foi possível estimar as calorias deste treino com os dados disponíveis."))
                            .font(.footnote).foregroundColor(.white.opacity(0.62))
                    }
                    if let volume = summary.volumeTotalKg {
                        HStack {
                            Text(L("Volume registrado")).foregroundColor(.white.opacity(0.65))
                            Spacer()
                            Text("\(volume.formatted(.number.precision(.fractionLength(0...1)))) kg").fontWeight(.bold).foregroundColor(.cyan)
                        }
                        .font(.subheadline).padding(15)
                        .background(Color.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 14))
                    }

                    DisclosureGroup(L("Ver exercícios e séries")) {
                        VStack(alignment: .leading, spacing: 16) {
                            ForEach(summary.exercises) { exercise in
                                VStack(alignment: .leading, spacing: 7) {
                                    Text(exercise.name).font(.subheadline.bold()).foregroundColor(.white)
                                    if exercise.completionMode == "planned", let prescription = exercise.plannedPrescription {
                                        Text(L("Conforme o plano · \(prescription.sets.map(String.init) ?? "—") séries · \(prescription.reps ?? "—")"))
                                            .font(.caption).foregroundColor(.white.opacity(0.62))
                                    } else if exercise.sets.isEmpty {
                                        Text(L("Concluído sem detalhes de séries.")).font(.caption).foregroundColor(.white.opacity(0.55))
                                    } else {
                                        ForEach(exercise.sets) { set in
                                            HStack(spacing: 4) {
                                                Text(L("Série \(set.setOrder)"))
                                                Text("· \(set.repetitions) reps")
                                                if let load = set.loadKg { Text("· \(load.formatted(.number.precision(.fractionLength(0...1)))) kg") }
                                                if set.isWarmup { Text(L("· aquecimento")) }
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

                    Button {
                        onClose()
                        NotificationCenter.default.post(name: Notification.Name("fitTrackerNavigate"), object: nil, userInfo: ["tab": "progress"])
                    } label: {
                        Label(L("Ver meu progresso"), systemImage: "chart.line.uptrend.xyaxis")
                            .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 15)
                    }.fitGlassButton(prominent: true).tint(Color.blue)

                    Button { showShare = true } label: {
                        Label(L("Compartilhar treino"), systemImage: "square.and.arrow.up")
                            .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 15)
                    }
                    .fitGlassButton().tint(Color.cyan)
                    .disabled(summary.exercises.isEmpty)

                    Button(L("Voltar para Treino"), action: onClose)
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

    private func stat(_ symbol: String, _ value: String, _ label: String) -> some View {
        VStack(spacing: 7) {
            Text(symbol).font(.title3).foregroundColor(.cyan)
            Text(value).font(.system(size: 21, weight: .bold, design: .rounded)).foregroundColor(.white)
            Text(label).font(.caption2).foregroundColor(.white.opacity(0.56))
        }.frame(maxWidth: .infinity).padding(.vertical, 6)
    }
}

private struct WorkoutConfetti: View {
    private let colors: [Color] = [.cyan, .blue, .white.opacity(0.9), Color(red: 0.55, green: 0.78, blue: 1)]
    @State private var falling = false

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
    @Environment(\.dismiss) private var dismiss
    let summary: WorkoutActivitySummary
    let duration: String

    @State private var selectedExerciseId: Int
    @State private var photo: UIImage?
    @State private var showingPhotoPicker = false
    @State private var shareImage: WorkoutSharedImage?

    init(summary: WorkoutActivitySummary, duration: String) {
        self.summary = summary
        self.duration = duration
        _selectedExerciseId = State(initialValue: summary.exercises.first?.id ?? 0)
    }

    private var selectedExercise: WorkoutPerformedExercise? {
        summary.exercises.first { $0.id == selectedExerciseId } ?? summary.exercises.first
    }

    var body: some View {
        NavigationView {
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
                            Label(photo == nil ? L("Adicionar foto") : L("Trocar foto"), systemImage: "photo")
                                .frame(maxWidth: .infinity).padding(.vertical, 12)
                        }.fitGlassButton()
                        if photo != nil {
                            Button(L("Remover")) { photo = nil }.fitGlassButton()
                        }
                    }

                    VStack(alignment: .leading, spacing: 9) {
                        Text(L("EXERCÍCIO EM DESTAQUE")).font(.caption.bold()).tracking(1).foregroundColor(.secondary)
                        Picker(L("Exercício em destaque"), selection: $selectedExerciseId) {
                            ForEach(summary.exercises) { exercise in Text(exercise.name).tag(exercise.id) }
                        }.pickerStyle(.menu).frame(maxWidth: .infinity, alignment: .leading)
                    }.frame(maxWidth: .infinity, alignment: .leading)

                    Text(L("O total considera os \(summary.exercisesPerformed) exercícios do treino. A foto permanece no aparelho até você compartilhar."))
                        .font(.caption).foregroundColor(.secondary).frame(maxWidth: .infinity, alignment: .leading)

                    Button(action: prepareShare) {
                        Label(L("Compartilhar"), systemImage: "square.and.arrow.up")
                            .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 14)
                    }.fitGlassButton(prominent: true).disabled(selectedExercise == nil)
                }.padding(20)
            }
            .background(Color(red: 0.025, green: 0.045, blue: 0.075).ignoresSafeArea())
            .navigationTitle(L("Compartilhar treino"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { dismiss() } } }
            .sheet(isPresented: $showingPhotoPicker) {
                WorkoutPhotoPicker(image: $photo, isPresented: $showingPhotoPicker)
            }
            .sheet(item: $shareImage) { item in
                WorkoutActivitySheet(items: [item.image])
            }
        }.navigationViewStyle(.stack).preferredColorScheme(.dark)
    }

    private func prepareShare() {
        guard let exercise = selectedExercise else { return }
        shareImage = renderShareCard(summary: summary, exercise: exercise, duration: duration, photo: photo).map { WorkoutSharedImage(image: $0) }
    }
}

private struct WorkoutSharedImage: Identifiable {
    let id = UUID()
    let image: UIImage
}

private struct WorkoutShareCard: View {
    let summary: WorkoutActivitySummary
    let exercise: WorkoutPerformedExercise?
    let duration: String
    let photo: UIImage?

    private var loads: [Double] { exercise?.sets.compactMap(\.loadKg) ?? [] }
    private var distinctLoads: Set<Double> { Set(loads) }
    private var distinctReps: Set<Int> { Set(exercise?.sets.map(\.repetitions) ?? []) }
    private var loadText: String {
        guard !distinctLoads.isEmpty else { return "—" }
        guard loads.count == (exercise?.sets.count ?? 0) else { return "—" }
        guard distinctLoads.count == 1 else { return L("Varia") }
        return (distinctLoads.first ?? 0).formatted(.number.precision(.fractionLength(0...1)))
    }
    private var repsText: String {
        guard !distinctReps.isEmpty else { return exercise?.plannedPrescription?.reps ?? "—" }
        return distinctReps.count > 1 ? L("Varia") : "\(distinctReps.first ?? 0)"
    }

    var body: some View {
        Image(uiImage: artwork()).resizable().aspectRatio(9 / 16, contentMode: .fit)
    }

    func artwork() -> UIImage {
        NativeShareArtwork.render(photo: photo) { context in
            NativeShareArtwork.text(L("TREINO CONCLUÍDO"), x: 88, baseline: 1260, size: 34, weight: .bold, color: NativeShareArtwork.blue)
            NativeShareArtwork.text(summary.workoutName, x: 84, baseline: 1358, size: 84, weight: .heavy)
            let count = summary.exercisesPerformed
            NativeShareArtwork.text(L("\(duration) · \(count) \(count == 1 ? L("exercício") : L("exercícios"))"), x: 88, baseline: 1416, size: 32, weight: .medium, color: .lightGray)
            NativeShareArtwork.text(exercise?.name ?? L("Treino"), x: 88, baseline: 1501, size: 38, weight: .semibold)
            let load = loadText == "—" || loadText == "Varia" ? loadText : "\(loadText) kg"
            let sets = exercise?.sets.isEmpty == false ? "\(exercise?.sets.count ?? 0)" : exercise?.plannedPrescription?.sets.map(String.init) ?? "—"
            NativeShareArtwork.metric(load, label: "CARGA", x: 88, blue: false, context: context)
            NativeShareArtwork.metric(sets, label: L("SÉRIES"), x: 398, blue: true, context: context)
            NativeShareArtwork.metric(repsText, label: L("REPETIÇÕES"), x: 708, blue: false, context: context)
        }
    }
}

@MainActor
private func renderShareCard(summary: WorkoutActivitySummary, exercise: WorkoutPerformedExercise, duration: String, photo: UIImage?) -> UIImage? {
    WorkoutShareCard(summary: summary, exercise: exercise, duration: duration, photo: photo).artwork()
}

private struct WorkoutPhotoPicker: UIViewControllerRepresentable {
    @Binding var image: UIImage?
    @Binding var isPresented: Bool

    func makeUIViewController(context: Context) -> PHPickerViewController {
        var configuration = PHPickerConfiguration()
        configuration.filter = .images
        configuration.selectionLimit = 1
        let picker = PHPickerViewController(configuration: configuration)
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ controller: PHPickerViewController, context: Context) { }
    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, PHPickerViewControllerDelegate {
        let parent: WorkoutPhotoPicker
        init(_ parent: WorkoutPhotoPicker) { self.parent = parent }

        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            guard let provider = results.first?.itemProvider, provider.canLoadObject(ofClass: UIImage.self) else {
                parent.isPresented = false
                return
            }
            provider.loadObject(ofClass: UIImage.self) { image, _ in
                DispatchQueue.main.async {
                    if let image = image as? UIImage { self.parent.image = image }
                    self.parent.isPresented = false
                }
            }
        }
    }
}

private struct WorkoutActivitySheet: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController { UIActivityViewController(activityItems: items, applicationActivities: nil) }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) { }
}
