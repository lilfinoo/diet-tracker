import Foundation

public struct WaterDay: Decodable, Sendable {
    public let date: String
    public let timezone: String
    public let totalMl: Int
    public let bottleCapacityMl: Int?
    public let entries: [WaterEntry]
}

public struct WaterEntry: Decodable, Sendable, Identifiable {
    public let id: Int
    public let amountMl: Int
    public let occurredAt: String
}

/// Freeze the amount, timestamp and key together before the first request.
public struct WaterPendingEntry: Codable, Sendable {
    public let amountMl: Int
    public let occurredAt: String
    public let key: String

    public init(amountMl: Int, occurredAt: Date = Date(), key: String = UUID().uuidString) {
        self.amountMl = amountMl
        self.occurredAt = ISO8601DateFormatter().string(from: occurredAt)
        self.key = key
    }
}

extension FitTrackerAPI {
    public func getWater(date: String? = nil) async throws -> WaterDay {
        try await request("water", queryItems: date.map { [URLQueryItem(name: "date", value: $0)] } ?? [], as: WaterDay.self)
    }

    public func addWater(_ entry: WaterPendingEntry, ownerId: UUID) async throws -> WaterDay {
        guard (1...10000).contains(entry.amountMl), !entry.key.isEmpty else {
            throw APIError.http(status: 400, message: "Informe um volume de 1 a 10.000 ml.")
        }
        let token = try await waterToken(ownerId: ownerId)
        let body = try JSONSerialization.data(withJSONObject: ["amount_ml": entry.amountMl, "occurred_at": entry.occurredAt])
        return try await request("water", method: "POST", body: body, csrfToken: token,
                                 idempotencyKey: entry.key, as: WaterDay.self)
    }

    public func saveWaterBottle(capacityMl: Int, ownerId: UUID) async throws -> WaterDay {
        guard (1...10000).contains(capacityMl) else {
            throw APIError.http(status: 400, message: "Informe a capacidade de 1 a 10.000 ml.")
        }
        let token = try await waterToken(ownerId: ownerId)
        return try await request("water/bottle", method: "POST",
            body: JSONSerialization.data(withJSONObject: ["bottle_capacity_ml": capacityMl]),
            csrfToken: token, as: WaterDay.self)
    }

    public func deleteWater(entryId: Int, ownerId: UUID) async throws -> WaterDay {
        let token = try await waterToken(ownerId: ownerId)
        return try await request("water/\(entryId)", method: "DELETE", csrfToken: token, as: WaterDay.self)
    }

    private func waterToken(ownerId: UUID) async throws -> String {
        let current = try await restoreSession()
        guard current.loggedIn, current.user?.id == ownerId, let token = current.csrfToken, !token.isEmpty else {
            throw APIError.http(status: 401, message: "Entre novamente na mesma conta para registrar água.")
        }
        return token
    }
}
