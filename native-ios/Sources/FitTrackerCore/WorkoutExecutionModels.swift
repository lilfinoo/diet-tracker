import Foundation

public struct WorkoutExecutionEnvelope: Decodable, Sendable {
    public let session: WorkoutExecutionSession?
}

public struct WorkoutExecutionSession: Codable, Sendable, Identifiable {
    public let id: Int
    public let workoutPlanId: Int
    public let workoutDayId: Int
    public let startedAt: String?
    public let completedAt: String?
    public let completedExerciseIds: [Int]
    public let draftSets: [String: [WorkoutDraftSet]]
    public let overrides: [WorkoutExerciseOverride]
}

public struct WorkoutExerciseOverride: Codable, Sendable {
    public let workoutExerciseId: Int
    public let catalogKey: String?
    public let name: String
    public let sets: Int?
    public let reps: String?
    public let weight: String?
    public let restSeconds: Int?
    public let notes: String?

    public init(workoutExerciseId: Int, catalogKey: String?, name: String, sets: Int?, reps: String?, weight: String? = nil, restSeconds: Int? = nil, notes: String? = nil) {
        self.workoutExerciseId = workoutExerciseId; self.catalogKey = catalogKey; self.name = name
        self.sets = sets; self.reps = reps; self.weight = weight; self.restSeconds = restSeconds; self.notes = notes
    }
}

public struct WorkoutDraftSet: Codable, Sendable, Equatable {
    public var loadKg: String
    public var repetitions: String
    public var isWarmup: Bool
    public var completed: Bool

    public init(loadKg: String = "", repetitions: String = "", isWarmup: Bool = false, completed: Bool = false) {
        self.loadKg = loadKg
        self.repetitions = repetitions
        self.isWarmup = isWarmup
        self.completed = completed
    }

    public func performedSet() throws -> WorkoutSetInput {
        let reps = repetitions.trimmingCharacters(in: .whitespacesAndNewlines)
        let load = loadKg.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: ",", with: ".")
        guard let numericRepetitions = Double(reps), numericRepetitions.isFinite,
              numericRepetitions.rounded(.towardZero) == numericRepetitions,
              (1...1000).contains(numericRepetitions) else {
            throw APIError.http(status: 400, message: "Informe de 1 a 1000 repetições nas séries realizadas.")
        }
        var weight: Double?
        if !load.isEmpty {
            guard let number = Double(load), number.isFinite, (0...100000).contains(number) else {
                throw APIError.http(status: 400, message: "Revise a carga das séries realizadas.")
            }
            weight = number
        }
        return WorkoutSetInput(repetitions: Int(numericRepetitions), loadKg: weight, isWarmup: isWarmup)
    }
}

public struct WorkoutSetInput: Codable, Sendable {
    public let repetitions: Int
    public let loadKg: Double?
    public let isWarmup: Bool
}

public struct WorkoutFinishResponse: Decodable, Sendable {
    public let session: WorkoutExecutionSession
    public let summary: WorkoutActivitySummary
}

/// Matches the web player: only filled rows become performed sets; blank rows
/// are not fabricated from the prescription, and warmups retain their identity.
public func workoutPerformedSets(_ rows: [WorkoutDraftSet]) throws -> [WorkoutSetInput] {
    try rows.filter { !$0.loadKg.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        || !$0.repetitions.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }.map { try $0.performedSet() }
}

/// Repeat only after an explicit user action. Existing entries and warmups are preserved.
public func workoutRepeatingSet(_ rows: [WorkoutDraftSet], at index: Int) throws -> [WorkoutDraftSet] {
    guard rows.indices.contains(index) else { throw APIError.invalidResponse }
    let source = rows[index]
    _ = try source.performedSet()
    guard !source.isWarmup else { return rows }
    return rows.enumerated().map { offset, row in
        guard offset > index, row.loadKg.isEmpty, row.repetitions.isEmpty, !row.isWarmup else { return row }
        return WorkoutDraftSet(loadKg: source.loadKg, repetitions: source.repetitions, completed: true)
    }
}

public struct WorkoutPendingCompletion: Codable, Sendable {
    public let exerciseId: Int
    public let sets: [WorkoutSetInput]
    public let key: String

