import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
import SkipRevenue
import FitTrackerCore

struct NativeSubscriptionView: View {
    @Environment(NativeSession.self) var session
    var body: some View { NativePaywallContent(store: session.billing) }
}

struct NativePaywallContent: View {
    @Environment(NativeSession.self) var session
    @Environment(\.dismiss) var dismiss
    @Bindable var store: NativeBillingStore
    @State var selected = "$rc_monthly"
    @State var status: SubscriptionStatus?

    var chosen: RCFusePackage? { store.packages.first { $0.identifier == selected } }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("FIT TRACKER PREMIUM").font(.caption.weight(.bold)).tracking(1.5).foregroundColor(.fitBlue)
                Text("Mais foco na sua evolução.").font(.title.bold())
                Text("Treino e alimentação personalizados para acompanhar sua rotina.").font(.subheadline).foregroundColor(.secondary)
                VStack(alignment: .leading, spacing: 12) {
                    benefit("Mais gerações de treino e dieta")
                    benefit("Mais análises de refeições por foto")
                    benefit("Ajustes de planos com IA")
                }.font(.subheadline)
                if status?.isPremium == true || session.user?.isPremium == true {
                    Label("Premium ativo", systemImage: "checkmark.seal.fill").foregroundColor(.green)
                    if let subscription = status?.subscription {
                        Text(subscription.status == "trialing" ? "Seu período de teste está ativo." : "Sua assinatura está ativa.").font(.subheadline)
                        if let end = subscription.currentPeriodEnd, let date = ISO8601DateFormatter().date(from: end) {
                            Text("Período atual até \(date.formatted(date: .abbreviated, time: .omitted))").font(.footnote).foregroundColor(.secondary)
                        }
                        if subscription.provider == "revenuecat" {
                            Link("Abrir assinaturas da Google Play", destination: URL(string: "https://play.google.com/store/account/subscriptions")!)
                            Text("Assinaturas compradas em outra plataforma devem ser gerenciadas na loja de origem.").font(.footnote).foregroundColor(.secondary)
                        }
                        else { Text("Sua assinatura foi contratada no site. Gerencie-a pelo Perfil do site.").font(.footnote) }
                    }
                } else {
                    ForEach(store.packages.sorted { $0.packageType == .monthly && $1.packageType != .monthly }, id: \.identifier) { item in
                        packageCard(item)
                    }
                    if store.loading { ProgressView("Consultando os planos da Google Play…").frame(maxWidth: .infinity) }
                    if let error = store.error {
                        Text(error).font(.footnote).foregroundColor(.red)
                        Button("Tentar novamente") { Task { await store.load(session: session, force: true) } }
                    }
                    if let chosen {
                        Text("\(chosen.storeProduct.localizedPriceString) cobrados \(chosen.packageType == .annual ? "uma vez por ano" : "por mês").")
                            .font(.footnote).foregroundColor(.secondary)
                        Text("Renovação automática até o cancelamento. Gerencie ou cancele nas assinaturas da Google Play. Ofertas de teste, quando disponíveis para você, aparecem antes da confirmação da compra.")
                            .font(.caption).foregroundColor(.secondary)
                        Button {
                            Task { await store.transact(package: chosen, restore: false, session: session); status = try? await session.api.subscriptionStatus() }
                        } label: {
                            HStack { Spacer(); if store.purchasing { ProgressView() } else { Text("Continuar com o \(chosen.packageType == .annual ? "anual" : "mensal")").bold() }; Spacer() }.padding(.vertical, 10)
                        }.buttonStyle(.borderedProminent).disabled(store.purchasing || store.loading)
                    }
                    Button("Continuar no gratuito") { dismiss() }.frame(maxWidth: .infinity).disabled(store.purchasing)
                }
                Button("Restaurar compras") {
                    Task { await store.transact(package: nil, restore: true, session: session); status = try? await session.api.subscriptionStatus() }
                }.frame(maxWidth: .infinity).font(.footnote).disabled(store.loading || store.purchasing || !store.canRestore(session: session))
                NativeLegalLinks()
            }.padding(22)
        }.background(Color.fitBackground.ignoresSafeArea()).navigationTitle("Premium").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Fechar") { dismiss() }.disabled(store.purchasing) } }
            .interactiveDismissDisabled(store.purchasing)
            .task {
                async let products: Void = store.load(session: session)
                status = try? await session.api.subscriptionStatus()
                await products
                if chosen == nil, let first = store.packages.first { selected = first.identifier }
            }
    }

    func benefit(_ title: String) -> some View { Label(title, systemImage: "checkmark").foregroundColor(.primary) }
    func packageCard(_ item: RCFusePackage) -> some View {
        let annual = item.packageType == .annual
        return Button { selected = item.identifier } label: {
            HStack(spacing: 12) {
                Image(systemName: selected == item.identifier ? "largecircle.fill.circle" : "circle").foregroundColor(.fitBlue)
                VStack(alignment: .leading, spacing: 6) {
                    if annual, let discount = annualDiscount(item) {
                        Text("\(discount)% DE DESCONTO").font(.caption2.bold()).foregroundColor(.green)
                    }
                    Text(annual ? "Anual" : "Mensal").font(.body.bold())
                    if annual { Text("\(item.storeProduct.localizedPriceString) cobrados por ano").font(.caption).foregroundColor(.secondary) }
                }
                Spacer(minLength: 4)
                VStack(alignment: .trailing, spacing: 4) {
                    Text(annual ? monthlyEquivalent(item) : item.storeProduct.localizedPriceString).font(.title3.bold())
                    Text(annual ? "equivalente por mês" : "por mês").font(.caption).foregroundColor(.secondary)
                }
            }.padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 17))
                .overlay(RoundedRectangle(cornerRadius: 17).stroke(selected == item.identifier ? Color.fitBlue : Color.white.opacity(0.12), lineWidth: 1))
        }.buttonStyle(.plain).disabled(store.purchasing)
    }
    func monthlyEquivalent(_ item: RCFusePackage) -> String {
        let formatter = NumberFormatter(); formatter.numberStyle = .currency
        formatter.locale = Locale(identifier: "pt_BR")
        formatter.currencyCode = item.storeProduct.currencyCode
        return formatter.string(from: NSNumber(value: item.storeProduct.price / 12)) ?? "—"
    }
    func annualDiscount(_ annual: RCFusePackage) -> Int? {
        guard let monthly = store.packages.first(where: { $0.packageType == .monthly }),
              monthly.storeProduct.currencyCode == annual.storeProduct.currencyCode, monthly.storeProduct.price > 0 else { return nil }
        let value = (1 - annual.storeProduct.price / (monthly.storeProduct.price * 12)) * 100
        let percent = Int(value)
        return percent > 0 ? percent : nil
    }
}

