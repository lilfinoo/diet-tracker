import Foundation

public struct PlanBackgroundStatus: Decodable, Sendable {
    public let planBackgroundEnabled: Bool
    public let pushEnabled: Bool?
    public let tasks: [PendingPlanTask]
}

public struct PendingPlanTask: Decodable, Sendable {
    public let jobId: UUID
    public let operation: String
    public let requestKey: String?
    public let status: String
}

extension FitTrackerAPI {
    public func planBackgroundStatus() async throws -> PlanBackgroundStatus {
        try await request("ai/tasks", as: PlanBackgroundStatus.self)
    }

    public func registerPushDevice(token: String, environment: String, installationId: UUID) async throws -> Bool {
        let state = try await workoutSessionForMutation()
        guard let csrf = state.csrfToken else { throw APIError.invalidResponse }
        let encoder = JSONEncoder(); encoder.keyEncodingStrategy = .convertToSnakeCase
        let body = try encoder.encode(PushRegistration(token: token, environment: environment, installationId: installationId))
        let result = try await request("push/devices", method: "POST", body: body, csrfToken: csrf,
                              as: PushRegistrationResponse.self)
        return result.registered && result.pushEnabled
    }
}

private struct PushRegistration: Encodable {
    let token: String
    let environment: String
    let installationId: UUID
}
private struct PushRegistrationResponse: Decodable { let registered: Bool; let pushEnabled: Bool }
