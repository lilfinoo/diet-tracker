import SwiftUI
import UIKit
import PhotosUI
import AVFoundation
import FitTrackerCore

struct NativeMealComposer: View {
    let date: String
    var slot: DietDaySlot? = nil
    var editingEntry: DietEntry? = nil
    @EnvironmentObject private var session: NativeSession
    @EnvironmentObject private var diary: NativeDietStore
    @Environment(\.dismiss) private var dismiss
    @State private var mode: String?
    @State private var loaded = false
    @State private var foodItems: [MealFoodPortion] = []
    @State private var editingFood: MealFoodPortion?
    @State private var pendingFood: MealFoodPortion?
    @State private var confirmFoodReplacement = false
    @State private var mealType = "Almoço"
    @State private var description = ""
    @State private var calories = ""
    @State private var protein = ""
    @State private var carbs = ""
    @State private var fat = ""
    @State private var error: String?
    @State private var busy = false
    @State private var saveAttempted = false
    @State private var showingDiscard = false
    @State private var analysisFailed = false
    @State private var resumingAnalysis = false
    @State private var recoveryLoadFailed = false
    @State private var recoveryDraft: NutritionAnalysisDraft?
    @State private var restoredDate: String?
    @State private var idempotencyKey = UUID().uuidString
    @State private var image: UIImage?
    @State private var picker: String?
    @State private var showFoods = false
    @State private var analysisTask: Task<Void, Never>?
    @State private var reviewed = false
    @State private var showingPremium = false
    @State private var sharingMeal: MealShareImage?
    @State private var usedFreeCredit = false
    @State private var remainingAfterAnalysis: Int?
    @State private var creditLoadFailed = false
    @State private var showingCreditConfirmation = false
    @State private var confirmationLoading = false
    @State private var confirmationError: String?
    @State private var confirmationMessage: String?
    @State private var confirmationVersion = 0
    @State private var premiumAfterConfirmation = false
    private let creditMint = Color(red: 0.49, green: 0.9, blue: 0.79)

    private var entryDate: String { restoredDate ?? date }
    private var linkedSlotKey: String? { recoveryDraft.map { $0.slotKey } ?? slot?.slotKey }
    private var linkedMealId: Int? { recoveryDraft.map { $0.planMealId } ?? slot?.selectedPlanMealId }
    private let analysisRecovery = NutritionAnalysisRecovery()

    private var creditsExhausted: Bool {
        !session.hasPremium && (remainingAfterAnalysis ?? session.freeAccess?.photos.remaining) == 0
    }

