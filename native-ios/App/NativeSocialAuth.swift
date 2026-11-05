import SwiftUI
import AuthenticationServices
import CryptoKit
import GoogleSignIn
import FitTrackerCore
import OSLog

@MainActor
final class NativeSocialAuth: NSObject, ObservableObject, ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {
    @Published var busy = false
    @Published var error: String?
    @Published var signupToken: String?
    @Published var provider: SocialProvider = .google
    @Published private(set) var connecting = false
    @Published private(set) var status: String?
    @Published private(set) var signupNeedsRestart = false
    private var connectionTask: Task<AuthConfiguration, Error>?
    var configuration: AuthConfiguration?
    private var nonce: String?
    private var appleController: ASAuthorizationController?
    private var accept: ((SessionResponse) async throws -> Void)?
    private var api: FitTrackerAPI?
    private var linking = false
    private var stage = "connection"
    private let logger = Logger(subsystem: "ai.fittracker.app", category: "Authentication")
    @Published var linkedProviders: [String] = []

    func login(_ provider: SocialProvider, api: FitTrackerAPI, accept: @escaping (SessionResponse) async throws -> Void, linking: Bool = false) async {
        guard !busy else { return }
        busy = true; error = nil; signupNeedsRestart = false; self.linking = linking; self.provider = provider; self.api = api; self.accept = accept
        do {
            connecting = true
            stage = "connection"
            status = L("Conectando ao Fit Tracker… A primeira conexão pode levar um pouco mais.")
            let task = Task { try await api.authConfiguration() }
            connectionTask = task
            let config = try await withTaskCancellationHandler { try await task.value } onCancel: { task.cancel() }
            try Task.checkCancellation()
            connecting = false; connectionTask = nil; status = nil
            configuration = config
            if provider == .google {
                guard let client = Bundle.main.object(forInfoDictionaryKey: "GIDClientID") as? String,
                      let server = config.googleClientId, !server.isEmpty,
                      let presenter = Self.presentationController() else { throw APIError.http(status: 503, message: L("Login Google indisponível. Tente novamente mais tarde.")) }
                GIDSignIn.sharedInstance.configuration = GIDConfiguration(clientID: client, serverClientID: server)
                stage = "google_provider"
                let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: presenter)
                guard let credential = result.user.idToken?.tokenString else { throw APIError.invalidResponse }
                await authenticate(credential: credential)
                busy = false
            } else {
                guard config.appleEnabled else { throw APIError.http(status: 503, message: L("Login Apple indisponível. Tente novamente mais tarde.")) }
                stage = "apple_challenge"
                let challenge = try await api.appleAuthChallenge(); nonce = challenge.nonce
                let request = ASAuthorizationAppleIDProvider().createRequest()
                request.requestedScopes = [.fullName, .email]; request.nonce = SHA256.hash(data: Data(challenge.nonce.utf8)).map { String(format: "%02x", $0) }.joined()
                let controller = ASAuthorizationController(authorizationRequests: [request])
                controller.delegate = self; controller.presentationContextProvider = self
                stage = "apple_provider"
                appleController = controller; controller.performRequests()
            }
        } catch {
            busy = false; connecting = false; connectionTask = nil; status = nil
            if !Self.cancelled(error) { logFailure(error); self.error = Self.message(for: error) }
        }
    }
    func cancelConnection() { connectionTask?.cancel() }
    private func authenticate(credential: String, authorizationCode: String? = nil, name: String? = nil) async {
        guard let api else { return }
        stage = "session_confirmation"
        status = L("Confirmando seu acesso…")
        defer { status = nil }
        do {
            if linking {
                let response = try await api.linkSocialIdentity(provider: provider, credential: credential, nonce: nonce, authorizationCode: authorizationCode, displayName: name)
                linkedProviders = response.providers
                return
            }
            let response = try await api.socialLogin(provider: provider, credential: credential, nonce: nonce, authorizationCode: authorizationCode, displayName: name)
            try await accept?(response)
        } catch APIError.socialSignupRequired(let token) { signupToken = token }
        catch { if !Self.cancelled(error) { logFailure(error); self.error = Self.message(for: error) } }
    }
    func complete(name: String, consent: Bool, referralCode: String) async {
        guard !busy, let api, let token = signupToken, let config = configuration else { return }
        busy = true; error = nil; status = L("Concluindo seu cadastro…"); defer { busy = false; status = nil }
        stage = "signup"
        do {
            let response = try await api.completeSocialSignup(provider: provider, token: token, name: name.trimmingCharacters(in: .whitespacesAndNewlines), aiConsent: consent, aiConsentVersion: config.legal.ai.version, referralCode: referralCode)
            signupToken = nil
            try await accept?(response)
        } catch {
            if !Self.cancelled(error) { logFailure(error) }
            if case APIError.http(let code, _) = error, code == 401 {
                signupNeedsRestart = true
                self.error = L("Seu acesso de cadastro expirou. Volte ao login e entre novamente para continuar.")
            } else if !Self.cancelled(error) { self.error = Self.message(for: error) }
        }
    }
    func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        guard let apple = authorization.credential as? ASAuthorizationAppleIDCredential,
              let identity = apple.identityToken.flatMap({ String(data: $0, encoding: .utf8) }),
              let code = apple.authorizationCode.flatMap({ String(data: $0, encoding: .utf8) }) else {
            busy = false; error = L("A Apple não retornou uma credencial válida."); return
        }
        let name = apple.fullName.map { PersonNameComponentsFormatter().string(from: $0) }
        Task { await authenticate(credential: identity, authorizationCode: code, name: name); busy = false; appleController = nil }
    }
    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        busy = false; appleController = nil
        if !Self.cancelled(error) { logFailure(error); self.error = Self.message(for: error) }
    }
    private func logFailure(_ error: Error) {
        let value = error as NSError
        logger.error("stage=\(self.stage, privacy: .public) domain=\(value.domain, privacy: .public) code=\(value.code)")
    }
    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.flatMap(\.windows).first(where: \.isKeyWindow) ?? ASPresentationAnchor()
    }
    private static func presentationController() -> UIViewController? {
        var controller = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.flatMap(\.windows).first(where: \.isKeyWindow)?.rootViewController
        while let presented = controller?.presentedViewController { controller = presented }
        return controller
    }
    private static func cancelled(_ error: Error) -> Bool {
        let value = error as NSError
        return error is CancellationError || (value.domain == NSURLErrorDomain && value.code == URLError.cancelled.rawValue) || (value.domain == ASAuthorizationError.errorDomain && value.code == ASAuthorizationError.canceled.rawValue) || (value.domain == kGIDSignInErrorDomain && value.code == GIDSignInError.canceled.rawValue)
    }
    private static func message(for error: Error) -> String {
        if let network = error as? URLError {
            switch network.code {
            case .timedOut: return L("O servidor demorou para responder. Tente novamente em instantes. Se você acabou de confirmar o cadastro, tente entrar com a mesma conta.")
            case .notConnectedToInternet, .networkConnectionLost, .cannotConnectToHost, .cannotFindHost:
                return L("Não conseguimos conectar ao Fit Tracker. Confira sua internet e tente novamente.")
            default: break
            }
        }
        return error.localizedDescription
    }
}

