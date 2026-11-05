import SwiftUI
import RevenueCat
import FitTrackerCore

struct NativeSubscriptionView: View {
    @EnvironmentObject private var session: NativeSession
    var surface: String = "plans_modal"
    var workoutUnlock = false
    var body: some View { NativePaywallContent(store: session.billing, surface: surface, workoutUnlock: workoutUnlock) }
}

private struct NativePaywallContent: View {
    @EnvironmentObject private var session: NativeSession
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var store: NativeBillingStore
    let surface: String
    let workoutUnlock: Bool
    @State private var experiment: PaywallExperiment?
    @State private var selected = "ai.fittracker.premium.monthly"
    @State private var status: SubscriptionStatus?
    @State private var partner: ReferralAttributionStatus?
    @State private var partnerCode = ""
    @State private var appliedPartner: ReferralApplication?
    @State private var partnerBusy = false
    @State private var partnerMessage: String?
    @State private var partnerError: String?

    private var currentPartner: (publicName: String, code: String)? {
        if let appliedPartner { return (appliedPartner.publicName, appliedPartner.code) }
        if let attribution = partner?.attribution, attribution.kind == "affiliate" {
            return (attribution.publicName, attribution.code)
        }
        return nil
    }
    private var chosen: RevenueCat.Package? { store.packages.first { $0.storeProduct.productIdentifier == selected } }
    private var trial: Bool { selected.hasSuffix("monthly") && store.sevenDayTrial }
    private var message: PaywallMessage {
        if workoutUnlock {
            return .workoutUnlock
        }
        return PaywallMessage.forSurface(surface, variant: experiment?.variant)
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("FIT TRACKER PREMIUM").font(.caption.weight(.bold)).tracking(1.5).foregroundColor(.fitBlue)
                Text(NativeLocalization.display(message.title)).font(.title.bold())
                Text(NativeLocalization.display(message.detail)).font(.subheadline).foregroundColor(.secondary)
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(message.benefits, id: \.self) { benefit(NativeLocalization.display($0)) }
                }.font(.subheadline)
                if status?.isPremium == true || session.user?.isPremium == true {
                    Label(L("Premium ativo"), systemImage: "checkmark.seal.fill").foregroundColor(.green)
                    if let subscription = status?.subscription {
                        Text(subscription.provider == "referral" ? L("Você conquistou este Premium com seus convites.") : subscription.status == "trialing" ? L("Seu período de teste está ativo.") : L("Sua assinatura está ativa.")).font(.subheadline)
                        if let end = subscription.currentPeriodEnd, let date = referralDateLabel(end) {
                            Text(L("Período atual até \(date)")).font(.footnote).foregroundColor(.secondary)
                        }
                        if subscription.provider == "revenuecat" { Link(L("Gerenciar assinatura"), destination: URL(string: "https://apps.apple.com/account/subscriptions")!) }
                        else if subscription.provider == "referral" {
                            Text(L("Esta recompensa não renova nem gera cobrança. Ela não pausa uma assinatura paga existente.")).font(.footnote)
                            Link(L("Assinaturas na Apple"), destination: URL(string: "https://apps.apple.com/account/subscriptions")!)
                        }
                        else { Text(L("Sua assinatura foi contratada no site. Gerencie-a pelo Perfil do site.")).font(.footnote) }
                    }
                } else {
                    ForEach(store.packages.sorted { $0.storeProduct.productIdentifier.hasSuffix("monthly") && !$1.storeProduct.productIdentifier.hasSuffix("monthly") }, id: \.identifier) { item in
                        packageCard(item)
                    }
                    if store.loading { ProgressView(L("Consultando os planos da Apple…")).frame(maxWidth: .infinity) }
                    if let feedback = store.feedback { recoveryNotice(feedback) }
                    if let chosen {
                        Text(trial ? L("7 dias grátis. Depois, \(chosen.storeProduct.localizedPriceString) por mês.") : L("\(chosen.storeProduct.localizedPriceString) cobrados \(selected.hasSuffix("annual") ? L("uma vez por ano") : L("por mês"))."))
                            .font(.footnote).foregroundColor(.secondary)
                        Text(L("Renovação automática até o cancelamento. Gerencie nas assinaturas da Apple. Cancele pelo menos 24 horas antes do fim do período para evitar a renovação."))
                            .font(.caption).foregroundColor(.secondary)
                        if store.canPurchase {
                            Button {
                                Task { await purchaseWithPartner(chosen) }
                            } label: {
                                HStack { Spacer(); if store.purchasing { ProgressView() } else { Text(store.feedback?.action == .retryPurchase ? L("Tentar este plano novamente") : trial ? L("Experimentar 7 dias grátis") : L("Continuar com o \(selected.hasSuffix("annual") ? L("anual") : L("mensal"))")).bold() }; Spacer() }.padding(.vertical, 10)
                            }.fitGlassButton(prominent: true).disabled(store.purchasing || store.loading || partnerBusy)
                        }
                    }
                    Button(L("Continuar no gratuito")) { dismiss() }.frame(maxWidth: .infinity).disabled(store.purchasing || partnerBusy)
                }
                Button(L("Restaurar compras")) {
                    Task { await store.transact(package: nil, restore: true, session: session); status = try? await session.api.subscriptionStatus() }
                }.frame(maxWidth: .infinity).font(.footnote).disabled(store.loading || store.purchasing || partnerBusy || !store.canRestore(session: session))
                NativeLegalLinks()
                partnerSection
            }.padding(22)
        }.background(Color.fitBackground.ignoresSafeArea()).navigationTitle("Premium").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Fechar")) { dismiss() }.disabled(store.purchasing || partnerBusy) } }
            .interactiveDismissDisabled(store.purchasing || partnerBusy)
            .task(id: session.user?.id) {
                let owner = session.user?.id
                status = nil; experiment = nil; partner = nil; appliedPartner = nil; partnerCode = ""; partnerMessage = nil; partnerError = nil
                async let products: Void = store.load(session: session)
                async let attribution: Void = loadPartner()
                if !session.hasPremium {
                    experiment = try? await session.api.paywallExperiment(surface: surface)
                    guard session.user?.id == owner else { return }
                    try? await session.api.trackPaywallView(surface: surface)
                }
                let currentStatus = try? await session.api.subscriptionStatus()
                await products
                await attribution
                guard session.user?.id == owner else { return }
                status = currentStatus
                if chosen == nil, let first = store.packages.first { selected = first.storeProduct.productIdentifier }
            }
    }

    private var partnerSection: some View {
        DisclosureGroup(L("Código de convite")) {
            VStack(alignment: .leading, spacing: 12) {
                if let attribution = currentPartner {
                    Label(attribution.publicName, systemImage: "checkmark.seal.fill").foregroundColor(.fitBlue)
                    Text(L("Código \(attribution.code) aplicado à sua conta.")).font(.subheadline)
                } else {
                    TextField(L("Código de convite"), text: $partnerCode)
                        .textInputAutocapitalization(.characters).autocorrectionDisabled(true)
                        .keyboardType(.asciiCapable).padding(14)
                        .background(Color.fitBackground, in: RoundedRectangle(cornerRadius: 12))
                        .disabled(partnerBusy || store.purchasing)
                    Button(partnerBusy ? L("Validando…") : L("Aplicar código")) { Task { await applyPartner() } }
                        .frame(maxWidth: .infinity, minHeight: 44).fitGlassButton()
                        .disabled(partnerBusy || store.purchasing || store.loading || partnerCode.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                if let partnerMessage { Label(partnerMessage, systemImage: "checkmark.circle.fill").font(.footnote).foregroundColor(.green) }
                if let partnerError { Text(partnerError).font(.footnote).foregroundColor(.orange) }
            }.padding(.top, 12)
        }.font(.footnote).foregroundColor(.secondary)
            .padding(14).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
    }

    private func loadPartner() async {
        let owner = session.user?.id
        do {
            let result = try await session.api.referralAttribution()
            guard session.user?.id == owner else { return }
            partner = result
        } catch {
            guard session.user?.id == owner, !isNativeRequestCancellation(error) else { return }
            partnerError = RequestFailure.message(error, fallback: L("Não foi possível consultar sua indicação."))
        }
    }

    private func applyPartnerCode(_ code: String, owner: UUID) async throws {
        let result = try await session.api.applyReferralCode(code, ownerId: owner)
        guard session.user?.id == owner else {
            throw APIError.http(status: 401, message: L("Entre novamente na mesma conta para continuar."))
        }
        appliedPartner = result
        partnerMessage = result.message
        partnerCode = ""
        await loadPartner()
    }

    private func applyPartner() async {
        guard !partnerBusy, !store.purchasing, let owner = session.user?.id else { return }
        partnerBusy = true; partnerError = nil
        defer { partnerBusy = false }
        do { try await applyPartnerCode(partnerCode, owner: owner) }
        catch {
            guard session.user?.id == owner, !isNativeRequestCancellation(error) else { return }
            partnerError = RequestFailure.message(error, fallback: L("Não foi possível aplicar o código."))
        }
    }

    private func purchaseWithPartner(_ package: RevenueCat.Package) async {
        guard !partnerBusy, !store.purchasing, let owner = session.user?.id else { return }
        partnerBusy = true; partnerError = nil
        defer { partnerBusy = false }
        do {
            let planCode = package.storeProduct.productIdentifier.hasSuffix("annual") ? "premium_student_annual" : "premium_student"
            Task { try? await session.api.trackPaywallPurchase(planCode: planCode) }
            try await ReferralPurchase.run(code: currentPartner == nil ? partnerCode : "", restore: false,
                isCurrentAccount: { session.user?.id == owner },
                apply: { try await applyPartnerCode($0, owner: owner) },
                purchase: { await store.transact(package: package, restore: false, session: session) })
            guard session.user?.id == owner else { return }
            status = try? await session.api.subscriptionStatus()
        } catch {
            guard session.user?.id == owner, !isNativeRequestCancellation(error) else { return }
            partnerError = RequestFailure.message(error, fallback: L("Não foi possível validar o código. A compra não foi iniciada."))
        }
    }

    private func recoveryNotice(_ feedback: BillingRecovery) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(NativeLocalization.display(feedback.title), systemImage: feedback == .cancelled ? "heart" : feedback.blocksNewPurchase ? "clock.arrow.circlepath" : "arrow.triangle.2.circlepath")
                .font(.subheadline.weight(.semibold)).foregroundColor(Color(red: 0.59, green: 0.91, blue: 0.83))
            Text(NativeLocalization.display(feedback.message)).font(.subheadline).foregroundColor(.secondary).fixedSize(horizontal: false, vertical: true)
            if let action = feedback.action, action != .retryPurchase, let title = feedback.actionTitle {
                Button {
                    Task {
                        switch action {
                        case .reloadPlans: await store.load(session: session, force: true)
                        case .verifyPurchase: await store.verifyPurchase(session: session)
                        case .restorePurchases: await store.transact(package: nil, restore: true, session: session)
                        case .retryPurchase: break
                        }
                        status = try? await session.api.subscriptionStatus()
                        if chosen == nil, let first = store.packages.first { selected = first.storeProduct.productIdentifier }
                    }
                } label: {
                    HStack { if store.purchasing || store.loading { ProgressView() }; Text(NativeLocalization.display(title)).fontWeight(.semibold) }
                        .frame(maxWidth: .infinity, minHeight: 44)
                }.fitGlassButton().disabled(store.purchasing || store.loading || partnerBusy)
            }
            if feedback == .accountConflict || feedback == .activationPending {
                Link(L("Falar com o suporte"), destination: URL(string: "https://diet-tracker-6i67.onrender.com/support.html")!)
                    .font(.subheadline).frame(minHeight: 44)
            }
        }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(red: 0.59, green: 0.91, blue: 0.83).opacity(0.06), in: RoundedRectangle(cornerRadius: 18))
            .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.white.opacity(0.1), lineWidth: 1))
            .accessibilityElement(children: .contain)
    }

    private func benefit(_ title: String) -> some View { Label(title, systemImage: "checkmark").foregroundColor(.primary) }
    private func packageCard(_ item: RevenueCat.Package) -> some View {
        let annual = item.storeProduct.productIdentifier.hasSuffix("annual")
        return Button { selected = item.storeProduct.productIdentifier } label: {
            HStack(spacing: 12) {
                Image(systemName: selected == item.storeProduct.productIdentifier ? "largecircle.fill.circle" : "circle").foregroundColor(.fitBlue)
                VStack(alignment: .leading, spacing: 6) {
                    if annual, let discount = annualDiscount(item) {
                        Text(L("\(discount)% DE DESCONTO")).font(.caption2.bold()).foregroundColor(.green)
                    }
                    Text(annual ? L("Anual") : L("Mensal")).font(.body.bold())
                    if annual { Text(L("\(item.storeProduct.localizedPriceString) cobrados por ano")).font(.caption).foregroundColor(.secondary) }
                    else if store.sevenDayTrial { Text(L("7 dias grátis para você")).font(.caption).foregroundColor(.secondary) }
                }
                Spacer(minLength: 4)
                VStack(alignment: .trailing, spacing: 4) {
                    Text(annual ? monthlyEquivalent(item) : item.storeProduct.localizedPriceString).font(.title3.bold())
                    Text(annual ? L("equivalente por mês") : L("por mês")).font(.caption).foregroundColor(.secondary)
                }
            }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 17))
                .overlay(RoundedRectangle(cornerRadius: 17).stroke(selected == item.storeProduct.productIdentifier ? Color.fitBlue : Color.white.opacity(0.12), lineWidth: 1))
        }.buttonStyle(.plain).disabled(store.purchasing || partnerBusy)
    }
    private func monthlyEquivalent(_ item: RevenueCat.Package) -> String {
        let formatter = NumberFormatter(); formatter.numberStyle = .currency
        formatter.locale = item.storeProduct.priceFormatter?.locale ?? .current
        formatter.currencyCode = item.storeProduct.currencyCode
        return formatter.string(from: NSDecimalNumber(decimal: item.storeProduct.price / 12)) ?? "—"
    }
    private func annualDiscount(_ annual: RevenueCat.Package) -> Int? {
        guard let monthly = store.packages.first(where: { $0.storeProduct.productIdentifier.hasSuffix("monthly") }),
              monthly.storeProduct.currencyCode == annual.storeProduct.currencyCode, monthly.storeProduct.price > 0 else { return nil }
        let value = (1 - annual.storeProduct.price / (monthly.storeProduct.price * 12)) * 100
        let percent = NSDecimalNumber(decimal: value).intValue
        return percent > 0 ? percent : nil
    }
}

