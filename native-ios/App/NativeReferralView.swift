import SwiftUI
import UIKit
import FitTrackerCore

struct NativeReferralView: View {
    @EnvironmentObject private var session: NativeSession
    @State private var status: ReferralStatus?
    @State private var loading = false
    @State private var error: String?
    @State private var copied = false
    @State private var sharing = false
    @State private var attribution: ReferralAttributionStatus?
    @State private var partnerCode = ""
    @State private var applying = false
    @State private var applicationMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                Label(L("CONVIDE E GANHE"), systemImage: "gift.fill").font(.caption.bold()).foregroundColor(.fitBlue)
                Text(L("3 convites no mês.\n1 mês de Premium.")).font(.title.bold())
                Text(L("Convide pessoas novas para o Fit Tracker. Quando 3 criarem uma conta com seu código no mesmo mês, seu Premium será liberado automaticamente."))
                    .font(.subheadline).foregroundColor(.secondary)
                if let status {
                    VStack(alignment: .leading, spacing: 14) {
                        Text(L("Seu código de convite")).font(.headline)
                        Text(status.code).font(.system(.title2, design: .monospaced).bold())
                            .textSelection(.enabled).accessibilityLabel(L("Código de convite: \(status.code)"))
                        Button {
                            UIPasteboard.general.string = status.code
                            copied = true
                        } label: { Label(copied ? L("Código copiado") : L("Copiar código"), systemImage: copied ? "checkmark" : "doc.on.doc").frame(maxWidth: .infinity, minHeight: 44) }
                            .fitGlassButton()
                        Button { sharing = true } label: { Label(L("Compartilhar convite"), systemImage: "square.and.arrow.up").frame(maxWidth: .infinity, minHeight: 44) }
                            .fitGlassButton(prominent: true)
                    }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 20))
                    VStack(alignment: .leading, spacing: 14) {
                        Text(L("Convites deste mês")).font(.headline)
                        HStack(spacing: 12) {
                            ForEach(0..<status.target, id: \.self) { index in
                                Image(systemName: index < status.progress ? "checkmark.circle.fill" : "circle")
                                    .font(.title).foregroundColor(index < status.progress ? .fitBlue : .secondary)
                            }
                            Spacer()
                            Text("\(status.progress)/\(status.target)").font(.title2.bold())
                        }.accessibilityElement(children: .ignore)
                            .accessibilityLabel(L("\(status.progress) de \(status.target) convites necessários neste mês"))
                        Text(L("\(status.qualifiedInvites) \(status.qualifiedInvites == 1 ? L("cadastro válido") : L("cadastros válidos")) neste mês")).font(.subheadline).foregroundColor(.secondary)
                        if status.rewardedThisMonth {
                            Label(L("Meta do mês concluída!"), systemImage: "gift.fill").foregroundColor(.green)
                        } else {
                            Text(L("Faltam \(max(0, status.target - status.progress)) \(status.target - status.progress == 1 ? L("convite válido") : L("convites válidos")) para ganhar seu mês Premium.")).font(.subheadline)
                        }
                        if let end = status.premiumUntil, let date = referralDateLabel(end) {
                            Text(L("Premium por convites até \(date).")).font(.subheadline).foregroundColor(.green)
                        }
                        if let date = referralDateLabel(status.periodEndsAt) {
                            Text(L("A contagem recomeça em \(date).")).font(.caption).foregroundColor(.secondary)
                        }
                    }.padding(18).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 20))
                    VStack(alignment: .leading, spacing: 10) {
                        Text(L("Como funciona")).font(.headline)
                        Text(L("Só contam novas contas que informam seu código no cadastro. Cada pessoa convidada conta uma vez."))
                        Text(L("A meta é mensal, pelo horário de Brasília. No máximo 1 recompensa por mês; convites excedentes não passam para o mês seguinte e não há meses guardados."))
                        Text(L("A recompensa dura 1 mês a partir da conquista, sem renovação paga. Ela não pausa nem cancela uma assinatura já existente."))
                    }.font(.footnote).foregroundColor(.secondary)
                }
                if let attribution {
                    DisclosureGroup {
                        VStack(alignment: .leading, spacing: 12) {
                            if let current = attribution.attribution {
                                Label(current.publicName, systemImage: "checkmark.seal.fill").foregroundColor(.fitBlue)
                                Text(L("Código \(current.code) aplicado.")).font(.subheadline)
                            }
                            if attribution.canApplyAffiliate {
                                Text(L("Tem um código de quem apresentou o Fit Tracker? Use aqui para apoiar esse criador."))
                                    .font(.footnote).foregroundColor(.secondary)
                                TextField(L("Código de convite"), text: $partnerCode)
                                    .textInputAutocapitalization(.characters).autocorrectionDisabled(true)
                                    .keyboardType(.asciiCapable).padding(14)
                                    .background(Color.fitBackground, in: RoundedRectangle(cornerRadius: 12))
                                    .disabled(applying)
                                Button { Task { await applyPartnerCode() } } label: {
                                    Text(applying ? L("Aplicando…") : L("Aplicar código")).frame(maxWidth: .infinity, minHeight: 44)
                                }.fitGlassButton(prominent: true)
                                    .disabled(applying || loading || partnerCode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                                Text(L("O vínculo é permanente e não libera Premium. Convites de amigos são usados no cadastro.")).font(.caption).foregroundColor(.secondary)
                            } else {
                                Text(L("Sua conta já está vinculada a um criador."))
                                    .font(.footnote).foregroundColor(.secondary)
                            }
                        }.padding(.top, 12)
                    } label: {
                        Label(L("Apoie o criador"), systemImage: "heart").font(.subheadline.weight(.semibold))
                    }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 20))
                }
                if let applicationMessage {
                    Label(applicationMessage, systemImage: "checkmark.circle.fill").font(.subheadline).foregroundColor(.green)
                }
                if loading { ProgressView(L("Consultando seus convites…")).frame(maxWidth: .infinity) }
                if let error {
                    NativeRecoveryCard(title: L("Vamos consultar seus convites?"), message: error, actionTitle: L("Tentar novamente")) { Task { await load() } }
                }
            }.padding(22)
        }.background(Color.fitBackground.ignoresSafeArea())
            .navigationTitle(L("Convide e ganhe")).navigationBarTitleDisplayMode(.inline)
            .task { await load() }.refreshable { await load() }
            .sheet(isPresented: $sharing) {
                if let status {
                    ReferralShareSheet(message: L("Venha cuidar do seu treino e alimentação no Fit Tracker! Baixe o app e use meu código \(status.code) ao criar sua conta.\nhttps://apps.apple.com/br/app/fittracker-ai/id6819823860"))
                }
            }
    }

    private func applyPartnerCode() async {
        guard !applying, let owner = session.user?.id else { return }
        applying = true; error = nil; applicationMessage = nil
        defer { applying = false }
        do {
            let result = try await session.api.applyReferralCode(partnerCode, ownerId: owner)
            guard session.user?.id == owner else { return }
            applicationMessage = result.message
            partnerCode = ""
            attribution = nil
            await load()
        } catch {
            guard session.user?.id == owner, !isNativeRequestCancellation(error) else { return }
            self.error = RequestFailure.message(error, fallback: L("Não foi possível aplicar o código agora. Tente novamente."))
        }
    }

    private func load() async {
        guard !loading, let owner = session.user?.id else { return }
        loading = true; error = nil
        defer { loading = false }
        do {
            let result = try await session.api.referralStatus()
            guard session.user?.id == owner else { return }
            status = result
            let attributionResult = try await session.api.referralAttribution()
            guard session.user?.id == owner else { return }
            attribution = attributionResult
            try? await session.refreshFreeAccess()
        } catch { if !isNativeRequestCancellation(error) { self.error = RequestFailure.message(error, fallback: L("Não foi possível consultar seus convites agora. Tente novamente.")) } }
    }
}

private struct ReferralShareSheet: UIViewControllerRepresentable {
    let message: String
    func makeUIViewController(context: Context) -> UIActivityViewController { UIActivityViewController(activityItems: [message], applicationActivities: nil) }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) { }
}

func referralDateLabel(_ value: String) -> String? {
    let parser = ISO8601DateFormatter()
    parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let fractional = parser.date(from: value)
    parser.formatOptions = [.withInternetDateTime]
    guard let date = fractional ?? parser.date(from: value) else { return nil }
    let display = DateFormatter()
    display.locale = NativeLocalization.locale
    display.timeZone = TimeZone(identifier: "America/Sao_Paulo")
    display.dateStyle = .medium
    return display.string(from: date)
}