    private var hasDraft: Bool {
        recoveryLoadFailed || recoveryDraft != nil || image != nil || !description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || [calories, protein, carbs, fat].contains { !$0.isEmpty }
    }

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                if recoveryLoadFailed {
                    NativeRecoveryCard(title: L("Sua análise precisa de atenção"), message: error ?? L("Não conseguimos recuperar a análise preservada."))
                    Button(L("Tentar recuperar")) { restoreAnalysis() }.fitGlassButton()
                }
                if recoveryDraft != nil {
                    Text(reviewed ? L("Sua análise foi recuperada. Revise antes de salvar.") : L("Sua análise está preservada. Verificar o resultado recupera a mesma solicitação, sem iniciar outra."))
                        .font(.caption).foregroundColor(.secondary)
                }
                if mode != nil, mode != "manual", !session.hasPremium { creditNotice }
                if mode == nil {
                    Text(L("Como quer registrar?")).font(.title2.bold())
                    Text(L("Escolha o caminho mais rápido para esta refeição.")).foregroundColor(.secondary)
                    choice(L("Foto da refeição"), icon: "camera", mode: "photo")
                    choice(L("Descrever o que comeu"), icon: "pencil", mode: "description")
                    choice(L("Registrar manualmente"), icon: "square.and.pencil", mode: "manual")
                } else {
                    Text(readableDate).font(.subheadline.weight(.semibold)).foregroundColor(.secondary)
                    if linkedSlotKey != nil { Label(L("Este registro substitui o consumo planejado"), systemImage: "arrow.triangle.2.circlepath").font(.caption).foregroundColor(.secondary) }
                    Picker(L("Tipo"), selection: $mealType) { ForEach(["Café da manhã", "Almoço", "Café da tarde", "Lanche", "Jantar", "Outros"], id: \.self) { Text(NativeLocalization.display($0)).tag($0) } }
                        .pickerStyle(.menu).disabled(busy || saveAttempted || editingEntry?.dailyMealStateId != nil || linkedSlotKey != nil)
                    if mode == "photo", !reviewed {
                        if let image { Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 260).clipShape(RoundedRectangle(cornerRadius: 18)) }
                        HStack {
                            Button { startCamera() } label: { Label(image == nil ? L("Tirar foto") : L("Tirar outra"), systemImage: "camera") }.fitGlassButton(prominent: true)
                            Button { picker = "library" } label: { Label(L("Galeria"), systemImage: "photo") }.fitGlassButton()
                        }.disabled(busy || saveAttempted || recoveryDraft != nil)
                    }
                    if mode == "manual" {
                        foodList
                        Button { showFoods = true } label: { Label(L("Adicionar alimento"), systemImage: "plus.circle") }.fitGlassButton().frame(minHeight: 44).disabled(busy || saveAttempted)
                    }
                    if mode != "manual", !reviewed {
                        Text(mode == "photo" ? L("Descrição da refeição (opcional)") : L("O que você comeu?")).font(.subheadline.weight(.semibold))
                        if mode == "photo" {
                            Text(L("Conte o que aparece no prato e as quantidades aproximadas.")).font(.caption).foregroundColor(.secondary)
                        }
                        TextEditor(text: $description).frame(minHeight: 110).padding(8).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16)).accessibilityLabel(L("Descrição da refeição")).disabled(busy || saveAttempted || recoveryDraft != nil)
                            .overlay(alignment: .topLeading) {
                                if description.isEmpty {
                                    Text(L("Ex.: arroz, feijão e frango grelhado; uma concha de arroz e um filé."))
                                        .font(.body).foregroundColor(.secondary.opacity(0.8)).padding(16).allowsHitTesting(false)
                                }
                            }
                        Text(L("A estimativa aparece para revisão. Nada é salvo automaticamente.")).font(.caption).foregroundColor(.secondary)
                    }
                    if mode == "manual", !reviewed {
                        Text(L("O que você comeu?")).font(.subheadline.weight(.semibold))
                        Text(L("Ex.: arroz, feijão e frango. Você pode informar os nutrientes ou usar a tabela.")).font(.caption).foregroundColor(.secondary)
                        TextEditor(text: $description).frame(minHeight: 90).padding(8).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16)).accessibilityLabel(L("Descrição da refeição")).disabled(busy || saveAttempted)
                    }
                    if reviewed, let image {
                        Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 170).clipShape(RoundedRectangle(cornerRadius: 18))
                    }
                    if reviewed || mode == "manual" {
                        Text(L("Revise os valores antes de salvar")).font(.headline)
                        Text(L("Proteínas, carboidratos e gorduras são opcionais. Campos vazios ficam como não informados.")).font(.caption).foregroundColor(.secondary)
                        if reviewed {
                            Text(L("Descrição da refeição")).font(.subheadline.weight(.semibold))
                            TextEditor(text: $description).frame(minHeight: 90).padding(8).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
                                .accessibilityLabel(L("Descrição da refeição")).disabled(busy || saveAttempted)
                        }
                        if !foodItems.isEmpty { Text(L("Totais calculados pelos alimentos. Toque na quantidade de um item para ajustar.")).font(.caption).foregroundColor(.secondary) }
                        VStack(spacing: 0) {
                            numberField(L("Calorias (kcal)"), text: $calories)
                            Divider(); numberField(L("Proteínas (g)"), text: $protein)
                            Divider(); numberField(L("Carboidratos (g)"), text: $carbs)
                            Divider(); numberField(L("Gorduras (g)"), text: $fat)
                        }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18)).disabled(busy || saveAttempted || !foodItems.isEmpty)
                        if reviewed, mode == "photo", image != nil {
                            Button { shareMeal() } label: { Label(L("Compartilhar refeição"), systemImage: "square.and.arrow.up") }
                                .fitGlassButton().disabled(busy)
                        }
                    }
                    if let error {
                        NativeRecoveryCard(title: saveAttempted ? L("Vamos conferir o envio da sua refeição?") : analysisFailed ? L("Sua refeição continua aqui") : L("Vamos conferir estes detalhes?"), message: error)
                        if analysisFailed && !saveAttempted {
                            Button(L("Continuar manualmente, sem nova análise")) {
                                guard clearRecoveredAnalysis() else { return }
                                analysisTask?.cancel()
                                mode = "manual"; analysisFailed = false; self.error = nil
                            }.fitGlassButton().frame(minHeight: 44)
                        }
                    }
                    if saveAttempted { Text(L("O resultado do envio ainda pode estar pendente. Tentar novamente confere a mesma refeição e evita duplicar o registro.")).font(.caption).foregroundColor(.secondary) }
                }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(editingEntry != nil ? L("Editar refeição") : reviewed ? L("Revisar refeição") : L("Adicionar refeição"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { if hasDraft { showingDiscard = true } else { dismiss() } }.disabled(busy && saveAttempted) } }
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    if mode != nil, editingEntry == nil {
                        Menu(L("Método")) {
                            Button(L("Foto")) { mode = "photo"; reviewed = false }
                            Button(L("Descrição")) { mode = "description"; reviewed = false }
                            Button(L("Manual")) { mode = "manual" }
                        }.disabled(busy || saveAttempted || recoveryDraft != nil)
                    }
                }
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button(L("Concluir")) { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }
                }
            }
            .safeAreaInset(edge: .bottom) { actionBar }
            .interactiveDismissDisabled(hasDraft || busy)
            .confirmationDialog(saveAttempted ? L("Sair e conferir o diário?") : L("Sair sem salvar esta refeição?"), isPresented: $showingDiscard, titleVisibility: .visible) {
                Button(saveAttempted ? L("Sair e conferir meu diário") : L("Descartar e sair"), role: .destructive) {
                    analysisTask?.cancel()
                    guard clearRecoveredAnalysis() else { return }
                    dismiss()
                    if saveAttempted { Task { await diary.load(entryDate, api: session.api, refreshAfterCurrent: true) } }
                }
                Button(L("Continuar preenchendo"), role: .cancel) { }
            } message: {
                Text(saveAttempted ? L("O envio não foi confirmado. A refeição pode já estar no diário; confira antes de criar outro registro.") : L("Sua foto e o que você preencheu ainda não foram salvos. Você pode voltar e continuar de onde parou."))
            }
            .sheet(item: Binding(get: { picker.map(PickerMode.init) }, set: { picker = $0?.id })) { selection in
                if selection.id == "camera" {
                    ZStack(alignment: .top) {
                        NativeCameraPicker(image: $image).ignoresSafeArea()
                        HStack {
                            Button(L("Fechar")) { picker = nil }
                            Spacer()
                            Button { picker = "library" } label: { Label(L("Galeria"), systemImage: "photo") }
                        }
                        .padding(.horizontal, 18).padding(.top, 12)
                        .fitGlassButton(prominent: true)
                    }
                }
                else { NativePhotoPicker(image: $image) }
            }
            .sheet(isPresented: $showFoods, onDismiss: { if pendingFood != nil { confirmFoodReplacement = true } }) {
                NativeFoodSearch { food, grams in
                    let item = MealFoodPortion(name: food.descricao, grams: grams, calories: food.calorias, protein: food.proteina, carbs: food.carboidrato, fat: food.gordura)
                    if foodItems.isEmpty, hasDraft { pendingFood = item }
                    else { foodItems.append(item); updateFoodTotals() }
                }
            }
            .alert(L("Usar os alimentos da tabela?"), isPresented: $confirmFoodReplacement) {
                Button(L("Usar tabela")) { if let item = pendingFood { foodItems.append(item); updateFoodTotals() }; pendingFood = nil }
                Button(L("Manter preenchimento"), role: .cancel) { pendingFood = nil }
            } message: { Text(L("A descrição e os nutrientes atuais serão substituídos pelos itens que você adicionar.")) }
            .sheet(item: $editingFood) { item in
                NativeFoodQuantityEditor(portion: item) { updated in
                    if let index = foodItems.firstIndex(where: { $0.id == updated.id }) { foodItems[index] = updated; updateFoodTotals() }
                }
            }
            .sheet(isPresented: $showingCreditConfirmation, onDismiss: {
                confirmationVersion += 1
                if premiumAfterConfirmation { premiumAfterConfirmation = false; showingPremium = true }
            }) {
                creditConfirmation.task { await refreshConfirmationCredits() }
            }
            .sheet(isPresented: $showingPremium) { NativeSubscriptionView(surface: "photos") }
            .sheet(item: $sharingMeal) { NativeMealSharePreview(image: $0.image) }
            .task {
                guard !loaded else { return }; loaded = true
                if let entry = editingEntry {
                    mode = "manual"; reviewed = true; mealType = entry.mealType; description = entry.description
                    calories = decimal(entry.calories); protein = decimal(entry.protein); carbs = decimal(entry.carbs); fat = decimal(entry.fat)
                } else {
                    if let slot { mealType = slot.alternatives.first(where: { $0.id == slot.selectedPlanMealId })?.mealType ?? slot.label }
                    else { mealType = suggestedMealType }
                    restoreAnalysis(); await loadCredits()
                }
            }
            .onDisappear { analysisTask?.cancel() }
        }.navigationViewStyle(.stack)
    }

    private var actionBar: some View {
        Group {
            if mode != nil {
                if reviewed || mode == "manual" {
                    Button { save() } label: {
                        HStack { if busy { ProgressView() }; Text(saveAttempted ? L("Conferir envio") : editingEntry == nil ? L("Salvar refeição") : L("Salvar alterações")).frame(maxWidth: .infinity) }
                    }.buttonStyle(FitPrimaryButtonStyle()).disabled(busy || description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                } else {
                    Button { requestAnalysis() } label: {
                        HStack { if busy { ProgressView() }; Text(busy ? L("Verificando análise…") : recoveryDraft != nil ? L("Verificar resultado") : L("Analisar refeição")).frame(maxWidth: .infinity) }
                    }.buttonStyle(FitPrimaryButtonStyle()).disabled(busy || (description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && image == nil && recoveryDraft == nil))
                }
            }
        }.padding(.horizontal, 20).padding(.vertical, 12).background(Color.fitBackground)
    }

    private var foodList: some View {
        VStack(alignment: .leading, spacing: 12) {
            if !foodItems.isEmpty { Text(L("Itens desta refeição")).font(.headline) }
            ForEach(foodItems) { item in
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(item.name).font(.subheadline)
                        Button(L("\(item.grams.formatted()) g · Ajustar")) { editingFood = item }.font(.subheadline).frame(minHeight: 44)
                    }
                    Spacer()
                    Button { foodItems.removeAll { $0.id == item.id }; updateFoodTotals() } label: { Image(systemName: "minus.circle").frame(width: 44, height: 44) }
                        .accessibilityLabel(L("Remover \(item.name)"))
                }.padding(12).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
            }
        }.disabled(busy || saveAttempted)
    }

    private func updateFoodTotals() {
        description = foodItems.map { "\($0.name) · \($0.grams.formatted()) g" }.joined(separator: "; ")
        calories = foodItems.isEmpty ? "" : decimal(foodItems.reduce(0) { $0 + $1.calories })
        protein = foodItems.isEmpty ? "" : decimal(foodItems.reduce(0) { $0 + $1.protein })
        carbs = foodItems.isEmpty ? "" : decimal(foodItems.reduce(0) { $0 + $1.carbs })
        fat = foodItems.isEmpty ? "" : decimal(foodItems.reduce(0) { $0 + $1.fat })
        reviewed = true
    }

    private var readableDate: String {
        let parser = DateFormatter(); parser.dateFormat = "yyyy-MM-dd"; parser.locale = Locale(identifier: "en_US_POSIX")
        guard let value = parser.date(from: entryDate) else { return entryDate }
        let display = DateFormatter(); display.locale = NativeLocalization.locale; display.dateStyle = .long
        return display.string(from: value)
    }
    private var suggestedMealType: String {
        var calendar = Calendar.current
        calendar.timeZone = session.profile?.profile?.timezone.flatMap(TimeZone.init(identifier:)) ?? .current
        switch calendar.component(.hour, from: Date()) {
        case 5..<11: return "Café da manhã"
        case 11..<15: return "Almoço"
        case 15..<18: return "Café da tarde"
        case 18..<23: return "Jantar"
        default: return L("Lanche")
        }
    }

    private var creditNotice: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Image(systemName: usedFreeCredit ? "checkmark.circle.fill" : "sparkles")
                    .foregroundColor(creditMint).font(.title3)
                VStack(alignment: .leading, spacing: 4) {
                    Text(usedFreeCredit ? L("Pronto! Vamos conferir sua refeição?") : creditsExhausted ? L("Seu registro continua por aqui") : L("Uma ajuda da IA para sua refeição"))
                        .font(.subheadline.weight(.semibold))
                    if let quota = session.freeAccess?.photos {
                        let remaining = remainingAfterAnalysis ?? quota.remaining
                        Text(usedFreeCredit ? L("1 crédito usado · \(remaining) de \(quota.limit) disponíveis") : creditsExhausted ? L("Os créditos de IA acabaram. O registro manual segue grátis.") : L("\(remaining) de \(quota.limit) créditos grátis · você confirma antes de usar"))
                            .font(.caption).foregroundColor(.secondary).monospacedDigit()
                    } else {
                        Text(creditLoadFailed ? L("Consulte seu saldo ao analisar a refeição.") : L("Consultando seus créditos…")).font(.caption).foregroundColor(.secondary)
                    }
                }
            }
            if creditsExhausted, !reviewed {
                if !reviewed {
                    Button(L("Continuar sem IA, grátis")) {
                        guard clearRecoveredAnalysis() else { return }
                        mode = "manual"; error = nil
                    }
                        .fitGlassButton(prominent: true).tint(creditMint).foregroundColor(.black).frame(minHeight: 44).disabled(busy)
                }
                Button(L("Conhecer o Premium")) { showingPremium = true }.font(.subheadline).frame(minHeight: 44)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(16)
        .background(creditMint.opacity(0.07), in: RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(creditMint.opacity(0.16), lineWidth: 1))
        .accessibilityElement(children: .contain)
    }

    private var creditConfirmation: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack(spacing: 14) {
                    Image(systemName: "sparkles")
                        .font(.system(size: 26, weight: .medium)).foregroundColor(creditMint)
                        .frame(width: 58, height: 58)
                        .background(LinearGradient(colors: [creditMint.opacity(0.18), Color.fitBlue.opacity(0.08)], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 20))
                    Text(L("ESTIMATIVA COM IA")).font(.caption.weight(.semibold)).tracking(1).foregroundColor(creditMint)
                    Spacer()
                    Button { cancelCreditConfirmation() } label: {
                        Image(systemName: "xmark").font(.body.weight(.semibold)).frame(width: 44, height: 44)
                    }.foregroundColor(.secondary).accessibilityLabel(L("Cancelar análise e voltar à refeição"))
                }
                VStack(alignment: .leading, spacing: 12) {
                    Text(creditsExhausted ? L("Seu cuidado continua.") : L("Vamos estimar sua refeição?"))
                        .font(.system(.title, design: .rounded).weight(.bold)).fixedSize(horizontal: false, vertical: true)
                    Text(creditsExhausted ? L("Você já aproveitou seus créditos de IA. Continue registrando de graça, no seu ritmo.") : L("A IA estima calorias e nutrientes. Você confere tudo antes de salvar."))
                        .font(.body).foregroundColor(.secondary).fixedSize(horizontal: false, vertical: true)
                }
                if confirmationLoading {
                    HStack(spacing: 12) { ProgressView().tint(creditMint); Text(L("Conferindo seu saldo…")).font(.subheadline) }
                        .frame(maxWidth: .infinity, minHeight: 100)
                } else if let confirmationError {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(confirmationError).font(.subheadline).foregroundColor(.secondary)
                        Button(L("Consultar saldo novamente")) { Task { await refreshConfirmationCredits() } }.frame(minHeight: 44)
                    }
                } else if let quota = session.freeAccess?.photos {
                    VStack(alignment: .leading, spacing: 18) {
                        HStack {
                            Label(L("Seu saldo gratuito"), systemImage: "circle.grid.2x2.fill").font(.subheadline).foregroundColor(.secondary)
                            Spacer()
                            Text(L("\(quota.remaining) de \(quota.limit)")).font(.title3.weight(.bold)).monospacedDigit()
                        }
                        if !creditsExhausted {
                            Divider().overlay(creditMint.opacity(0.12))
                            HStack(alignment: .firstTextBaseline, spacing: 6) {
                                Text("1").font(.system(size: 48, weight: .bold, design: .rounded)).foregroundColor(creditMint)
                                Text(L("crédito nesta análise")).font(.headline)
                            }
                            Text(L("Depois, \(max(0, quota.remaining - 1)) \(quota.remaining == 2 ? L("crédito disponível") : L("créditos disponíveis"))."))
                                .font(.subheadline).foregroundColor(.secondary).monospacedDigit()
                            if quota.remaining == 1 {
                                Label(L("Este é seu último crédito gratuito."), systemImage: "sparkle").font(.subheadline).foregroundColor(creditMint)
                            }
                        }
                    }
                    .padding(20).frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 24))
                    .overlay(RoundedRectangle(cornerRadius: 24).stroke(creditMint.opacity(0.2), lineWidth: 1))
                    if let confirmationMessage { Text(confirmationMessage).font(.subheadline).foregroundColor(creditMint) }
                }
                VStack(spacing: 10) {
                    if creditsExhausted, !confirmationLoading, confirmationError == nil {
                        Button { cancelCreditConfirmation(); mode = "manual"; error = nil } label: {
                            Label(L("Continuar sem IA, grátis"), systemImage: "square.and.pencil").font(.headline).frame(maxWidth: .infinity, minHeight: 54)
                        }.fitGlassButton(prominent: true).tint(creditMint).foregroundColor(.black)
                        Button { premiumAfterConfirmation = true; showingCreditConfirmation = false } label: { Text(L("Conhecer o Premium")).frame(maxWidth: .infinity, minHeight: 44) }
                    } else {
                        Button { confirmAnalysis() } label: {
                            Label(L("Usar 1 crédito e analisar"), systemImage: "sparkles").font(.headline).frame(maxWidth: .infinity, minHeight: 54)
                        }.fitGlassButton(prominent: true).tint(creditMint).foregroundColor(.black)
                            .disabled(confirmationLoading || confirmationError != nil || session.freeAccess == nil)
                        Button { cancelCreditConfirmation() } label: { Text(L("Agora não")).frame(maxWidth: .infinity, minHeight: 44) }.foregroundColor(.secondary)
                    }
                    Text(L("Créditos gratuitos não se renovam. Nenhuma cobrança ao confirmar."))
                        .font(.caption).foregroundColor(.secondary).multilineTextAlignment(.center)
                }
            }.padding(24)
        }
        .background(Color.fitBackground.ignoresSafeArea()).preferredColorScheme(.dark)
    }

    private func requestAnalysis() {
        guard !busy, !recoveryLoadFailed else { return }
        if let recoveryDraft { analyze(freeRemaining: recoveryDraft.freeRemaining); return }
        if session.hasPremium { analyze(); return }
        confirmationVersion += 1
        confirmationLoading = true
        confirmationError = nil
        confirmationMessage = nil
        showingCreditConfirmation = true
    }

    private func cancelCreditConfirmation() {
        confirmationVersion += 1
        showingCreditConfirmation = false
    }

    private func refreshConfirmationCredits() async {
        let requestVersion = confirmationVersion
        let owner = session.user?.id
        confirmationLoading = true
        confirmationError = nil
        do {
            try await session.refreshFreeAccess()
            guard requestVersion == confirmationVersion, owner == session.user?.id, showingCreditConfirmation, !Task.isCancelled else { return }
            remainingAfterAnalysis = nil
            if session.freeAccess == nil { throw APIError.invalidResponse }
        } catch {
            guard requestVersion == confirmationVersion, owner == session.user?.id, showingCreditConfirmation else { return }
            if !isNativeRequestCancellation(error) { confirmationError = L("Seu saldo não carregou. Tente de novo; sua refeição continua aqui.") }
        }
        confirmationLoading = false
    }

    private func confirmAnalysis() {
        guard !confirmationLoading, confirmationError == nil else { return }
        let requestVersion = confirmationVersion
        let owner = session.user?.id
        let shownRemaining = session.freeAccess?.photos.remaining
        confirmationLoading = true
        Task {
            await refreshConfirmationCredits()
            guard requestVersion == confirmationVersion, showingCreditConfirmation, owner == session.user?.id, confirmationError == nil else { return }
            if session.hasPremium { showingCreditConfirmation = false; analyze(); return }
            guard let remaining = session.freeAccess?.photos.remaining, remaining > 0 else { return }
            guard remaining == shownRemaining else {
                confirmationMessage = L("Seu saldo foi atualizado. Confira antes de continuar.")
                return
            }
            showingCreditConfirmation = false
            analyze(freeRemaining: remaining)
        }
    }

    private func loadCredits() async {
        creditLoadFailed = false
        do { try await session.refreshFreeAccess(); remainingAfterAnalysis = nil }
        catch { if !isNativeRequestCancellation(error) { creditLoadFailed = true } }
    }

    private func choice(_ title: String, icon: String, mode: String) -> some View {
        Button {
            self.mode = mode
            if mode == "photo" { startCamera() }
            
        } label: {
            HStack(spacing: 14) {
                Image(systemName: icon).font(.title2).foregroundColor(.fitBlue)
                    .frame(width: 48, height: 48)
                    .background(Color.fitBlue.opacity(0.12), in: RoundedRectangle(cornerRadius: 14))
                VStack(alignment: .leading, spacing: 6) {
                    Text(title).font(.headline).foregroundColor(.primary)
                    Text(mode == "photo" ? L("Fotografe seu prato ou escolha na galeria") : mode == "description" ? L("Conte os alimentos e as quantidades") : L("Informe as calorias e, se quiser, os nutrientes"))
                        .font(.caption).foregroundColor(.secondary).multilineTextAlignment(.leading)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundColor(.secondary)
            }.frame(maxWidth: .infinity, alignment: .leading).padding(18)
                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain).disabled(recoveryLoadFailed)
    }
    private func startCamera() {
        if [.denied, .restricted].contains(AVCaptureDevice.authorizationStatus(for: .video)) { error = L("A câmera está bloqueada. Escolha uma foto da galeria ou permita o acesso nos Ajustes.") }
        else if UIImagePickerController.isSourceTypeAvailable(.camera) { picker = "camera" }
        else { error = L("A câmera não está disponível neste aparelho. Escolha uma foto da galeria.") }
    }
    private func numberField(_ title: String, text: Binding<String>) -> some View {
        HStack { Text(title); TextField(L("Não informado"), text: text).keyboardType(.decimalPad).multilineTextAlignment(.trailing).accessibilityLabel(title) }
    }
    private func decimal(_ number: Double?) -> String { number.map { String(format: "%.1f", $0).replacingOccurrences(of: ".", with: ",") } ?? "" }
    private func number(_ text: String, maximum: Double) throws -> Double? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }
        guard let value = Double(trimmed.replacingOccurrences(of: ",", with: ".")), value.isFinite, value >= 0, value <= maximum else {
            throw APIError.http(status: 400, message: L("Revise os valores: use números de 0 a \(Int(maximum))."))
        }
        return value
    }
    private func shareMeal() {
        do {
            guard let image, let kcal = try number(calories, maximum: 20000) else {
                error = L("Informe as calorias antes de compartilhar.")
                return
            }
            let macros = [try number(protein, maximum: 5000), try number(carbs, maximum: 5000), try number(fat, maximum: 5000)]
            sharingMeal = MealShareImage(image: renderMealShare(photo: image, mealType: mealType, calories: kcal, macros: macros))
            error = nil
        } catch { self.error = error.localizedDescription }
    }
    private func save() {
        error = nil
        let wasRetry = saveAttempted
        let owner = session.user?.id
        do {
            guard description.trimmingCharacters(in: .whitespacesAndNewlines).count <= 2000 else {
                throw APIError.http(status: 400, message: L("Use uma descrição de até 2.000 caracteres."))
            }
            let entry = NewDietEntry(date: entryDate, mealType: mealType, description: description.trimmingCharacters(in: .whitespacesAndNewlines),
                                     calories: try number(calories, maximum: 20000), protein: try number(protein, maximum: 5000),
                                     carbs: try number(carbs, maximum: 5000), fat: try number(fat, maximum: 5000), notes: editingEntry?.notes)
            busy = true
            saveAttempted = true
            Task {
                do {
                    if let editingEntry {
                        _ = try await session.api.updateDietEntry(id: editingEntry.id, entry: entry, idempotencyKey: idempotencyKey)
                    } else if let key = linkedSlotKey, let mealId = linkedMealId {
                        _ = try await session.api.recordDifferentMeal(date: entryDate, slotKey: key, mealId: mealId, entry: entry, idempotencyKey: idempotencyKey)
                    } else {
                        _ = try await session.api.addDietEntry(entry, idempotencyKey: idempotencyKey)
                    }
                    guard session.user?.id == owner else { return }
                    if editingEntry == nil { _ = clearRecoveredAnalysis() }
                    diary.successMessage = editingEntry == nil ? L("Refeição registrada. Você pode conferir e editar no diário.") : L("Refeição atualizada.")
                    NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
                    busy = false
                    dismiss()
                    Task { await diary.load(entryDate, api: session.api, refreshAfterCurrent: true) }
                } catch {
                    guard session.user?.id == owner else { return }
                    busy = false
                    self.error = RequestFailure.message(error, fallback: L("Ainda não confirmamos o envio. Sua refeição continua nesta tela. Tente novamente para conferir o mesmo registro."))
                    if !wasRetry, case APIError.http(let status, _) = error, [400, 401, 403, 409, 422, 429].contains(status) {
                        saveAttempted = false
                        idempotencyKey = UUID().uuidString
                    } else if !wasRetry, case APIError.csrfMismatch = error {
                        saveAttempted = false
                        idempotencyKey = UUID().uuidString
                    }
                }
            }
        } catch { self.error = error.localizedDescription }
    }
    private func restoreAnalysis() {
        guard recoveryDraft == nil, let owner = session.user?.id else { return }
        recoveryLoadFailed = false
        error = nil
        do {
            guard let draft = try analysisRecovery.load(owner: owner) else { return }
            recoveryDraft = draft
            restoredDate = draft.date; mealType = draft.mealType
            description = draft.description
            image = draft.photoData.flatMap(UIImage.init(data:))
            mode = draft.photoData == nil ? "description" : "photo"
            idempotencyKey = draft.requestKey + ".entry"
            if let estimate = draft.estimate {
                applyEstimate(estimate)
                usedFreeCredit = draft.freeRemaining != nil
            }
        } catch {
            recoveryLoadFailed = true
            self.error = L("Não conseguimos abrir a análise preservada. Tente reabrir esta tela antes de iniciar outra estimativa.")
        }
    }

    @discardableResult
    private func clearRecoveredAnalysis() -> Bool {
        guard editingEntry == nil else { return true }
        guard let owner = session.user?.id else { return false }
        do {
            try analysisRecovery.clear(owner: owner)
            recoveryDraft = nil
            recoveryLoadFailed = false
            return true
        } catch {
            self.error = L("Não conseguimos limpar a análise preservada. Tente novamente antes de iniciar outra refeição.")
            return false
        }
    }

    private func applyEstimate(_ estimate: NutritionEstimate) {
        foodItems = []
        description = estimate.description
        calories = decimal(estimate.calories); protein = decimal(estimate.protein)
        carbs = decimal(estimate.carbs); fat = decimal(estimate.fat)
        reviewed = true
    }

    private func analyze(freeRemaining: Int? = nil) {
        guard !busy, let owner = session.user?.id else { return }
        busy = true
        error = nil
        analysisFailed = false
        let savedDraft = recoveryDraft
        resumingAnalysis = savedDraft != nil
        let text = description
        let photo = image.map { NutritionPhotoSource(image: $0) }
        analysisTask = Task {
            defer { busy = false }
            let photoData: Data?
            if let savedDraft { photoData = savedDraft.photoData }
            else {
                photoData = await Task.detached(priority: .userInitiated) {
                    photo.flatMap { preparePhoto($0.image) }
                }.value
            }
            do {
                try Task.checkCancellation()
                guard session.user?.id == owner else { return }
                var draft = savedDraft ?? NutritionAnalysisDraft(date: entryDate, mealType: mealType, description: text,
                                                                  photoData: photoData, freeRemaining: freeRemaining, slotKey: slot?.slotKey, planMealId: slot?.selectedPlanMealId)
                // Persist the confirmed intent before any POST can spend a credit.
                try analysisRecovery.save(draft, owner: owner)
                recoveryDraft = draft
                idempotencyKey = draft.requestKey + ".entry"
                let response: NutritionAnalysisResponse
                if let queuedId = draft.jobId { response = .queued(jobId: queuedId) }
                else {
                    response = try await session.api.analyzeNutrition(description: draft.description,
                        image: draft.photoData.map { NutritionImage(data: $0, mimeType: "image/jpeg") }, idempotencyKey: draft.requestKey)
                }
                try Task.checkCancellation()
                guard session.user?.id == owner else { return }
                var estimate: NutritionEstimate?
                switch response {
                case .estimate(let result): estimate = result
                case .queued(let id):
                    draft.jobId = id
                    try analysisRecovery.save(draft, owner: owner)
                    recoveryDraft = draft
                            for _ in 0..<90 {
                        try Task.checkCancellation()
                        let job = try await session.api.getNutritionAnalysisTask(jobId: id)
                        guard session.user?.id == owner else { return }
                        if job.status == "succeeded" { estimate = job.result; break }
                        if job.status == "failed" {
                            _ = clearRecoveredAnalysis()
                            throw APIError.http(status: job.httpStatus ?? 500, message: job.error ?? L("Não foi possível analisar esta refeição."))
                        }
                        try await Task.sleep(nanoseconds: 2_000_000_000)
                    }
                }
                try Task.checkCancellation()
                guard session.user?.id == owner else { return }
                guard let estimate else { throw APIError.http(status: 408, message: L("A análise está demorando. Você pode preencher os valores manualmente.")) }
                draft.estimate = estimate
                try analysisRecovery.save(draft, owner: owner)
                recoveryDraft = draft
                applyEstimate(estimate)
                if let remaining = draft.freeRemaining {
                    usedFreeCredit = true
                    remainingAfterAnalysis = max(0, remaining - 1)
                }
                do { try await session.refreshFreeAccess(); remainingAfterAnalysis = nil } catch { }
            } catch is CancellationError { }
            catch {
                guard !Task.isCancelled, session.user?.id == owner else { return }
                let analysisError = error
                if case APIError.http(let status, _) = analysisError, [400, 413, 422].contains(status) {
                    _ = clearRecoveredAnalysis()
                    }
                do { try await session.refreshFreeAccess(); remainingAfterAnalysis = nil } catch { }
                if case APIError.http(let status, _) = analysisError, status == 403, creditsExhausted, recoveryDraft == nil { self.error = nil }
                else {
                    analysisFailed = true
                    self.error = recoveryDraft != nil
                        ? RequestFailure.message(analysisError, fallback: L("Ainda não conseguimos confirmar o resultado.")) + L(" Sua solicitação está preservada. Verificar resultado retoma a mesma análise, ou você pode continuar manualmente.")
                        : RequestFailure.message(analysisError, fallback: L("Não conseguimos concluir a estimativa agora. Sua foto e descrição estão preservadas; você pode tentar novamente ou registrar manualmente."))
                }
            }
        }
    }
}