struct NativeSocialLoginView: View {
    @EnvironmentObject private var session: NativeSession
    @StateObject private var auth = NativeSocialAuth()
    @State private var displayName = ""
    @State private var referralCode = ""
    @State private var aiChoice: Bool?
    @State private var showAI = false
    @State private var showReviewAccess = false
    private let site = "https://diet-tracker-6i67.onrender.com"
    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Spacer(minLength: 8)
                    Image("FitTrackerLogo").resizable().scaledToFit().frame(height: 50).accessibilityLabel("Fit Tracker")
                    Text(L("Seu ritmo.\nSua evolução.")).font(.largeTitle.bold())
                    Text(L("Treino e alimentação que combinam com você.")).foregroundStyle(.secondary)
                    Label(L("Seu primeiro plano, do seu jeito"), systemImage: "sparkles")
                    Label(L("Registre refeições em poucos toques"), systemImage: "camera")
                    Spacer(minLength: 8)
                    Button { Task { await auth.login(.google, api: session.api, accept: session.acceptSocialSession) } } label: {
                        HStack { Text("G").font(.headline); Text(L("Continuar com Google")).font(.body.weight(.semibold)) }.frame(maxWidth: .infinity).padding(16)
                    }.foregroundStyle(.black).background(.white, in: RoundedRectangle(cornerRadius: 15)).disabled(auth.busy)
                    Button { Task { await auth.login(.apple, api: session.api, accept: session.acceptSocialSession) } } label: {
                        Label(L("Continuar com Apple"), systemImage: "apple.logo").font(.body.weight(.semibold)).frame(maxWidth: .infinity).padding(16)
                    }.foregroundStyle(.white).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 15)).overlay(RoundedRectangle(cornerRadius: 15).stroke(.white.opacity(0.2))).disabled(auth.busy)
                    if auth.busy { ProgressView().frame(maxWidth: .infinity) }
                    if let status = auth.status { Text(status).font(.footnote).foregroundStyle(.secondary) }
                    if auth.connecting { Button(L("Cancelar conexão")) { auth.cancelConnection() }.font(.subheadline) }
                    if let error = auth.error { Text(NativeLocalization.display(error)).font(.footnote).foregroundStyle(.red) }
                    VStack(spacing: 8) {
                        Text(L("Ao continuar, consulte nossos documentos:")).font(.caption).foregroundStyle(.secondary)
                        HStack { Link(L("Termos de Uso"), destination: URL(string: site + "/terms.html")!).frame(minHeight: 44); Text("·"); Link(L("Privacidade"), destination: URL(string: site + "/privacy.html")!).frame(minHeight: 44) }.font(.footnote)
                    }.frame(maxWidth: .infinity)
                    Button(L("Acesso de avaliação")) { showReviewAccess = true }
                        .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, minHeight: 44)
                        .sheet(isPresented: $showReviewAccess) { NativeReviewAccessView() }
                        .disabled(auth.busy)
                    Spacer(minLength: 8)
                }.padding(24).frame(minHeight: max(0, geometry.size.height))
            }.background(Color.fitBackground)
        }
        .onOpenURL { GIDSignIn.sharedInstance.handle($0) }
        .onDisappear { auth.cancelConnection() }
        .sheet(isPresented: Binding(get: { auth.signupToken != nil }, set: { if !$0 { auth.signupToken = nil; aiChoice = nil; referralCode = "" } })) {
            NavigationView {
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        Text(L("Como podemos chamar você?")).font(.title2.bold())
                        Text(L("Seu nome não precisa ser exclusivo. Você continuará entrando com Apple ou Google, sem criar uma senha.")).foregroundStyle(.secondary)
                        TextField(L("Como você quer ser chamado?"), text: $displayName).textContentType(.name).textInputAutocapitalization(.words).padding(14).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 12)).accessibilityLabel(L("Seu nome"))
                        if displayName.count > 255 { Text(L("Use um nome com até 255 caracteres.")).font(.subheadline).foregroundStyle(.orange) }
                        VStack(alignment: .leading, spacing: 8) {
                            Text(L("Código de convite ou parceiro (opcional)")).font(.subheadline.weight(.semibold))
                            TextField(L("Código de convite"), text: $referralCode)
                                .textInputAutocapitalization(.characters).autocorrectionDisabled(true)
                                .keyboardType(.asciiCapable).padding(14)
                                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 12)).disabled(auth.busy)
                            Text(L("Informe o código de um amigo ou parceiro. Convites de amigos contam para a recompensa de quem convidou; códigos de parceiros registram sua indicação.")).font(.caption).foregroundStyle(.secondary)
                        }
                        Text(L("Planos e análises com IA")).font(.headline)
                        Text(L("Você escolhe se autoriza o envio dos dados necessários para planos e análises. Pode mudar isso no Perfil. Escolher Agora não mantém o registro manual disponível.")).font(.subheadline).foregroundStyle(.secondary)
                        Button(L("Ver como seus dados são usados")) { showAI = true }.font(.subheadline).frame(minHeight: 44)
                        Button { aiChoice = true } label: { Label(L("Autorizo o uso da IA"), systemImage: aiChoice == true ? "checkmark.circle.fill" : "circle").frame(maxWidth: .infinity, minHeight: 44, alignment: .leading) }
                            .accessibilityAddTraits(aiChoice == true ? .isSelected : [])
                        Button { aiChoice = false } label: { Label(L("Agora não"), systemImage: aiChoice == false ? "checkmark.circle.fill" : "circle").frame(maxWidth: .infinity, minHeight: 44, alignment: .leading) }
                            .accessibilityAddTraits(aiChoice == false ? .isSelected : [])
                        if let error = auth.error { Text(NativeLocalization.display(error)).foregroundStyle(.red).font(.footnote) }
                        if auth.signupNeedsRestart {
                            Button(L("Voltar ao login")) { auth.signupToken = nil }.fitGlassButton()
                        }
                        Button { if let choice = aiChoice { Task { await auth.complete(name: displayName, consent: choice, referralCode: referralCode) } } } label: { Text(auth.busy ? L("Entrando…") : L("Continuar")).frame(maxWidth: .infinity).padding(16) }.background(Color.fitBlue, in: RoundedRectangle(cornerRadius: 15)).foregroundStyle(.white).disabled(auth.busy || auth.signupNeedsRestart || aiChoice == nil || displayName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || displayName.count > 255)
                    }.padding(24)
                }.background(Color.fitBackground).navigationTitle(L("Seu primeiro acesso")).navigationBarTitleDisplayMode(.inline).toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Cancelar")) { auth.signupToken = nil; aiChoice = nil; referralCode = "" }.disabled(auth.busy) } }
            }
            .interactiveDismissDisabled(auth.busy)
        }
        .alert(L("Uso dos dados pela IA"), isPresented: $showAI) {
            Button(L("Entendi"), role: .cancel) { }
        } message: { Text(L("Quando você pedir uma geração ou análise, os dados necessários podem ser enviados ao Google Gemini e, se ele falhar, à OpenAI: mensagens, fotos de refeições, perfil, alimentação, medidas e treinos. A IA pode produzir estimativas incorretas. Revise os resultados antes de usar. Recusar não impede o registro manual.")) }
    }
}


