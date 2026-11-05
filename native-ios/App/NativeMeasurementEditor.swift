import SwiftUI
import FitTrackerCore

struct NativeMeasurementEditor: View {
    var existing: MeasurementEntry? = nil
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    @State private var date = Date()
    @State private var weight = ""
    @State private var height = ""
    @State private var bodyFat = ""
    @State private var muscleMass = ""
    @State private var waist = ""
    @State private var chest = ""
    @State private var arm = ""
    @State private var thigh = ""
    @State private var pending: NewMeasurementEntry?
    @State private var idempotencyKey = UUID().uuidString
    @State private var busy = false
    @State private var error: String?
    @State private var showingDiscard = false
    @State private var otherMeasurements = false
    @State private var loaded = false

    private var hasDraft: Bool {
        pending != nil || [weight, height, bodyFat, muscleMass, waist, chest, arm, thigh].contains { !$0.isEmpty }
    }

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    VStack(spacing: 16) {
                        DatePicker(L("Data"), selection: $date, displayedComponents: .date)
                        numberField(L("Peso (kg)"), text: $weight)
                        DisclosureGroup(L("Outras medidas (opcional)"), isExpanded: $otherMeasurements) {
                        VStack(spacing: 16) {
                        numberField(L("Altura (cm)"), text: $height)
                        numberField(L("Gordura corporal (%)"), text: $bodyFat)
                        numberField(L("Massa muscular (kg)"), text: $muscleMass)
                        numberField(L("Cintura (cm)"), text: $waist)
                        numberField(L("Peito (cm)"), text: $chest)
                        numberField(L("Braço (cm)"), text: $arm)
                        numberField(L("Coxa (cm)"), text: $thigh)
                        }.padding(.top, 12)
                        }
                    }
                    .padding(20).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 22))
                    .disabled(busy || pending != nil)
                    Text(L("Deixe em branco o que não souber. Zero não é uma medida válida."))
                        .font(.caption).foregroundColor(.secondary)
                    if let error { NativeRecoveryCard(title: pending == nil ? L("Vamos conferir suas medidas?") : L("Suas medidas continuam aqui"), message: error) }
                    Button { save() } label: {
                        HStack {
                            if busy { ProgressView().tint(.white) }
                            Text(busy ? L("Salvando…") : (pending == nil ? L("Salvar medidas") : L("Tentar novamente"))).fontWeight(.semibold)
                        }.frame(maxWidth: .infinity).padding(16)
                            .background(Color.fitBlue, in: RoundedRectangle(cornerRadius: 14)).foregroundColor(.white)
                    }.disabled(busy)
                    if pending != nil && !busy {
                        Text(L("O envio pode já ter sido recebido. Tente novamente para confirmar estas mesmas medidas sem criar outro registro. Evite fechar e iniciar um novo registro antes da confirmação."))
                            .font(.caption).foregroundColor(.secondary)
                    }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(existing == nil ? L("Registrar medidas") : L("Editar medidas")).navigationBarTitleDisplayMode(.inline)
            .onAppear {
                guard !loaded else { return }; loaded = true
                if let existing {
                    let formatter = DateFormatter(); formatter.dateFormat = "yyyy-MM-dd"; formatter.locale = Locale(identifier: "en_US_POSIX")
                    formatter.timeZone = session.profile?.profile?.timezone.flatMap(TimeZone.init(identifier:)) ?? .current
                    date = formatter.date(from: existing.date) ?? Date()
                    weight = value(existing.weight); height = value(existing.height); bodyFat = value(existing.bodyFat)
                    muscleMass = value(existing.muscleMass); waist = value(existing.waist); chest = value(existing.chest)
                    arm = value(existing.arm); thigh = value(existing.thigh)
                    otherMeasurements = existing.weight == nil
                }
            }
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { if hasDraft { showingDiscard = true } else { dismiss() } }.disabled(busy) } }
            .interactiveDismissDisabled(busy || hasDraft)
            .confirmationDialog(pending == nil ? L("Sair sem salvar estas medidas?") : L("Sair e conferir seu progresso?"), isPresented: $showingDiscard, titleVisibility: .visible) {
                Button(L("Continuar preenchendo"), role: .cancel) { }
                Button(pending == nil ? L("Descartar e sair") : L("Sair e conferir"), role: .destructive) { dismiss() }
            } message: {
                Text(pending == nil ? L("Seus valores ainda não foram salvos. Você pode continuar de onde parou.") : L("O envio ainda não foi confirmado. Confira seu progresso antes de criar outro registro com as mesmas medidas."))
            }
        }.navigationViewStyle(.stack)
    }

    private func value(_ number: Double?) -> String { number.map { String($0) } ?? "" }

    private func numberField(_ title: String, text: Binding<String>) -> some View {
        HStack {
            Text(title)
            TextField(L("Não informado"), text: text).keyboardType(.decimalPad)
                .multilineTextAlignment(.trailing).accessibilityLabel(title)
        }
    }

    private func number(_ text: String, title: String, maximum: Double) throws -> Double? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }
        guard let value = Double(trimmed.replacingOccurrences(of: ",", with: ".")),
              value.isFinite, value > 0, value <= maximum else {
            throw APIError.http(status: 400, message: L("\(title): informe um número maior que zero e até \(Int(maximum)), ou deixe em branco."))
        }
        return value
    }

    private func save() {
        error = nil
        let owner = session.user?.id
        let wasRetry = pending != nil
        do {
            let entry: NewMeasurementEntry
            if let pending { entry = pending }
            else {
                entry = NewMeasurementEntry(date: dietDate(date, timezone: session.profile?.profile?.timezone),
                    weight: try number(weight, title: L("Peso"), maximum: 500),
                    height: try number(height, title: L("Altura"), maximum: 300),
                    bodyFat: try number(bodyFat, title: L("Gordura corporal"), maximum: 100),
                    muscleMass: try number(muscleMass, title: L("Massa muscular"), maximum: 500),
                    waist: try number(waist, title: L("Cintura"), maximum: 500),
                    chest: try number(chest, title: L("Peito"), maximum: 500),
                    arm: try number(arm, title: L("Braço"), maximum: 500),
                    thigh: try number(thigh, title: L("Coxa"), maximum: 500), notes: existing?.notes)
                guard [entry.weight, entry.height, entry.bodyFat, entry.muscleMass, entry.waist, entry.chest, entry.arm, entry.thigh].contains(where: { $0 != nil }) else {
                    throw APIError.http(status: 400, message: L("Informe pelo menos uma medida, como seu peso."))
                }
            }
            pending = entry
            busy = true
            Task {
                defer { busy = false }
                do {
                    if let existing, let owner {
                        _ = try await session.api.updateMeasurementEntry(id: existing.id, entry: entry, idempotencyKey: idempotencyKey, ownerId: owner)
                    } else { _ = try await session.api.addMeasurementEntry(entry, idempotencyKey: idempotencyKey) }
                    guard session.user?.id == owner else { return }
                    NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
                    dismiss()
                } catch {
                    guard session.user?.id == owner else { return }
                    self.error = RequestFailure.message(error, fallback: L("Não recebemos a confirmação. Seus valores continuam nesta tela; tente novamente para conferir o mesmo registro."))
                    // A later rejection cannot disprove an earlier uncertain save.
                    if !wasRetry {
                        if case APIError.http(let status, _) = error, [400, 401, 403, 422, 429].contains(status) {
                            pending = nil
                            idempotencyKey = UUID().uuidString
                        } else if case APIError.csrfMismatch = error {
                            pending = nil
                            idempotencyKey = UUID().uuidString
                        }
                    }
                }
            }
        } catch { self.error = error.localizedDescription }
    }
}

