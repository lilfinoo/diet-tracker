import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
#if !os(Android)
import UIKit
#endif
import FitTrackerCore

struct NativeMealComposer: View {
    let date: String
    @Environment(NativeSession.self) var session
    @Environment(NativeDietStore.self) var diary
    @Environment(\.dismiss) var dismiss
    @State var mode: String?
    @State var mealType = "Almoço"
    @State var description = ""
    @State var calories = ""
    @State var protein = ""
    @State var carbs = ""
    @State var fat = ""
    @State var error: String?
    @State var busy = false
    @State var saveAttempted = false
    @State var idempotencyKey = UUID().uuidString
    @State var image: NativePhoto?
    @State var picker: String?
    @State var showFoods = false
    @State var analysisTask: Task<Void, Never>?
    @State var reviewed = false
    @State var showingPremium = false
    @State var sharingMeal: MealShareImage?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                if mode == nil {
                    Text("Como quer registrar?").font(.title2.bold())
                    Text("Escolha o caminho mais rápido para esta refeição.").foregroundColor(.secondary)
                    choice("Foto da refeição", icon: "camera", mode: "photo")
                    choice("Descrever o que comeu", icon: "pencil", mode: "description")
                    choice("Registrar manualmente", icon: "square.and.pencil", mode: "manual")
                } else {
                    Text("Refeição · \(date)").font(.caption.weight(.semibold)).foregroundColor(.fitBlue)
                    Picker("Tipo", selection: $mealType) { ForEach(["Café da manhã", "Almoço", "Café da tarde", "Lanche", "Jantar", "Outros"], id: \.self) { Text($0) } }
                        .pickerStyle(.menu).disabled(busy || saveAttempted)
                    if mode == "photo", !reviewed {
                        if let image { NativePhotoPreview(photo: image).scaledToFit().frame(maxHeight: 260).clipShape(RoundedRectangle(cornerRadius: 18)) }
                        HStack {
                            Button { startCamera() } label: { Label(image == nil ? "Tirar foto" : "Tirar outra", systemImage: "camera") }.buttonStyle(.borderedProminent)
                            Button { picker = "library" } label: { Label("Galeria", systemImage: "photo") }.buttonStyle(.bordered)
                        }.disabled(busy || saveAttempted)
                    }
                    if mode == "manual" {
                        Button { showFoods = true } label: { Label("Buscar alimento na tabela", systemImage: "magnifyingglass") }.buttonStyle(.borderedProminent).disabled(busy || saveAttempted)
                    }
                    if mode != "manual", !reviewed {
                        if mode == "photo" {
                            Text("Descrição da refeição (opcional)").font(.subheadline.weight(.semibold))
                            Text("Conte o que aparece no prato e as quantidades aproximadas.").font(.caption).foregroundColor(.secondary)
                        }
                        TextEditor(text: $description).frame(minHeight: 110).padding(8).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16)).accessibilityLabel("Descrição da refeição").disabled(busy || saveAttempted)
                            .overlay(alignment: .topLeading) {
                                if mode == "photo", description.isEmpty {
                                    Text("Ex.: arroz, feijão e frango grelhado; uma concha de arroz e um filé.")
                                        .font(.body).foregroundColor(.secondary.opacity(0.8)).padding(16).allowsHitTesting(false)
                                }
                            }
                        Button { analyze() } label: { HStack { if busy && !saveAttempted { ProgressView() }; Text("Estimar nutrientes") } }.buttonStyle(.borderedProminent).disabled(busy || saveAttempted || (description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && image == nil))
                        Text("A estimativa aparece para revisão. Nada é salvo automaticamente.").font(.caption).foregroundColor(.secondary)
                    }
                    if mode == "manual", !reviewed {
                        TextEditor(text: $description).frame(minHeight: 90).padding(8).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16)).accessibilityLabel("Descrição da refeição").disabled(busy || saveAttempted)
                    }
                    if reviewed, let image {
                        NativePhotoPreview(photo: image).scaledToFit().frame(maxHeight: 170).clipShape(RoundedRectangle(cornerRadius: 18))
                    }
                    if reviewed || mode == "manual" {
                        Text("Revise os valores antes de salvar").font(.headline)
                        Text("Proteínas, carboidratos e gorduras são opcionais. Campos vazios ficam como não informados.").font(.caption).foregroundColor(.secondary)
                        if reviewed { Text(description).font(.body).accessibilityLabel("Descrição da refeição") }
                        VStack(spacing: 0) {
                            numberField("Calorias (kcal)", text: $calories)
                            Divider(); numberField("Proteínas (g)", text: $protein)
                            Divider(); numberField("Carboidratos (g)", text: $carbs)
                            Divider(); numberField("Gorduras (g)", text: $fat)
                        }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18)).disabled(busy || saveAttempted)
                        if reviewed, mode == "photo", image != nil {
                            Button { shareMeal() } label: { Label("Compartilhar refeição", systemImage: "square.and.arrow.up") }
                                .buttonStyle(.bordered).disabled(busy)
                        }
                        Button { save() } label: { HStack { if busy && saveAttempted { ProgressView() }; Text(saveAttempted ? "Tentar novamente" : "Salvar refeição").fontWeight(.semibold) } }.buttonStyle(.borderedProminent).disabled(busy || description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                    if let error { Text(error).foregroundColor(.red) }
                    if saveAttempted { Text("O envio usa a mesma chave para evitar duplicidade em uma nova tentativa.").font(.caption).foregroundColor(.secondary) }
                }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(mode == nil ? "Nova refeição" : "Revisar refeição")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() }.disabled(busy && saveAttempted) } }
            .interactiveDismissDisabled(busy && saveAttempted)
            .sheet(item: Binding(get: { picker.map(PickerMode.init) }, set: { picker = $0?.id })) { selection in
                NativePhotoPicker(photo: $image, camera: selection.id == "camera")
            }
            .sheet(isPresented: $showFoods) {
                NativeFoodSearch { food, grams in
                    description = "\(food.descricao) · \(grams.formatted()) g"
                    calories = decimal(food.calorias * grams / 100)
                    protein = decimal(food.proteina * grams / 100)
                    carbs = decimal(food.carboidrato * grams / 100)
                    fat = decimal(food.gordura * grams / 100)
                    reviewed = true
                }
            }
            .sheet(isPresented: $showingPremium) { NativeSubscriptionView() }
            .sheet(item: $sharingMeal) { NativeMealSharePreview(image: $0.image) }
            .onDisappear { analysisTask?.cancel() }
        }
    }

    func choice(_ title: String, icon: String, mode: String) -> some View {
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
                    Text(mode == "photo" ? "Fotografe seu prato ou escolha na galeria" : mode == "description" ? "Conte os alimentos e as quantidades" : "Informe as calorias e, se quiser, os nutrientes")
                        .font(.caption).foregroundColor(.secondary).multilineTextAlignment(.leading)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").font(.caption.weight(.semibold)).foregroundColor(.secondary)
            }.frame(maxWidth: .infinity, alignment: .leading).padding(18)
                .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain)
    }
    func startCamera() {
        picker = "camera"
    }
    func numberField(_ title: String, text: Binding<String>) -> some View {
        HStack { Text(title); TextField("Não informado", text: text).keyboardType(.decimalPad).multilineTextAlignment(.trailing).accessibilityLabel(title) }
    }
    func decimal(_ number: Double?) -> String { number.map { String(format: "%.1f", $0).replacingOccurrences(of: ".", with: ",") } ?? "" }
    func number(_ text: String, maximum: Double) throws -> Double? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }
        guard let value = Double(trimmed.replacingOccurrences(of: ",", with: ".")), value.isFinite, value >= 0, value <= maximum else {
            throw APIError.http(status: 400, message: "Revise os valores: use números de 0 a \(Int(maximum)).")
        }
        return value
    }
    func shareMeal() {
        do {
            guard let image, let kcal = try number(calories, maximum: 20000) else {
                error = "Informe as calorias antes de compartilhar."
                return
            }
            let macros = [try number(protein, maximum: 5000), try number(carbs, maximum: 5000), try number(fat, maximum: 5000)]
            sharingMeal = MealShareImage(image: try renderMealShare(photo: image, mealType: mealType, calories: kcal, macros: macros))
            error = nil
        } catch { self.error = error.localizedDescription }
    }
    func save() {
        error = nil
        let wasRetry = saveAttempted
        do {
            guard description.trimmingCharacters(in: .whitespacesAndNewlines).count <= 2000 else {
                throw APIError.http(status: 400, message: "Use uma descrição de até 2.000 caracteres.")
            }
            let entry = NewDietEntry(date: date, mealType: mealType, description: description.trimmingCharacters(in: .whitespacesAndNewlines),
                                     calories: try number(calories, maximum: 20000), protein: try number(protein, maximum: 5000),
                                     carbs: try number(carbs, maximum: 5000), fat: try number(fat, maximum: 5000))
            busy = true
            saveAttempted = true
            Task {
                do {
                    _ = try await session.api.addDietEntry(entry, idempotencyKey: idempotencyKey)
                    NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
                    busy = false
                    dismiss()
                    Task { await diary.load(date, api: session.api, refreshAfterCurrent: true) }
                } catch {
                    self.error = error.localizedDescription
                    busy = false
                    if !wasRetry {
                        if case APIError.http(let status, _) = error, [400, 401, 403, 422, 429].contains(status) {
                            saveAttempted = false
                            idempotencyKey = UUID().uuidString
                        } else if case APIError.csrfMismatch = error {
                            saveAttempted = false
                            idempotencyKey = UUID().uuidString
                        }
                    }
                }
            }
        } catch { self.error = error.localizedDescription }
    }
    func analyze() {
        busy = true
        error = nil
        let text = description
        let photo = image
        analysisTask = Task {
            defer { busy = false }
            let upload = photo.map { NutritionImage(data: $0.data, mimeType: "image/jpeg") }
            do {
                try Task.checkCancellation()
                if session.freeAccess == nil { try await session.refreshFreeAccess() }
                if let access = session.freeAccess, !access.premium, access.photos.remaining == 0 {
                    showingPremium = true
                    return
                }
                let response = try await session.api.analyzeNutrition(description: text, image: upload)
                var estimate: NutritionEstimate?
                switch response {
                case .estimate(let result): estimate = result
                case .queued(let id):
                    for _ in 0..<90 {
                        try Task.checkCancellation()
                        let job = try await session.api.getNutritionAnalysisTask(jobId: id)
                        if job.status == "succeeded" { estimate = job.result; break }
                        if job.status == "failed" { throw APIError.http(status: job.httpStatus ?? 500, message: job.error ?? "Não foi possível analisar esta refeição.") }
                        try await Task.sleep(nanoseconds: 2_000_000_000)
                    }
                }
                try Task.checkCancellation()
                guard let estimate else { throw APIError.http(status: 408, message: "A análise está demorando. Você pode preencher os valores manualmente.") }
                description = estimate.description
                calories = decimal(estimate.calories); protein = decimal(estimate.protein)
                carbs = decimal(estimate.carbs); fat = decimal(estimate.fat)
                reviewed = true
                Task {
                    try? await session.refreshFreeAccess()
                    if let access = session.freeAccess, !access.premium, access.photos.remaining == 0 { showingPremium = true }
                }
            } catch is CancellationError { }
            catch {
                let analysisError = error
                Task { try? await session.refreshFreeAccess() }
                if case APIError.http(let status, _) = analysisError, status == 403,
                   let access = session.freeAccess, !access.premium, access.photos.remaining == 0 { showingPremium = true }
                else { self.error = error.localizedDescription }
            }
        }
    }
}