struct NativeLegalLinks: View {
    var body: some View {
        HStack(spacing: 20) {
            Link(L("Termos de Uso"), destination: URL(string: "https://diet-tracker-6i67.onrender.com/terms.html")!)
            Link(L("Privacidade"), destination: URL(string: "https://diet-tracker-6i67.onrender.com/privacy.html")!)
        }.font(.caption).frame(maxWidth: .infinity)
    }
}

struct NativeFreeAccessCard: View {
    @EnvironmentObject private var session: NativeSession
    var body: some View {
        if let access = session.freeAccess, !access.premium {
            VStack(alignment: .leading, spacing: 10) {
                Text(L("Seu acesso gratuito")).font(.subheadline.bold())
                HStack { Text(L("Treino com IA")); Spacer(); Text(L("\(access.remainingPlans(for: .workout)) restante")) }
                HStack { Text(L("Dieta com IA")); Spacer(); Text(L("\(access.remainingPlans(for: .diet)) restante")) }
                HStack { Text(L("Fotos ou descrições")); Spacer(); Text(L("\(access.photos.remaining) de \(access.photos.limit) restantes")) }
                Text(L("Limites únicos por conta. Registro manual de calorias e macros disponível.")).font(.caption2).foregroundColor(.secondary)
                Text(L("Criação e edição manual de planos, aplicação e execução de treinos disponíveis gratuitamente.")).font(.caption2).foregroundColor(.secondary)
            }.font(.caption).padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
        }
    }
}
