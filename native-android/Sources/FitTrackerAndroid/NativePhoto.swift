import Foundation
import SwiftUI
#if os(Android)
import SkipFuse
#else
import UIKit
import PhotosUI
#endif

struct NativePhoto: Identifiable, Sendable {
    let id = UUID()
    let data: Data
    let url: URL

    init(data: Data) throws {
        self.data = data
        #if os(Android)
        let directory = URL(fileURLWithPath: try androidPhotoCacheDirectory())
        #else
        let directory = FileManager.default.temporaryDirectory
        #endif
        let fileExtension = data.starts(with: [0x89, 0x50, 0x4e, 0x47]) ? "png" : "jpg"
        url = directory.appendingPathComponent("fit-photo-\(UUID().uuidString).\(fileExtension)")
        try data.write(to: url, options: .atomic)
    }

    init(url: URL) throws {
        data = try Data(contentsOf: url)
        self.url = url
    }
}

struct NativePhotoPreview: View {
    let photo: NativePhoto
    var body: some View {
        AsyncImage(url: photo.url) { image in image.resizable() } placeholder: { ProgressView() }
    }
}

func nativePhotoLogo() throws -> URL {
    guard let source = Bundle.module.url(forResource: "FitTrackerLogo", withExtension: "png") else {
        throw CocoaError(.fileNoSuchFile)
    }
    #if os(Android)
    let directory = URL(fileURLWithPath: try androidPhotoCacheDirectory())
    #else
    let directory = FileManager.default.temporaryDirectory
    #endif
    let destination = directory.appendingPathComponent("fit-tracker-official-logo.png")
    if !FileManager.default.fileExists(atPath: destination.path) {
        try Data(contentsOf: source).write(to: destination, options: .atomic)
    }
    return destination
}

struct NativePhotoPicker: View {
    @Binding var photo: NativePhoto?
    var camera = false
    @Environment(\.dismiss) var dismiss
    @State var error: String?
    @State var processing = false
    @State var preparationTask: Task<Void, Never>?
    @State var pickerId = UUID().uuidString
    @State var active = true

    var body: some View {
        VStack(spacing: 18) {
            #if os(Android)
            ComposeView {
                AndroidPhotoPickerComposer(camera: camera) { url, failure in
                    guard active else {
                        if let url { try? androidDiscardCapture(source: url) }
                        return
                    }
                    if let failure { error = failure; return }
                    guard let url else { dismiss(); return }
                    processing = true
                    preparationTask?.cancel()
                    preparationTask = Task {
                        do {
                            let path = try await Task.detached(priority: .userInitiated) {
                                try androidPreparePhoto(source: url)
                            }.value
                            guard !Task.isCancelled, active else {
                                try? FileManager.default.removeItem(atPath: path)
                                return
                            }
                            do { photo = try NativePhoto(url: URL(fileURLWithPath: path)) }
                            catch { try? FileManager.default.removeItem(atPath: path); throw error }
                            dismiss()
                        } catch {
                            guard !Task.isCancelled, active else { return }
                            self.error = "Não foi possível abrir esta foto. Escolha outra imagem."
                        }
                        processing = false
                    }
                }
            }
            .androidCompositionBoundary(id: pickerId, inputs: camera)
            .frame(width: 1, height: 1)
            #else
            HostPhotoPicker(photo: $photo, camera: camera).ignoresSafeArea()
            #endif
            if processing { ProgressView("Preparando foto…") }
            if let error { Text(error).foregroundColor(.red) }
            Button("Fechar") { active = false; preparationTask?.cancel(); dismiss() }
        }.padding(20)
        .onDisappear { active = false; preparationTask?.cancel() }
    }
}

#if os(Android)
func shareNativePhoto(_ photo: NativePhoto) throws {
    try androidSharePhoto(path: photo.url.path)
}
#endif

#if !os(Android)
struct NativePhotoActivitySheet: UIViewControllerRepresentable {
    let photo: NativePhoto
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: [photo.url], applicationActivities: nil)
    }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) { }
}

struct HostPhotoPicker: UIViewControllerRepresentable {
    @Binding var photo: NativePhoto?
    let camera: Bool
    @Environment(\.dismiss) var dismiss
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIViewController(context: Context) -> UIViewController {
        if camera, UIImagePickerController.isSourceTypeAvailable(.camera) {
            let picker = UIImagePickerController()
            picker.sourceType = .camera
            picker.delegate = context.coordinator
            return picker
        }
        var config = PHPickerConfiguration()
        config.filter = .images
        config.selectionLimit = 1
        let picker = PHPickerViewController(configuration: config)
        picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ controller: UIViewController, context: Context) { }
    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate, PHPickerViewControllerDelegate {
        let owner: HostPhotoPicker
        init(_ owner: HostPhotoPicker) { self.owner = owner }
        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage, let data = hostPreparePhoto(image) { owner.photo = try? NativePhoto(data: data) }
            owner.dismiss()
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { owner.dismiss() }
        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            guard let provider = results.first?.itemProvider else { owner.dismiss(); return }
            provider.loadObject(ofClass: UIImage.self) { image, _ in
                DispatchQueue.main.async {
                    if let image = image as? UIImage, let data = hostPreparePhoto(image) { self.owner.photo = try? NativePhoto(data: data) }
                    self.owner.dismiss()
                }
            }
        }
    }
}

func hostPreparePhoto(_ image: UIImage) -> Data? {
    let scale = min(1, 1600 / max(image.size.width, image.size.height))
    let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
    let format = UIGraphicsImageRendererFormat(); format.scale = 1
    return UIGraphicsImageRenderer(size: size, format: format).image { _ in image.draw(in: CGRect(origin: .zero, size: size)) }.jpegData(compressionQuality: 0.8)
}
#endif

#if SKIP
struct AndroidPhotoPickerComposer: ContentComposer {
    let camera: Bool
    let completion: (String?, String?) -> Void
    init(camera: Bool, completion: @escaping (String?, String?) -> Void) {
        self.camera = camera
        self.completion = completion
    }
    @Composable func Compose(context: ComposeContext) {
        NativePhotoPlatform.Picker(camera: camera, completion: completion)
    }
}

func androidPhotoCacheDirectory() throws -> String {
    NativePhotoPlatform.directory(ProcessInfo.processInfo.androidContext).absolutePath
}

func androidPreparePhoto(source: String) throws -> String {
    NativePhotoPlatform.prepare(ProcessInfo.processInfo.androidContext, source)
}

func androidDiscardCapture(source: String) throws {
    NativePhotoPlatform.discardCapture(ProcessInfo.processInfo.androidContext, source)
}

func androidSharePhoto(path: String) throws {
    guard let activity = UIApplication.shared.androidActivity else { throw java.lang.IllegalStateException("Abra o aplicativo para compartilhar a imagem.") }
    NativePhotoPlatform.share(activity, path)
}
#endif
