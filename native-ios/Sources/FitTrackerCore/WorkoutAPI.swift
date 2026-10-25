import Foundation

extension FitTrackerAPI {
    public func deleteWorkoutActivity(id: Int) async throws {
        let current = try await workoutSessionForMutation()
        guard current.loggedIn, let token = current.csrfToken, !token.isEmpty else {
            throw APIError.http(status: 401, message: "Entre novamente para excluir o registro.")
        }
        _ = try await request("activities/\(id)", method: "DELETE", csrfToken: token, as: ActivityDeletionMessage.self)
    }

    public func getWorkoutToday() async throws -> WorkoutToday {
        try await request("workouts/today", as: WorkoutToday.self)
    }

    public func getWorkoutActivities(offset: Int = 0) async throws -> WorkoutActivityPage {
        try await request("activities", queryItems: [
            URLQueryItem(name: "limit", value: "20"),
            URLQueryItem(name: "offset", value: String(max(0, offset)))
        ], as: WorkoutActivityPage.self)
    }

    public func getWorkoutActivity(id: Int) async throws -> WorkoutActivityDetail {
        try await request("activities/\(id)", as: WorkoutActivityDetail.self)
    }
}

private struct ActivityDeletionMessage: Decodable { let message: String? }
