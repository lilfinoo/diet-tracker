import Capacitor
import UIKit
import AuthenticationServices
import CryptoKit

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

@objc(FitTrackerAppleAuth)
final class FitTrackerAppleAuthPlugin: CAPPlugin, CAPBridgedPlugin, ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {
    let identifier = "FitTrackerAppleAuth"
    let jsName = "FitTrackerAppleAuth"
    let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "signIn", returnType: CAPPluginReturnPromise),
    ]
    private var pendingCall: CAPPluginCall?
    private var authorizationController: ASAuthorizationController?
    private var presentationWindow: UIWindow?

    @objc func signIn(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            guard self.pendingCall == nil else {
                call.reject("Um login já está em andamento.", "sign_in_in_progress")
                return
            }
            guard let nonce = call.getString("nonce"),
                  nonce.count >= 32, nonce.count <= 256 else {
                call.reject("O desafio do login Apple é inválido.", "invalid_nonce")
                return
            }
            guard let window = self.bridge?.viewController?.view.window else {
                call.reject("Não foi possível abrir o login Apple.", "presentation_unavailable")
                return
            }
            let request = ASAuthorizationAppleIDProvider().createRequest()
            request.requestedScopes = [.email, .fullName]
            request.nonce = SHA256.hash(data: Data(nonce.utf8)).map { String(format: "%02x", $0) }.joined()
            let controller = ASAuthorizationController(authorizationRequests: [request])
            controller.delegate = self
            controller.presentationContextProvider = self
            self.pendingCall = call
            self.presentationWindow = window
            self.authorizationController = controller
            controller.performRequests()
        }
    }

    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        return presentationWindow ?? UIWindow()
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        guard controller === authorizationController, let call = pendingCall else { return }
        defer { finish() }
        guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
              let tokenData = credential.identityToken,
              let token = String(data: tokenData, encoding: .utf8), !token.isEmpty,
              let codeData = credential.authorizationCode,
              let code = String(data: codeData, encoding: .utf8), !code.isEmpty else {
            call.reject("A Apple não devolveu os dados de autenticação.", "missing_credentials")
            return
        }
        var result: [String: Any] = ["idToken": token, "authorizationCode": code]
        if let name = credential.fullName {
            result["displayName"] = PersonNameComponentsFormatter().string(from: name)
        }
        if let email = credential.email { result["email"] = email }
        call.resolve(result)
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        guard controller === authorizationController, let call = pendingCall else { return }
        defer { finish() }
        if let authorizationError = error as? ASAuthorizationError, authorizationError.code == .canceled {
            call.reject("cancelled", "cancelled")
        } else {
            call.reject("Não foi possível concluir o login Apple. Tente novamente.", "apple_sign_in_failed")
        }
    }

    private func finish() {
        pendingCall = nil
        authorizationController = nil
        presentationWindow = nil
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

@objc(FitTrackerRefresh)
final class FitTrackerRefreshPlugin: CAPPlugin, CAPBridgedPlugin {
    let identifier = "FitTrackerRefresh"
    let jsName = "FitTrackerRefresh"
    let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "setEnabled", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "end", returnType: CAPPluginReturnPromise),
    ]
    private weak var refreshControl: UIRefreshControl?
    private var timeout: DispatchWorkItem?

    @objc override func load() {
        DispatchQueue.main.async { [weak self] in self?.installIfNeeded() }
    }

    private func installIfNeeded() {
        guard refreshControl == nil, let scrollView = bridge?.webView?.scrollView else { return }
        let control = UIRefreshControl()
        control.tintColor = UIColor(red: 0.376, green: 0.647, blue: 0.980, alpha: 1)
        control.isEnabled = false
        control.addTarget(self, action: #selector(didPullToRefresh), for: .valueChanged)
        scrollView.alwaysBounceVertical = true
        scrollView.refreshControl = control
        refreshControl = control
    }

    @objc private func didPullToRefresh() {
        timeout?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.refreshControl?.endRefreshing() }
        timeout = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 20, execute: work)
        bridge?.triggerJSEvent(eventName: "fittracker:native-refresh", target: "window")
    }

    @objc func setEnabled(_ call: CAPPluginCall) {
        let enabled = call.getBool("enabled") ?? false
        DispatchQueue.main.async { [weak self] in
            self?.installIfNeeded()
            self?.refreshControl?.isEnabled = enabled
            if !enabled { self?.finish() }
            call.resolve()
        }
    }

    @objc func end(_ call: CAPPluginCall) {
        DispatchQueue.main.async { [weak self] in
            self?.finish()
            call.resolve()
        }
    }

    private func finish() {
        timeout?.cancel()
        timeout = nil
        refreshControl?.endRefreshing()
    }
}

final class FitTrackerBridgeViewController: CAPBridgeViewController {
    override public func capacitorDidLoad() {
        bridge?.registerPluginInstance(FitTrackerGoogleAuthPlugin())
        bridge?.registerPluginInstance(FitTrackerAppleAuthPlugin())
        bridge?.registerPluginInstance(FitTrackerSharePlugin())
        bridge?.registerPluginInstance(FitTrackerBillingPlugin())
        bridge?.registerPluginInstance(FitTrackerConsolePlugin())
        bridge?.registerPluginInstance(FitTrackerRefreshPlugin())
    }
}
