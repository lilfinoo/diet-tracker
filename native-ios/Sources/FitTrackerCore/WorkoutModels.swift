import Foundation

public struct WorkoutToday: Decodable, Sendable {
    public let state: String
    public let timezone: String
    public let localDate: String
    public let currentPlanId: Int?
    public let currentPlan: WorkoutPlanSummary?
    public let currentDay: WorkoutDay?
    public let nextDay: WorkoutDay?
    public let session: WorkoutSessionSummary?
    public let completedSession: WorkoutSessionSummary?
    public let week: [WorkoutWeekday]
}

public struct WorkoutPlanSummary: Decodable, Sendable, Identifiable {
    public let id: Int
    public let title: String
    public let description: String?
    public let sessionDuration: Int?
}

public struct WorkoutDay: Decodable, Sendable, Identifiable {
    public let id: Int
    public let title: String
    public let focus: String?
    public let exercises: [WorkoutExercise]

    public init(id: Int, title: String, focus: String? = nil, exercises: [WorkoutExercise]) {
        self.id = id; self.title = title; self.focus = focus; self.exercises = exercises
    }
}

public struct WorkoutExercise: Decodable, Sendable, Identifiable {
    public let id: Int
    public let catalogKey: String?
    public let name: String
    public let sets: Int?
    public let reps: String?
    public let weight: String?
    public let restSeconds: Int?
    public let notes: String?

    public init(id: Int, catalogKey: String? = nil, name: String, sets: Int? = nil, reps: String? = nil, weight: String? = nil, restSeconds: Int? = nil, notes: String? = nil) {
        self.id = id; self.catalogKey = catalogKey; self.name = name; self.sets = sets; self.reps = reps; self.weight = weight; self.restSeconds = restSeconds; self.notes = notes
    }
}

public struct WorkoutWeekday: Decodable, Sendable, Identifiable {
    public var id: Int { weekday }
    public let weekday: Int
    public let label: String
    public let dayId: Int?
    public let dayTitle: String?
    public let active: Bool
}

public struct WorkoutSessionSummary: Decodable, Sendable, Identifiable {
    public let id: Int
    public let completedExerciseIds: [Int]
}

public struct WorkoutActivityPage: Decodable, Sendable {
    public let items: [WorkoutActivity]
    public let limit: Int
    public let offset: Int
    public let hasMore: Bool
}

public struct WorkoutActivity: Decodable, Sendable, Identifiable {
    public let id: Int
    public let workoutName: String
    public let planName: String
    public let startedAt: String
    public let completedAt: String?
    public let durationSeconds: Int
    public let exercisesPerformed: Int
    public let totalExercises: Int
    public let setsPerformed: Int
    public let volumeTotalKg: Double?
}

public struct WorkoutActivityDetail: Decodable, Sendable {
    public let activity: WorkoutActivitySummary
}

public struct WorkoutActivitySummary: Decodable, Sendable, Identifiable {
    public let id: Int
    public let workoutName: String
    public let planName: String
    public let durationSeconds: Int
    public let exercisesPerformed: Int
    public let totalExercises: Int
    public let setsPerformed: Int
    public let volumeTotalKg: Double?
    public let exercises: [WorkoutPerformedExercise]
    public let energyEstimate: WorkoutEnergyEstimate?

    public init(id: Int, workoutName: String, planName: String, durationSeconds: Int, exercisesPerformed: Int, totalExercises: Int, setsPerformed: Int, volumeTotalKg: Double?, exercises: [WorkoutPerformedExercise], energyEstimate: WorkoutEnergyEstimate? = nil) {
        self.id = id; self.workoutName = workoutName; self.planName = planName
        self.durationSeconds = durationSeconds; self.exercisesPerformed = exercisesPerformed
        self.totalExercises = totalExercises; self.setsPerformed = setsPerformed
        self.volumeTotalKg = volumeTotalKg; self.exercises = exercises
        self.energyEstimate = energyEstimate
    }
}

public struct WorkoutEnergyEstimate: Decodable, Sendable {
    public let activeKcal: Double?
    public let totalKcal: Double?
    public let weightKg: Double?
    public let durationSeconds: Int?
    public let met: Double?
    public let method: String?
    public let reason: String?
}

public struct WorkoutPerformedExercise: Decodable, Sendable, Identifiable {
    public var id: Int { exerciseId }
    public let exerciseId: Int
    public let name: String
    public let sets: [WorkoutPerformedSet]
    public let completionMode: String?
    public let plannedPrescription: WorkoutPlannedPrescription?
    public let setsPlanned: Int?

    public init(exerciseId: Int, name: String, sets: [WorkoutPerformedSet], completionMode: String? = nil, plannedPrescription: WorkoutPlannedPrescription? = nil, setsPlanned: Int? = nil) {
        self.exerciseId = exerciseId; self.name = name; self.sets = sets
        self.completionMode = completionMode; self.plannedPrescription = plannedPrescription
        self.setsPlanned = setsPlanned
    }
}

public struct WorkoutPlannedPrescription: Decodable, Sendable {
    public let sets: Int?
    public let reps: String?
    public let restSeconds: Int?

    public init(sets: Int?, reps: String?, restSeconds: Int? = nil) {
        self.sets = sets; self.reps = reps; self.restSeconds = restSeconds
    }
}

public struct WorkoutPerformedSet: Decodable, Sendable, Identifiable {
    public var id: Int { setOrder }
    public let setOrder: Int
    public let repetitions: Int
    public let loadKg: Double?
    public let isWarmup: Bool

    public init(setOrder: Int, repetitions: Int, loadKg: Double?, isWarmup: Bool) {
        self.setOrder = setOrder; self.repetitions = repetitions
        self.loadKg = loadKg; self.isWarmup = isWarmup
    }
}
