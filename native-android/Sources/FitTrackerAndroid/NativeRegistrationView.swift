import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
import FitTrackerCore

struct NativeRegistrationView: View {
    @Environment(NativeSession.self) var session
    @Environment(\.dismiss) var dismiss
    @State var name = ""
    @State var username = ""
    @State var email = ""
    @State var referralCode = ""
    @State var password = ""
    @State var confirmation = ""
    @State var aiChoice: Bool?
    @State var configuration: AuthConfiguration?
    @State var loading = true
    @State var loadError: String?
    @State var attempted = false

    var canRegister: Bool {
        configuration != nil && !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
            name.count <= 255 && !username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
            username.count <= 80 && email.count <= 320 && password.count >= 8 &&
            password.count <= 128 && password == confirmation && aiChoice != nil && !session.busy
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text("Vamos começar").font(.title2.bold())
                    Text("Crie sua conta para salvar seus planos e acompanhar sua evolução.").foregroundStyle(.secondary)
                    TextField("Seu nome", text: $name).textContentType(.name)
                        .padding(15).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
                    TextField("Nome de usuário", text: $username).textContentType(.username)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .padding(15).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
                    TextField("E-mail (opcional)", text: $email).textContentType(.emailAddress)
                        .keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .padding(15).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
                    TextField("Código de convite (opcional)", text: $referralCode)
                        .textInputAutocapitalization(.characters).autocorrectionDisabled()
                        .padding(15).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
                    SecureField("Senha (8 a 128 caracteres)", text: $password).textContentType(.newPassword)
                        .padding(15).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
                    SecureField("Confirme sua senha", text: $confirmation).textContentType(.newPassword)
                        .padding(15).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
                    if !confirmation.isEmpty, password != confirmation {
                        Text("As senhas precisam ser iguais.").font(.footnote).foregroundStyle(.red)
                    }
                    Text("Planos e análises com IA").font(.headline)
                    Text("Quando você pedir planos ou análises, os dados necessários podem ser enviados ao Google Gemini e, se ele falhar, à OpenAI: mensagens, fotos de refeições, perfil, alimentação, medidas e treinos. A IA pode produzir estimativas incorretas. Revise os resultados antes de usar. Recusar não impede o registro manual. Você pode mudar sua escolha no Perfil.")
                        .font(.footnote).foregroundStyle(.secondary)
                    Button { aiChoice = true } label: {
                        Label("Autorizo o uso da IA", systemImage: aiChoice == true ? "checkmark.circle.fill" : "circle")
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    }
                    Button { aiChoice = false } label: {
                        Label("Agora não", systemImage: aiChoice == false ? "checkmark.circle.fill" : "circle")
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    }
                    if loading { ProgressView("Consultando os termos atuais…") }
                    if let loadError {
                        Text(loadError).font(.footnote).foregroundStyle(.red)
                        Button("Tentar novamente") { Task { await loadConfiguration() } }
                    }
                    if attempted, let error = session.error { Text(error).font(.footnote).foregroundStyle(.red) }
                    Text("Ao criar sua conta, consulte nossos documentos:").font(.caption).foregroundStyle(.secondary)
                    NativeLegalLinks()
                    Button { register() } label: {
                        HStack {
                            if session.busy { ProgressView().tint(.white) }
                            Text(session.busy ? "Criando conta…" : "Criar conta").fontWeight(.semibold)
                        }.frame(maxWidth: .infinity).padding(16)
                    }.foregroundStyle(.white).background(Color.fitBlue, in: RoundedRectangle(cornerRadius: 15))
                        .disabled(!canRegister)
                }.padding(24)
            }.background(Color.fitBackground).navigationTitle("Seu primeiro acesso").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() }.disabled(session.busy) } }
        }.interactiveDismissDisabled(session.busy)
            .task { await loadConfiguration() }
            .onDisappear { password = ""; confirmation = "" }
    }

    func loadConfiguration() async {
        loading = true; loadError = nil
        defer { loading = false }
        do { configuration = try await session.api.authConfiguration() }
        catch { if !isNativeRequestCancellation(error) { loadError = NativeSocialAuth.message(for: error) } }
    }

    func register() {
        guard canRegister, let configuration, let aiChoice else { return }
        attempted = true
        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        let registration = Registration(username: username.trimmingCharacters(in: .whitespacesAndNewlines),
                                        password: password, name: name.trimmingCharacters(in: .whitespacesAndNewlines),
                                        email: trimmedEmail.isEmpty ? nil : trimmedEmail,
                                        aiConsent: aiChoice, aiConsentVersion: configuration.legal.ai.version,
                                        referralCode: referralCode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : referralCode.trimmingCharacters(in: .whitespacesAndNewlines).uppercased())
        Task {
            await session.register(registration)
            password = ""; confirmation = ""
            if session.user != nil { dismiss() }
        }
    }
}
