import Foundation

public enum NativePlanKind: String, Sendable, CaseIterable {
    case diet, workout
    public var path: String { self == .diet ? "diet_plans" : "workout_plans" }
    public var title: String { self == .diet ? "Planos alimentares" : "Planos de treino" }
}

public struct NativePlan: Decodable, Sendable, Identifiable {
    public let id: Int
    public let title: String
    public let description: String?
    public let isCurrent: Bool?
    public let meals: [DietMealAlternative]?
    public let days: [PlanWorkoutDay]?
    public let daysCount: Int?
    public let mealsCount: Int?
    public let source: String?
}

public struct PlanWorkoutDay: Decodable, Sendable, Identifiable {
    public let id: Int
    public let title: String
    public let exercises: [PlanWorkoutExercise]
}

public struct PlanWorkoutExercise: Decodable, Sendable, Identifiable {
    public let id: Int
    public let catalogKey: String?
    public let name: String
    public let sets: Int?
    public let reps: String?
    public let weight: String?
    public let restSeconds: Int?
}

public struct DietPlanPreferences: Codable, Equatable, Sendable {
    public var goal = "maintenance"
    public var mealsPerDay = 3
    public var dietPattern = "omnivore"
    public var trainingDaysPerWeek = 3
    public var changePace = "conservative"
    public var allergies: [String] = []
    public var intolerances: [String] = []
    public var dislikedFoods: [String] = []
    public var preferredFoods: [String] = []
    public var availableIngredients: [String] = []
    public var budget = "moderate"
    public var prepMinutes = 30
    public var notes = ""
    public init() { }
}

public struct WorkoutPlanPreferences: Codable, Equatable, Sendable {
    public var goal = "hypertrophy"
    public var experienceLevel = "beginner"
    public var daysPerWeek = 3
    public var sessionDuration = 45
    public var equipment = ["full_gym"]
    public var limitations = ""
    public var priorities = ""
    public var avoidExercises = ""
    // Omitting split_type asks the server for its recommended split.
    public init() { }
}

public enum PlanGenerationResponse: Decodable, Sendable {
    case plan(NativePlan)
    case queued(UUID)
    private enum CodingKeys: String, CodingKey { case plan, jobId }
    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        if let id = try values.decodeIfPresent(UUID.self, forKey: .jobId) { self = .queued(id) }
        else { self = .plan(try values.decode(NativePlan.self, forKey: .plan)) }
    }
}

public struct PlanGenerationTask: Decodable, Sendable {
    public let status: String
    public let error: String?
    public let plan: NativePlan?
    private enum CodingKeys: String, CodingKey { case status, error, result }
    private struct Result: Decodable { let plan: NativePlan }
    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        status = try values.decode(String.self, forKey: .status)
        error = try values.decodeIfPresent(String.self, forKey: .error)
        plan = status == "succeeded" ? try values.decode(Result.self, forKey: .result).plan : nil
    }
}

public struct PlanActivationResponse: Decodable, Sendable {
    public let message: String
    public let effectiveFrom: String?
}

public struct PlanCatalogItem: Decodable, Sendable, Identifiable {
    public var id: String { key }
    public let key: String
    public let name: String
    public let group: String?
    public let equipment: String?
}
public struct PlanExerciseChange: Codable, Sendable, Identifiable {
    public var id: Int { exerciseId }
    public let exerciseId: Int
    public let catalogKey: String
    public let name: String
    public let sets: Int
    public let reps: String
    public let weight: String?
    public let restSeconds: Int
}
public struct PlanChangesProposal: Decodable, Sendable { public let changes: [PlanExerciseChange]; public let revision: String; public let plan: NativePlan }

public struct ManualPlanExercise: Encodable, Identifiable, Sendable {
    public let id = UUID()
    public var catalogKey: String? = nil
    public var name = ""
    public var sets = 3
    public var reps = "10"
    public var weight = ""
    public var restSeconds = 60
    public init() {}
    enum CodingKeys: String, CodingKey { case catalogKey, name, sets, reps, weight, restSeconds }
}
public struct ManualPlanDay: Encodable, Identifiable, Sendable {
    public let id = UUID()
    public var title = "Treino A"
    public var exercises = [ManualPlanExercise()]
    public init() {}
    enum CodingKeys: String, CodingKey { case title, exercises }
}
public struct ManualPlanMeal: Encodable, Identifiable, Sendable {
    public let id = UUID()
    public var dayOfWeek = "Dia 1"
    public var mealType = "Almoço"
    public var description = ""
    public var calories: Double? = nil
    public var protein: Double? = nil
    public var carbs: Double? = nil
    public var fat: Double? = nil
    public init() {}
    enum CodingKeys: String, CodingKey { case dayOfWeek, mealType, description, calories, protein, carbs, fat }
}