private struct PickerMode: Identifiable { let id: String }

private struct MealShareImage: Identifiable {
    let id = UUID()
    let image: UIImage
}

private struct NativeMealSharePreview: View {
    let image: UIImage
    @Environment(\.dismiss) private var dismiss
    @State private var showingActivity = false

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 18) {
                    Image(uiImage: image).resizable().scaledToFit()
                        .clipShape(RoundedRectangle(cornerRadius: 20)).padding(.horizontal, 28)
                    Text(L("Estimativa nutricional por IA. A foto permanece no aparelho até você compartilhar."))
                        .font(.caption).foregroundColor(.secondary)
                    Button { showingActivity = true } label: {
                        Label(L("Compartilhar"), systemImage: "square.and.arrow.up")
                            .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 14)
                    }.fitGlassButton(prominent: true)
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(L("Compartilhar refeição")).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { dismiss() } } }
            .sheet(isPresented: $showingActivity) { MealActivitySheet(image: image) }
        }.navigationViewStyle(.stack).preferredColorScheme(.dark)
    }
}

private struct MealActivitySheet: UIViewControllerRepresentable {
    let image: UIImage
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: [image], applicationActivities: nil)
    }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) { }
}

private func renderMealShare(photo: UIImage, mealType: String, calories: Double, macros: [Double?]) -> UIImage {
    NativeShareArtwork.render(photo: photo) { context in
        let title = mealType == "Outros" ? L("Refeição") : mealType
        NativeShareArtwork.text(NativeLocalization.display(title).uppercased(with: NativeLocalization.locale), x: 88, baseline: 1340, size: 42, weight: .bold, color: NativeShareArtwork.blue)
        let value = calories.formatted(.number.locale(NativeLocalization.locale).precision(.fractionLength(0...1)))
        let calorieWidth = NativeShareArtwork.text(value, x: 80, baseline: 1496, size: 156, weight: .heavy, maxWidth: 590)
        NativeShareArtwork.text(L("kcal estimadas"), x: 96 + calorieWidth, baseline: 1487, size: 36, weight: .medium, color: .lightGray, maxWidth: 904 - calorieWidth)
        let labels = [L("PROTEÍNAS"), L("CARBOIDRATOS"), L("GORDURAS")]
        let shown = macros.prefix(3).enumerated().compactMap { index, value in value.map { (index, $0) } }
        let width = 930 / CGFloat(max(1, shown.count))
        for (position, macro) in shown.enumerated() {
            let value = macro.1.formatted(.number.locale(NativeLocalization.locale).precision(.fractionLength(0...1)))
            NativeShareArtwork.metric("\(value) g", label: labels[macro.0], x: 88 + CGFloat(position) * width,
                                      width: width - 24, blue: macro.0 == 1, context: context)
        }
    }
}

