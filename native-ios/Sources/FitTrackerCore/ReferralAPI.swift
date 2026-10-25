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

extension FitTrackerAPI {
    public func referralStatus() async throws -> ReferralStatus {
        try await request("referrals", as: ReferralStatus.self)
    }
}
