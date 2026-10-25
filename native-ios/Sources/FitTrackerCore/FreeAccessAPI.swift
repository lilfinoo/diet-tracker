import Foundation

public struct FreeAccessStatus: Decodable, Sendable {
    public struct Quota: Decodable, Sendable {
        public let limit: Int
        public let used: Int
        public let remaining: Int
    }
    public let premium: Bool
    public let policy: String
    public let plans: Quota
    public let workoutPlans: Quota?
    public let dietPlans: Quota?
    public func remainingPlans(for kind: NativePlanKind) -> Int {
        (kind == .workout ? workoutPlans : dietPlans)?.remaining ?? plans.remaining
    }
    public let photos: Quota
    public let manualLogging: Bool
}

extension FitTrackerAPI {
    public func freeAccessStatus() async throws -> FreeAccessStatus {
        try await request("ai/usage", as: FreeAccessStatus.self)
    }
}