/// Shared 1080 × 1920 artwork for the meal and workout previews and exported images.
enum NativeShareArtwork {
    static let blue = UIColor(red: 0.44, green: 0.69, blue: 1, alpha: 1)
    static let mint = UIColor(red: 0.40, green: 0.87, blue: 0.74, alpha: 1)

    static func render(photo: UIImage?, content: (CGContext) -> Void) -> UIImage {
        let size = CGSize(width: 1080, height: 1920)
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).image { renderer in
            let context = renderer.cgContext
            UIColor(red: 0.05, green: 0.11, blue: 0.18, alpha: 1).setFill()
            context.fill(CGRect(origin: .zero, size: size))
            if let photo {
                let scale = max(size.width / photo.size.width, size.height / photo.size.height)
                let rect = CGRect(x: (size.width - photo.size.width * scale) / 2, y: (size.height - photo.size.height * scale) / 2,
                                  width: photo.size.width * scale, height: photo.size.height * scale)
                photo.draw(in: rect)
            }
            let colors = [0.0, 0.38, 0.86, 0.97].map { UIColor(red: 4 / 255, green: 12 / 255, blue: 22 / 255, alpha: $0).cgColor }
            if let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors as CFArray, locations: [0, 0.35, 0.65, 1]) {
                context.drawLinearGradient(gradient, start: CGPoint(x: 0, y: 850), end: CGPoint(x: 0, y: 1920), options: [.drawsAfterEndLocation])
            }
            content(context)
            logo(context: context)
        }
    }

    @discardableResult
    static func text(_ value: String, x: CGFloat, baseline: CGFloat, size: CGFloat, weight: UIFont.Weight = .semibold,
                     color: UIColor = .white, maxWidth: CGFloat = 904) -> CGFloat {
        let originalFont = UIFont.systemFont(ofSize: size, weight: weight)
        let originalWidth = (value as NSString).size(withAttributes: [.font: originalFont]).width
        let font = UIFont.systemFont(ofSize: size * min(1, maxWidth / max(1, originalWidth)), weight: weight)
        let attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: color]
        (value as NSString).draw(at: CGPoint(x: x, y: baseline - font.ascender), withAttributes: attributes)
        return (value as NSString).size(withAttributes: attributes).width
    }

    static func metric(_ value: String, label: String, x: CGFloat, width: CGFloat = 286, blue: Bool, context: CGContext) {
        (blue ? self.blue : mint).setFill()
        context.fill(CGRect(x: x, y: 1550, width: 45, height: 4))
        text(value, x: x, baseline: 1630, size: 56, weight: .bold, maxWidth: width)
        text(label, x: x, baseline: 1672, size: 28, color: .lightGray, maxWidth: width)
    }

    private static func logo(context: CGContext) {
        guard let logo = UIImage(named: "FitTrackerFullLogo") else { return }
        let rect = CGRect(x: 80, y: 1724, width: 480, height: 480 * logo.size.height / logo.size.width)
        logo.draw(in: rect)
        context.saveGState()
        context.clip(to: CGRect(x: rect.minX + rect.width * 0.25, y: rect.minY, width: rect.width * 0.565, height: rect.height))
        let outline = logo.withTintColor(.black, renderingMode: .alwaysOriginal)
        for step in 0..<16 {
            let angle = CGFloat(step) * .pi / 8
            outline.draw(in: rect.offsetBy(dx: cos(angle) * 2, dy: sin(angle) * 2))
        }
        logo.withTintColor(.white, renderingMode: .alwaysOriginal).draw(in: rect)
        context.restoreGState()
    }
}

