import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
import FitTrackerCore

let aiConsentExplanation = "Autorizo enviar ao Google Gemini e, se ele falhar, à OpenAI minhas mensagens, fotos de refeições e dados de perfil, alimentação, medidas e treino usados para gerar análises e planos. Posso revogar esta escolha no Perfil."

struct NativeLoginView: View {
    var body: some View { NativeSocialLoginView() }
}

struct NativeProfileView: View {
    @Environment(NativeSession.self) var session
    @State var editor = false
    @State var logout = false
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    HStack(spacing: 16) {
                        Text(String((session.user?.name ?? "Você").prefix(1))).font(.title.bold())
                            .frame(width: 62, height: 62).background(Color.fitBlue.opacity(0.22), in: RoundedRectangle(cornerRadius: 22))
                        VStack(alignment: .leading, spacing: 5) {
                            Text(session.user?.name ?? "Seu perfil").font(.title2.bold())
                            Text(session.user?.isPremium == true ? "PREMIUM" : "PLANO GRATUITO").font(.caption2.bold()).tracking(1).foregroundColor(.fitBlue)
                        }
                    }
                    HStack(alignment: .top, spacing: 12) {
                        metric("Objetivo", session.profile?.profile?.goal ?? "Não informado")
                        metric("Peso", session.profile?.profile?.weight.map { "\($0.formatted()) kg" } ?? "—")
                        metric("Altura", session.profile?.profile?.height.map { "\($0.formatted()) cm" } ?? "—")
                    }.padding(.vertical, 16)
                    NativeFreeAccessCard()
                    NavigationLink(destination: NativeReferralView()) { profileRow("Convide e ganhe Premium", detail: "3 novos usuários por mês", icon: "gift") }.buttonStyle(.plain)
                    if session.user?.isPremium != true {
                        NavigationLink(destination: NativeSubscriptionView()) { NativePremiumBanner() }.buttonStyle(.plain)
                    }
                    Text("Do seu jeito").font(.headline)
                    VStack(spacing: 0) {
                        Button { editor = true } label: { profileRow("Dados e objetivos", detail: "Medidas e personalização", icon: "slider.horizontal.3") }
                        Divider()
                        NavigationLink(destination: NativePrivacyView()) { profileRow("Privacidade e IA", detail: "Você decide como seus dados são usados", icon: "hand.raised") }
                        Divider()
                        NavigationLink(destination: NativeSubscriptionView()) { profileRow("Minha assinatura", detail: "Planos e gerenciamento", icon: "crown") }
                    }.padding(.horizontal, 16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                    Text("Sua conta").font(.headline)
                    VStack(spacing: 0) {
                        NavigationLink(destination: NativeLinkedAccountsView()) { profileRow("Acessos conectados", detail: "Google e Apple", icon: "person.badge.key") }
                        Divider()
                        NativeLegalLinks().padding(.vertical, 20)
                        Divider()
                        Button { logout = true } label: { profileRow("Sair da conta", detail: "", icon: "rectangle.portrait.and.arrow.right") }.disabled(session.busy)
                    }.padding(.horizontal, 16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                    NavigationLink(destination: NativeDeleteAccountView()) { Text("Excluir minha conta").font(.caption).foregroundColor(.red) }
                }.padding(22)
            }.background(Color.fitBackground.ignoresSafeArea())
                .navigationTitle("Perfil").navigationBarTitleDisplayMode(.inline)
                .sheet(isPresented: $editor) { NativeProfileEditor() }
                .confirmationDialog("Sair desta conta?", isPresented: $logout, titleVisibility: .visible) {
                    Button("Sair", role: .destructive) { Task { await session.logout() } }
                }
                .task { try? await session.refreshFreeAccess() }
        }
    }
    func metric(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 7) { Text(label).font(.caption2).foregroundColor(.secondary); Text(value).font(.caption.bold()) }.frame(maxWidth: .infinity, alignment: .leading)
    }
    func profileRow(_ title: String, detail: String, icon: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon).font(.title3).foregroundColor(.fitBlue).frame(width: 28)
            VStack(alignment: .leading, spacing: 5) { Text(title).font(.subheadline.weight(.semibold)); if !detail.isEmpty { Text(detail).font(.caption2).foregroundColor(.secondary) } }
            Spacer(); Image(systemName: "chevron.right").font(.caption).foregroundColor(.secondary)
        }.padding(.vertical, 18).foregroundColor(.primary)
    }
}

