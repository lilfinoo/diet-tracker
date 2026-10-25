import Foundation

/// Choices are separate from the pending generation job: reopening a form never
/// creates another request or loses restrictions entered before generation.
public struct PlanSetupDraft: Codable, Equatable, Sendable {
    public var step = 0
    public var diet = DietPlanPreferences()
    public var workout = WorkoutPlanPreferences()
    public var allergies = ""
    public var intolerances = ""
    public var disliked = ""
    public var preferred = ""
    public var routine = ""
    public var prepStyle = "mixed"
    public var equipment = "full_gym"
    public var requestKey = UUID().uuidString
    public init() {}
}

public struct PlanSetupDraftStore {
    private let defaults: UserDefaults
    public init(defaults: UserDefaults = .standard) { self.defaults = defaults }

    public func load(owner: UUID, kind: NativePlanKind) throws -> PlanSetupDraft? {
        guard let data = defaults.data(forKey: key(owner, kind)) else { return nil }
        return try JSONDecoder().decode(PlanSetupDraft.self, from: data)
    }

    public func save(_ draft: PlanSetupDraft, owner: UUID, kind: NativePlanKind) throws {
        defaults.set(try JSONEncoder().encode(draft), forKey: key(owner, kind))
    }

    public func clear(owner: UUID, kind: NativePlanKind) {
        defaults.removeObject(forKey: key(owner, kind))
    }

    private func key(_ owner: UUID, _ kind: NativePlanKind) -> String {
        "fitTracker.planSetup.\(owner.uuidString).\(kind.rawValue)"
    }
}