// UIImage is captured as an immutable snapshot and used only by this preparation task.
private struct NutritionPhotoSource: @unchecked Sendable { let image: UIImage }

private func preparePhoto(_ image: UIImage) -> Data? {
    let scale = min(1, 1600 / max(image.size.width, image.size.height))
    let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
    let format = UIGraphicsImageRendererFormat(); format.scale = 1
    return UIGraphicsImageRenderer(size: size, format: format).image { _ in image.draw(in: CGRect(origin: .zero, size: size)) }.jpegData(compressionQuality: 0.8)
}

private struct NativeCameraPicker: UIViewControllerRepresentable {
    @Binding var image: UIImage?
    @Environment(\.dismiss) private var dismiss
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController(); picker.sourceType = .camera; picker.delegate = context.coordinator; return picker
    }
    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) { }
    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let owner: NativeCameraPicker
        init(_ owner: NativeCameraPicker) { self.owner = owner }
        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            owner.image = info[.originalImage] as? UIImage; owner.dismiss()
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { owner.dismiss() }
    }
}

private struct NativePhotoPicker: UIViewControllerRepresentable {
    @Binding var image: UIImage?
    @Environment(\.dismiss) private var dismiss
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIViewController(context: Context) -> PHPickerViewController {
        var config = PHPickerConfiguration(); config.filter = .images; config.selectionLimit = 1
        let picker = PHPickerViewController(configuration: config); picker.delegate = context.coordinator; return picker
    }
    func updateUIViewController(_ uiViewController: PHPickerViewController, context: Context) { }
    final class Coordinator: NSObject, PHPickerViewControllerDelegate {
        let owner: NativePhotoPicker
        init(_ owner: NativePhotoPicker) { self.owner = owner }
        func picker(_ picker: PHPickerViewController, didFinishPicking results: [PHPickerResult]) {
            owner.dismiss()
            guard let provider = results.first?.itemProvider, provider.canLoadObject(ofClass: UIImage.self) else { return }
            provider.loadObject(ofClass: UIImage.self) { image, _ in
                DispatchQueue.main.async { self.owner.image = image as? UIImage }
            }
        }
    }
}