struct PickerMode: Identifiable { let id: String }

struct MealShareImage: Identifiable {
    let id = UUID()
    let image: NativePhoto
}

struct NativeMealSharePreview: View {
    let image: NativePhoto
    @Environment(\.dismiss) var dismiss
    @State var showingActivity = false
    @State var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    NativePhotoPreview(photo: image).scaledToFit()
                        .clipShape(RoundedRectangle(cornerRadius: 20)).padding(.horizontal, 28)
                    Text("Estimativa nutricional por IA. Compartilhe somente depois de revisar os valores.")
                        .font(.caption).foregroundColor(.secondary)
                    if let error { Text(error).foregroundColor(.red) }
                    Button {
                        #if os(Android)
                        do { try shareNativePhoto(image) } catch { self.error = "Não foi possível compartilhar a imagem. Tente novamente." }
                        #else
                        showingActivity = true
                        #endif
                    } label: {
                        Label("Compartilhar", systemImage: "square.and.arrow.up")
                            .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 14)
                    }.buttonStyle(.borderedProminent)
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle("Compartilhar refeição").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() } } }
            #if !os(Android)
            .sheet(isPresented: $showingActivity) { NativePhotoActivitySheet(photo: image) }
            #endif
        }.preferredColorScheme(.dark)
    }
}

