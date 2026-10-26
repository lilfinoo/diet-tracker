import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
import Foundation
import FitTrackerAuthBridge
import FitTrackerCore

@MainActor
@Observable final class NativeSocialAuth {
    var busy = false
    var error: String?
    var signupToken: String?
    var provider: SocialProvider = .google
    var connecting = false
    var status: String?
    var signupNeedsRestart = false
    var connectionTask: Task<AuthConfiguration, Error>?
    var configuration: AuthConfiguration?
    var accept: ((SessionResponse) async throws -> Void)?
    var api: FitTrackerAPI?
    var linking = false
    var linkedProviders: [String] = []
    var isCurrent: () -> Bool = { true }

    func login(_ provider: SocialProvider, api: FitTrackerAPI, accept: @escaping (SessionResponse) async throws -> Void, linking: Bool = false, isCurrent: @escaping () -> Bool) async {
        guard !busy else { return }
        busy = true; error = nil; signupNeedsRestart = false
        self.linking = linking; self.provider = provider; self.api = api; self.accept = accept
        self.isCurrent = isCurrent
        defer { busy = false; connecting = false; connectionTask = nil; status = nil }
        do {
            guard provider == .google else {
                throw APIError.http(status: 503, message: "O acesso Apple no Android ainda precisa ser configurado. Use um acesso Google conectado à mesma conta.")
            }
            connecting = true
            status = "Conectando ao Fit Tracker… A primeira conexão pode levar um pouco mais."
            let task = Task { try await api.authConfiguration() }
            connectionTask = task
            let config = try await withTaskCancellationHandler { try await task.value } onCancel: { task.cancel() }
            try Task.checkCancellation()
            guard isCurrent() else { throw CancellationError() }
            configuration = config
            guard let client = config.googleClientId, !client.isEmpty else {
                throw APIError.http(status: 503, message: "Login Google indisponível. Tente novamente mais tarde.")
            }
            connecting = false; connectionTask = nil
            status = "Escolha sua conta Google…"
            guard let credential = try await AndroidAuthBridge.googleCredential(serverClientID: client) else { return }
            try Task.checkCancellation()
            guard isCurrent() else { throw CancellationError() }
            status = "Confirmando seu acesso…"
            if linking {
                let result = try await api.linkSocialIdentity(provider: provider, credential: credential)
                guard isCurrent() else { throw CancellationError() }
                linkedProviders = result.providers
            } else {
                let response = try await api.socialLogin(provider: provider, credential: credential)
                guard isCurrent() else { throw CancellationError() }
                try await accept(response)
            }
        } catch APIError.socialSignupRequired(let token) { signupToken = token }
        catch { if !isNativeRequestCancellation(error) { self.error = Self.message(for: error) } }
    }
    func cancelConnection() { connectionTask?.cancel() }
    func complete(username: String, consent: Bool) async {
        guard !busy, isCurrent(), let api, let token = signupToken, let config = configuration else { return }
        busy = true; error = nil; status = "Concluindo seu cadastro…"
        defer { busy = false; status = nil }
        do {
            let response = try await api.completeSocialSignup(provider: provider, token: token, name: username.trimmingCharacters(in: .whitespacesAndNewlines), aiConsent: consent, aiConsentVersion: config.legal.ai.version)
            guard isCurrent() else { throw CancellationError() }
            try await accept?(response)
            signupToken = nil
        } catch {
            if case APIError.http(let code, _) = error, code == 401 {
                signupNeedsRestart = true
                self.error = "Seu acesso de cadastro expirou. Volte ao login e entre novamente para continuar."
            } else if !isNativeRequestCancellation(error) { self.error = Self.message(for: error) }
        }
    }
    static func message(for error: Error) -> String {
        if let network = error as? URLError {
            switch network.code {
            case .timedOut: return "O servidor demorou para responder. Tente novamente em instantes. Se você acabou de confirmar o cadastro, tente entrar com a mesma conta."
            case .notConnectedToInternet, .networkConnectionLost, .cannotConnectToHost, .cannotFindHost:
                return "Não conseguimos conectar ao Fit Tracker. Confira sua internet e tente novamente."
            default: break
            }
        }
        return error.localizedDescription
    }
}

