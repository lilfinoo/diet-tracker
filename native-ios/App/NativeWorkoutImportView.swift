import SwiftUI
import PhotosUI
import Vision
import ImageIO
import FitTrackerCore

struct NativeWorkoutImportView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @State private var choosingPhoto = false
    @State private var reading = false
    @State private var error: String?
    @State private var draft: WorkoutTextImport?
    @State private var recognitionTask: Task<Void, Never>?
    @State private var preview: WorkoutTextImport?
    @FocusState private var editingText: Bool

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(L("Do WhatsApp para o seu treino"))
                            .font(FitTrackerTheme.sectionTitle)
                        Text(L("Cole a mensagem do seu personal ou envie uma foto. Depois, confira os exercícios antes de salvar."))
                            .font(.subheadline).foregroundColor(.secondary)
                    }
                    exampleCard
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text(L("Seu treino")).font(.headline)
                            Spacer()
                            Button { choosingPhoto = true; editingText = false } label: {
                                Label(L("Usar foto"), systemImage: "photo")
                                    .font(.subheadline.weight(.semibold))
                            }.disabled(reading)
                        }
                        ZStack(alignment: .topLeading) {
                            if text.isEmpty {
                                Text(L("Cole aqui o treino que recebeu…"))
                                    .foregroundColor(.secondary).padding(.horizontal, 12).padding(.top, 17)
                                    .allowsHitTesting(false)
                            }
                            if #available(iOS 16.0, *) {
                                textEditor.scrollContentBackground(.hidden)
                            } else { textEditor }
                        }
                        .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.white.opacity(0.12)))
                        if reading { ProgressView(L("Lendo o texto da imagem…")) }
                        if let preview {
                            Label(L("\(preview.days.count) treinos · \(preview.days.reduce(0) { $0 + $1.exercises.count }) exercícios identificados"), systemImage: "checkmark.circle.fill")
                                .font(.caption).foregroundColor(FitTrackerTheme.electricBlue)
                        }
                        Text(L("Uma linha por exercício, com séries e repetições. Ex.: Supino reto 3x10 · descanso 60s."))
                            .font(.caption).foregroundColor(.secondary)
                        Text(L("Aceita até 7 treinos, com 12 exercícios em cada um. Fotos em colunas ou tabelas podem precisar de ajustes."))
                            .font(.caption).foregroundColor(.secondary)
                    }
                    if let error {
                        Label(NativeLocalization.display(error), systemImage: "exclamationmark.circle")
                            .font(.subheadline).foregroundColor(.orange)
                    }
                }
                .padding(FitTrackerTheme.pagePadding)
            }
            .background(FitTrackerTheme.background.ignoresSafeArea())
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 8) {
                    Button {
                        editingText = false
                        do { draft = try WorkoutTextParser.parse(text); error = nil }
                        catch { self.error = error.localizedDescription }
                    } label: {
                        Label(L("Revisar treino"), systemImage: "arrow.right")
                            .frame(maxWidth: .infinity).fitPrimarySurface()
                    }
                    .buttonStyle(.plain)
                    .disabled(reading || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .opacity(reading || text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? 0.45 : 1)
                    Text(L("Você revisa tudo antes de salvar."))
                        .font(.caption).foregroundColor(.secondary)
                }
                .padding(.horizontal, FitTrackerTheme.pagePadding).padding(.vertical, 12)
                .fitGlassBar()
            }
            .navigationTitle(L("Importar treino")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { dismiss() } } }
                .onChange(of: text) { value in
                    preview = try? WorkoutTextParser.parse(value)
                    error = nil
                }
                .sheet(isPresented: $choosingPhoto) {
                    WorkoutImportPhotoPicker { image, message in
                        if let message { error = message }
                        if let image { read(image) }
                    }
                }
                .sheet(item: $draft) { NativeManualPlanView(kind: .workout, imported: $0) }
                .onDisappear { recognitionTask?.cancel() }
        }.navigationViewStyle(.stack)
    }

    private var textEditor: some View {
        TextEditor(text: $text)
            .font(.body).foregroundColor(.white)
            .frame(minHeight: 150).padding(8)
            .focused($editingText)
            .accessibilityLabel(L("Texto do treino para importar"))
            .disabled(reading)
    }

    private var exampleCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(L("Mensagem do personal · exemplo"), systemImage: "bubble.left.and.bubble.right")
                .font(.caption.weight(.semibold)).foregroundColor(FitTrackerTheme.electricBlue)
            Text(exampleText)
                .font(.subheadline).lineSpacing(4)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
            if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Button {
                    text = exampleText
                    editingText = false
                } label: {
                    Label(L("Usar este exemplo"), systemImage: "doc.on.doc")
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .background(Color.fitBlue.opacity(0.15), in: RoundedRectangle(cornerRadius: 12))
                }.buttonStyle(.plain).foregroundColor(FitTrackerTheme.electricBlue).disabled(reading)
            }
        }
        .padding(16).fitPremiumCard()
    }

    private var exampleText: String {
        L("Treino A - Peito e tríceps\n1. Supino reto 3x10 · descanso 60s\n2. Supino inclinado 3x12 · descanso 60s\n3. Tríceps corda 3x12 · descanso 45s\n\nTreino B - Pernas\n1. Agachamento 4x10 · descanso 90s\n2. Leg press 3x12 · descanso 60s\n3. Mesa flexora 3x12 · descanso 60s")
    }

    private func read(_ image: CGImage) {
        recognitionTask?.cancel()
        reading = true; error = nil
        recognitionTask = Task {
            do {
                let recognized = try await recognizeWorkoutText(image)
                guard !Task.isCancelled else { return }
                guard !recognized.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                    reading = false; error = L("Não encontramos texto nesta imagem. Tente uma foto mais nítida ou cole o treino."); return
                }
                // Append rather than overwrite any text already entered or a previous image.
                text = text.isEmpty ? recognized : text + "\n\n" + recognized
                reading = false
            } catch {
                guard !Task.isCancelled else { return }
                reading = false; self.error = L("Não foi possível ler esta imagem. Tente novamente ou cole o texto do treino.")
            }
        }
    }
}

