import Foundation

public struct PaywallExperiment: Decodable, Sendable, Equatable {
    public let experimentId: String
    public let variant: String
}

public struct PaywallMessage: Sendable, Equatable {
    public let title: String
    public let detail: String
    public let benefits: [String]

    public static let workoutUnlock = PaywallMessage(title: "Seu treino está pronto para começar.",
        detail: "Desbloqueie o Premium para aplicar seu plano e iniciar seus treinos.",
        benefits: ["Aplique seu plano e acompanhe cada treino", "Registre séries e acompanhe sua evolução", "Personalize planos com IA"])

    public static func forSurface(_ surface: String, variant: String?) -> PaywallMessage {
        let benefits = ["Mais gerações de treino e dieta", "Mais análises de refeições por foto", "Ajustes de planos com IA"]
        guard variant == "B" else {
            return PaywallMessage(title: "Mais foco na sua evolução.", detail: "Treino e alimentação personalizados para acompanhar sua rotina.", benefits: benefits)
        }
        switch surface {
        case "photos":
            return PaywallMessage(title: "Continue registrando suas refeições por foto.", detail: "Use foto ou descrição para facilitar seus registros com o Premium.", benefits: ["Mais análises de refeições por foto", "Registro de refeições por descrição", "Mais gerações de treino e dieta"])
        case "diet_plans":
            return PaywallMessage(title: "Uma dieta que acompanha suas preferências.", detail: "Escolha os alimentos que gosta e prefere evitar ao gerar sua dieta com o Premium.", benefits: ["Alimentos que você gosta", "Alimentos que você prefere evitar", "Mais gerações de dieta"])
        case "workout_plans":
            return PaywallMessage(title: "Dê prioridade aos seus objetivos.", detail: "Escolha os músculos em foco e peça ajustes no treino com o Premium.", benefits: ["Prioridade para os músculos que você escolher", "Ajustes do treino por texto com IA", "Mais gerações de treino"])
        case "chat":
            return PaywallMessage(title: "Continue sua conversa com a IA.", detail: "Tenha mais acesso ao assistente para acompanhar sua rotina de treino e alimentação.", benefits: ["Mais acesso ao assistente de IA", "Mais gerações de treino e dieta", "Ajustes de planos com IA"])
        case "premium", "app_open":
            return PaywallMessage(title: "Facilite sua rotina com o Premium.", detail: "Mais personalização para seus planos e praticidade para registrar suas refeições.", benefits: benefits)
        default:
            return PaywallMessage(title: "Personalize sua evolução com o Premium.", detail: "Conheça os recursos para adaptar treino e alimentação à sua rotina.", benefits: benefits)
        }
    }
}

extension FitTrackerAPI {
    public func paywallExperiment(surface: String) async throws -> PaywallExperiment? {
        let token = try await paywallToken()
        let body = try JSONSerialization.data(withJSONObject: ["surface": surface, "platform": "ios"])
        return try await request("analytics/paywall", method: "POST", body: body, csrfToken: token, as: PaywallExperimentResponse.self).experiment
    }

    public func trackPaywallView(surface: String) async throws {
        try await trackPaywallEvent("paywall_viewed", properties: ["surface": surface])
    }

    public func trackPaywallPurchase(planCode: String) async throws {
        try await trackPaywallEvent("paywall_cta_clicked", properties: ["plan_code": planCode, "platform": "ios"])
    }

    private func trackPaywallEvent(_ name: String, properties: [String: String]) async throws {
        let token = try await paywallToken()
        let body = try JSONSerialization.data(withJSONObject: ["events": [["name": name, "anonymous_id": UUID().uuidString, "properties": properties]]])
        _ = try await request("analytics/events", method: "POST", body: body, csrfToken: token, as: PaywallEventsResponse.self)
    }

    private func paywallToken() async throws -> String {
        let current = try await restoreSession()
        guard current.loggedIn, let token = try csrfToken(for: current) else {
            throw APIError.http(status: 401, message: "Entre novamente para continuar.")
        }
        return token
    }
}

private struct PaywallExperimentResponse: Decodable { let experiment: PaywallExperiment? }
private struct PaywallEventsResponse: Decodable { let accepted: Int }