private struct NativeFood: Decodable, Identifiable {
    var id: String { descricao }
    let descricao: String
    let calorias: Double
    let proteina: Double
    let gordura: Double
    let carboidrato: Double
}

private struct NativeFoodQuantityEditor: View {
    let portion: MealFoodPortion
    let onSave: (MealFoodPortion) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var grams = ""
    private var quantity: Double? {
        guard let value = Double(grams.replacingOccurrences(of: ",", with: ".")), value.isFinite, value > 0, value <= 10000 else { return nil }
        return value
    }
    var body: some View {
        NavigationView {
            Form {
                Section(portion.name) {
                    HStack { Text(L("Quantidade (g)")); TextField(L("Ex.: 100"), text: $grams).keyboardType(.decimalPad).multilineTextAlignment(.trailing).accessibilityLabel(L("Quantidade em gramas")) }
                    if quantity == nil { Text(L("Informe uma quantidade maior que zero, até 10.000 g.")).foregroundColor(.red).font(.footnote) }
                }
            }.navigationTitle(L("Ajustar quantidade")).navigationBarTitleDisplayMode(.inline)
                .onAppear { grams = String(portion.grams) }
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button(L("Cancelar")) { dismiss() } }
                    ToolbarItem(placement: .confirmationAction) {
                        Button(L("Salvar")) { if let quantity { var updated = portion; updated.grams = quantity; onSave(updated); dismiss() } }.disabled(quantity == nil)
                    }
                }
        }.navigationViewStyle(.stack)
    }
}

