import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
import FitTrackerCore

struct NativeDietSlotView: View {
    let slot: DietDaySlot
    let date: String
    var compact = false
    @Environment(NativeSession.self) var session
    @Environment(NativeDietStore.self) var diary
    @Environment(\.accessibilityReduceMotion) var reduceMotion
    @State var busy = false
    @State var error: String?
    @State var confirmReset = false
    @State var showAlternatives = false
    @State var selectedAlternative = 0
    @State var swipeOffset: CGFloat = 0
    @State var horizontalSwipe: Bool?
    @State var showingDescription = false

    var meal: DietMealAlternative? { slot.alternatives.first { $0.id == slot.selectedPlanMealId } }
    var pending: Bool { slot.result == "pending" }
    var mealStyle: (symbol: String, color: Color) {
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
                    Label("Pular", systemImage: "forward.end.fill").foregroundColor(.orange).padding(.leading, 18)
                }
                Spacer()
                if swipeOffset < -8 {
                    Label("Registrar", systemImage: "checkmark.circle.fill").foregroundColor(.green).padding(.trailing, 18)
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
                        if compact { statusBadge }
                    }
                    Spacer()
                    if diary.isPending(date: date, slotKey: slot.slotKey) && !pending {
                        Text("Sincronizando").font(.caption).foregroundColor(.secondary)
                    }
                    if busy && pending { ProgressView() }
                    if pending && slot.alternatives.count > 1 {
                        Button {
                            selectedAlternative = slot.selectedPlanMealId
                            error = nil
                            showAlternatives = true
                        } label: {
                            Image(systemName: "ellipsis").frame(width: 44, height: 44).contentShape(Rectangle())
                        }.accessibilityLabel("Trocar opção de \(slot.label)")
                    }
                }
                if let meal {
                    if compact {
                        Button { withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) { showingDescription.toggle() } } label: {
                            Text(slot.entry?.description ?? meal.description).font(.subheadline).foregroundColor(.secondary)
                                .lineLimit(showingDescription ? nil : 2).multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
                        }.buttonStyle(.plain).accessibilityLabel(Text("\(slot.entry?.description ?? meal.description). Toque para expandir ou recolher os alimentos"))
                    } else {
                        Text(slot.entry?.description ?? meal.description).font(.subheadline).foregroundColor(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if let calories = slot.entry?.calories ?? (pending || slot.result == "skipped" ? meal.calories : nil) {
                        Text("\(Int(calories)) kcal\(slot.entry == nil ? " previstas" : " registradas")")
                            .font(.caption).foregroundColor(.secondary)
                    }
                }
                if pending {
                    HStack {
                        Button { Task { await setOutcome(.consumedPlanned) } } label: {
                            Label("Comi como planejado", systemImage: "checkmark")
                                .lineLimit(1).minimumScaleFactor(0.75).frame(maxWidth: .infinity)
                        }.buttonStyle(FitPrimaryButtonStyle(compact: true))
                        Button { Task { await setOutcome(.skipped) } } label: { Label("Pular", systemImage: "forward.fill").font(.caption.weight(.medium)).padding(.vertical, 6) }.buttonStyle(.bordered)
                    }.font(.subheadline)
                } else {
                    HStack {
                        Label(status, systemImage: slot.result == "skipped" ? "minus.circle" : "checkmark.circle.fill")
                            .font(.subheadline).foregroundColor(slot.result == "skipped" ? .secondary : .green)
                        Spacer()
                        Button("Corrigir") { confirmReset = true }.font(.subheadline)
                    }
                }
                if let error { Text(error).font(.footnote).foregroundColor(.red) }
            }
            .frame(maxWidth: .infinity, alignment: .leading).padding(16)
            .background(compact ? FitTrackerTheme.cardGradient : LinearGradient(colors: [.fitSurface, .fitSurface], startPoint: .top, endPoint: .bottom), in: RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius))
            .overlay(RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius).stroke(compact ? FitTrackerTheme.electricBlue.opacity(0.18) : .clear, lineWidth: 1))
            .offset(x: swipeOffset)
        }
        .background(RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius).fill(swipeOffset < -8 ? Color.green.opacity(0.16) : Color.orange.opacity(0.16)))
        .clipShape(RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius))
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
                    Task { await setOutcome(value.translation.width < 0 ? .consumedPlanned : .skipped) }
                } else {
                    withAnimation(reduceMotion ? nil : .spring(response: 0.32, dampingFraction: 0.85)) { swipeOffset = 0 }
                }
            })
        .disabled(busy || diary.isPending(date: date, slotKey: slot.slotKey))
        .sheet(isPresented: $showAlternatives) { alternativesSheet }
        .confirmationDialog("Corrigir esta refeição?", isPresented: $confirmReset, titleVisibility: .visible) {
            Button("Remover resultado e escolher novamente", role: .destructive) { Task { await reset() } }
        } message: {
            Text("O consumo vinculado a esta refeição será removido dos totais do dia. Depois você poderá escolher outra opção e registrar novamente.")
        }
    }

    var statusBadge: some View {
        Text(pending ? "Planejado" : slot.result == "skipped" ? "Pulada" : "Registrada")
            .font(.caption2.weight(.medium)).foregroundColor(pending ? .mint : .secondary)
            .padding(.horizontal, 8).padding(.vertical, 5)
            .background((pending ? Color.mint : Color.gray).opacity(0.1), in: Capsule())
            .overlay(Capsule().stroke((pending ? Color.mint : Color.gray).opacity(0.25), lineWidth: 1))
    }

    var alternativesSheet: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        Text(slot.label).font(.title3.bold())
                        Text("Escolha o que combina melhor com seu dia.").font(.subheadline).foregroundColor(.secondary)
                        ForEach(Array(slot.alternatives.enumerated()), id: \.element.id) { index, alternative in
                            Button { selectedAlternative = alternative.id } label: {
                                VStack(alignment: .leading, spacing: 12) {
                                    HStack {
                                        Text("Opção \(index + 1)").font(.caption.weight(.semibold))
                                        Spacer()
                                        if alternative.id == selectedAlternative {
                                            Label("Selecionada", systemImage: "checkmark").font(.caption)
                                        }
                                    }.foregroundColor(.fitBlue)
                                    Text(alternative.description).font(.body).foregroundColor(.primary)
                                        .fixedSize(horizontal: false, vertical: true).multilineTextAlignment(.leading)
                                    if let calories = alternative.calories {
                                        Text("\(Int(calories)) kcal previstas").font(.caption).foregroundColor(.secondary)
                                    }
                                }.frame(maxWidth: .infinity, alignment: .leading).padding(18)
                                    .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
                                    .overlay(RoundedRectangle(cornerRadius: 18)
                                        .stroke(alternative.id == selectedAlternative ? Color.fitBlue : Color.white.opacity(0.08), lineWidth: 1))
                            }.buttonStyle(.plain).accessibilityAddTraits(alternative.id == selectedAlternative ? .isSelected : [])
                        }
                        if let error { Text(error).font(.footnote).foregroundColor(.red) }
                    }.padding(20)
                }
                Button {
                    Task {
                        if await perform({ try await session.api.selectDietAlternative(date: date, slotKey: slot.slotKey, mealId: selectedAlternative) }) {
                            showAlternatives = false
                        }
                    }
                } label: {
                    HStack { if busy && pending { ProgressView() }; Text("Usar esta opção").fontWeight(.semibold) }
                        .frame(maxWidth: .infinity).padding(.vertical, 10)
                }.buttonStyle(.borderedProminent).disabled(busy).padding(20).background(Color.fitBackground)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle("Trocar refeição").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { showAlternatives = false }.disabled(busy) } }
            .interactiveDismissDisabled(busy)
        }
    }

    var status: String {
        switch slot.result {
        case "consumed_planned": return "Registrada como planejado"
        case "consumed_different": return "Consumo diferente registrado"
        case "skipped": return "Refeição pulada"
        default: return "Resultado registrado"
        }
    }
    @MainActor
    func setOutcome(_ outcome: DietSlotOutcome) async {
        guard !busy, !diary.isPending(date: date, slotKey: slot.slotKey), let owner = session.user?.id else { return }
        busy = true
        swipeOffset = 0
        await diary.setOutcome(date: date, slot: slot, outcome: outcome, api: session.api,
            isCurrentOwner: { session.user?.id == owner })
        busy = false
    }
    func reset() async {
        _ = await perform { try await session.api.resetDietSlotOutcome(date: date, slotKey: slot.slotKey) }
    }
    @MainActor
    func perform(_ action: @escaping @MainActor () async throws -> Void) async -> Bool {
        guard !busy else { return false }; busy = true; error = nil
        guard let owner = session.user?.id else { busy = false; return false }
        defer { busy = false }
        return await diary.mutateSlot(date: date, slotKey: slot.slotKey, api: session.api,
            isCurrentOwner: { session.user?.id == owner }, action: action)
    }
}