struct NativeSocialLoginView: View {
    @Environment(NativeSession.self) var session
    @State var auth = NativeSocialAuth()
    @State var username = ""
    @State var aiChoice: Bool?
    @State var showAI = false
    @State var showReviewAccess = false
    @State var showRegistration = false
    let site = "https://diet-tracker-6i67.onrender.com"
    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Spacer(minLength: 8)
                    Image("FitTrackerLogo", bundle: .module).resizable().scaledToFit().frame(height: 50).accessibilityLabel("Fit Tracker")
                    Text("Seu ritmo.\nSua evolução.").font(.system(size: 34, weight: .bold))
                    Text("Treino e alimentação que combinam com você.").foregroundStyle(.secondary)
                    Label("Seu primeiro plano, do seu jeito", systemImage: "sparkles")
                    Label("Registre refeições em poucos toques", systemImage: "camera")
                    Spacer(minLength: 8)
                    Button { Task { await auth.login(.google, api: session.api, accept: session.acceptSocialSession, isCurrent: { session.user == nil && !session.busy }) } } label: {
                        HStack { Text("G").font(.headline); Text("Continuar com Google").font(.body.weight(.semibold)) }.frame(maxWidth: .infinity).padding(16)
                    }.foregroundStyle(.black).background(.white, in: RoundedRectangle(cornerRadius: 15)).disabled(true)
                    Text("Neste teste Android, use usuário e senha ou crie uma conta. O acesso Google ainda está em configuração. Contas criadas com Apple ou Google precisam ter uma senha cadastrada para entrar por aqui.")
                        .font(.footnote).foregroundStyle(.secondary)
                    if auth.busy { ProgressView().frame(maxWidth: .infinity) }
                    if let status = auth.status { Text(status).font(.footnote).foregroundStyle(.secondary) }
                    if auth.connecting { Button("Cancelar conexão") { auth.cancelConnection() }.font(.subheadline) }
                    if let error = auth.error { Text(error).font(.footnote).foregroundStyle(.red) }
                    VStack(spacing: 8) {
                        Text("Ao continuar, consulte nossos documentos:").font(.caption).foregroundStyle(.secondary)
                        HStack { Link("Termos de Uso", destination: URL(string: site + "/terms.html")!); Text("·"); Link("Privacidade", destination: URL(string: site + "/privacy.html")!) }.font(.caption)
                    }.frame(maxWidth: .infinity)
                    Button("Entrar com usuário e senha") { showReviewAccess = true }
                        .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, minHeight: 44)
                        .sheet(isPresented: $showReviewAccess) { NativeReviewAccessView() }
                        .disabled(auth.busy)
                    Button("Criar conta com usuário e senha") { showRegistration = true }
                        .font(.subheadline).frame(maxWidth: .infinity, minHeight: 44)
                        .sheet(isPresented: $showRegistration) { NativeRegistrationView() }
                        .disabled(auth.busy)
                    Spacer(minLength: 8)
                }.padding(24).frame(minHeight: max(0, geometry.size.height))
            }.background(Color.fitBackground)
        }
        .onDisappear { auth.cancelConnection() }
        .sheet(isPresented: Binding(get: { auth.signupToken != nil }, set: { if !$0 { auth.signupToken = nil; aiChoice = nil } })) {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        Text("Como podemos chamar você?").font(.title2.bold())
                        Text("Informe seu nome para completar seu acesso. Você não precisa criar uma senha.").foregroundStyle(.secondary)
                        TextField("Seu nome", text: $username).textInputAutocapitalization(.words).autocorrectionDisabled().padding(14).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 12))
                        Text("Planos e análises com IA").font(.headline)
                        Text("Você escolhe se autoriza o envio dos dados necessários para planos e análises. Pode mudar isso no Perfil.").font(.subheadline).foregroundStyle(.secondary)
                        Button("Ver como seus dados são usados") { showAI = true }.font(.subheadline)
                        Button { aiChoice = true } label: { Label("Autorizo o uso da IA", systemImage: aiChoice == true ? "checkmark.circle.fill" : "circle").frame(maxWidth: .infinity, alignment: .leading) }
                        Button { aiChoice = false } label: { Label("Agora não", systemImage: aiChoice == false ? "checkmark.circle.fill" : "circle").frame(maxWidth: .infinity, alignment: .leading) }
                        if let error = auth.error { Text(error).foregroundStyle(.red).font(.footnote) }
                        if auth.signupNeedsRestart {
                            Button("Voltar ao login") { auth.signupToken = nil }.buttonStyle(.bordered)
                        }
                        Button { if let choice = aiChoice { Task { await auth.complete(username: username, consent: choice) } } } label: { Text(auth.busy ? "Entrando…" : "Continuar").frame(maxWidth: .infinity).padding(16) }.background(Color.fitBlue, in: RoundedRectangle(cornerRadius: 15)).foregroundStyle(.white).disabled(auth.busy || auth.signupNeedsRestart || aiChoice == nil || username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || username.count > 80)
                    }.padding(24)
                }.background(Color.fitBackground).navigationTitle("Seu primeiro acesso").navigationBarTitleDisplayMode(.inline).toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancelar") { auth.signupToken = nil; aiChoice = nil }.disabled(auth.busy) } }
            }
            .interactiveDismissDisabled(auth.busy)
        }
        .alert("Uso dos dados pela IA", isPresented: $showAI) {
            Button("Entendi", role: .cancel) { }
        } message: { Text("Quando você pedir uma geração ou análise, os dados necessários podem ser enviados ao Google Gemini e, se ele falhar, à OpenAI: mensagens, fotos de refeições, perfil, alimentação, medidas e treinos. A IA pode produzir estimativas incorretas. Revise os resultados antes de usar. Recusar não impede o registro manual.") }
    }
}


