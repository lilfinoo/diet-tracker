import SwiftUI
#if os(Android)
import SkipFuse
#endif
import FitTrackerCore

struct NativeWorkoutTextImportView: View {
    @Environment(\.dismiss) var dismiss
    @State var text = ""
    @State var error: String?
    @State var draft: WorkoutTextImport?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Traga o treino que você já tem").font(.title3.bold())
                    Text("Cole seu treino e confira todos os exercícios antes de salvar. Neste piloto Android, a importação aceita texto.").foregroundColor(.secondary)
                }
                Section("Texto do treino") {
                    TextEditor(text: $text).frame(minHeight: 220).accessibilityLabel("Texto do treino para importar")
                    Text("Exemplo:\nTreino A\nSupino reto 3x10 · descanso 60s\nTreino B\nAgachamento 4x8-12 · 20 kg · descanso 90s").font(.caption).foregroundColor(.secondary)
                    Text("Aceita até 7 treinos com 12 exercícios em cada um. Linhas fora desse formato podem precisar de correção.").font(.caption).foregroundColor(.secondary)
                }
                Section {
                    if let error { Text(error).foregroundColor(.orange) }
                    Button("Revisar exercícios importados") {
                        do { draft = try WorkoutTextParser.parse(text); error = nil }
                        catch { self.error = error.localizedDescription }
                    }.disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    Text("Nenhum plano será salvo ou colocado em uso nesta etapa.").font(.caption).foregroundColor(.secondary)
                }
            }.navigationTitle("Importar treino").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() } } }
                .sheet(item: $draft) { NativeManualPlanView(kind: .workout, imported: $0) }
        }
    }
}