struct NativeLegalLinks: View {
    var body: some View {
        HStack(spacing: 20) {
            Link("Termos de Uso", destination: URL(string: "https://diet-tracker-6i67.onrender.com/terms.html")!)
            Link("Privacidade", destination: URL(string: "https://diet-tracker-6i67.onrender.com/privacy.html")!)
        }.font(.caption).frame(maxWidth: .infinity)
    }
}

struct NativeFreeAccessCard: View {
    @Environment(NativeSession.self) var session
    var body: some View {
        if let access = session.freeAccess, !access.premium {
            VStack(alignment: .leading, spacing: 10) {
                Text("Seu acesso gratuito").font(.subheadline.bold())
                HStack { Text("Treino com IA"); Spacer(); Text("\(access.remainingPlans(for: .workout)) restante") }
                HStack { Text("Dieta com IA"); Spacer(); Text("\(access.remainingPlans(for: .diet)) restante") }
                HStack { Text("Fotos ou descrições"); Spacer(); Text("\(access.photos.remaining) de \(access.photos.limit) restantes") }
                Text("Limites únicos por conta. Registro manual de calorias e macros disponível.").font(.caption2).foregroundColor(.secondary)
                Text("Criação e edição manual de planos, aplicação e execução de treinos disponíveis gratuitamente.").font(.caption2).foregroundColor(.secondary)
            }.font(.caption).padding(16).background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 16))
        }
    }
}
