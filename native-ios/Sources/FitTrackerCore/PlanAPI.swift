import Foundation

extension FitTrackerAPI {
    public func getPlans(kind: NativePlanKind, limit: Int = 30, offset: Int = 0) async throws -> [NativePlan] {
        try await request(kind.path, queryItems: [URLQueryItem(name: "limit", value: String(limit)), URLQueryItem(name: "offset", value: String(offset))], as: [NativePlan].self)
    }
    public func getPlan(kind: NativePlanKind, id: Int) async throws -> NativePlan {
        try await request("\(kind.path)/\(id)", as: NativePlan.self)
    }
    public func deletePlan(kind: NativePlanKind, id: Int) async throws -> String {
        let token = try await planToken()
        return try await request("\(kind.path)/\(id)", method: "DELETE", csrfToken: token, as: PlanMessage.self).message
    }
    public func generateDietPlan(_ preferences: DietPlanPreferences, background: Bool = false, idempotencyKey: String? = nil) async throws -> PlanGenerationResponse {
        try await generatePlan(kind: .diet, preferences: preferences, background: background, idempotencyKey: idempotencyKey)
    }
    public func generateWorkoutPlan(_ preferences: WorkoutPlanPreferences, background: Bool = false, idempotencyKey: String? = nil) async throws -> PlanGenerationResponse {
        try await generatePlan(kind: .workout, preferences: preferences, background: background, idempotencyKey: idempotencyKey)
    }
    public func getPlanGenerationTask(id: UUID) async throws -> PlanGenerationTask {
        try await request("ai/tasks/\(id.uuidString)", as: PlanGenerationTask.self)
    }
    public func activatePlan(kind: NativePlanKind, id: Int, weekdays: [Int] = []) async throws -> PlanActivationResponse {
        let token = try await planToken()
        return try await request("\(kind.path)/\(id)/current", method: "PUT", body: try planBody(Weekdays(weekdays: weekdays)), csrfToken: token, as: PlanActivationResponse.self)
    }
    public func editDietPlanMeal(planId: Int, mealId: Int, description: String, calories: Double? = nil, protein: Double? = nil, carbs: Double? = nil, fat: Double? = nil) async throws {
        let token = try await planToken()
        _ = try await request("diet_plans/\(planId)/meals/\(mealId)", method: "PATCH", body: try planBody(MealEdit(description: description, calories: calories, protein: protein, carbs: carbs, fat: fat)), csrfToken: token, as: PlanMessage.self)
    }
    /// The server may version a plan that already has recorded history. Always
    /// use the returned plan and its IDs after an edit.
    public func editWorkoutPrescription(planId: Int, exerciseId: Int, catalogKey: String?, sets: Int, reps: String, weight: String, restSeconds: Int, name: String? = nil) async throws -> NativePlan {
        let token = try await planToken()
        let body = Prescription(catalogKey: catalogKey, sets: sets, reps: reps, weight: weight, restSeconds: restSeconds, name: name)
        return try await request("workout_plans/\(planId)/exercises/\(exerciseId)", method: "PATCH", body: try planBody(body), csrfToken: token, as: PlanEnvelope.self).plan
    }
    public func getPlanExerciseCatalog(planId: Int) async throws -> [PlanCatalogItem] {
        try await request("workout_plans/\(planId)/exercises/catalog", as: PlanCatalogEnvelope.self).items
    }
    public func getPlanReplacementOptions(planId: Int, exerciseId: Int) async throws -> WorkoutReplacementOptions {
        try await request("workout_plans/\(planId)/exercises/\(exerciseId)/replacement_options", as: WorkoutReplacementOptions.self)
    }
    public func suggestPlanChanges(planId: Int, feedback: String, dayId: Int?) async throws -> PlanChangesProposal {
        let token = try await planToken()
        return try await request("workout_plans/\(planId)/suggest_changes", method: "POST", body: try planBody(PlanFeedback(feedback: feedback, dayId: dayId)), csrfToken: token, as: PlanChangesProposal.self)
    }
    public func applyPlanChanges(planId: Int, changes: [PlanExerciseChange], revision: String) async throws -> NativePlan {
        let token = try await planToken()
        return try await request("workout_plans/\(planId)/apply_changes", method: "POST", body: try planBody(PlanChangeBody(changes: changes, revision: revision)), csrfToken: token, as: PlanEnvelope.self).plan
    }
    private func generatePlan<T: Encodable>(kind: NativePlanKind, preferences: T, background: Bool, idempotencyKey: String?) async throws -> PlanGenerationResponse {
        let token = try await planToken()
        return try await request("\(kind.path)/generate", method: "POST", body: try planBody(preferences), csrfToken: token, idempotencyKey: idempotencyKey, backgroundPlan: background, as: PlanGenerationResponse.self)
    }
    private func planBody<T: Encodable>(_ value: T) throws -> Data {
        let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
        return try encoder.encode(value)
    }
    private func planToken() async throws -> String {
        let state = try await restoreSession()
        guard state.loggedIn, let token = state.csrfToken else { throw APIError.http(status: 401, message: "Entre na sua conta para gerenciar os planos.") }
        return token
    }
}
private struct PlanEnvelope: Decodable { let plan: NativePlan }
private struct PlanMessage: Decodable { let message: String }
private struct Weekdays: Encodable { let weekdays: [Int] }
private struct MealEdit: Encodable {
    let description: String
    let calories: Double?
    let protein: Double?
    let carbs: Double?
    let fat: Double?
}
private struct Prescription: Encodable {
    let catalogKey: String?
    let sets: Int
    let reps: String
    let weight: String
    let restSeconds: Int
    let name: String?
}

private struct PlanCatalogEnvelope: Decodable { let items: [PlanCatalogItem] }
private struct PlanFeedback: Encodable { let feedback: String; let dayId: Int? }
private struct PlanChangeBody: Encodable { let changes: [PlanExerciseChange]; let revision: String }

extension FitTrackerAPI {
    public func getManualExerciseCatalog() async throws -> [PlanCatalogItem] {
        try await request("workout_plans/exercises/catalog", as: PlanCatalogEnvelope.self).items
    }
    public func createManualWorkout(title: String, days: [ManualPlanDay]) async throws -> NativePlan {
        let token = try await planToken()
        return try await request("workout_plans/manual", method: "POST", body: try planBody(ManualWorkout(title: title, days: days)), csrfToken: token, as: PlanEnvelope.self).plan
    }
    public func createManualDiet(title: String, meals: [ManualPlanMeal]) async throws -> NativePlan {
        let token = try await planToken()
        return try await request("diet_plans/manual", method: "POST", body: try planBody(ManualDiet(title: title, meals: meals)), csrfToken: token, as: PlanEnvelope.self).plan
    }
}
private struct ManualWorkout: Encodable { let title: String; let days: [ManualPlanDay] }
private struct ManualDiet: Encodable { let title: String; let meals: [ManualPlanMeal] }
