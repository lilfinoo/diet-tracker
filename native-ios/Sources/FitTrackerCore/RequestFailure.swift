import Foundation

/// User-facing guidance at the screen boundary. Transport errors remain typed so
/// callers can preserve uncertain writes and never automatically repeat them.
public enum RequestFailure {
    public static func message(_ error: Error, fallback: String) -> String {
        if let network = error as? URLError {
            switch network.code {
            case .notConnectedToInternet, .networkConnectionLost, .dataNotAllowed, .internationalRoamingOff:
                return "A conexão caiu. Confira sua internet e tente novamente."
            case .timedOut:
                return "A resposta está demorando mais que o esperado. Tente novamente em instantes."
            case .cannotFindHost, .cannotConnectToHost, .dnsLookupFailed:
                return "Não conseguimos conectar agora. Confira sua internet e tente novamente em instantes."
            default: return fallback
            }
        }
        if let failure = error as? APIError {
            switch failure {
            case .http(let status, let message):
                if status == 401 { return "Sua sessão terminou. Entre novamente para continuar." }
                if status == 429 { return "Vamos dar uma pausa. Aguarde um pouco antes de tentar novamente." }
                if status >= 500 { return fallback }
                return message.isEmpty ? fallback : message
            case .csrfMismatch:
                return "Precisamos confirmar seu acesso. Entre novamente e tente mais uma vez."
            case .invalidResponse: return fallback
            case .socialSignupRequired: return "Complete seu perfil de acesso para continuar."
            }
        }
        return fallback
    }
}