struct NativeLinkedAccountsView: View {
    @Environment(NativeSession.self) var session
    @State var auth = NativeSocialAuth()
    @State var loading = true
    @State var loadError: String?
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Entre do seu jeito").font(.title2.bold())
                Text("Conecte Google a esta conta para preservar seus planos, histórico e assinatura. Um acesso que pertence a outra conta não pode ser vinculado.").foregroundStyle(.secondary)
                if loading { ProgressView() }
                if let loadError { Text(loadError).foregroundStyle(.red); Button("Tentar novamente") { Task { await load() } } }
                ForEach([SocialProvider.google] + (auth.linkedProviders.contains("apple") ? [.apple] : []), id: \.rawValue) { provider in
                    let linked = auth.linkedProviders.contains(provider.rawValue)
                    Button {
                        let owner = session.user?.id
                        Task { await auth.login(provider, api: session.api, accept: { _ in }, linking: true,
                                                isCurrent: { owner != nil && session.user?.id == owner && !session.busy }) }
                    } label: {
                        HStack {
                            Image(systemName: provider == .apple ? "apple.logo" : "person.crop.circle")
                            Text(provider == .apple ? "Apple" : "Google").font(.body.weight(.semibold))
                            Spacer()
                            if linked { Label("Conectado", systemImage: "checkmark.circle.fill").foregroundStyle(.green) }
                            else { Text("Conectar").foregroundStyle(Color.fitBlue) }
                        }.padding(18).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                    }.buttonStyle(.plain).disabled(linked || auth.busy || loading || loadError != nil)
                }
                if auth.busy { ProgressView("Conectando acesso…") }
                if let error = auth.error { Text(error).foregroundStyle(.red).font(.footnote) }
                Text("Não alteramos sua senha nem transferimos dados entre contas.").font(.footnote).foregroundStyle(.secondary)
            }.padding(24)
        }.background(Color.fitBackground).navigationTitle("Acessos conectados").navigationBarTitleDisplayMode(.inline)
            .task { await load() }
    }
    func load() async {
        loading = true; loadError = nil; defer { loading = false }
        do { auth.linkedProviders = try await session.api.linkedIdentities().providers }
        catch { if !isNativeRequestCancellation(error) { loadError = error.localizedDescription } }
    }
}


/// Uses the same authenticated session endpoint as existing accounts; no local access grants.
struct NativeReviewAccessView: View {
    @Environment(NativeSession.self) var session
    @Environment(\.dismiss) var dismiss
    @State var username = ""
    @State var password = ""
    @State var attempted = false
    @FocusState var passwordFocused: Bool

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Image(systemName: "person.badge.key.fill").font(.system(size: 32)).foregroundStyle(Color.fitBlue)
                    Text("Entre na sua conta").font(.title2.bold())
                    Text("Use seu nome de usuário e senha do Fit Tracker.").font(.subheadline).foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Usuário").font(.caption.weight(.semibold))
                        TextField("Nome de usuário", text: $username)
                            .textContentType(.username).textInputAutocapitalization(.never).autocorrectionDisabled()
                            .submitLabel(.next).onSubmit { passwordFocused = true }
                            .padding(15).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Senha").font(.caption.weight(.semibold))
                        SecureField("Sua senha", text: $password)
                            .textContentType(.password).focused($passwordFocused).submitLabel(.go)
                            .onSubmit { signIn() }
                            .padding(15).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
                    }
                    if attempted, let error = session.error { Text(error).font(.footnote).foregroundStyle(.red).accessibilityLabel(Text("Erro de acesso: " + error)) }
                    Button { signIn() } label: {
                        HStack { if session.busy { ProgressView().tint(.white) }; Text(session.busy ? "Entrando…" : "Entrar").fontWeight(.semibold) }
                            .frame(maxWidth: .infinity).padding(16)
                    }.foregroundStyle(.white).background(Color.fitBlue, in: RoundedRectangle(cornerRadius: 15))
                        .disabled(session.busy || username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || password.isEmpty)
                }.padding(24)
            }.background(Color.fitBackground).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { password = ""; dismiss() }.disabled(session.busy) } }
        }.interactiveDismissDisabled(session.busy)
            .onDisappear { password = "" }
    }

    func signIn() {
        guard !session.busy, !username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, !password.isEmpty else { return }
        passwordFocused = false; attempted = true
        Task {
            await session.login(username: username.trimmingCharacters(in: .whitespacesAndNewlines), password: password)
            password = ""
            if session.user != nil { dismiss() }
        }
    }
}