    public init(exerciseId: Int, sets: [WorkoutSetInput], key: String = UUID().uuidString) {
        self.exerciseId = exerciseId; self.sets = sets; self.key = key
    }
}

public struct WorkoutPendingOperation: Codable, Sendable {
    public enum Kind: String, Codable, Sendable { case complete, reopen, replace, finish }
    public let kind: Kind
    public let exerciseId: Int?
    public let sets: [WorkoutSetInput]?
    public let completionMode: String?
    public let catalogKey: String?
    public let replacementName: String?
    public let replacementSets: Int?
    public let replacementReps: String?
    public let durationSeconds: Int?
    public let finishedAt: String?
    public let key: String

    public init(kind: Kind, exerciseId: Int? = nil, sets: [WorkoutSetInput]? = nil,
                completionMode: String? = nil, catalogKey: String? = nil,
                replacementName: String? = nil, replacementSets: Int? = nil,
                replacementReps: String? = nil, durationSeconds: Int? = nil,
                finishedAt: String? = nil, key: String = UUID().uuidString) {
        self.kind = kind; self.exerciseId = exerciseId; self.sets = sets
        self.completionMode = completionMode; self.catalogKey = catalogKey
        self.replacementName = replacementName; self.replacementSets = replacementSets
        self.replacementReps = replacementReps; self.key = key
        self.durationSeconds = durationSeconds; self.finishedAt = finishedAt
    }
}

public struct WorkoutLocalDraft: Codable, Sendable {
    public var sets: [String: [WorkoutDraftSet]] = [:]
    public var activeExerciseId: Int?
    public var pendingCompletion: WorkoutPendingCompletion?
    public var queuedCompletions: [WorkoutPendingCompletion]?
    public var pendingFinishKey: String?
    public var operations: [WorkoutPendingOperation]?
    public var planId: Int?
    public var dayId: Int?
    public var cachedSession: WorkoutExecutionSession?
    public var completedSets: [String: [WorkoutSetInput]]?
    public var startedAt: Date?
    public var finishedAt: Date?
    public var confirmedDurationSeconds: Int?
    public var restUntil: Date?
    public init() { }

    public var completionQueue: [WorkoutPendingCompletion] {
        get { (pendingCompletion.map { [$0] } ?? []) + (queuedCompletions ?? []) }
        set {
            pendingCompletion = newValue.first
            queuedCompletions = Array(newValue.dropFirst())
        }
    }
    public var pendingReopenExerciseIds: [Int]?

    /// Legacy drafts had two separate queues. Their previous processing order was
    /// completions, then reopens, then finish; preserve that order on first write.
    public var operationQueue: [WorkoutPendingOperation] {
        get {
            if let operations { return operations }
            return completionQueue.map {
                WorkoutPendingOperation(kind: .complete, exerciseId: $0.exerciseId,
                                        sets: $0.sets, completionMode: $0.sets.isEmpty ? "planned" : nil, key: $0.key)
            } + (pendingReopenExerciseIds ?? []).map {
                WorkoutPendingOperation(kind: .reopen, exerciseId: $0)
            } + (pendingFinishKey.map { [WorkoutPendingOperation(kind: .finish, key: $0)] } ?? [])
        }
        set {
            operations = newValue
            pendingCompletion = nil; queuedCompletions = nil
            pendingReopenExerciseIds = nil; pendingFinishKey = nil
        }
    }

    public func completedIds(onServer serverIds: [Int]) -> Set<Int> {
        var ids = Set(serverIds)
        for operation in operationQueue {
            guard let id = operation.exerciseId else { continue }
            switch operation.kind {
            case .complete: ids.insert(id)
            case .reopen: ids.remove(id)
            case .replace, .finish: break
            }
        }
        return ids
    }
}

public struct WorkoutReplacementOption: Decodable, Sendable, Identifiable {
    public var id: String { catalogKey }
    public let catalogKey: String
    public let name: String
    public let sets: Int?
    public let reps: String?
}

public struct WorkoutReplacementOptions: Decodable, Sendable {
    public let options: [WorkoutReplacementOption]
    public let message: String?
}
