import SwiftUI
import FitTrackerCore

enum NativeFirstIntent: String {
    case diet, workout
}

enum NativeFirstDay {
    static func intent(owner: UUID) -> NativeFirstIntent? {
        UserDefaults.standard.string(forKey: key("intent", owner: owner)).flatMap(NativeFirstIntent.init(rawValue:))
    }

    static func hasFinished(owner: UUID) -> Bool {
        UserDefaults.standard.bool(forKey: key("finished", owner: owner))
    }

    static func finish(owner: UUID, intent: NativeFirstIntent?) {
        UserDefaults.standard.set(intent?.rawValue, forKey: key("intent", owner: owner))
        UserDefaults.standard.set(true, forKey: key("finished", owner: owner))
    }

    private static func key(_ field: String, owner: UUID) -> String {
        "fittracker.native.firstDay.\(owner.uuidString.lowercased()).\(field)"
    }
}

extension Notification.Name {
    static let nativeFirstAction = Notification.Name("fitTrackerFirstAction")
}

struct NativeOnboardingView: View {
    let onFinished: (NativeFirstIntent?) -> Void
    @EnvironmentObject private var session: NativeSession

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    Text(L("SEU PRIMEIRO DIA")).font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                    Text(L("Por onde você quer começar?")).font(.largeTitle.bold())
                    Text(L("Escolha uma primeira ação. Você pode explorar o app e personalizar seu perfil depois."))
                        .font(.body).foregroundColor(.secondary)
                    firstAction(L("Registrar uma refeição"), description: L("Comece com o que você comeu. O registro manual é gratuito."), icon: "fork.knife", intent: .diet)
                    firstAction(L("Começar pelo treino"), description: L("Monte seu treino ou crie um plano para sua rotina."), icon: "dumbbell.fill", intent: .workout)
                    Text(L("Se você optar por um plano personalizado, pediremos os dados necessários durante a criação."))
                        .font(.subheadline).foregroundColor(.secondary)
                    Button(L("Explorar o app")) { finish(nil) }
                        .frame(maxWidth: .infinity, minHeight: 44).fitGlassButton()
                }.padding(24)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationBarHidden(true)
        }.navigationViewStyle(.stack)
    }

    private func firstAction(_ title: String, description: String, icon: String, intent: NativeFirstIntent) -> some View {
        Button { finish(intent) } label: {
            HStack(alignment: .top, spacing: 14) {
                Image(systemName: icon).font(.title2).foregroundColor(.fitBlue).frame(width: 32).accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 8) {
                    Text(title).font(.headline)
                    Text(description).font(.subheadline).foregroundColor(.secondary)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").font(.caption).accessibilityHidden(true)
            }
            .padding(20).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 20))
        }.buttonStyle(.plain)
    }

    private func finish(_ intent: NativeFirstIntent?) {
        guard let owner = session.user?.id else { return }
        NativeFirstDay.finish(owner: owner, intent: intent)
        onFinished(intent)
    }
}

/// Requested only when the user chooses to create a personalized plan.
struct NativePlanProfileSetupView: View {
    let onSaved: () -> Void
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    @State private var step = 0
    @State private var goal = ""
    @State private var age = ""
    @State private var weight = ""
    @State private var height = ""
    @State private var gender = ""
    @State private var activity = ""
    @State private var busy = false
    @State private var attempted = false
    @State private var error: String?
    @State private var loaded = false
    @FocusState private var focusedField: ProfileField?