struct NativeLinkedAccountsView: View {
    @EnvironmentObject private var session: NativeSession
    @StateObject private var auth = NativeSocialAuth()
    @State private var loading = true
    @State private var loadError: String?
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text(L("Entre do seu jeito")).font(.title2.bold())
                Text(L("Conecte Google ou Apple a esta conta para preservar seus planos, histórico e assinatura. Um acesso que pertence a outra conta não pode ser vinculado.")).foregroundStyle(.secondary)
                if loading { ProgressView() }
                if let loadError { Text(loadError).foregroundStyle(.red); Button(L("Tentar novamente")) { Task { await load() } } }
                ForEach([SocialProvider.google, .apple], id: \.rawValue) { provider in
                    let linked = auth.linkedProviders.contains(provider.rawValue)
                    Button {
                        Task { await auth.login(provider, api: session.api, accept: { _ in }, linking: true) }
                    } label: {
                        HStack {
                            Image(systemName: provider == .apple ? "apple.logo" : "person.crop.circle")
                            Text(provider == .apple ? "Apple" : "Google").font(.body.weight(.semibold))
                            Spacer()
                            if linked { Label(L("Conectado"), systemImage: "checkmark.circle.fill").foregroundStyle(.green) }
                            else { Text(L("Conectar")).foregroundStyle(Color.fitBlue) }
                        }.padding(18).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                    }.buttonStyle(.plain).disabled(linked || auth.busy || loading || loadError != nil)
                }
                if auth.busy { ProgressView(L("Conectando acesso…")) }
                if let error = auth.error { Text(NativeLocalization.display(error)).foregroundStyle(.red).font(.footnote) }
                Text(L("Não alteramos sua senha nem transferimos dados entre contas.")).font(.footnote).foregroundStyle(.secondary)
            }.padding(24)
        }.background(Color.fitBackground).navigationTitle(L("Acessos conectados")).navigationBarTitleDisplayMode(.inline)
            .task { await load() }.onOpenURL { GIDSignIn.sharedInstance.handle($0) }
    }
    private func load() async {
        loading = true; loadError = nil; defer { loading = false }
        do { auth.linkedProviders = try await session.api.linkedIdentities().providers }
        catch { if !isNativeRequestCancellation(error) { loadError = error.localizedDescription } }
    }
}