func renderMealShare(photo: NativePhoto, mealType: String, calories: Double, macros: [Double?]) throws -> NativePhoto {
    #if os(Android)
    let logo = try nativePhotoLogo()
    let displayed = macros.map { value in value.map { $0.formatted(.number.locale(Locale(identifier: "pt_BR")).precision(.fractionLength(0...1))) + " g" } ?? "" }
    let path = try androidRenderMealShare(photo: photo.url.path, title: mealType == "Outros" ? "Refeição" : mealType,
                                         calories: calories.formatted(.number.locale(Locale(identifier: "pt_BR")).precision(.fractionLength(0...1))),
                                         protein: displayed[0], carbs: displayed[1], fat: displayed[2], logo: logo.path)
    return try NativePhoto(url: URL(fileURLWithPath: path))
    #else
    guard let photo = UIImage(data: photo.data) else { throw APIError.invalidResponse }
    let size = CGSize(width: 1080, height: 1920)
    let format = UIGraphicsImageRendererFormat(); format.scale = 1
    let rendered = UIGraphicsImageRenderer(size: size, format: format).image { renderer in
        let context = renderer.cgContext
        let scale = max(size.width / photo.size.width, size.height / photo.size.height)
        let photoSize = CGSize(width: photo.size.width * scale, height: photo.size.height * scale)
        photo.draw(in: CGRect(x: (size.width - photoSize.width) / 2, y: (size.height - photoSize.height) / 2,
                              width: photoSize.width, height: photoSize.height))
        let cyan = UIColor(red: 0, green: 0.85, blue: 0.93, alpha: 1)
        let panel = UIBezierPath(roundedRect: CGRect(x: 48, y: 1320, width: 984, height: 552), cornerRadius: 42)
        UIColor(red: 0.015, green: 0.035, blue: 0.065, alpha: 0.78).setFill(); panel.fill()
        cyan.withAlphaComponent(0.8).setStroke(); panel.lineWidth = 3; panel.stroke()
        func text(_ value: String, x: CGFloat, y: CGFloat, size: CGFloat, color: UIColor, weight: UIFont.Weight = .semibold) {
            (value as NSString).draw(in: CGRect(x: x, y: y, width: 980 - x, height: size * 1.4),
                                    withAttributes: [.font: UIFont.systemFont(ofSize: size, weight: weight), .foregroundColor: color])
        }
        context.setShadow(offset: .zero, blur: 28, color: cyan.cgColor)
        cyan.setFill(); context.fill(CGRect(x: 90, y: 1452, width: 6, height: 138))
        context.setShadow(offset: .zero, blur: 0, color: nil)
        text(calories.formatted(.number.locale(Locale(identifier: "pt_BR")).precision(.fractionLength(0...1))), x: 120, y: 1428, size: 128, color: .white, weight: .heavy)
        text("kcal estimadas", x: 120, y: 1590, size: 28, color: .lightGray)
        let labels = ["PROTEÍNAS", "CARBOIDRATOS", "GORDURAS"]
        let shown = macros.enumerated().compactMap { index, value in value.map { (index, $0) } }
        let width = 888 / CGFloat(max(1, shown.count))
        for (position, macro) in shown.enumerated() {
            let x = 96 + CGFloat(position) * width
            let color = macro.0 == 1 ? UIColor.systemBlue : UIColor(red: 0, green: 0.85, blue: 0.75, alpha: 1)
            color.setFill(); context.fill(CGRect(x: x, y: 1670, width: 44, height: 5))
            text(labels[macro.0], x: x, y: 1700, size: 22, color: .lightGray)
            text("\(macro.1.formatted(.number.locale(Locale(identifier: "pt_BR")).precision(.fractionLength(0...1)))) g", x: x, y: 1740, size: 58, color: .white, weight: .bold)
        }
        let title = mealType == "Outros" ? "Refeição" : mealType
        text(title, x: 90, y: 1360, size: title.count > 24 ? 42 : 54, color: .white, weight: .bold)
        if let logo = UIImage(named: "FitTrackerLogo", in: .module, compatibleWith: nil) {
            let width = 60 * logo.size.width / logo.size.height
            logo.draw(in: CGRect(x: 980 - width, y: 1354, width: width, height: 60))
        }
    }
    guard let data = rendered.jpegData(compressionQuality: 0.9) else { throw APIError.invalidResponse }
    return try NativePhoto(data: data)
    #endif
}

