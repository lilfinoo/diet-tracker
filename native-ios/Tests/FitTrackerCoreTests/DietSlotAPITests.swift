import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class DietSlotAPITests: XCTestCase {
    private var session: URLSession!
    private let user = """
    {"id":"00000000-0000-0000-0000-000000000001","username":"ana","name":"Ana",
    "is_banned":false,"is_admin":false,"is_premium":true,"plan_code":"premium",
    "ai_trial_uses":0,"has_password":true,"is_public":false,"onboarding_status":"complete",
    "profile_missing_fields":[],"profile_complete":true}
    """
    private let state = "{\"state\":{\"id\":\"00000000-0000-0000-0000-000000000123\",\"slot_key\":\"almoco\",\"selected_plan_meal_id\":8,\"result\":\"consumed_planned\"}}"
    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral; config.protocolClasses = [SlotStubProtocol.self]
        session = URLSession(configuration: config)
    }
    override func tearDown() { session.invalidateAndCancel(); SlotStubProtocol.handler = nil; super.tearDown() }

    func testOptimisticConsumptionAddsSelectedNutrientsOnlyOnce() throws {
        let day = try optimisticDay()
        let changed = day.applyingPlannedOutcome(slotKey: "almoco", outcome: .consumedPlanned)
        XCTAssertEqual(changed.totals.calories, 1600)
        XCTAssertEqual(changed.totals.protein, 103)
        XCTAssertEqual(changed.totals.carbs, 184)
        XCTAssertNil(changed.totals.fat)
        XCTAssertNil(changed.slots.first?.entry)
        XCTAssertEqual(changed.slots.first?.result, "consumed_planned")
        XCTAssertEqual(changed.applyingPlannedOutcome(slotKey: "almoco", outcome: .consumedPlanned).totals.calories, 1600)
        XCTAssertEqual(day.totals.calories, 980)
        XCTAssertEqual(day.slots.first?.result, "pending")
    }

    func testOptimisticSkipAndUnknownSlotPreserveTotals() throws {
        let day = try optimisticDay()
        let skipped = day.applyingPlannedOutcome(slotKey: "almoco", outcome: .skipped)
        XCTAssertEqual(skipped.totals.calories, 980)
        XCTAssertEqual(skipped.slots.first?.result, "skipped")
        XCTAssertEqual(day.applyingPlannedOutcome(slotKey: "missing", outcome: .consumedPlanned).slots.first?.result, "pending")
    }

    private func optimisticDay() throws -> DietDayResponse {
        let json = """
        {"date":"2026-10-08","plan":null,"manual_entries":[],"targets":{},
        "totals":{"calories":980,"protein":61,"carbs":112},
        "slots":[{"slot_key":"almoco","label":"Almoço","selected_plan_meal_id":8,"result":"pending","entry":null,
        "alternatives":[{"id":8,"meal_type":"Almoço","description":"Arroz e frango","calories":620,"protein":42,"carbs":72,"fat":17}]}]}
        """
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(DietDayResponse.self, from: Data(json.utf8))
    }

    func testConfirmedOutcomeKeepsServerEntryAndDoesNotDoubleCountOptimisticTotals() throws {
        let day = try optimisticDay()
        let json = """
        {"id":"00000000-0000-0000-0000-000000000123","slot_key":"almoco","selected_plan_meal_id":8,"result":"consumed_planned",
        "entry":{"id":41,"date":"2026-10-08","meal_type":"Almoço","description":"Arroz e frango","calories":620,"protein":42,"carbs":72,"fat":17}}
        """
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let state = try decoder.decode(DietSlotState.self, from: Data(json.utf8))
        let confirmed = day.applyingConfirmedOutcome(state)
        XCTAssertEqual(confirmed.totals.calories, 1600)
        XCTAssertEqual(confirmed.slots.first?.entry?.id, 41)
        XCTAssertEqual(day.applyingPlannedOutcome(slotKey: "almoco", outcome: .consumedPlanned)
            .applyingConfirmedOutcome(state).totals.calories, 1600)
        XCTAssertEqual(confirmed.applyingConfirmedOutcome(state).totals.calories, 1600)
    }

    func testRepeatedWritesReuseAuthenticatedSession() async throws {
        var paths: [String] = []
        SlotStubProtocol.handler = { request in
            paths.append(request.url!.path)
            return request.httpMethod == "GET" ? (200, self.auth()) : (200, self.state)
        }
        let api = client()
        try await api.selectDietAlternative(date: "2026-10-07", slotKey: "almoco", mealId: 8)
        try await api.selectDietAlternative(date: "2026-10-07", slotKey: "almoco", mealId: 8)
        XCTAssertEqual(paths.filter { $0 == "/api/check_session" }.count, 1)
    }

    func testSelectionUsesActualAlternativeAndFreshCSRF() async throws {
        var paths: [String] = []
        SlotStubProtocol.handler = { request in
            paths.append(request.url!.path)
            if paths.count == 1 { return (200, self.auth()) }
            XCTAssertEqual(request.httpMethod, "PUT")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh")
            let payload = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Int]
            XCTAssertEqual(payload["diet_plan_meal_id"], 8)
            return (200, self.state)
        }
        try await client().selectDietAlternative(date: "2026-10-07", slotKey: "almoco", mealId: 8)
        XCTAssertEqual(paths, ["/api/check_session", "/api/diet/days/2026-10-07/slots/almoco/selection"])
    }
    func testConsumedOutcomeUsesBackendResultAndLinkedPlanMealInsteadOfManualEntry() async throws {
        var paths: [String] = []
        SlotStubProtocol.handler = { request in
            paths.append(request.url!.path)
            if paths.count == 1 { return (200, self.auth()) }
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), "persisted-meal-operation")
            let payload = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            XCTAssertEqual(payload["result"] as? String, "consumed_planned")
            XCTAssertEqual(payload["diet_plan_meal_id"] as? Int, 8)
            return (201, self.state.dropLast(2) + ",\"entry\":{\"id\":41,\"date\":\"2026-10-07\",\"meal_type\":\"Almoço\",\"description\":\"Arroz\",\"calories\":620}}}")
        }
        try await client().setDietSlotOutcome(date: "2026-10-07", slotKey: "almoco", mealId: 8, outcome: .consumedPlanned, idempotencyKey: "persisted-meal-operation")
        XCTAssertEqual(paths.last, "/api/diet/days/2026-10-07/slots/almoco/outcome")
        XCTAssertFalse(paths.contains("/api/diet"))
    }
    func testSkipDoesNotSendConsumedEntry() async throws {
        SlotStubProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, self.auth()) }
            let payload = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            XCTAssertEqual(payload["result"] as? String, "skipped")
            XCTAssertNil(payload["entry"])
            return (201, self.state.replacingOccurrences(of: "consumed_planned", with: "skipped"))
        }
        try await client().setDietSlotOutcome(date: "2026-10-07", slotKey: "almoco", mealId: 8, outcome: .skipped)
    }
    func testConsumedOutcomeWithoutServerEntryRemainsUnconfirmed() async throws {
        var writes = 0
        SlotStubProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, self.auth()) }
            writes += 1
            return (201, self.state)
        }
        do {
            try await client().setDietSlotOutcome(date: "2026-10-07", slotKey: "almoco", mealId: 8, outcome: .consumedPlanned)
            XCTFail("An optimistic meal is not proof of a saved entry")
        } catch APIError.invalidResponse { }
        XCTAssertEqual(writes, 1)
    }

    func testResetAcceptsAlreadyReset204WithoutInventingState() async throws {
        SlotStubProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, self.auth()) }
            XCTAssertEqual(request.httpMethod, "DELETE")
            XCTAssertNil(request.httpBody)
            return (204, "")
        }
        try await client().resetDietSlotOutcome(date: "2026-10-07", slotKey: "almoco")
    }
    func testOutcomeConflictNeverReplaysOrOverwritesExistingConsumption() async throws {
        var count = 0
        SlotStubProtocol.handler = { _ in
            count += 1
            return count == 1 ? (200, self.auth()) : (409, "{\"error\":\"Esta refeição já possui um resultado. Corrija o registro existente.\"}")
        }
        do { try await client().setDietSlotOutcome(date: "2026-10-07", slotKey: "almoco", mealId: 8, outcome: .skipped); XCTFail("Expected conflict") }
        catch APIError.http(let status, _) { XCTAssertEqual(status, 409) }
        XCTAssertEqual(count, 2)
    }
    func testResetCSRFRejectionNeverReplaysDelete() async throws {
        var count = 0
        SlotStubProtocol.handler = { _ in
            count += 1
            return count == 1 ? (200, self.auth()) : (403, "{\"error\":\"Token CSRF inválido.\"}")
        }
        do { try await client().resetDietSlotOutcome(date: "2026-10-07", slotKey: "almoco"); XCTFail("Expected rejection") }
        catch APIError.csrfMismatch { }
        XCTAssertEqual(count, 2)
    }
    private func client() -> FitTrackerAPI { FitTrackerAPI(baseURL: URL(string: "https://slots.invalid/api")!, session: session) }
    private func auth() -> String { "{\"logged_in\":true,\"user\":\(user),\"csrf_token\":\"fresh\"}" }
    private func body(_ request: URLRequest) -> Data {
        if let data = request.httpBody { return data }
        guard let stream = request.httpBodyStream else { return Data() }; stream.open(); defer { stream.close() }
        var output = Data(), buffer = [UInt8](repeating: 0, count: 1024)
        while stream.hasBytesAvailable { let count = stream.read(&buffer, maxLength: buffer.count); if count <= 0 { break }; output.append(buffer, count: count) }
        return output
    }
}
private final class SlotStubProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            guard let handler = Self.handler else { throw URLError(.badServerResponse) }
            let (status, json) = try handler(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            if !json.isEmpty { client?.urlProtocol(self, didLoad: Data(json.utf8)) }
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() { }
}