/// Uses the same authenticated session endpoint as existing accounts; no local access grants.
private struct NativeReviewAccessView: View {
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    @State private var username = ""
    @State private var password = ""
    @State private var attempted = false
    @FocusState private var passwordFocused: Bool

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Image(systemName: "person.badge.key.fill").font(.system(size: 32)).foregroundStyle(Color.fitBlue)
                    Text(L("Acesso de avaliação")).font(.title2.bold())
                    Text(L("Entre com a conta de teste fornecida para avaliar o app. Este acesso não cria uma conta nova.")).font(.subheadline).foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 8) {
                        Text(L("Usuário")).font(.caption.weight(.semibold))
                        TextField(L("Nome de usuário"), text: $username)
                            .textContentType(.username).textInputAutocapitalization(.never).autocorrectionDisabled()
                            .submitLabel(.next).onSubmit { passwordFocused = true }
                            .padding(15).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        Text(L("Senha")).font(.caption.weight(.semibold))
                        SecureField(L("Senha da conta de teste"), text: $password)
                            .textContentType(.password).focused($passwordFocused).submitLabel(.go)
                            .onSubmit { signIn() }
                            .padding(15).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
                    }
                    if attempted, let error = session.error { Text(NativeLocalization.display(error)).font(.footnote).foregroundStyle(.red).accessibilityLabel(L("Erro de acesso: ") + error) }
                    Button { signIn() } label: {
                        HStack { if session.busy { ProgressView().tint(.white) }; Text(session.busy ? L("Entrando…") : L("Entrar")).fontWeight(.semibold) }
                            .frame(maxWidth: .infinity).padding(16)
                    }.foregroundStyle(.white).background(Color.fitBlue, in: RoundedRectangle(cornerRadius: 15))
                        .disabled(session.busy || username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || password.isEmpty)
                }.padding(24)
            }.background(Color.fitBackground).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { password = ""; dismiss() }.disabled(session.busy) } }
        }.navigationViewStyle(.stack).interactiveDismissDisabled(session.busy)
            .onDisappear { password = "" }
    }

    private func signIn() {
        guard !session.busy, !username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, !password.isEmpty else { return }
        passwordFocused = false; attempted = true
        Task {
            await session.login(username: username.trimmingCharacters(in: .whitespacesAndNewlines), password: password)
            password = ""
            if session.user != nil { dismiss() }
        }
    }
}
