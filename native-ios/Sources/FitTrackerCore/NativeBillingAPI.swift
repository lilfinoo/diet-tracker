import Foundation

public struct NativeBillingConfiguration: Decodable, Sendable {
    public let configured: Bool
    public let publicApiKey: String?
    public let entitlementId: String
    public let productIdentifiers: [String]?
}
public struct NativeBillingSync: Decodable, Sendable {
    public let user: SessionUser
    public let isPremium: Bool
}
extension FitTrackerAPI {
    public func nativeBillingConfiguration(platform: String = "ios") async throws -> NativeBillingConfiguration {
        try await request("billing/revenuecat/config", queryItems: [URLQueryItem(name: "platform", value: platform)], as: NativeBillingConfiguration.self)
    }
    public func syncNativeSubscription() async throws -> NativeBillingSync {
        let current = try await restoreSession()
        guard current.loggedIn else { throw APIError.http(status: 401, message: "Entre novamente para continuar.") }
        return try await request("billing/revenuecat/sync", method: "POST", csrfToken: csrfToken(for: current), as: NativeBillingSync.self)
    }
}
