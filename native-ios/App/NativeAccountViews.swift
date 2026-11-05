import SwiftUI
import FitTrackerCore

private let aiConsentExplanation = L("Autorizo enviar ao Google Gemini e, se ele falhar, à OpenAI minhas mensagens, fotos de refeições e dados de perfil, alimentação, medidas e treino usados para gerar análises e planos. Posso revogar esta escolha no Perfil.")

struct NativeLoginView: View {
    var body: some View { NativeSocialLoginView() }
}

struct NativeProfileView: View {
    @EnvironmentObject private var session: NativeSession
    @State private var editor = false
    @State private var logout = false
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    HStack(spacing: 16) {
                        Text(String((session.user?.name ?? L("Você")).prefix(1))).font(.title.bold())
                            .frame(width: 62, height: 62).background(Color.fitBlue.opacity(0.22), in: RoundedRectangle(cornerRadius: 22))
                        VStack(alignment: .leading, spacing: 5) {
                            Text(session.user?.name ?? L("Seu perfil")).font(.title2.bold())
                            Text(session.hasPremium ? "PREMIUM" : L("PLANO GRATUITO")).font(.caption2.bold()).tracking(1).foregroundColor(.fitBlue)
                        }
                    }
                    HStack(alignment: .top, spacing: 12) {
                        metric(L("Objetivo"), NativeLocalization.display(session.profile?.profile?.goal ?? L("Não informado")))
                        metric(L("Peso"), session.profile?.profile?.weight.map { "\($0.formatted()) kg" } ?? "—")
                        metric(L("Altura"), session.profile?.profile?.height.map { "\($0.formatted()) cm" } ?? "—")
                    }.padding(.vertical, 16)
                    NativeFreeAccessCard()
                    if !session.hasPremium {
                        NavigationLink(destination: NativeSubscriptionView()) { NativePremiumBanner() }.buttonStyle(.plain)
                    }
                    NavigationLink(destination: NativeReferralView()) {
                        profileRow(L("Convide e ganhe Premium"), detail: L("3 novas contas por mês = 1 mês grátis"), icon: "gift")
                            .padding(.horizontal, 16).background(Color.fitBlue.opacity(0.12), in: RoundedRectangle(cornerRadius: 18))
                    }.buttonStyle(.plain)
                    Text(L("Do seu jeito")).font(.headline)
                    VStack(spacing: 0) {
                        Button { editor = true } label: { profileRow(L("Dados e objetivos"), detail: L("Medidas e personalização"), icon: "slider.horizontal.3") }
                        Divider()
                        NavigationLink(destination: NativePrivacyView()) { profileRow(L("Privacidade e IA"), detail: L("Você decide como seus dados são usados"), icon: "hand.raised") }
                        Divider()
                        NavigationLink(destination: NativeSubscriptionView()) { profileRow(L("Minha assinatura"), detail: L("Planos e gerenciamento"), icon: "crown") }
                    }.padding(.horizontal, 16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                    Text(L("Sua conta")).font(.headline)
                    VStack(spacing: 0) {
                        NavigationLink(destination: NativeLinkedAccountsView()) { profileRow(L("Acessos conectados"), detail: L("Google e Apple"), icon: "person.badge.key") }
                        Divider()
                        NativeLegalLinks().padding(.vertical, 20)
                        Divider()
                        Button { logout = true } label: { profileRow(L("Sair da conta"), detail: "", icon: "rectangle.portrait.and.arrow.right") }.disabled(session.busy)
                    }.padding(.horizontal, 16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                    NavigationLink(destination: NativeDeleteAccountView()) { Text(L("Excluir minha conta")).font(.caption).foregroundColor(.red) }
                }.padding(22)
            }.background(Color.fitBackground.ignoresSafeArea())
                .navigationTitle(L("Perfil")).navigationBarTitleDisplayMode(.inline)
                .sheet(isPresented: $editor) { NativeProfileEditor() }
                .confirmationDialog(L("Sair desta conta?"), isPresented: $logout, titleVisibility: .visible) {
                    Button(L("Sair"), role: .destructive) { Task { await session.logout() } }
                }
                .task { try? await session.refreshFreeAccess() }
        }.navigationViewStyle(.stack)
    }
    private func metric(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 7) { Text(label).font(.caption2).foregroundColor(.secondary); Text(value).font(.caption.bold()) }.frame(maxWidth: .infinity, alignment: .leading)
    }
    private func profileRow(_ title: String, detail: String, icon: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon).font(.title3).foregroundColor(.fitBlue).frame(width: 28)
            VStack(alignment: .leading, spacing: 5) { Text(title).font(.subheadline.weight(.semibold)); if !detail.isEmpty { Text(NativeLocalization.display(detail)).font(.caption2).foregroundColor(.secondary) } }
            Spacer(); Image(systemName: "chevron.right").font(.caption).foregroundColor(.secondary)
        }.padding(.vertical, 18).foregroundColor(.primary)
    }
}

