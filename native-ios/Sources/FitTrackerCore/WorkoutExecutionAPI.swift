import Foundation

extension FitTrackerAPI {
    public func getWorkoutExecutionSession(planId: Int, dayId: Int) async throws -> WorkoutExecutionSession? {
        try await request("workout_plans/\(planId)/days/\(dayId)/sessions/active", as: WorkoutExecutionEnvelope.self).session
    }

    public func startWorkout(planId: Int, dayId: Int) async throws -> WorkoutExecutionSession {
        let token = try await workoutMutationToken()
        let response = try await request("workout_plans/\(planId)/days/\(dayId)/sessions", method: "POST",
                                         csrfToken: token, as: WorkoutExecutionEnvelope.self)
        guard let session = response.session else { throw APIError.invalidResponse }
        return session
    }

    public func saveWorkoutDraft(sessionId: Int, exerciseId: Int, sets: [WorkoutDraftSet]) async throws -> WorkoutExecutionSession {
        guard sets.count <= 20 else { throw APIError.invalidResponse }
        let token = try await workoutMutationToken()
        return try await workoutSessionMutation("workout_sessions/\(sessionId)/exercises/\(exerciseId)/draft",
                                                method: "PUT", token: token, payload: WorkoutSetsPayload(sets: sets))
    }

    public func completeWorkoutExercise(sessionId: Int, exerciseId: Int, sets: [WorkoutSetInput],
                                        completionMode: String? = nil, idempotencyKey: String) async throws -> WorkoutExecutionSession {
        guard sets.count <= 20, !idempotencyKey.isEmpty else { throw APIError.invalidResponse }
        let token = try await workoutMutationToken()
        return try await workoutSessionMutation("workout_sessions/\(sessionId)/exercises/\(exerciseId)/complete",
                                                method: "POST", token: token,
                                                payload: WorkoutCompletionPayload(sets: sets, completionMode: completionMode), key: idempotencyKey)
    }

    public func undoWorkoutExercise(sessionId: Int, exerciseId: Int, idempotencyKey: String? = nil) async throws -> WorkoutExecutionSession {
        let token = try await workoutMutationToken()
        let response = try await request("workout_sessions/\(sessionId)/exercises/\(exerciseId)/complete",
                                         method: "DELETE", csrfToken: token, idempotencyKey: idempotencyKey,
                                         as: WorkoutExecutionEnvelope.self)
        guard let session = response.session else { throw APIError.invalidResponse }
        return session
    }

    public func finishWorkout(sessionId: Int, idempotencyKey: String,
                              durationSeconds: Int? = nil, finishedAt: String? = nil) async throws -> WorkoutFinishResponse {
        guard !idempotencyKey.isEmpty else { throw APIError.invalidResponse }
        guard (durationSeconds == nil) == (finishedAt == nil), durationSeconds.map({ $0 > 0 }) ?? true else {
            throw APIError.http(status: 400, message: "Confirme a duração do treino.")
        }
        let token = try await workoutMutationToken()
        let body = try durationSeconds.map { try JSONSerialization.data(withJSONObject: ["duration_seconds": $0, "finished_at": finishedAt!]) }
        return try await request("workout_sessions/\(sessionId)/finish", method: "POST", body: body, csrfToken: token,
                                 idempotencyKey: idempotencyKey, as: WorkoutFinishResponse.self)
    }

    public func workoutReplacementOptions(sessionId: Int, exerciseId: Int) async throws -> WorkoutReplacementOptions {
        let token = try await workoutMutationToken()
        return try await request("workout_sessions/\(sessionId)/exercises/\(exerciseId)/replacement_options",
                                 method: "POST", body: Data("{}".utf8), csrfToken: token, as: WorkoutReplacementOptions.self)
    }

    public func replaceWorkoutExercise(sessionId: Int, exerciseId: Int, catalogKey: String?,
                                       idempotencyKey: String? = nil) async throws {
        let token = try await workoutMutationToken()
        let body = try catalogKey.map { try JSONSerialization.data(withJSONObject: ["catalog_key": $0]) }
        _ = try await request("workout_sessions/\(sessionId)/exercises/\(exerciseId)/replace",
                              method: catalogKey == nil ? "DELETE" : "POST", body: body,
                              csrfToken: token, idempotencyKey: idempotencyKey,
                              as: WorkoutMutationMessage.self)
    }

    public func cancelWorkout(sessionId: Int) async throws {
        let token = try await workoutMutationToken()
        _ = try await request("workout_sessions/\(sessionId)", method: "DELETE", csrfToken: token, as: WorkoutMutationMessage.self)
    }

    private func workoutMutationToken() async throws -> String {
        let session = try await workoutSessionForMutation()
        guard session.loggedIn, let token = session.csrfToken, !token.isEmpty else {
            throw APIError.http(status: 401, message: "Entre novamente para registrar o treino.")
        }
        return token
    }

    private func workoutSessionMutation<Payload: Encodable>(_ path: String, method: String, token: String,
                                                            payload: Payload, key: String? = nil) async throws -> WorkoutExecutionSession {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let response = try await request(path, method: method, body: encoder.encode(payload), csrfToken: token,
                                         idempotencyKey: key, as: WorkoutExecutionEnvelope.self)
        guard let session = response.session else { throw APIError.invalidResponse }
        return session
    }
}

private struct WorkoutSetsPayload<Element: Encodable>: Encodable { let sets: [Element] }

private struct WorkoutCompletionPayload: Encodable {
    let sets: [WorkoutSetInput]
    let completionMode: String?
}

private struct WorkoutMutationMessage: Decodable { let message: String? }