struct NativePremiumBanner: View {
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "sparkles").font(.title2).foregroundColor(.yellow)
            VStack(alignment: .leading, spacing: 5) {
                Text("Seu próximo passo com Premium").font(.subheadline.bold())
                Text("Mais planos e análises para sua rotina.").font(.caption).foregroundColor(.secondary)
            }
            Spacer(minLength: 4); Image(systemName: "chevron.right").font(.caption)
        }.padding(18).foregroundColor(.primary).background(LinearGradient(colors: [Color.fitBlue.opacity(0.25), Color.fitSurface], startPoint: .leading, endPoint: .trailing), in: RoundedRectangle(cornerRadius: 18))
    }
}

struct NativeProfileEditor: View {
    @Environment(NativeSession.self) var session
    @Environment(\.dismiss) var dismiss
    @State var age = ""
    @State var weight = ""
    @State var height = ""
    @State var gender = ""
    @State var goal = ""
    @State var activity = ""
    @State var restrictions = ""
    @State var busy = false
    @State var error: String?
    var body: some View {
        NavigationStack {
            Form {
                Section(header: Text("Dados pessoais")) {
                    TextField("Idade", text: $age).keyboardType(.numberPad)
                    TextField("Peso (kg)", text: $weight).keyboardType(.decimalPad)
                    TextField("Altura (cm)", text: $height).keyboardType(.decimalPad)
                    Picker("Gênero", selection: $gender) { Text("Não informado").tag(""); Text("Masculino").tag("masculino"); Text("Feminino").tag("feminino") }
                }
                Section(header: Text("Objetivos e rotina")) {
                    Picker("Objetivo", selection: $goal) {
                        Text("Escolha").tag(""); Text("Perder peso").tag("perder peso"); Text("Ganhar massa muscular").tag("ganhar massa muscular"); Text("Manter peso").tag("manter peso"); Text("Melhorar saúde").tag("melhorar saude")
                    }
                    Picker("Atividade", selection: $activity) {
                        Text("Escolha").tag(""); Text("Sedentário").tag("sedentario"); Text("Leve").tag("leve"); Text("Moderado").tag("moderado"); Text("Intenso").tag("intenso")
                    }
                    TextField("Restrições alimentares", text: $restrictions)
                }
                Section { Text("Alterar peso ou altura também pode adicionar uma medição ao seu histórico.").font(.footnote).foregroundColor(.secondary) }
                if let error { Text(error).foregroundColor(.red) }
                if busy { ProgressView() }
            }.disabled(busy).navigationTitle("Dados e objetivos").navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() }.disabled(busy) }
                    ToolbarItem(placement: .confirmationAction) { Button("Salvar") { Task { await save() } }.disabled(busy) }
                }.onAppear {
                    let profile = session.profile?.profile
                    age = profile?.age.map(String.init) ?? ""; weight = profile?.weight.map { String($0) } ?? ""; height = profile?.height.map { String($0) } ?? ""
                    gender = profile?.gender ?? ""; goal = profile?.goal ?? ""; activity = profile?.activityLevel ?? ""; restrictions = profile?.dietaryRestrictions ?? ""
                }
        }.interactiveDismissDisabled(busy)
    }
    func save() async {
        let parsedWeight = Double(weight.replacingOccurrences(of: ",", with: "."))
        let parsedHeight = Double(height.replacingOccurrences(of: ",", with: "."))
        guard (age.isEmpty || Int(age).map { (0...120).contains($0) } == true),
              (weight.isEmpty || parsedWeight.map { $0 > 0 && $0 <= 500 } == true),
              (height.isEmpty || parsedHeight.map { $0 > 0 && $0 <= 300 } == true) else { error = "Confira idade, peso e altura."; return }
        let current = session.profile?.profile
        guard !(age.isEmpty && current?.age != nil), !(weight.isEmpty && current?.weight != nil), !(height.isEmpty && current?.height != nil) else {
            error = "Mantenha os valores atuais ou informe novos valores. Para remover medidas, use o histórico de medições."; return
        }
        busy = true; error = nil
        defer { busy = false }
        do {
            _ = try await session.api.updateProfile(ProfileChanges(age: Int(age), gender: gender, goal: goal, activityLevel: activity, dietaryRestrictions: restrictions, weight: parsedWeight == current?.weight ? nil : parsedWeight, height: parsedHeight == current?.height ? nil : parsedHeight))
            try await session.refreshProfile()
            NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
            dismiss()
        } catch { self.error = error.localizedDescription }
    }
}

