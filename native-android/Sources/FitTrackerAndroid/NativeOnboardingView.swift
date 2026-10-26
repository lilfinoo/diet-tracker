import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
import FitTrackerCore

/// Profile setup uses the same persisted fields required by the plan endpoints.
struct NativeOnboardingView: View {
    let onFinished: () -> Void
    let onPremium: () -> Void
    @Environment(NativeSession.self) var session
    @State var step = 0
    @State var goal = ""
    @State var age = ""
    @State var weight = ""
    @State var height = ""
    @State var gender = ""
    @State var activity = ""
    @State var busy = false
    @State var error: String?
    @State var selectedPlan: NativePlanKind?
    @State var loaded = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                HStack {
                    if step > 0 && step < 3 {
                        Button { step -= 1 } label: { Image(systemName: "chevron.left").frame(width: 44, height: 44) }.accessibilityLabel("Voltar")
                    }
                    Spacer()
                    Text(step < 3 ? "Seu primeiro dia" : "Seu próximo passo").font(.headline)
                    Spacer()
                    Button("Depois") { onFinished() }.disabled(busy)
                }.padding(.horizontal, 20).padding(.vertical, 8)
                if step < 3 { ProgressView(value: Double(step + 1), total: 3).tint(.fitBlue).padding(.horizontal, 20) }
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        if let error { Text(error).font(.footnote).foregroundColor(.red) }
                        content
                    }.padding(24)
                }
                if step < 3 {
                    Button {
                        if step == 2 { Task { await saveProfile() } } else { step += 1 }
                    } label: {
                        HStack { if busy { ProgressView() }; Text(step == 2 ? "Salvar meu perfil" : "Continuar").fontWeight(.semibold) }
                            .frame(maxWidth: .infinity).padding(16)
                    }.buttonStyle(.borderedProminent).disabled(busy || !canContinue)
                        .padding(.horizontal, 24).padding(.bottom, 20)
                }
            }.background(Color.fitBackground.ignoresSafeArea()).navigationBarHidden(true)
                .onAppear { populate() }
                .sheet(isPresented: Binding(get: { selectedPlan != nil }, set: { if !$0 { selectedPlan = nil } }), onDismiss: { onFinished() }) {
                    if let kind = selectedPlan { PlanGeneratorView(kind: kind, firstPlan: true) }
                }
        }.interactiveDismissDisabled(busy)
    }

    @ViewBuilder var content: some View {
        switch step {
        case 0:
            Image(systemName: "target").font(.system(size: 36)).foregroundColor(.fitBlue).padding(.vertical, 8)
            Text("O que você quer conquistar?").font(.title.bold())
            Text("Vamos usar seu objetivo para personalizar o treino e a alimentação.").foregroundColor(.secondary)
            choices([("Ganhar massa", "ganhar massa muscular"), ("Perder gordura", "perder peso"), ("Manter peso", "manter peso"), ("Mais saúde", "melhorar saude")], selection: $goal)
        case 1:
            Text("Um pouco sobre você").font(.title.bold())
            Text("Esses dados ajudam a adequar seus planos. Você pode atualizá-los no Perfil.").foregroundColor(.secondary)
            field("Idade", placeholder: "Anos", text: $age, keyboard: .numberPad)
            HStack(alignment: .top, spacing: 12) {
                field("Peso", placeholder: "kg", text: $weight, keyboard: .decimalPad)
                field("Altura", placeholder: "cm", text: $height, keyboard: .decimalPad)
            }
            Text("Referência para os cálculos").font(.subheadline.weight(.semibold))
            choices([("Masculino", "masculino"), ("Feminino", "feminino")], selection: $gender)
        case 2:
            Text("Como é sua rotina?").font(.title.bold())
            Text("Considere tanto os exercícios quanto a atividade do dia a dia.").foregroundColor(.secondary)
            choices([("Pouco movimento", "sedentario"), ("Atividade leve", "leve"), ("Atividade moderada", "moderado"), ("Atividade intensa", "intenso")], selection: $activity)
        case 3:
            Image(systemName: "sparkles").font(.system(size: 36)).foregroundColor(.fitBlue)
            Text("Um plano para evoluir").font(.title.bold())
            Text("Conheça o Premium para criar novos planos e continuar usando os recursos de IA.").foregroundColor(.secondary)
            Label("Treino e alimentação personalizados", systemImage: "checkmark.circle")
            Label("Acompanhamento da sua evolução", systemImage: "chart.line.uptrend.xyaxis")
            Button { onPremium() } label: { Text("Conhecer o Premium").fontWeight(.semibold).frame(maxWidth: .infinity).padding(16) }.buttonStyle(.borderedProminent)
            Button { step = 4 } label: { Text("Continuar grátis").frame(maxWidth: .infinity).padding(14) }.buttonStyle(.bordered)
            Text("No gratuito: 1 treino e 1 dieta com IA, além de 3 registros por foto ou descrição, uma única vez por conta. Monte e edite planos manualmente e use seus treinos sem assinatura.").font(.caption).foregroundColor(.secondary)
        default:
            Text("Por onde você quer começar?").font(.title.bold())
            Text("Você revisa o resultado antes de ativar. Seus dados de perfil já estão preenchidos.").foregroundColor(.secondary)
            planChoice("Criar meu treino", description: "Exercícios para seu objetivo e equipamentos", icon: "dumbbell.fill", kind: .workout)
            planChoice("Criar minha dieta", description: "Refeições que combinam com sua rotina", icon: "fork.knife", kind: .diet)
            Text("A autorização para processamento por IA é solicitada separadamente; nada é gerado ao escolher esta opção.").font(.caption).foregroundColor(.secondary)
        }
    }

    func choices(_ options: [(String, String)], selection: Binding<String>) -> some View {
        VStack(spacing: 10) {
            ForEach(options, id: \.1) { option in
                Button { selection.wrappedValue = option.1 } label: {
                    HStack { Text(option.0).font(.body.weight(.medium)); Spacer(); Image(systemName: selection.wrappedValue == option.1 ? "checkmark.circle.fill" : "circle").foregroundColor(.fitBlue) }
                        .padding(17).background(selection.wrappedValue == option.1 ? Color.fitBlue.opacity(0.16) : Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                }.buttonStyle(.plain).accessibilityAddTraits(selection.wrappedValue == option.1 ? .isSelected : [])
            }
        }
    }
    func field(_ title: String, placeholder: String, text: Binding<String>, keyboard: UIKeyboardType) -> some View {
        VStack(alignment: .leading, spacing: 8) { Text(title).font(.caption.weight(.semibold)); TextField(placeholder, text: text).keyboardType(keyboard).padding(15).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14)).accessibilityLabel(Text(title)) }
    }
    func planChoice(_ title: String, description: String, icon: String, kind: NativePlanKind) -> some View {
        Button { selectedPlan = kind } label: {
            HStack(spacing: 14) {
                Image(systemName: icon).font(.title2).foregroundColor(.fitBlue).frame(width: 42)
                VStack(alignment: .leading, spacing: 6) { Text(title).font(.headline); Text(description).font(.caption).foregroundColor(.secondary) }
                Spacer(); Image(systemName: "chevron.right").font(.caption)
            }.padding(18).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain)
    }
    var canContinue: Bool {
        if step == 0 { return !goal.isEmpty }
        if step == 2 { return !activity.isEmpty }
        guard let years = Int(age), let kg = number(weight), let cm = number(height) else { return false }
        return (18...120).contains(years) && (30...300).contains(kg) && (120...250).contains(cm) && !gender.isEmpty
    }
    func number(_ value: String) -> Double? { Double(value.replacingOccurrences(of: ",", with: ".")) }
    func populate() {
        guard !loaded else { return }; loaded = true
        let profile = session.profile?.profile
        goal = profile?.goal ?? ""; age = profile?.age.map(String.init) ?? ""
        weight = profile?.weight.map { String($0) } ?? ""; height = profile?.height.map { String($0) } ?? ""
        gender = profile?.gender ?? ""; activity = profile?.activityLevel ?? ""
        if session.profile?.profileComplete == true { step = 3 }
    }
    func saveProfile() async {
        guard !busy, canContinue else { return }; busy = true; error = nil
        defer { busy = false }
        do {
            _ = try await session.api.updateProfile(ProfileChanges(age: Int(age), gender: gender, goal: goal, activityLevel: activity, dietaryRestrictions: nil, weight: number(weight), height: number(height)))
            try await session.refreshProfile()
            step = 3
        } catch { self.error = error.localizedDescription }
    }
}

