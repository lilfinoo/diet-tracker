import Foundation

public struct SessionResponse: Decodable, Sendable {
    public let loggedIn: Bool
    public let user: SessionUser?
    public let csrfToken: String?

    public init(loggedIn: Bool, user: SessionUser?, csrfToken: String?) {
        self.loggedIn = loggedIn
        self.user = user
        self.csrfToken = csrfToken
    }
}

public struct SessionUser: Decodable, Sendable, Identifiable {
    public let id: UUID
    public let username: String
    public let name: String
    public let email: String?
    public let isBanned: Bool
    public let bannedAt: String?
    public let createdAt: String?
    public let isAdmin: Bool
    public let isPremium: Bool
    public let planCode: String
    public let aiTrialUses: Int
    public let hasPassword: Bool
    public let isPublic: Bool
    public let avatarUrl: String?
    public let onboardingStatus: String
    public let profileMissingFields: [String]
    public let profileComplete: Bool

    /// A newer usage response overrides the entitlement cached at sign-in.
    public func hasPremium(currentUsage: FreeAccessStatus?) -> Bool {
        currentUsage?.premium ?? isPremium
    }
}

public struct ProfileResponse: Decodable, Sendable {
    public let profile: UserProfile?
    public let onboardingStatus: String
    public let profileMissingFields: [String]
    public let profileComplete: Bool
}

public struct UserProfile: Decodable, Sendable, Identifiable {
    public let id: Int
    public let userId: UUID
    public let age: Int?
    public let gender: String?
    public let goal: String?
    public let activityLevel: String?
    public let dietaryRestrictions: String?
    public let weight: Double?
    public let height: Double?
    public let timezone: String?
    public let isPublic: Bool
    public let avatarUrl: String?
    public let acceptsExternalWorkoutReviews: Bool
    public let acceptsExternalDietReviews: Bool
    public let currentDietPlanId: Int?
    public let currentWorkoutPlanId: Int?
    public let pendingWorkoutPlanId: Int?
    public let workoutScheduleEffectiveFrom: String?
    public let workoutScheduleTimezone: String?
    public let createdAt: String?
    public let updatedAt: String?
}