struct NativePrivacyView: View {
    @Environment(NativeSession.self) var session
    @State var status: ConsentStatus?
    @State var granted = false
    @State var busy = false
    @State var error: String?
    var body: some View {
        Form {
            if let status {
                Section { Text(status.ai.accepted ? "IA autorizada" : "IA não autorizada").font(.headline); Text(aiConsentExplanation).font(.footnote); Toggle("Autorizar processamento por IA", isOn: $granted) }
                Section { Text("Revogar bloqueia novas solicitações à IA.").font(.footnote); Button("Salvar escolha") { Task { await save() } }.disabled(busy || granted == status.ai.accepted) }
            } else if error == nil { ProgressView("Carregando preferências…") }
            if let error { Text(error).foregroundColor(.red); Button("Tentar novamente") { Task { await load() } } }
        }.navigationTitle("Privacidade e IA").navigationBarTitleDisplayMode(.inline).task { await load() }.disabled(busy)
    }
    func load() async { do { let result = try await session.api.consentStatus(); status = result; granted = result.ai.accepted; error = nil } catch { self.error = error.localizedDescription } }
    func save() async {
        guard let status else { return }; busy = true; defer { busy = false }
        do { self.status = try await session.api.updateConsent(granted: granted, version: status.versions.ai.version); error = nil } catch { self.error = error.localizedDescription }
    }
}

struct LabeledContentCompat: View {
    let label: String; let value: String
    var body: some View { HStack { Text(label); Spacer(); Text(value).foregroundColor(.secondary) } }
}

struct NativeDeleteAccountView: View {
    @Environment(NativeSession.self) var session
    @State var username = ""
    @State var password = ""
    @State var understood = false
    @State var confirmation = false
    @State var busy = false
    @State var error: String?
    var expectedUsername: String { session.user?.username ?? "" }
    var confirmedUsername: String { username.trimmingCharacters(in: .whitespacesAndNewlines) }
    var canDelete: Bool {
        understood && !expectedUsername.isEmpty && confirmedUsername == expectedUsername
            && (session.user?.hasPassword != true || !password.isEmpty)
    }
    var body: some View {
        Form {
            Section {
                Text("Sua conta e seus dados serão excluídos definitivamente. Esta ação não pode ser desfeita.")
                Text("Excluir a conta não cancela sua assinatura. Cancele na loja onde você a contratou.")
                Link("Abrir assinaturas da Google Play", destination: URL(string: "https://play.google.com/store/account/subscriptions")!)
            }
            Section {
                Text("Para confirmar, digite seu nome de usuário:")
                Text(expectedUsername).font(.headline)
                TextField("Nome de usuário", text: $username).textInputAutocapitalization(.never).autocorrectionDisabled(true)
                if !username.isEmpty && confirmedUsername != expectedUsername {
                    Text("Digite exatamente \(expectedUsername), como mostrado acima. Seu nome de perfil pode ser diferente.").font(.footnote).foregroundColor(.orange)
                }
                if session.user?.hasPassword == true { SecureField("Senha atual", text: $password).textContentType(.password) }
                else { Text("Por segurança, entre novamente com Google antes de excluir, caso seu último login tenha sido há mais de 10 minutos. Você pode sair e entrar novamente pelo Perfil.").font(.footnote) }
                Toggle("Entendo que a exclusão é definitiva", isOn: $understood)
            }
            if let error { Text(error).foregroundColor(.red) }
            Button("Excluir minha conta", role: .destructive) { confirmation = true }.disabled(!canDelete)
            if busy { ProgressView() }
        }.disabled(busy).navigationTitle("Excluir conta").navigationBarTitleDisplayMode(.inline)
            .confirmationDialog("Excluir definitivamente sua conta?", isPresented: $confirmation, titleVisibility: .visible) {
                Button("Excluir definitivamente", role: .destructive) { Task { await remove() } }
            }
    }
    func remove() async {
        busy = true; error = nil; defer { busy = false; password = "" }
        do { try await session.api.deleteAccount(username: confirmedUsername, password: session.user?.hasPassword == true ? password : nil); session.invalidate() }
        catch { self.error = error.localizedDescription }
    }
}
