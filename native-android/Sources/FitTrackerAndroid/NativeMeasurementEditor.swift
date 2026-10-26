import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
import FitTrackerCore

struct NativeMeasurementEditor: View {
    @Environment(NativeSession.self) var session
    @Environment(\.dismiss) var dismiss
    @State var date = Date()
    @State var weight = ""
    @State var height = ""
    @State var bodyFat = ""
    @State var muscleMass = ""
    @State var waist = ""
    @State var chest = ""
    @State var arm = ""
    @State var thigh = ""
    @State var pending: NewMeasurementEntry?
    @State var idempotencyKey = UUID().uuidString
    @State var busy = false
    @State var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    VStack(spacing: 16) {
                        DatePicker("Data", selection: $date, displayedComponents: .date)
                        numberField("Peso (kg)", text: $weight)
                        numberField("Altura (cm)", text: $height)
                        numberField("Gordura corporal (%)", text: $bodyFat)
                        numberField("Massa muscular (kg)", text: $muscleMass)
                        numberField("Cintura (cm)", text: $waist)
                        numberField("Peito (cm)", text: $chest)
                        numberField("Braço (cm)", text: $arm)
                        numberField("Coxa (cm)", text: $thigh)
                    }
                    .padding(20).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 22))
                    .disabled(busy || pending != nil)
                    Text("Deixe em branco o que não souber. Zero não é uma medida válida.")
                        .font(.caption).foregroundColor(.secondary)
                    if let error { Text(error).foregroundColor(.red).accessibilityLabel("Erro: \(error)") }
                    Button { save() } label: {
                        HStack {
                            if busy { ProgressView().tint(.white) }
                            Text(busy ? "Salvando…" : (pending == nil ? "Salvar medidas" : "Tentar novamente")).fontWeight(.semibold)
                        }.frame(maxWidth: .infinity).padding(16)
                            .background(Color.fitBlue, in: RoundedRectangle(cornerRadius: 14)).foregroundColor(.white)
                    }.disabled(busy)
                    if pending != nil && !busy {
                        Text("O envio pode já ter sido recebido. Tente novamente para confirmar estas mesmas medidas sem criar outro registro. Evite fechar e iniciar um novo registro antes da confirmação.")
                            .font(.caption).foregroundColor(.secondary)
                    }
                }.padding(20)
            }
            .background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle("Registrar medidas").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() }.disabled(busy) } }
            .interactiveDismissDisabled(busy)
        }
    }

    func numberField(_ title: String, text: Binding<String>) -> some View {
        HStack {
            Text(title)
            TextField("Não informado", text: text).keyboardType(.decimalPad)
                .multilineTextAlignment(.trailing).accessibilityLabel(Text(title))
        }
    }

    func number(_ text: String, title: String, maximum: Double) throws -> Double? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }
        guard let value = Double(trimmed.replacingOccurrences(of: ",", with: ".")),
              value.isFinite, value > 0, value <= maximum else {
            throw APIError.http(status: 400, message: "\(title): informe um número maior que zero e até \(Int(maximum)), ou deixe em branco.")
        }
        return value
    }

    func save() {
        error = nil
        let wasRetry = pending != nil
        do {
            let entry: NewMeasurementEntry
            if let pending { entry = pending }
            else {
                entry = NewMeasurementEntry(date: dietDate(date, timezone: session.profile?.profile?.timezone),
                    weight: try number(weight, title: "Peso", maximum: 500),
                    height: try number(height, title: "Altura", maximum: 300),
                    bodyFat: try number(bodyFat, title: "Gordura corporal", maximum: 100),
                    muscleMass: try number(muscleMass, title: "Massa muscular", maximum: 500),
                    waist: try number(waist, title: "Cintura", maximum: 500),
                    chest: try number(chest, title: "Peito", maximum: 500),
                    arm: try number(arm, title: "Braço", maximum: 500),
                    thigh: try number(thigh, title: "Coxa", maximum: 500))
            }
            pending = entry
            busy = true
            Task {
                defer { busy = false }
                do {
                    _ = try await session.api.addMeasurementEntry(entry, idempotencyKey: idempotencyKey)
                    NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
                    dismiss()
                } catch {
                    self.error = error.localizedDescription
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
