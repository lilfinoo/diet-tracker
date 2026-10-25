import Foundation

extension FitTrackerAPI {
    /// Retries are explicit and must preserve both this entry and its key when
    /// a response is uncertain. The transport does not repeat a POST.
    public func addMeasurementEntry(_ entry: NewMeasurementEntry, idempotencyKey: String) async throws -> MeasurementEntry {
        guard !idempotencyKey.isEmpty else { throw APIError.invalidResponse }
        try entry.validate()
        let current = try await restoreSession()
        guard current.loggedIn else {
            throw APIError.http(status: 401, message: "Entre na sua conta para registrar medidas.")
        }
        guard let token = current.csrfToken, !token.isEmpty else { throw APIError.invalidResponse }
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let response = try await request("measurements", method: "POST", body: try encoder.encode(entry),
                                         csrfToken: token, idempotencyKey: idempotencyKey,
                                         as: MeasurementEntryEnvelope.self)
        return response.measurement
    }

    public func getMeasurementEntries(offset: Int = 0) async throws -> [MeasurementEntry] {
        try await request("measurements", queryItems: [URLQueryItem(name: "limit", value: "50"),
            URLQueryItem(name: "offset", value: String(max(0, offset)))], as: [MeasurementEntry].self)
    }

    public func updateMeasurementEntry(id: Int, entry: NewMeasurementEntry, idempotencyKey: String, ownerId: UUID) async throws -> MeasurementEntry {
        guard !idempotencyKey.isEmpty else { throw APIError.invalidResponse }
        try entry.validate()
        let token = try await measurementToken(ownerId: ownerId)
        // PUT must send null for cleared fields; omitting them would retain old values.
        var values: [String: Any] = ["date": entry.date]
        for (key, value) in [("weight", entry.weight), ("height", entry.height), ("body_fat", entry.bodyFat),
                             ("muscle_mass", entry.muscleMass), ("waist", entry.waist), ("chest", entry.chest),
                             ("arm", entry.arm), ("thigh", entry.thigh)] {
            values[key] = value.map { $0 as Any } ?? NSNull()
        }
        let response = try await request("measurements/\(id)", method: "PUT",
            body: JSONSerialization.data(withJSONObject: values), csrfToken: token,
            idempotencyKey: idempotencyKey, as: MeasurementEntryEnvelope.self)
        return response.measurement
    }

    public func deleteMeasurementEntry(id: Int, ownerId: UUID) async throws {
        let token = try await measurementToken(ownerId: ownerId)
        do {
            _ = try await request("measurements/\(id)", method: "DELETE", csrfToken: token,
                                  as: MeasurementMutationResponse.self)
        } catch APIError.http(let status, _) where status == 404 {
            // A retry after a lost response may find the same record already removed.
        }
    }

    private func measurementToken(ownerId: UUID) async throws -> String {
        let current = try await restoreSession()
        guard current.loggedIn, current.user?.id == ownerId, let token = current.csrfToken, !token.isEmpty else {
            throw APIError.http(status: 401, message: "Entre novamente na mesma conta para alterar suas medidas.")
        }
        return token
    }

}

private struct MeasurementEntryEnvelope: Decodable { let measurement: MeasurementEntry }

private struct MeasurementMutationResponse: Decodable { let message: String }
