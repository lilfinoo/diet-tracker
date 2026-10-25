import Foundation

extension FitTrackerAPI {
    public func getDietDay(date: String) async throws -> DietDayResponse {
        try await request("diet/days/\(date)", as: DietDayResponse.self)
    }

    /// Keep this key with the draft when the outcome is uncertain. The caller can
    /// retry explicitly using the same key; the transport never replays a write.
    public func addDietEntry(_ entry: NewDietEntry, idempotencyKey: String) async throws -> DietEntry {
        guard !idempotencyKey.isEmpty else { throw APIError.invalidResponse }
        let token = try await dietMutationToken()
        let body = try dietEncoder().encode(entry)
        let response = try await request("diet", method: "POST", body: body,
                                         csrfToken: token, idempotencyKey: idempotencyKey,
                                         as: DietEntryEnvelope.self)
        return response.entry
    }

    public func updateDietEntry(id: Int, entry: NewDietEntry, idempotencyKey: String) async throws -> DietEntry {
        guard !idempotencyKey.isEmpty else { throw APIError.invalidResponse }
        let token = try await dietMutationToken()
        // Clearing an optional nutrient must send null, not omit the field.
        var payload = try JSONSerialization.jsonObject(with: dietEncoder().encode(entry)) as! [String: Any]
        for key in ["calories", "protein", "carbs", "fat", "notes"] where payload[key] == nil { payload[key] = NSNull() }
        let response = try await request("diet/\(id)", method: "PUT", body: try JSONSerialization.data(withJSONObject: payload),
            csrfToken: token, idempotencyKey: idempotencyKey, as: DietEntryEnvelope.self)
        return response.entry
    }

    public func deleteDietEntry(id: Int) async throws {
        let token = try await dietMutationToken()
        do {
            _ = try await request("diet/\(id)", method: "DELETE", csrfToken: token, as: DietDeleteResponse.self)
        } catch APIError.http(let status, _) where status == 404 {
            // An explicit retry after a lost response may find it already deleted.
        }
    }

    public func analyzeNutrition(description: String, image: NutritionImage? = nil, idempotencyKey: String? = nil) async throws -> NutritionAnalysisResponse {
        let token = try await dietMutationToken()
        let body = try dietEncoder().encode(NutritionAnalysisRequest(description: description, image: image))
        return try await request("diet/ai_macros", method: "POST", body: body,
                                 csrfToken: token, idempotencyKey: idempotencyKey, as: NutritionAnalysisResponse.self)
    }

    /// Poll only while the owning account and draft are still active. A pending
    /// task has no estimate; failed tasks expose their server error to the caller.
    public func getNutritionAnalysisTask(jobId: UUID) async throws -> NutritionAnalysisTask {
        try await request("ai/tasks/\(jobId.uuidString)", as: NutritionAnalysisTask.self)
    }

    private func dietMutationToken() async throws -> String {
        let current = try await workoutSessionForMutation()
        guard current.loggedIn else {
            throw APIError.http(status: 401, message: "Entre na sua conta para registrar a refeição.")
        }
        guard let token = current.csrfToken, !token.isEmpty else { throw APIError.invalidResponse }
        return token
    }

    private func dietEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }
}

private struct DietEntryEnvelope: Decodable { let entry: DietEntry }
private struct DietDeleteResponse: Decodable { let message: String? }
private struct NutritionAnalysisRequest: Encodable {
    let description: String
    let image: NutritionImage?
}
