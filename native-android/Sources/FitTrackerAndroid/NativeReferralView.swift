import SwiftUI
#if os(Android)
import SkipFuse
#endif
import FitTrackerCore

struct NativeReferralView: View {
    @Environment(NativeSession.self) var session
    @State var status: ReferralStatus?
    @State var error: String?
    @State var loading = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                Text("Convide 3 pessoas este mês").font(.title2.bold())
                Text("Cada pessoa precisa criar uma nova conta usando seu código. Ao completar 3 convites no mês, você recebe um mês de Premium.").foregroundStyle(.secondary)
                if loading { ProgressView("Consultando seus convites…") }
                if let status {
                    Text("Seu código").font(.headline)
                    Text(status.code).font(.title.bold())
                    ShareLink(item: "Use meu código \(status.code) ao criar sua conta no Fit Tracker: https://diet-tracker-6i67.onrender.com") {
                        Label("Compartilhar código", systemImage: "square.and.arrow.up")
                    }.buttonStyle(.borderedProminent)
                    Text(status.rewardedThisMonth ? "Meta do mês concluída" : "\(status.progress) de \(status.target) convites neste mês").font(.headline)
                    ProgressView(value: Double(status.progress), total: Double(status.target))
                    Text("A contagem recomeça todo mês. Convites extras não acumulam meses nem passam para o mês seguinte. Máximo de um mês de Premium por mês.").font(.footnote).foregroundStyle(.secondary)
                    Text("O benefício não pausa nem cancela cobranças de assinaturas pagas.").font(.footnote).foregroundStyle(.secondary)
                }
                if let error {
                    Text(error).foregroundStyle(.red)
                    Button("Tentar novamente") { Task { await load() } }.disabled(loading)
                }
            }.padding(24)
        }.background(Color.fitBackground).navigationTitle("Convites").navigationBarTitleDisplayMode(.inline)
            .task { await load() }
    }

    func load() async {
        guard !loading, let owner = session.user?.id else { return }
        loading = true; error = nil
        defer { loading = false }
        do {
            let response = try await session.api.referralStatus()
            guard session.user?.id == owner else { return }
            status = response
        } catch { if !isNativeRequestCancellation(error) { self.error = error.localizedDescription } }
    }
}