    private enum ProfileField: Hashable { case age, weight, height }

    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                HStack {
                    if step > 0 {
                        Button { focusedField = nil; attempted = false; step -= 1 } label: {
                            Image(systemName: "chevron.left").frame(width: 44, height: 44)
                        }.accessibilityLabel(L("Voltar")).disabled(busy)
                    }
                    Spacer()
                    Text(L("Seu perfil · \(step + 1) de 3")).font(.headline)
                    Spacer()
                    Button(L("Agora não")) { dismiss() }.frame(minHeight: 44).disabled(busy)
                }.padding(.horizontal, 20).padding(.vertical, 8)
                ProgressView(value: Double(step + 1), total: 3).tint(.fitBlue).padding(.horizontal, 20)
                    .accessibilityLabel(L("Configuração do perfil")).accessibilityValue(L("Etapa \(step + 1) de 3"))
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        content
                        if let error { Text(NativeLocalization.display(error)).font(.subheadline).foregroundColor(.red).accessibilityLabel(L("Erro: ") + error) }
                    }.padding(24)
                }
                Button { advance() } label: {
                    HStack {
                        if busy { ProgressView() }
                        Text(step == 2 ? L("Salvar e continuar") : L("Continuar")).fontWeight(.semibold)
                    }.frame(maxWidth: .infinity, minHeight: 44).padding(.vertical, 6)
                }.fitGlassButton(prominent: true).disabled(busy)
                    .padding(.horizontal, 24).padding(.bottom, 20)
            }
            .background(Color.fitBackground.ignoresSafeArea()).navigationBarHidden(true)
            .onAppear { populate() }
            .toolbar {
                ToolbarItemGroup(placement: .keyboard) {
                    Button(L("Anterior")) { focusedField = focusedField == .height ? .weight : .age }
                        .disabled(focusedField == .age)
                    Spacer()
                    Button(focusedField == .height ? L("Concluir") : L("Próximo")) { advanceFocus() }
                }
            }
        }.navigationViewStyle(.stack).interactiveDismissDisabled(busy)
    }

    @ViewBuilder private var content: some View {
        switch step {
        case 0:
            Text(L("O que você quer conquistar?")).font(.title.bold())
            Text(L("Seu objetivo ajuda a personalizar o plano. Você pode alterá-lo depois no Perfil.")).foregroundColor(.secondary)
            choices([(L("Ganhar massa"), "ganhar massa muscular"), (L("Perder gordura"), "perder peso"), (L("Manter peso"), "manter peso"), (L("Mais saúde"), "melhorar saude")], selection: $goal)
            if attempted && goal.isEmpty { validationMessage(L("Escolha um objetivo para continuar.")) }
        case 1:
            Text(L("Um pouco sobre você")).font(.title.bold())
            Text(L("Usamos esses dados para adequar seu plano.")).foregroundColor(.secondary)
            field(L("Idade"), unit: L("anos"), example: L("Ex.: 30"), text: $age, kind: .age, keyboard: .numberPad)
            field(L("Peso"), unit: "kg", example: L("Ex.: 70,5"), text: $weight, kind: .weight, keyboard: .decimalPad)
            field(L("Altura"), unit: "cm", example: L("Ex.: 175"), text: $height, kind: .height, keyboard: .decimalPad)
            Text(L("Referência para os cálculos")).font(.subheadline.weight(.semibold))
            choices([(L("Masculino"), "masculino"), (L("Feminino"), "feminino")], selection: $gender)
            if attempted && gender.isEmpty { validationMessage(L("Escolha a referência usada nos cálculos.")) }
        default:
            Text(L("Como é sua rotina?")).font(.title.bold())
            Text(L("Considere os exercícios e o movimento do dia a dia.")).foregroundColor(.secondary)
            choices([(L("Pouco movimento"), "sedentario"), (L("Atividade leve"), "leve"), (L("Atividade moderada"), "moderado"), (L("Atividade intensa"), "intenso")], selection: $activity)
            if attempted && activity.isEmpty { validationMessage(L("Escolha a opção que mais combina com sua rotina.")) }
        }
    }

    private func choices(_ options: [(String, String)], selection: Binding<String>) -> some View {
        VStack(spacing: 10) {
            ForEach(options, id: \.1) { option in
                Button { focusedField = nil; selection.wrappedValue = option.1 } label: {
                    HStack {
                        Text(option.0).font(.body.weight(.medium)); Spacer()
                        Image(systemName: selection.wrappedValue == option.1 ? "checkmark.circle.fill" : "circle").foregroundColor(.fitBlue).accessibilityHidden(true)
                    }.padding(17).background(selection.wrappedValue == option.1 ? Color.fitBlue.opacity(0.16) : Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                }.buttonStyle(.plain).accessibilityAddTraits(selection.wrappedValue == option.1 ? .isSelected : []).disabled(busy)
            }
        }
    }

    private func field(_ title: String, unit: String, example: String, text: Binding<String>, kind: ProfileField, keyboard: UIKeyboardType) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.subheadline.weight(.semibold))
            HStack {
                TextField(example, text: text).keyboardType(keyboard).focused($focusedField, equals: kind)
                    .submitLabel(kind == .height ? .done : .next).onSubmit { advanceFocus() }
                    .accessibilityLabel(L("\(title), em \(unit)")).accessibilityHint(fieldError(kind) ?? example)
                Text(unit).foregroundColor(.secondary).accessibilityHidden(true)
            }.padding(15).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14)).disabled(busy)
            if (attempted || !text.wrappedValue.isEmpty), let message = fieldError(kind) { validationMessage(message) }
        }
    }

    private func validationMessage(_ message: String) -> some View {
        Text(NativeLocalization.display(message)).font(.subheadline).foregroundColor(.orange).fixedSize(horizontal: false, vertical: true)
    }

    private func fieldError(_ field: ProfileField) -> String? {
        switch field {
        case .age:
            guard let value = Int(age.trimmingCharacters(in: .whitespacesAndNewlines)), (18...120).contains(value) else { return L("Informe sua idade em anos, entre 18 e 120.") }
        case .weight:
            guard let value = number(weight), (30...300).contains(value) else { return L("Informe seu peso em kg, entre 30 e 300. Ex.: 70,5.") }
        case .height:
            if let value = number(height), value > 0 && value < 3 { return L("Use centímetros: para 1,75 m, digite 175.") }
            guard let value = number(height), (120...250).contains(value) else { return L("Informe sua altura em cm, entre 120 e 250. Ex.: 175.") }
        }
        return nil
    }

    private func advanceFocus() {
        switch focusedField {
        case .age: focusedField = .weight
        case .weight: focusedField = .height
        default: focusedField = nil
        }
    }

    private func advance() {
        guard !busy else { return }
        attempted = true; error = nil
        if step == 0 { guard !goal.isEmpty else { return } }
        if step == 1 {
            for field in [ProfileField.age, .weight, .height] where fieldError(field) != nil { focusedField = field; return }
            guard !gender.isEmpty else { focusedField = nil; return }
        }
        if step == 2 {
            guard !activity.isEmpty else { return }
            Task { await saveProfile() }
        } else { focusedField = nil; attempted = false; step += 1 }
    }

    private func number(_ value: String) -> Double? { Double(value.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: ",", with: ".")) }
    private func populate() {
        guard !loaded else { return }; loaded = true
        let profile = session.profile?.profile
        goal = profile?.goal ?? ""; age = profile?.age.map(String.init) ?? ""
        weight = profile?.weight.map { String($0) } ?? ""; height = profile?.height.map { String($0) } ?? ""
        gender = profile?.gender ?? ""; activity = profile?.activityLevel ?? ""
    }
    private func saveProfile() async {
        guard !busy else { return }; busy = true; error = nil
        defer { busy = false }
        do {
            _ = try await session.api.updateProfile(ProfileChanges(age: Int(age.trimmingCharacters(in: .whitespacesAndNewlines)), gender: gender, goal: goal, activityLevel: activity, dietaryRestrictions: nil, weight: number(weight), height: number(height)))
            try await session.refreshProfile()
            dismiss(); onSaved()
        } catch { self.error = RequestFailure.message(error, fallback: L("Não foi possível salvar seu perfil. Suas respostas continuam aqui; tente novamente.")) }
    }
}

extension NativePlanKind: Identifiable { public var id: String { rawValue } }