#if SKIP
func androidRenderMealShare(photo: String, title: String, calories: String, protein: String, carbs: String, fat: String, logo: String) throws -> String {
    NativePhotoPlatform.renderMeal(ProcessInfo.processInfo.androidContext, photo, title, calories, protein, carbs, fat, logo)
}
#endif

struct NativeFood: Decodable, Identifiable {
    var id: String { descricao }
    let descricao: String
    let calorias: Double
    let proteina: Double
    let gordura: Double
    let carboidrato: Double
}

struct NativeFoodSearch: View {
    let apply: (NativeFood, Double) -> Void
    @Environment(\.dismiss) var dismiss
    @State var query = ""
    @State var grams = "100"
    @State var selected: NativeFood?
    @State var foods: [NativeFood] = []
    @State var error: String?
    var quantity: Double? {
        guard let value = Double(grams.replacingOccurrences(of: ",", with: ".")), value.isFinite, value > 0, value <= 10000 else { return nil }
        return value
    }
    var body: some View {
        NavigationStack {
            List {
                if let selected {
                    Section("Quantidade") {
                        Text(selected.descricao)
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            TextField("100", text: $grams).keyboardType(.decimalPad).font(.system(size: 34, weight: .semibold, design: .rounded)).frame(width: 110).accessibilityLabel("Quantidade em gramas")
                            Text("gramas").foregroundColor(.secondary)
                        }
                        HStack {
                            ForEach([50, 100, 150, 200], id: \.self) { amount in
                                Button("\(amount) g") { grams = String(amount) }.buttonStyle(.bordered)
                            }
                        }
                        Text("Valores da tabela por 100 g, ajustados à quantidade informada.").font(.caption).foregroundColor(.secondary)
                        Button("Usar na refeição") { if let quantity { apply(selected, quantity); dismiss() } }.disabled(quantity == nil)
                        Button("Escolher outro alimento") { self.selected = nil }
                    }
                } else {
                    if let error { Text(error).foregroundColor(.red) }
                    ForEach(foods.filter { query.isEmpty || $0.descricao.localizedStandardContains(query) }.prefix(50)) { food in
                        Button(food.descricao) { selected = food }
                    }
                }
            }
            .searchable(text: $query, prompt: "Buscar alimento")
            .navigationTitle("Alimentos")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() } } }
            .task {
                do {
                    guard let url = Bundle.module.url(forResource: "alimentos", withExtension: "json") else { throw APIError.invalidResponse }
                    foods = try JSONDecoder().decode([NativeFood].self, from: Data(contentsOf: url))
                } catch { self.error = "Não foi possível abrir a tabela de alimentos. Você pode inserir a refeição manualmente." }
            }
        }
    }
}