struct NativeMeasurementHistoryView: View {
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    @State private var entries: [MeasurementEntry] = []
    @State private var editing: MeasurementEntry?
    @State private var deleting: MeasurementEntry?
    @State private var confirmDelete = false
    @State private var busy = false
    @State private var error: String?
    @State private var hasMore = false

    var body: some View {
        NavigationView {
            List {
                if let error { Text(NativeLocalization.display(error)).foregroundColor(.red); Button(L("Tentar novamente")) { Task { await load() } }.disabled(busy) }
                if entries.isEmpty, !busy, error == nil { Text(L("Seus registros de medidas aparecerão aqui.")) }
                ForEach(entries) { entry in
                    VStack(alignment: .leading, spacing: 10) {
                        Text(displayDate(entry.date)).font(.headline)
                        if let weight = entry.weight { Text("\(weight.formatted()) kg") }
                        HStack {
                            Button(L("Editar medidas")) { editing = entry }
                            Spacer()
                            Button(L("Excluir"), role: .destructive) { deleting = entry; confirmDelete = true }
                        }.buttonStyle(.borderless).frame(minHeight: 44).disabled(busy)
                    }
                }
                if hasMore { Button(L("Carregar mais")) { Task { await load(more: true) } }.disabled(busy) }
                if busy { ProgressView() }
            }.navigationTitle(L("Histórico de medidas")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { dismiss() } } }
                .task { await load() }
                .sheet(item: $editing, onDismiss: { Task { await load() } }) { NativeMeasurementEditor(existing: $0) }
                .confirmationDialog(L("Excluir este registro de medidas?"), isPresented: $confirmDelete, titleVisibility: .visible) {
                    Button(L("Excluir registro"), role: .destructive) { Task { await remove() } }
                    Button(L("Cancelar"), role: .cancel) { deleting = nil }
                } message: { Text(L("Todas as medidas deste registro serão removidas do histórico.")) }
        }.navigationViewStyle(.stack)
    }

    private func displayDate(_ value: String) -> String {
        let parser = DateFormatter(); parser.locale = Locale(identifier: "en_US_POSIX"); parser.dateFormat = "yyyy-MM-dd"
        guard let date = parser.date(from: value) else { return value }
        let display = DateFormatter(); display.locale = NativeLocalization.locale; display.dateStyle = .long
        return display.string(from: date)
    }

    private func load(more: Bool = false) async {
        guard !busy, let owner = session.user?.id else { return }; busy = true; error = nil
        defer { busy = false }
        do {
            let result = try await session.api.getMeasurementEntries(offset: more ? entries.count : 0)
            guard session.user?.id == owner else { return }
            entries = more ? entries + result : result; hasMore = result.count == 50
        } catch { if session.user?.id == owner { self.error = RequestFailure.message(error, fallback: L("Não conseguimos carregar suas medidas.")) } }
    }
    private func remove() async {
        guard !busy, let deleting, let owner = session.user?.id else { return }; busy = true; error = nil
        do {
            try await session.api.deleteMeasurementEntry(id: deleting.id, ownerId: owner)
            guard session.user?.id == owner else { busy = false; return }
            NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
            busy = false; self.deleting = nil; await load()
        } catch { busy = false; self.error = RequestFailure.message(error, fallback: L("Não confirmamos a exclusão. Confira o histórico e tente novamente.")) }
    }
}