struct NativePremiumBanner: View {
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "sparkles").font(.title2).foregroundColor(.yellow)
            VStack(alignment: .leading, spacing: 5) {
                Text(L("Seu próximo passo com Premium")).font(.subheadline.bold())
                Text(L("Mais planos e análises para sua rotina.")).font(.caption).foregroundColor(.secondary)
            }
            Spacer(minLength: 4); Image(systemName: "chevron.right").font(.caption)
        }.padding(18).foregroundColor(.primary).background(LinearGradient(colors: [Color.fitBlue.opacity(0.25), Color.fitSurface], startPoint: .leading, endPoint: .trailing), in: RoundedRectangle(cornerRadius: 18))
    }
}

private struct NativeProfileEditor: View {
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    @State private var age = ""
    @State private var weight = ""
    @State private var height = ""
    @State private var gender = ""
    @State private var goal = ""
    @State private var activity = ""
    @State private var restrictions = ""
    @State private var busy = false
    @State private var error: String?
    var body: some View {
        NavigationView {
            Form {
                Section(header: Text(L("Dados pessoais"))) {
                    TextField(L("Idade"), text: $age).keyboardType(.numberPad)
                    TextField(L("Peso (kg)"), text: $weight).keyboardType(.decimalPad)
                    TextField(L("Altura (cm)"), text: $height).keyboardType(.decimalPad)
                    Picker(L("Gênero"), selection: $gender) { Text(L("Não informado")).tag(""); Text(L("Masculino")).tag("masculino"); Text(L("Feminino")).tag("feminino") }
                }
                Section(header: Text(L("Objetivos e rotina"))) {
                    Picker(L("Objetivo"), selection: $goal) {
                        Text(L("Escolha")).tag(""); Text(L("Perder peso")).tag("perder peso"); Text(L("Ganhar massa muscular")).tag("ganhar massa muscular"); Text(L("Manter peso")).tag("manter peso"); Text(L("Melhorar saúde")).tag("melhorar saude")
                    }
                    Picker(L("Atividade"), selection: $activity) {
                        Text(L("Escolha")).tag(""); Text(L("Sedentário")).tag("sedentario"); Text(L("Leve")).tag("leve"); Text(L("Moderado")).tag("moderado"); Text(L("Intenso")).tag("intenso")
                    }
                    TextField(L("Restrições alimentares"), text: $restrictions)
                }
                Section { Text(L("Alterar peso ou altura também pode adicionar uma medição ao seu histórico.")).font(.footnote).foregroundColor(.secondary) }
                if let error { Text(NativeLocalization.display(error)).foregroundColor(.red) }
                if busy { ProgressView() }
            }.disabled(busy).navigationTitle(L("Dados e objetivos")).navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { dismiss() }.disabled(busy) }
                    ToolbarItem(placement: .confirmationAction) { Button(L("Salvar")) { Task { await save() } }.disabled(busy) }
                }.onAppear {
                    let profile = session.profile?.profile
                    age = profile?.age.map(String.init) ?? ""; weight = profile?.weight.map { String($0) } ?? ""; height = profile?.height.map { String($0) } ?? ""
                    gender = profile?.gender ?? ""; goal = profile?.goal ?? ""; activity = profile?.activityLevel ?? ""; restrictions = profile?.dietaryRestrictions ?? ""
                }
        }.navigationViewStyle(.stack).interactiveDismissDisabled(busy)
    }
    private func save() async {
        let parsedWeight = Double(weight.replacingOccurrences(of: ",", with: "."))
        let parsedHeight = Double(height.replacingOccurrences(of: ",", with: "."))
        guard (age.isEmpty || Int(age).map { (0...120).contains($0) } == true),
              (weight.isEmpty || parsedWeight.map { $0 > 0 && $0 <= 500 } == true),
              (height.isEmpty || parsedHeight.map { $0 > 0 && $0 <= 300 } == true) else { error = L("Confira idade, peso e altura."); return }
        let current = session.profile?.profile
        guard !(age.isEmpty && current?.age != nil), !(weight.isEmpty && current?.weight != nil), !(height.isEmpty && current?.height != nil) else {
            error = L("Mantenha os valores atuais ou informe novos valores. Para remover medidas, use o histórico de medições."); return
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
    @EnvironmentObject private var session: NativeSession
    @State private var status: ConsentStatus?
    @State private var granted = false
    @State private var busy = false
    @State private var error: String?
    var body: some View {
        Form {
            if let status {
                Section { Text(status.ai.accepted ? L("IA autorizada") : L("IA não autorizada")).font(.headline); Text(aiConsentExplanation).font(.footnote); Toggle(L("Autorizar processamento por IA"), isOn: $granted) }
                Section { Text(L("Revogar bloqueia novas solicitações à IA.")).font(.footnote); Button(L("Salvar escolha")) { Task { await save() } }.disabled(busy || granted == status.ai.accepted) }
            } else if error == nil { ProgressView(L("Carregando preferências…")) }
            if let error { Text(NativeLocalization.display(error)).foregroundColor(.red); Button(L("Tentar novamente")) { Task { await load() } } }
        }.navigationTitle(L("Privacidade e IA")).navigationBarTitleDisplayMode(.inline).task { await load() }.disabled(busy)
    }
    private func load() async { do { let result = try await session.api.consentStatus(); status = result; granted = result.ai.accepted; error = nil } catch { self.error = error.localizedDescription } }
    private func save() async {
        guard let status else { return }; busy = true; defer { busy = false }
        do { self.status = try await session.api.updateConsent(granted: granted, version: status.versions.ai.version); error = nil } catch { self.error = error.localizedDescription }
    }
}

private struct LabeledContentCompat: View {
    let label: String; let value: String
    var body: some View { HStack { Text(label); Spacer(); Text(value).foregroundColor(.secondary) } }
}

private struct NativeDeleteAccountView: View {
    @EnvironmentObject private var session: NativeSession
    @State private var username = ""
    @State private var password = ""
    @State private var understood = false
    @State private var confirmation = false
    @State private var busy = false
    @State private var error: String?
    private var expectedUsername: String { session.user?.username ?? "" }
    private var confirmedUsername: String { username.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var canDelete: Bool {
        understood && !expectedUsername.isEmpty && confirmedUsername == "EXCLUIR"
            && (session.user?.hasPassword != true || !password.isEmpty)
    }
    var body: some View {
        Form {
            Section { Text(L("Sua conta e seus dados serão excluídos definitivamente. Esta ação não pode ser desfeita.")); Text(L("Excluir a conta não cancela uma assinatura da Apple.")); Link(L("Gerenciar assinatura na Apple"), destination: URL(string: "https://apps.apple.com/account/subscriptions")!) }
            Section {
                Text(L("Para confirmar, digite EXCLUIR:"))
                TextField("EXCLUIR", text: $username).textInputAutocapitalization(.never).disableAutocorrection(true)
                if !username.isEmpty && confirmedUsername != "EXCLUIR" {
                    Text(L("Digite EXCLUIR para confirmar a exclusão.")).font(.footnote).foregroundColor(.orange)
                }
                if session.user?.hasPassword == true { SecureField(L("Senha atual"), text: $password).textContentType(.password) }
                else { Text(L("Por segurança, entre novamente com Apple ou Google antes de excluir, caso seu último login tenha sido há mais de 10 minutos. Você pode sair e entrar novamente pelo Perfil.")).font(.footnote) }
                Toggle(L("Entendo que a exclusão é definitiva"), isOn: $understood)
            }
            if let error { Text(NativeLocalization.display(error)).foregroundColor(.red) }
            Button(L("Excluir minha conta"), role: .destructive) { confirmation = true }.disabled(!canDelete)
            if busy { ProgressView() }
        }.disabled(busy).navigationTitle(L("Excluir conta")).navigationBarTitleDisplayMode(.inline)
            .confirmationDialog(L("Excluir definitivamente sua conta?"), isPresented: $confirmation, titleVisibility: .visible) {
                Button(L("Excluir definitivamente"), role: .destructive) { Task { await remove() } }
            }
    }
    private func remove() async {
        busy = true; error = nil; defer { busy = false; password = "" }
        let owner = session.user?.id
        do {
            try await session.api.deleteAccount(username: expectedUsername, password: session.user?.hasPassword == true ? password : nil)
            if let owner { try? NutritionAnalysisRecovery().clear(owner: owner) }
            session.invalidate()
        }
        catch { self.error = error.localizedDescription }
    }
}