private func recognizeWorkoutText(_ image: CGImage) async throws -> String {
    try await withCheckedThrowingContinuation { continuation in
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                let request = VNRecognizeTextRequest()
                request.recognitionLevel = .accurate
                let supported = try request.supportedRecognitionLanguages()
                request.recognitionLanguages = ["pt-BR", "en-US"].filter { supported.contains($0) }
                request.usesLanguageCorrection = true
                try VNImageRequestHandler(cgImage: image, orientation: .up).perform([request])
                let text = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
                continuation.resume(returning: text)
            } catch { continuation.resume(throwing: error) }
        }
    }
}

private struct WorkoutImportPhotoPicker: UIViewControllerRepresentable {
    let onImage: (CGImage?, String?) -> Void
    @Environment(\.dismiss) private var dismiss
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIViewController(context: Context) -> PHPickerViewController {
        var config = PHPickerConfiguration(); config.filter = .images; config.selectionLimit = 1
        let picker = PHPickerViewController(configuration: config); picker.delegate = context.coordinator; return picker
    }
    func updateUIViewController(_ controller: PHPickerViewController, context: Context) { }
    final class Coordinator: NSObject, PHPickerViewControllerDelegate {
        let owner: WorkoutImportPhotoPicker
        init(_ owner: WorkoutImportPhotoPicker) { self.owner = owner }
        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            guard let provider = results.first?.itemProvider else { owner.dismiss(); return }
            // File-backed downsampling avoids decoding an unrestricted full-resolution photo.
            provider.loadFileRepresentation(forTypeIdentifier: "public.image") { url, _ in
                let image: CGImage?
                if let url, let size = try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize, size <= 25_000_000,
                   let source = CGImageSourceCreateWithURL(url as CFURL, nil) {
                    image = CGImageSourceCreateThumbnailAtIndex(source, 0, [
                        kCGImageSourceCreateThumbnailFromImageAlways: true,
                        kCGImageSourceCreateThumbnailWithTransform: true,
                        kCGImageSourceThumbnailMaxPixelSize: 3000,
                    ] as CFDictionary)
                } else { image = nil }
                DispatchQueue.main.async {
                    self.owner.dismiss()
                    self.owner.onImage(image, image == nil ? L("Não foi possível abrir a imagem. Escolha uma foto de até 25 MB ou cole o texto.") : nil)
                }
            }
        }
    }
}
