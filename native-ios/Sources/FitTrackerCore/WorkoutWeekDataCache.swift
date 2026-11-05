import Foundation

/// Account-scoped week data; explicit refreshes invalidate plans and completion status together.
@MainActor
public final class WorkoutWeekDataCache {
    public private(set) var generation = 0
    public private(set) var activities: WorkoutActivityPage?
    private var plan: NativePlan?
    private var planRequest: (id: Int, task: Task<NativePlan, Error>)?
    private var activitiesRequest: Task<WorkoutActivityPage, Error>?
    private let api: FitTrackerAPI

    public init(api: FitTrackerAPI) { self.api = api }

    public func cachedPlan(id: Int) -> NativePlan? { plan?.id == id ? plan : nil }

    public func invalidate() {
        generation += 1
        plan = nil
        activities = nil
        planRequest = nil
        activitiesRequest = nil
    }

    public func loadPlan(id: Int) async throws -> NativePlan {
        if let cached = cachedPlan(id: id) { return cached }
        let revision = generation
        let request: Task<NativePlan, Error>
        if let existing = planRequest, existing.id == id { request = existing.task }
        else {
            request = Task { try await api.getPlan(kind: .workout, id: id) }
            planRequest = (id, request)
        }
        do {
            let result = try await request.value
            if generation == revision, planRequest?.id == id { plan = result; planRequest = nil }
            return result
        } catch {
            if generation == revision, planRequest?.id == id { planRequest = nil }
            throw error
        }
    }

    public func loadActivities() async throws -> WorkoutActivityPage {
        if let activities { return activities }
        let revision = generation
        let request: Task<WorkoutActivityPage, Error>
        if let existing = activitiesRequest { request = existing }
        else {
            request = Task { try await api.getWorkoutActivities() }
            activitiesRequest = request
        }
        do {
            let result = try await request.value
            if generation == revision { activities = result; activitiesRequest = nil }
            return result
        } catch {
            if generation == revision { activitiesRequest = nil }
            throw error
        }
    }
}
