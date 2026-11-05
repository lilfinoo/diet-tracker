import SwiftUI
import FitTrackerCore

struct NativeDietSlotView: View {
    let slot: DietDaySlot
    let date: String
    var compact = false
    @EnvironmentObject private var session: NativeSession
    @EnvironmentObject private var diary: NativeDietStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.sizeCategory) private var textSize
    @State private var busy = false
    @State private var error: String?
    @State private var confirmReset = false
    @State private var showAlternatives = false
    @State private var selectedAlternative = 0
    @State private var swipeOffset: CGFloat = 0
    @State private var horizontalSwipe: Bool?
    @State private var showingDescription = false
    @State private var showingDifferentMeal = false
    @State private var globalOrigin = CGPoint.zero

    private var meal: DietMealAlternative? { slot.alternatives.first { $0.id == slot.selectedPlanMealId } }
    private var pending: Bool { slot.result == "pending" }
    private var mealStyle: (symbol: String, color: Color) {
        let label = slot.label.folding(options: .diacriticInsensitive, locale: Locale(identifier: "pt_BR")).lowercased()
        if label.contains("lanche") { return ("takeoutbag.and.cup.and.straw.fill", .pink) }
        if label.contains("cafe") || label.contains("manha") { return ("cup.and.saucer.fill", .orange) }
        if label.contains("almoco") { return ("fork.knife", .blue) }
        if label.contains("jantar") || label.contains("ceia") { return ("moon.stars.fill", .purple) }
        return ("fork.knife.circle.fill", .cyan)
    }

    var body: some View {
        ZStack {
            HStack {
                if swipeOffset > 8 {
                    Label(L("Pular"), systemImage: "forward.end.fill").foregroundColor(.orange).padding(.leading, 18)
                }
                Spacer()
                if swipeOffset < -8 {
                    Label(L("Registrar"), systemImage: "checkmark.circle.fill").foregroundColor(.green).padding(.trailing, 18)
                }
            }.font(.subheadline.weight(.semibold))
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    Image(systemName: mealStyle.symbol).font(.system(size: 20))
                        .foregroundColor(mealStyle.color).frame(width: 40, height: 40)
                        .background(mealStyle.color.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 6) {
                        Text(slot.label).font(.headline)
                        if compact && textSize.isAccessibilityCategory { statusBadge }
                    }
                    Spacer()
                    if compact && !textSize.isAccessibilityCategory { statusBadge }
                    if diary.isPending(date: date, slotKey: slot.slotKey) && !pending {
                        Text(L("Sincronizando")).font(.caption).foregroundColor(.secondary)
                    }
                    if busy && pending { ProgressView() }
                    if pending && slot.alternatives.count > 1 {
                        Button {
                            selectedAlternative = slot.selectedPlanMealId
                            error = nil
                            showAlternatives = true
                        } label: {
                            Image(systemName: "ellipsis").frame(width: 44, height: 44).contentShape(Rectangle())
                        }.accessibilityLabel(L("Trocar opção de \(slot.label)"))
                    }
                }
                if let meal {
                    if compact {
                        Button { withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) { showingDescription.toggle() } } label: {
                            Text(slot.entry?.description ?? meal.description).font(.subheadline).foregroundColor(.secondary)
                                .lineLimit(showingDescription ? nil : 2).multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
                        }.buttonStyle(.plain).accessibilityHint(L("Toque para expandir ou recolher os alimentos"))
                    } else {
                        Text(slot.entry?.description ?? meal.description).font(.subheadline).foregroundColor(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if let calories = slot.entry?.calories ?? (pending || slot.result == "skipped" ? meal.calories : nil) {
                        Text(L("\(Int(calories)) kcal\(slot.entry == nil ? L(" previstas") : L(" registradas"))"))
                            .font(.caption).foregroundColor(.secondary)
                    }
                }
                if pending, meal == nil {
                    NativeRecoveryCard(title: L("Vamos conferir esta refeição?"), message: L("Os alimentos desta opção ainda não carregaram. Atualize antes de registrar o consumo."), systemImage: "fork.knife", actionTitle: L("Atualizar refeição")) {
                        Task {
                            let owner = session.user?.id
                            await diary.retry(date, api: session.api, isCurrentOwner: { session.user?.id == owner })
                        }
                    }
                }
                if pending && meal != nil {
                    VStack(spacing: 8) {
                        Button { Task { await setOutcome(.consumedPlanned) } } label: {
                            Label(L("Comi como planejado"), systemImage: "checkmark")
                                .frame(maxWidth: .infinity, minHeight: 28)
                        }.buttonStyle(FitPrimaryButtonStyle(compact: true))
                        HStack {
                            Button(L("Comi diferente")) { showingDifferentMeal = true }.frame(minHeight: 44)
                            Spacer()
                            Button(L("Não fiz esta refeição")) { Task { await setOutcome(.skipped) } }.frame(minHeight: 44)
                        }.font(.subheadline)
                    }.font(.subheadline)
                } else if !pending {
                    HStack {
                        Label(status, systemImage: slot.result == "skipped" ? "minus.circle" : "checkmark.circle.fill")
                            .font(.subheadline).foregroundColor(slot.result == "skipped" ? .secondary : .green)
                        Spacer()
                        Button(L("Corrigir")) { confirmReset = true }.font(.subheadline)
                    }
                }
                if let error { NativeRecoveryCard(title: L("Sua escolha continua aqui"), message: error) }
            }
            .frame(maxWidth: .infinity, alignment: .leading).padding(16)
            .background(compact ? FitTrackerTheme.cardGradient : LinearGradient(colors: [.fitSurface, .fitSurface], startPoint: .top, endPoint: .bottom), in: RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius))
            .overlay(RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius).stroke(compact ? FitTrackerTheme.electricBlue.opacity(0.18) : .clear, lineWidth: 1))
            .offset(x: swipeOffset)
        }
        .background(RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius).fill(swipeOffset < -8 ? Color.green.opacity(0.16) : Color.orange.opacity(0.16)))
        .clipShape(RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius))
        .background(GeometryReader { proxy in
            Color.clear.preference(key: NativeDietSlotOriginKey.self, value: proxy.frame(in: .global).origin)
        })
        .onPreferenceChange(NativeDietSlotOriginKey.self) { globalOrigin = $0 }
        .sheet(isPresented: $showingDifferentMeal) { NativeMealComposer(date: date, slot: slot) }
        .simultaneousGesture(DragGesture(minimumDistance: 16)
            .onChanged { value in
                guard pending, !busy, !diary.isPending(date: date, slotKey: slot.slotKey) else { return }
                if horizontalSwipe == nil {
                    horizontalSwipe = abs(value.translation.width) > abs(value.translation.height) * 1.35
                }
                guard horizontalSwipe == true else { return }
                swipeOffset = reduceMotion ? 0 : value.translation.width * 0.9
            }
            .onEnded { value in
                defer { horizontalSwipe = nil }
                guard pending, !busy, !diary.isPending(date: date, slotKey: slot.slotKey) else { return }
                if horizontalSwipe == true, abs(value.translation.width) >= 85 {
                    let origin = CGPoint(x: globalOrigin.x + value.startLocation.x, y: globalOrigin.y + value.startLocation.y)
                    Task { await setOutcome(value.translation.width < 0 ? .consumedPlanned : .skipped, origin: origin) }
                } else {
                    withAnimation(reduceMotion ? nil : .spring(response: 0.32, dampingFraction: 0.85)) { swipeOffset = 0 }
                }
            })
        .disabled(busy || diary.isPending(date: date, slotKey: slot.slotKey))
        .sheet(isPresented: $showAlternatives) { alternativesSheet }
        .confirmationDialog(L("Corrigir esta refeição?"), isPresented: $confirmReset, titleVisibility: .visible) {
            Button(L("Remover resultado e escolher novamente"), role: .destructive) { Task { await reset() } }
        } message: {
            Text(L("O consumo vinculado a esta refeição será removido dos totais do dia. Depois você poderá escolher outra opção e registrar novamente."))
        }
    }

    private var statusBadge: some View {
        Text(pending ? L("Planejado") : slot.result == "skipped" ? L("Pulada") : L("Registrada"))
            .font(.caption2.weight(.medium)).foregroundColor(pending ? .mint : .secondary)
            .padding(.horizontal, 8).padding(.vertical, 5)
            .background((pending ? Color.mint : Color.gray).opacity(0.1), in: Capsule())
            .overlay(Capsule().stroke((pending ? Color.mint : Color.gray).opacity(0.25), lineWidth: 1))
    }

    private var alternativesSheet: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text(slot.label).font(.title3.bold())
                    Text(L("Escolha o que combina melhor com seu dia.")).font(.subheadline).foregroundColor(.secondary)
                    ForEach(Array(slot.alternatives.enumerated()), id: \.element.id) { index, alternative in
                        Button { selectedAlternative = alternative.id } label: {
                            VStack(alignment: .leading, spacing: 12) {
                                HStack {
                                    Text(L("Opção \(index + 1)")).font(.caption.weight(.semibold))
                                    Spacer()
                                    if alternative.id == selectedAlternative {
                                        Label(L("Selecionada"), systemImage: "checkmark").font(.caption)
                                    }
                                }.foregroundColor(.fitBlue)
                                Text(alternative.description).font(.body).foregroundColor(.primary)
                                    .fixedSize(horizontal: false, vertical: true).multilineTextAlignment(.leading)
                                if let calories = alternative.calories {
                                    Text(L("\(Int(calories)) kcal previstas")).font(.caption).foregroundColor(.secondary)
                                }
                            }.frame(maxWidth: .infinity, alignment: .leading).padding(18)
                                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                                .overlay(RoundedRectangle(cornerRadius: 18)
                                    .stroke(alternative.id == selectedAlternative ? Color.fitBlue : Color.white.opacity(0.08), lineWidth: 1))
                        }.buttonStyle(.plain).accessibilityAddTraits(alternative.id == selectedAlternative ? .isSelected : [])
                    }
                    if let error { NativeRecoveryCard(title: L("Não confirmamos a troca ainda"), message: error) }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(L("Trocar refeição")).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { showAlternatives = false }.disabled(busy) } }
            .safeAreaInset(edge: .bottom) {
                Button {
                    Task {
                        if await perform({ try await session.api.selectDietAlternative(date: date, slotKey: slot.slotKey, mealId: selectedAlternative) }) {
                            showAlternatives = false
                        }
                    }
                } label: {
                    HStack { if busy && pending { ProgressView() }; Text(L("Usar esta opção")).fontWeight(.semibold) }
                        .frame(maxWidth: .infinity).padding(.vertical, 10)
                }.fitGlassButton(prominent: true).disabled(busy).padding(20).background(Color.fitBackground)
            }
            .interactiveDismissDisabled(busy)
        }.navigationViewStyle(.stack)
    }

    private var status: String {
        switch slot.result {
        case "consumed_planned": return L("Registrada como planejado")
        case "consumed_different": return L("Consumo diferente registrado")
        case "skipped": return L("Refeição pulada")
        default: return L("Resultado registrado")
        }
    }
    @MainActor
    private func setOutcome(_ outcome: DietSlotOutcome, origin: CGPoint? = nil) async {
        guard !busy, !diary.isPending(date: date, slotKey: slot.slotKey), let owner = session.user?.id else { return }
        busy = true
        swipeOffset = 0
        await diary.setOutcome(date: date, slot: slot, outcome: outcome, origin: origin, api: session.api,
            isCurrentOwner: { session.user?.id == owner })
        busy = false
    }
    private func reset() async {
        _ = await perform { try await session.api.resetDietSlotOutcome(date: date, slotKey: slot.slotKey) }
    }
    @MainActor
    private func perform(_ action: @escaping @MainActor () async throws -> Void) async -> Bool {
        guard !busy else { return false }; busy = true; error = nil
        guard let owner = session.user?.id else { busy = false; return false }
        defer { busy = false }
        let succeeded = await diary.mutateSlot(date: date, slotKey: slot.slotKey, api: session.api,
            isCurrentOwner: { session.user?.id == owner }, action: action)
        if !succeeded, session.user?.id == owner {
            error = diary.errors[date] ?? L("Não foi possível confirmar sua escolha. Ela continua selecionada; tente novamente quando estiver conectado.")
        }
        return succeeded
    }
}

private struct NativeDietSlotOriginKey: PreferenceKey {
    static var defaultValue = CGPoint.zero
    static func reduce(value: inout CGPoint, nextValue: () -> CGPoint) { value = nextValue() }
}
