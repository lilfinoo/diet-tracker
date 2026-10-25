import Foundation

/// Recovery choices deliberately separate checking an existing purchase from buying again.
public enum BillingRecovery: String, Codable, Equatable, Sendable {
    case plansUnavailable
    case cancelled
    case purchaseFailed
    case purchaseNotAllowed
    case purchaseUnverified
    case activationPending
    case paymentPending
    case noActivePurchase
    case restoreFailed
    case accountConflict

    public enum Action: Equatable, Sendable { case reloadPlans, retryPurchase, verifyPurchase, restorePurchases }

    public var blocksNewPurchase: Bool {
        switch self {
        case .purchaseUnverified, .activationPending, .paymentPending, .accountConflict: return true
        default: return false
        }
    }

    public var action: Action? {
        switch self {
        case .plansUnavailable: return .reloadPlans
        case .purchaseFailed: return .retryPurchase
        case .purchaseUnverified, .activationPending, .paymentPending: return .verifyPurchase
        case .restoreFailed: return .restorePurchases
        case .cancelled, .purchaseNotAllowed, .noActivePurchase, .accountConflict: return nil
        }
    }

    public static func afterVerification(premiumActive: Bool, storePurchaseActive: Bool, previous: BillingRecovery?) -> BillingRecovery? {
        if premiumActive { return nil }
        if storePurchaseActive { return .activationPending }
        if previous == .activationPending || previous == .paymentPending { return previous }
        return .noActivePurchase
    }

    public var title: String {
        switch self {
        case .plansUnavailable: return "Os planos ainda não carregaram"
        case .cancelled: return "Tudo bem, você pode decidir depois"
        case .purchaseFailed: return "Sua compra não foi concluída"
        case .purchaseNotAllowed: return "A Apple não autorizou esta compra"
        case .purchaseUnverified: return "Vamos conferir sua compra?"
        case .activationPending: return "Falta confirmar seu acesso"
        case .paymentPending: return "Sua compra está aguardando aprovação"
        case .noActivePurchase: return "Nenhuma assinatura ativa encontrada"
        case .restoreFailed: return "Não conseguimos restaurar agora"
        case .accountConflict: return "Vamos encontrar a conta da sua compra"
        }
    }

    public var message: String {
        switch self {
        case .plansUnavailable: return "Não foi possível consultar os planos agora. Tente novamente ou continue usando o gratuito."
        case .cancelled: return "Sua escolha de plano continua aqui. Você pode seguir no gratuito e voltar quando quiser."
        case .purchaseFailed: return "Confira a forma de pagamento da sua conta Apple antes de tentar novamente. Sua escolha de plano foi mantida."
        case .purchaseNotAllowed: return "Confira as permissões de compra e a forma de pagamento da sua conta Apple. Seu acesso gratuito continua disponível."
        case .purchaseUnverified: return "A conexão interrompeu a confirmação. Verifique o status antes de tentar comprar novamente."
        case .activationPending: return "A compra foi recebida, mas o Premium ainda não foi confirmado nesta conta. Verifique o acesso, sem fazer outra compra."
        case .paymentPending: return "Conclua a aprovação pela Apple. Depois, confira o acesso aqui. Você pode continuar no gratuito enquanto espera."
        case .noActivePurchase: return "Confira se você usa a mesma conta Apple da assinatura. Se ainda não assinou, pode escolher um plano ou continuar no gratuito."
        case .restoreFailed: return "Confira sua conexão e tente restaurar novamente. Restaurar uma compra não inicia uma nova assinatura."
        case .accountConflict: return "Esta compra está vinculada a outra conta. Entre na conta Fit Tracker usada na assinatura ou procure o suporte antes de tentar outra compra."
        }
    }

    public var actionTitle: String? {
        switch action {
        case .reloadPlans: return "Carregar planos novamente"
        case .retryPurchase: return "Tentar este plano novamente"
        case .verifyPurchase: return "Verificar meu acesso"
        case .restorePurchases: return "Tentar restaurar novamente"
        case nil: return nil
        }
    }
}
