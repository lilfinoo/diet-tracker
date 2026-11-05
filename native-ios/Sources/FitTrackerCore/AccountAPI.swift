import Foundation

public struct AuthConfiguration: Decodable, Sendable {
    public let appleEnabled: Bool
    public let googleClientId: String?
    public let legal: LegalVersions
}
public struct LegalVersions: Decodable, Sendable {
    public struct Document: Decodable, Sendable { public let version: String }
    public let ai: Document
}
public struct ConsentStatus: Decodable, Sendable {
    public struct Choice: Decodable, Sendable { public let accepted: Bool; public let version: String? }
    public let versions: LegalVersions
    public let ai: Choice
}
public struct SubscriptionStatus: Decodable, Sendable {
    public struct Subscription: Decodable, Sendable {
        public let provider: String
        public let status: String
        public let currentPeriodEnd: String?
    }
    public let planCode: String
    public let isPremium: Bool
    public let subscription: Subscription?
}
public struct Registration: Encodable, Sendable {
    public let username: String
    public let password: String
    public let name: String
    public let email: String?
    public let aiConsent: Bool
    public let aiConsentVersion: String
    public let referralCode: String?
    public init(username: String, password: String, name: String, email: String?, aiConsent: Bool, aiConsentVersion: String, referralCode: String? = nil) {
        self.username = username; self.password = password; self.name = name; self.email = email
        self.aiConsent = aiConsent; self.aiConsentVersion = aiConsentVersion
        let code = referralCode?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        self.referralCode = code?.isEmpty == false ? code : nil
    }
}
public struct ProfileChanges: Encodable, Sendable {
    public var age: Int?
    public var gender: String?
    public var goal: String?
    public var activityLevel: String?
    public var dietaryRestrictions: String?
    public var weight: Double?
    public var height: Double?
    public init(age: Int?, gender: String?, goal: String?, activityLevel: String?, dietaryRestrictions: String?, weight: Double?, height: Double?) {
        self.age = age; self.gender = gender; self.goal = goal; self.activityLevel = activityLevel
        self.dietaryRestrictions = dietaryRestrictions; self.weight = weight; self.height = height
    }
}
extension FitTrackerAPI {
    public func authConfiguration() async throws -> AuthConfiguration {
        try await request("auth/config", as: AuthConfiguration.self)
    }
    public func register(_ registration: Registration) async throws -> SessionResponse {
        try await beginAuthenticationChange()
        defer { endAuthenticationChange() }
        let current = try await restoreSession()
        let response = try await request("register", method: "POST", body: accountBody(registration), csrfToken: csrfToken(for: current), as: AccountLoginResponse.self)
        acceptAuthenticatedSession()
        return SessionResponse(loggedIn: true, user: response.user, csrfToken: response.csrfToken)
    }
    public func updateProfile(_ changes: ProfileChanges) async throws -> ProfileResponse {
        let token = try await accountToken()
        return try await request("profile", method: "POST", body: accountBody(changes), csrfToken: token, as: ProfileResponse.self)
    }
    public func consentStatus() async throws -> ConsentStatus { try await request("account/consents", as: ConsentStatus.self) }
    public func updateConsent(granted: Bool, version: String) async throws -> ConsentStatus {
        let token = try await accountToken()
        return try await request("account/consents", method: "PUT", body: accountBody(ConsentUpdate(aiConsent: granted, aiConsentVersion: version)), csrfToken: token, as: ConsentStatus.self)
    }
    public func subscriptionStatus() async throws -> SubscriptionStatus { try await request("subscription", as: SubscriptionStatus.self) }
    public func deleteAccount(username: String, password: String?) async throws {
        try await beginAuthenticationChange()
        defer { endAuthenticationChange() }
        let token = try await accountToken()
        _ = try await request("account", method: "DELETE", body: accountBody(AccountDeletion(username: username, password: password, confirmDelete: true)), csrfToken: token, as: AccountMessage.self)
        clearSessionCookies()
    }
    private func accountToken() async throws -> String {
        let current = try await restoreSession()
        guard current.loggedIn, let token = current.csrfToken else { throw APIError.http(status: 401, message: "Entre novamente para continuar.") }
        return token
    }
    private func accountBody<T: Encodable>(_ value: T) throws -> Data {
        let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
        return try encoder.encode(value)
    }
}
private struct ConsentUpdate: Encodable { let aiConsent: Bool; let aiConsentVersion: String }
private struct AccountDeletion: Encodable { let username: String; let password: String?; let confirmDelete: Bool }
private struct AccountMessage: Decodable { let message: String }
private struct AccountLoginResponse: Decodable { let user: SessionUser; let csrfToken: String }
