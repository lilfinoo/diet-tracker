import Capacitor
import UIKit

@objc(FitTrackerShare)
public class FitTrackerSharePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "FitTrackerShare"
    public let jsName = "FitTrackerShare"
    public let pluginMethods: [CAPPluginMethod] = [CAPPluginMethod(name: "sharePNG", returnType: CAPPluginReturnPromise)]
    private var sharing = false

    @objc public func sharePNG(_ call: CAPPluginCall) {
        guard let encoded = call.getString("base64"), encoded.count <= 20_000_000,
              let data = Data(base64Encoded: encoded),
              data.starts(with: [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]) else {
            call.reject("Não foi possível ler o card PNG.")
            return
        }
        DispatchQueue.main.async { [weak self] in
            guard let self = self, let presenter = self.bridge?.viewController else {
                call.reject("Não foi possível abrir o compartilhamento.")
                return
            }
            guard !self.sharing, presenter.presentedViewController == nil else {
                call.reject("Aguarde o compartilhamento atual.")
                return
            }
            let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            let file = directory.appendingPathComponent(call.getString("filename") == "macros-card.png" ? "macros-card.png" : "treino-card.png")
            do {
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                try data.write(to: file, options: .atomic)
            } catch {
                try? FileManager.default.removeItem(at: directory)
                call.reject("Não foi possível preparar o arquivo.", nil, error)
                return
            }
            self.sharing = true
            let activity = UIActivityViewController(activityItems: [file], applicationActivities: nil)
            if let popover = activity.popoverPresentationController {
                popover.sourceView = presenter.view
                popover.sourceRect = CGRect(x: presenter.view.bounds.midX, y: presenter.view.bounds.midY, width: 1, height: 1)
                popover.permittedArrowDirections = []
            }
            activity.completionWithItemsHandler = { [weak self] _, completed, _, error in
                self?.sharing = false
                try? FileManager.default.removeItem(at: directory)
                if let error = error { call.reject("Não foi possível compartilhar o card.", nil, error) }
                else { call.resolve(["status": completed ? "shared" : "cancelled"]) }
            }
            presenter.present(activity, animated: true)
        }
    }
}
