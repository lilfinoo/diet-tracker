import Foundation

public struct ReferralStatus: Decodable, Sendable {
    public let code: String
    public let qualifiedInvites: Int
    public let rewardedThisMonth: Bool
    public let period: String
    public let periodEndsAt: String
    public let target: Int
    public let progress: Int
    public let premiumUntil: String?
}

public struct ReferralAttribution: Decodable, Sendable {
    public let kind: String
    public let publicName: String
    public let code: String
    public let createdAt: String
}

public struct ReferralAttributionStatus: Decodable, Sendable {
    public let attribution: ReferralAttribution?
    public let canApplyAffiliate: Bool
}

public struct ReferralApplication: Decodable, Sendable {
    public let kind: String
    public let message: String
    public let publicName: String
    public let code: String
}

extension FitTrackerAPI {
    public func referralAttribution() async throws -> ReferralAttributionStatus {
        try await request("referrals/attribution", as: ReferralAttributionStatus.self)
    }

    public func applyReferralCode(_ code: String, ownerId: UUID) async throws -> ReferralApplication {
        let current = try await restoreSession()
        guard current.loggedIn, current.user?.id == ownerId else {
            throw APIError.http(status: 401, message: "Entre novamente na mesma conta para aplicar o código.")
        }
        let normalized = code.components(separatedBy: .whitespacesAndNewlines).joined().uppercased()
        let body = try JSONSerialization.data(withJSONObject: ["code": normalized])
        return try await request("referrals/apply", method: "POST", body: body,
                                 csrfToken: csrfToken(for: current), as: ReferralApplication.self)
    }

    public func referralStatus() async throws -> ReferralStatus {
        try await request("referrals", as: ReferralStatus.self)
    }
}
