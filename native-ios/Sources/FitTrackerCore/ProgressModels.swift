import Foundation

public struct ProgressOverview: Decodable, Sendable {
    public let body: BodyProgressSummary
    public let weekly: WeeklyProgressSummary
    public let consistency: ConsistencySummary
}

public struct BodyProgressSummary: Decodable, Sendable {
    public let latestDate: String?
    public let metrics: [String: BodyMetricSummary]
}

public struct BodyMetricSummary: Decodable, Sendable {
    public let latest: BodyMetricPoint?
    public let previous: BodyMetricPoint?
    public let change: Double?
}

public struct BodyMetricPoint: Decodable, Sendable {
    public let date: String
    public let value: Double

    public init(date: String, value: Double) { self.date = date; self.value = value }
}

public struct BodyMetricSeries: Decodable, Sendable {
    public let points: [BodyMetricPoint]
    public let latestDate: String?
}

public enum BodyMetric: String, CaseIterable, Sendable {
    case weight, bodyFat = "body_fat", waist, chest, arm, thigh, muscleMass = "muscle_mass"
}

public struct WeeklyProgressSummary: Decodable, Sendable {
    public let timezone: String
    public let current: WeeklyProgressCurrent
}

public struct WeeklyProgressCurrent: Decodable, Sendable {
    public let weekStart: String
    public let weekEnd: String
    public let completed: Int
    public let target: Int?
    public let fulfilled: Bool
    public let streak: Int
}

public struct ConsistencySummary: Decodable, Sendable {
    public let startDate: String
    public let endDate: String
    public let days: [ConsistencyDay]
}

public struct ConsistencyDay: Decodable, Sendable, Identifiable {
    public var id: String { date }
    public let date: String
    public let workout: Bool
    public let dietTracked: Bool
}

public struct ProgressAchievements: Decodable, Sendable {
    public let items: [ProgressAchievement]
}

public struct ProgressAchievement: Decodable, Sendable, Identifiable {
    public var id: String { code }
    public let code: String
    public let title: String
    public let description: String
    public let hidden: Bool
    public let progress: AchievementProgress?
    public let unlocked: AchievementUnlockSummary?
}

public struct AchievementProgress: Decodable, Sendable {
    public let current: Int
    public let target: Int
    public let percentage: Int
}

public struct AchievementUnlockSummary: Decodable, Sendable {
    public let unlockedAt: String?
}

public struct ExerciseProgressOptions: Decodable, Sendable {
    public let items: [ExerciseProgressOption]
}

public struct ExerciseProgressOption: Decodable, Sendable, Identifiable, Hashable {
    public var id: String { key }
    public let key: String
    public let name: String
}

public struct ExerciseProgressHistory: Decodable, Sendable {
    public let exerciseKey: String
    public let exerciseName: String
    public let maxLoadKg: Double?
    public let sessions: ExerciseProgressPage
}

public struct ExerciseProgressPage: Decodable, Sendable {
    public let items: [ExerciseProgressSession]
    public let hasMore: Bool
    public let offset: Int
    public let limit: Int
}

public struct ExerciseProgressSession: Decodable, Sendable, Identifiable {
    public var id: Int { sessionId }
    public let sessionId: Int
    public let completedAt: String
    public let localDate: String?
    public let sets: [ExerciseProgressSet]

    /// Match the site's work-set metric; unknown and warmup loads are not zero.
    public var bestWorkingLoad: Double? {
        sets.filter { !$0.isWarmup && $0.repetitions > 0 }
            .compactMap(\.loadKg).filter { $0 > 0 && $0.isFinite }.max()
    }
}

public struct ExerciseProgressSet: Decodable, Sendable {
    public let repetitions: Int
    public let loadKg: Double?
    public let isWarmup: Bool
}

public struct ProgressDayActivities: Decodable, Sendable {
    public let date: String?
    public let items: [WorkoutActivity]
    public let offset: Int
    public let hasMore: Bool
}

public struct PersonalRecordPage: Decodable, Sendable {
    public let items: [PersonalRecord]
    public let offset: Int
    public let limit: Int
}

public struct PersonalRecord: Decodable, Sendable, Identifiable {
    public let id: Int
    public let workoutSessionId: Int?
    public let exerciseName: String
    public let metricType: String
    public let newValue: Double
    public let loadKg: Double?
    public let repetitions: Int?
    public let achievedAt: String
}
