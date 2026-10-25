import Foundation

public enum SocialProvider: String, Sendable { case google, apple }
public struct AppleAuthChallenge: Decodable, Sendable { public let nonce: String }
private struct SocialSession: Decodable { let user: SessionUser; let csrfToken: String }
private struct SocialCredentials: Encodable {
    let credential: String?; let nonce: String?; let authorizationCode: String?; let displayName: String?
    let signupToken: String?; let name: String?; let aiConsent: Bool?; let aiConsentVersion: String?
    var username: String? = nil
    var referralCode: String? = nil
}
extension FitTrackerAPI {
    public func appleAuthChallenge() async throws -> AppleAuthChallenge {
        let current = try await restoreSession()
        return try await request("auth/apple/challenge", method: "POST", csrfToken: csrfToken(for: current), as: AppleAuthChallenge.self)
    }
    public func socialLogin(provider: SocialProvider, credential: String, nonce: String? = nil, authorizationCode: String? = nil, displayName: String? = nil) async throws -> SessionResponse {
        try await authenticateSocial(provider: provider, credentials: SocialCredentials(credential: credential, nonce: nonce, authorizationCode: authorizationCode, displayName: displayName, signupToken: nil, name: nil, aiConsent: nil, aiConsentVersion: nil))
    }
    public func completeSocialSignup(provider: SocialProvider, token: String, name: String, aiConsent: Bool, aiConsentVersion: String, referralCode: String? = nil) async throws -> SessionResponse {
        var credentials = SocialCredentials(credential: nil, nonce: nil, authorizationCode: nil, displayName: nil, signupToken: token, name: name, aiConsent: aiConsent, aiConsentVersion: aiConsentVersion)
        // The deployed API still requires a login handle; newer servers use name.
        // Keep the opaque compatibility handle separate from the person's name.
        credentials.username = "user_" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        let code = referralCode?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        credentials.referralCode = code?.isEmpty == false ? code : nil
        return try await authenticateSocial(provider: provider, credentials: credentials)
    }
    private func authenticateSocial(provider: SocialProvider, credentials: SocialCredentials) async throws -> SessionResponse {
        try await beginAuthenticationChange()
        defer { endAuthenticationChange() }
        let current = try await restoreSession()
        let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
        let result = try await request("auth/\(provider.rawValue)", method: "POST", body: encoder.encode(credentials), csrfToken: csrfToken(for: current), as: SocialSession.self)
        acceptAuthenticatedSession()
        return SessionResponse(loggedIn: true, user: result.user, csrfToken: result.csrfToken)
    }
}

public struct LinkedIdentities: Decodable, Sendable { public let providers: [String] }
extension FitTrackerAPI {
    public func linkedIdentities() async throws -> LinkedIdentities {
        try await request("account/identities", as: LinkedIdentities.self)
    }
    public func linkSocialIdentity(provider: SocialProvider, credential: String, nonce: String? = nil, authorizationCode: String? = nil, displayName: String? = nil) async throws -> LinkedIdentities {
        let current = try await restoreSession()
        guard current.loggedIn else { throw APIError.http(status: 401, message: "Entre na conta que deseja preservar antes de conectar um acesso.") }
        let body = SocialCredentials(credential: credential, nonce: nonce, authorizationCode: authorizationCode, displayName: displayName, signupToken: nil, name: nil, aiConsent: nil, aiConsentVersion: nil)
        let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
        return try await request("account/identities/\(provider.rawValue)", method: "POST", body: encoder.encode(body), csrfToken: csrfToken(for: current), as: LinkedIdentities.self)
    }
}
