import Capacitor
import UIKit

#if canImport(GoogleSignIn)
import GoogleSignIn
#endif

@objc(FitTrackerGoogleAuth)
public class FitTrackerGoogleAuthPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "FitTrackerGoogleAuth"
    public let jsName = "FitTrackerGoogleAuth"
    private var signInInProgress = false
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "signIn", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "signOut", returnType: CAPPluginReturnPromise),
    ]

    @objc public func signIn(_ call: CAPPluginCall) {
        #if canImport(GoogleSignIn)
        DispatchQueue.main.async {
            guard !self.signInInProgress else {
                call.reject("Um login já está em andamento.", "sign_in_in_progress")
                return
            }
            guard let clientID = Bundle.main.object(forInfoDictionaryKey: "GIDClientID") as? String,
                  !clientID.isEmpty,
                  !clientID.hasPrefix("$(") else {
                call.reject("O login Google do iOS ainda não foi configurado.")
                return
            }
            let serverClientID = Bundle.main.object(forInfoDictionaryKey: "GIDServerClientID") as? String
            GIDSignIn.sharedInstance.configuration = GIDConfiguration(clientID: clientID, serverClientID: serverClientID)
            guard let presenter = self.bridge?.viewController else {
                call.reject("Não foi possível abrir o login Google.")
                return
            }
            self.signInInProgress = true
            GIDSignIn.sharedInstance.signIn(withPresenting: presenter) { result, error in
                DispatchQueue.main.async {
                    defer { self.signInInProgress = false }
                    if let error = error {
                        if (error as NSError).code == GIDSignInError.canceled.rawValue {
                            call.reject("cancelled")
                        } else {
                            call.reject(error.localizedDescription)
                        }
                        return
                    }
                    guard let token = result?.user.idToken?.tokenString else {
                        call.reject("O Google não devolveu um token de identidade.")
                        return
                    }
                    call.resolve(["idToken": token])
                }
            }
        }
        #else
        call.reject("O SDK GoogleSignIn não está disponível neste build.")
        #endif
    }

    @objc public func signOut(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            #if canImport(GoogleSignIn)
            GIDSignIn.sharedInstance.signOut()
            #endif
            call.resolve()
        }
    }
}

@objc(FitTrackerConsole)
final class FitTrackerConsolePlugin: CAPPlugin, CAPBridgedPlugin {
    let identifier = "FitTrackerConsole"
    let jsName = "Console"
    let pluginMethods: [CAPPluginMethod] = [CAPPluginMethod(name: "log", returnType: CAPPluginReturnNone)]

    @objc func log(_ call: CAPPluginCall) {
        guard let message = call.getString("message"),
              ["[Auth]", "[API]", "[App]"].contains(where: { message.hasPrefix($0) }) else { return }
        Swift.print(message)
    }
}

final class FitTrackerBridgeViewController: CAPBridgeViewController {
    override public func capacitorDidLoad() {
        bridge?.registerPluginInstance(FitTrackerGoogleAuthPlugin())
        bridge?.registerPluginInstance(FitTrackerSharePlugin())
        bridge?.registerPluginInstance(FitTrackerConsolePlugin())
    }
}