private struct NativeFoodSearch: View {
    let apply: (NativeFood, Double) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var grams = "100"
    @State private var selected: NativeFood?
    @State private var foods: [NativeFood] = []
    @State private var error: String?
    private var quantity: Double? {
        guard let value = Double(grams.replacingOccurrences(of: ",", with: ".")), value.isFinite, value > 0, value <= 10000 else { return nil }
        return value
    }
    var body: some View {
        NavigationView {
            List {
                if let selected {
                    Section(L("Quantidade")) {
                        Text(selected.descricao)
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            TextField("100", text: $grams).keyboardType(.decimalPad).font(.system(size: 34, weight: .semibold, design: .rounded)).frame(width: 110).accessibilityLabel(L("Quantidade em gramas"))
                            Text(L("gramas")).foregroundColor(.secondary)
                        }
                        HStack {
                            ForEach([50, 100, 150, 200], id: \.self) { amount in
                                Button("\(amount) g") { grams = String(amount) }.fitGlassButton()
                            }
                        }
                        Text(L("Valores da tabela por 100 g, ajustados à quantidade informada.")).font(.caption).foregroundColor(.secondary)
                        Button(L("Adicionar à refeição")) { if let quantity { apply(selected, quantity); dismiss() } }.disabled(quantity == nil)
                        Button(L("Escolher outro alimento")) { self.selected = nil }
                    }
                } else {
                    if let error {
                        NativeRecoveryCard(title: L("Podemos registrar de outro jeito"), message: error, actionTitle: L("Voltar ao registro manual")) { dismiss() }
                    } else if !query.isEmpty && !foods.contains(where: { $0.descricao.localizedStandardContains(query) }) {
                        NativeRecoveryCard(title: L("Vamos tentar outro nome?"), message: L("Não encontramos esse alimento na tabela. Use um nome mais simples ou preencha os nutrientes manualmente."), systemImage: "magnifyingglass", actionTitle: L("Limpar busca")) { query = "" }
                    }
                    ForEach(foods.filter { query.isEmpty || $0.descricao.localizedStandardContains(query) }.prefix(50)) { food in
                        Button(food.descricao) { selected = food }
                    }
                }
            }
            .searchable(text: $query, prompt: L("Buscar alimento"))
            .navigationTitle(L("Alimentos"))
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { dismiss() } } }
            .task {
                do {
                    guard let url = Bundle.main.url(forResource: "alimentos", withExtension: "json") else { throw APIError.invalidResponse }
                    foods = try JSONDecoder().decode([NativeFood].self, from: Data(contentsOf: url))
                    if foods.isEmpty { error = L("A tabela está vazia. Seu registro manual continua disponível.") }
                } catch { self.error = L("Não foi possível abrir a tabela de alimentos. Você pode inserir a refeição manualmente.") }
            }
        }.navigationViewStyle(.stack)
    }
}
