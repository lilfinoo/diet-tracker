import Foundation

public enum DietSlotOutcome: String, Codable, Sendable {
    case consumedPlanned = "consumed_planned"
    case skipped
}

extension FitTrackerAPI {
    public func recordDifferentMeal(date: String, slotKey: String, mealId: Int, entry: NewDietEntry, idempotencyKey: String) async throws -> DietSlotState {
        let token = try await dietSlotToken()
        let body = DietDifferentMeal(dietPlanMealId: mealId, entry: entry)
        let response = try await request("diet/days/\(date)/slots/\(slotKey)/outcome", method: "PUT",
            body: try slotBody(body), csrfToken: token, idempotencyKey: idempotencyKey, as: DietSlotMutationResponse.self)
        guard let state = response.state, state.slotKey == slotKey, state.result == "consumed_different", state.selectedPlanMealId == mealId,
              let saved = state.entry, saved.description == entry.description, saved.mealType == entry.mealType,
              saved.calories == entry.calories, saved.protein == entry.protein,
              saved.carbs == entry.carbs, saved.fat == entry.fat, saved.notes == entry.notes else {
            throw APIError.http(status: 409, message: "Esta refeição já foi alterada. Confira o registro no diário antes de tentar novamente.")
        }
        return state
    }

    public func selectDietAlternative(date: String, slotKey: String, mealId: Int) async throws {
        let token = try await dietSlotToken()
        _ = try await request("diet/days/\(date)/slots/\(slotKey)/selection", method: "PUT", body: try slotBody(DietSlotSelection(dietPlanMealId: mealId)), csrfToken: token, as: DietSlotMutationResponse.self)
    }

    /// The server creates the consumed entry linked to this planned meal. It
    /// treats an identical result as an existing outcome. Persisted writes retain
    /// their key and reconcile the server state before an explicit replay.
    @discardableResult
    public func setDietSlotOutcome(date: String, slotKey: String, mealId: Int, outcome: DietSlotOutcome, idempotencyKey: String? = nil) async throws -> DietSlotState {
        let token = try await dietSlotToken()
        let response = try await request("diet/days/\(date)/slots/\(slotKey)/outcome", method: "PUT", body: try slotBody(DietSlotResult(dietPlanMealId: mealId, result: outcome.rawValue)), csrfToken: token, idempotencyKey: idempotencyKey, as: DietSlotMutationResponse.self)
        guard let state = response.state, state.slotKey == slotKey, state.result == outcome.rawValue,
              outcome == .skipped || (state.selectedPlanMealId == mealId && state.entry != nil) else { throw APIError.invalidResponse }
        return state
    }

    public func resetDietSlotOutcome(date: String, slotKey: String) async throws {
        let token = try await dietSlotToken()
        _ = try await request("diet/days/\(date)/slots/\(slotKey)/outcome", method: "DELETE", csrfToken: token, allowEmptyResponse: true, as: DietSlotMutationResponse.self)
    }

    private func slotBody<T: Encodable>(_ value: T) throws -> Data {
        let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
        return try encoder.encode(value)
    }
    private func dietSlotToken() async throws -> String {
        let current = try await workoutSessionForMutation()
        guard current.loggedIn, let token = current.csrfToken else {
            throw APIError.http(status: 401, message: "Entre na sua conta para registrar a refeição.")
        }
        return token
    }
}

private struct DietSlotSelection: Encodable { let dietPlanMealId: Int }
private struct DietDifferentMeal: Encodable {
    let result = "consumed_different"
    let dietPlanMealId: Int
    let entry: NewDietEntry
}
private struct DietSlotResult: Encodable { let dietPlanMealId: Int; let result: String }
private struct DietSlotMutationResponse: Decodable { let state: DietSlotState? }
public struct DietSlotState: Decodable, Sendable {
    public let id: UUID
    public let slotKey: String
    public let selectedPlanMealId: Int
    public let result: String
    public let entry: DietEntry?
}
