import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class DietAPITests: XCTestCase {
    private var session: URLSession!
    private let user = """
    {"id":"00000000-0000-0000-0000-000000000001","username":"ana","name":"Ana",
    "is_banned":false,"is_admin":false,"is_premium":true,"plan_code":"premium",
    "ai_trial_uses":0,"has_password":true,"is_public":false,"onboarding_status":"complete",
    "profile_missing_fields":[],"profile_complete":true}
    """
    private let entry = """
    {"id":9,"date":"2026-10-07","meal_type":"Almoço","description":"Arroz e feijão",
    "calories":null,"protein":0,"carbs":30.5,"fat":null,"notes":null,"source":"manual","daily_meal_state_id":null}
    """

    override func setUp() {
        super.setUp()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [DietStubProtocol.self]
        session = URLSession(configuration: configuration)
    }
    override func tearDown() {
        session.invalidateAndCancel(); DietStubProtocol.handler = nil
        super.tearDown()
    }

    func testDayWithoutPlanPreservesMissingTargetsAndUnknownNutrients() async throws {
        DietStubProtocol.handler = { request in
            XCTAssertEqual(request.url!.path, "/api/diet/days/2026-10-07")
            XCTAssertEqual(request.httpMethod, "GET")
            return (200, "{\"date\":\"2026-10-07\",\"plan\":null,\"slots\":[],\"manual_entries\":[\(self.entry)],\"totals\":{\"calories\":0,\"protein\":0,\"carbs\":30.5,\"fat\":0},\"targets\":{}}")
        }
        let day = try await api().getDietDay(date: "2026-10-07")
        XCTAssertNil(day.plan); XCTAssertNil(day.targets.calories)
        XCTAssertNil(day.entries.first?.calories)
        XCTAssertEqual(day.entries.first?.protein, 0)
        XCTAssertEqual(day.totals.carbs, 30.5)
    }

    func testDayIncludesPlannedConsumptionWithoutCountingPendingSlots() async throws {
        DietStubProtocol.handler = { _ in (200, """
        {"date":"2026-10-07","plan":{"id":4,"title":"Plano atual","description":null,"meals_count":2},
        "slots":[{"slot_key":"almoco","label":"Almoço","selected_plan_meal_id":6,"result":"consumed_as_planned",
        "alternatives":[{"id":6,"meal_type":"Almoço","description":"Arroz","calories":400,"protein":20,"carbs":50,"fat":10,"option":1}],"entry":\(self.entry)},
        {"slot_key":"jantar","label":"Jantar","selected_plan_meal_id":7,"result":"pending","alternatives":[],"entry":null}],
        "manual_entries":[],"totals":{"calories":400,"protein":20,"carbs":50,"fat":10},"targets":{"calories":2200}}
        """) }
        let day = try await api().getDietDay(date: "2026-10-07")
        XCTAssertEqual(day.entries.count, 1)
        XCTAssertEqual(day.slots.count, 2)
        XCTAssertEqual(day.plan?.id, 4)
        XCTAssertEqual(day.slots.first?.alternatives.first?.option, 1)
        XCTAssertEqual(day.targets.calories, 2200)
        XCTAssertNil(day.targets.protein)
    }

    func testManualSaveUsesFreshCSRFCallerKeyAndSnakeCasePayload() async throws {
        var paths: [String] = []
        DietStubProtocol.handler = { request in
            paths.append(request.url!.path)
            if paths.count == 1 { return (200, self.auth()) }
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh-token")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), "draft-key")
            let payload = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            XCTAssertEqual(payload["meal_type"] as? String, "Almoço")
            XCTAssertEqual(payload["date"] as? String, "2026-10-07")
            XCTAssertEqual(payload["protein"] as? Double, 0)
            XCTAssertNil(payload["calories"])
            return (201, "{\"entry\":\(self.entry),\"message\":\"Registro de dieta adicionado\"}")
        }
        let saved = try await api().addDietEntry(NewDietEntry(date: "2026-10-07", mealType: "Almoço", description: "Arroz e feijão", protein: 0), idempotencyKey: "draft-key")
        XCTAssertEqual(paths, ["/api/check_session", "/api/diet"])
        XCTAssertEqual(saved.id, 9)
    }

    func testCSRFRejectionNeverReplaysMealWrite() async throws {
        var count = 0
        DietStubProtocol.handler = { _ in
            count += 1
            return count == 1 ? (200, self.auth()) : (403, "{\"error\":\"Token CSRF inválido.\"}")
        }
        do { _ = try await api().addDietEntry(draft(), idempotencyKey: "key"); XCTFail("Expected rejection") }
        catch APIError.csrfMismatch { } catch { XCTFail("Unexpected \(error)") }
        XCTAssertEqual(count, 2)
    }

    func testExpiredSessionStopsWrite() async throws {
        var count = 0
        DietStubProtocol.handler = { _ in count += 1; return (200, "{\"logged_in\":false}") }
        do { _ = try await api().addDietEntry(draft(), idempotencyKey: "key"); XCTFail("Expected rejection") }
        catch APIError.http(let status, _) { XCTAssertEqual(status, 401) }
        XCTAssertEqual(count, 1)
    }

    func testExplicitRetryKeepsIdempotencyKeyAndReusesValidatedToken() async throws {
        var count = 0
        var keys: [String?] = []
        DietStubProtocol.handler = { request in
            count += 1
            if request.httpMethod == "GET" { return (200, self.auth()) }
            keys.append(request.value(forHTTPHeaderField: "Idempotency-Key"))
            if count == 2 { throw URLError(.networkConnectionLost) }
            return (201, "{\"entry\":\(self.entry)}")
        }
        let client = api()
        do { _ = try await client.addDietEntry(draft(), idempotencyKey: "same-draft"); XCTFail("Expected uncertainty") }
        catch let error as URLError { XCTAssertEqual(error.code, .networkConnectionLost) }
        _ = try await client.addDietEntry(draft(), idempotencyKey: "same-draft")
        XCTAssertEqual(count, 3); XCTAssertEqual(keys, ["same-draft", "same-draft"])
    }

    func testAnalysisPhotoReturnsEstimateWithoutDiaryMutation() async throws {
        var paths: [String] = []
        DietStubProtocol.handler = { request in
            paths.append(request.url!.path)
            if paths.count == 1 { return (200, self.auth()) }
            let payload = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            let image = payload["image"] as! [String: String]
            XCTAssertEqual(image["mime_type"], "image/jpeg")
            XCTAssertEqual(image["data"], Data([1,2,3]).base64EncodedString())
            return (200, "{\"description\":\"Arroz\",\"calories\":100,\"protein\":null,\"carbs\":20,\"fat\":0}")
        }
        let response = try await api().analyzeNutrition(description: "", image: NutritionImage(data: Data([1,2,3]), mimeType: "image/jpeg"))
        guard case .estimate(let estimate) = response else { return XCTFail("Expected estimate") }
        XCTAssertEqual(estimate.calories, 100); XCTAssertNil(estimate.protein)
        XCTAssertEqual(paths, ["/api/check_session", "/api/diet/ai_macros"])
    }

    func testQueuedAnalysisAndFailedTaskDecodeWithoutInventingEstimate() async throws {
        let id = UUID(uuidString: "00000000-0000-0000-0000-000000000123")!
        DietStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.auth()) }
            if request.httpMethod == "POST" { return (202, "{\"job_id\":\"\(id)\",\"status\":\"queued\"}") }
            return (200, "{\"job_id\":\"\(id)\",\"status\":\"failed\",\"http_status\":503,\"result\":{\"error\":\"Indisponível\"},\"error\":\"Indisponível\"}")
        }
        let client = api()
        guard case .queued(let jobId) = try await client.analyzeNutrition(description: "Arroz") else { return XCTFail("Expected task") }
        XCTAssertEqual(jobId, id)
        let task = try await client.getNutritionAnalysisTask(jobId: id)
        XCTAssertEqual(task.status, "failed"); XCTAssertEqual(task.error, "Indisponível"); XCTAssertNil(task.result)
    }

    func testTaskPendingAndSucceededUseResultOnlyWhenComplete() async throws {
        let id = UUID(uuidString: "00000000-0000-0000-0000-000000000123")!
        var count = 0
        DietStubProtocol.handler = { _ in
            count += 1
            if count == 1 { return (200, "{\"job_id\":\"\(id)\",\"status\":\"running\",\"http_status\":null}") }
            return (200, "{\"job_id\":\"\(id)\",\"status\":\"succeeded\",\"http_status\":200,\"result\":{\"description\":\"Arroz\",\"calories\":120,\"protein\":2,\"carbs\":26,\"fat\":0},\"error\":null}")
        }
        let client = api()
        let pending = try await client.getNutritionAnalysisTask(jobId: id)
        XCTAssertNil(pending.result)
        let completed = try await client.getNutritionAnalysisTask(jobId: id)
        XCTAssertEqual(completed.result?.calories, 120)
        XCTAssertEqual(completed.status, "succeeded")
    }

    func testEditingMealClearsUnknownNutrientsAndKeepsSameRecord() async throws {
        var writes = 0
        DietStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.auth()) }
            writes += 1
            XCTAssertEqual(request.url!.path, "/api/diet/9")
            XCTAssertEqual(request.httpMethod, "PUT")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), "edit-9")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh-token")
            let payload = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            XCTAssertEqual(payload["description"] as? String, "Arroz e feijão")
            XCTAssertEqual(payload["protein"] as? Double, 0)
            XCTAssertTrue(payload["calories"] is NSNull)
            XCTAssertTrue(payload["fat"] is NSNull)
            return (200, "{\"entry\":\(self.entry)}")
        }
        let saved = try await api().updateDietEntry(id: 9, entry: NewDietEntry(date: "2026-10-07", mealType: "Almoço", description: "Arroz e feijão", protein: 0, carbs: 30.5), idempotencyKey: "edit-9")
        XCTAssertEqual(saved.id, 9)
        XCTAssertEqual(writes, 1)
    }

    func testDeleteAlreadyRemovedMealIsSafeWithoutCreatingAnotherEntry() async throws {
        var methods: [String] = []
        DietStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.auth()) }
            methods.append(request.httpMethod!)
            XCTAssertEqual(request.url!.path, "/api/diet/9")
            return (404, "{\"error\":\"Registro não encontrado\"}")
        }
        try await api().deleteDietEntry(id: 9)
        XCTAssertEqual(methods, ["DELETE"])
    }

    func testDifferentMealUsesLinkedSlotAndActualNutrients() async throws {
        DietStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.auth()) }
            XCTAssertEqual(request.url!.path, "/api/diet/days/2026-10-07/slots/almoco/outcome")
            XCTAssertEqual(request.httpMethod, "PUT")
            let payload = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            XCTAssertEqual(payload["result"] as? String, "consumed_different")
            XCTAssertEqual(payload["diet_plan_meal_id"] as? Int, 6)
            let nested = try XCTUnwrap(payload["entry"] as? [String: Any])
            XCTAssertEqual(nested["carbs"] as? Double, 30.5)
            XCTAssertEqual(nested["description"] as? String, "Arroz e feijão")
            return (200, "{\"state\":{\"id\":\"00000000-0000-0000-0000-000000000006\",\"slot_key\":\"almoco\",\"selected_plan_meal_id\":6,\"result\":\"consumed_different\",\"entry\":\(self.entry)}}")
        }
        let saved = try await api().recordDifferentMeal(date: "2026-10-07", slotKey: "almoco", mealId: 6, entry: NewDietEntry(date: "2026-10-07", mealType: "Almoço", description: "Arroz e feijão", protein: 0, carbs: 30.5), idempotencyKey: "slot-draft")
        XCTAssertEqual(saved.entry?.id, 9)
        XCTAssertNil(saved.entry?.calories)
    }

    func testDifferentMealCannotReportSuccessForEarlierConsumption() async throws {
        DietStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.auth()) }
            return (200, "{\"state\":{\"id\":\"00000000-0000-0000-0000-000000000006\",\"slot_key\":\"almoco\",\"selected_plan_meal_id\":6,\"result\":\"consumed_different\",\"entry\":\(self.entry)}}")
        }
        do {
            _ = try await api().recordDifferentMeal(date: "2026-10-07", slotKey: "almoco", mealId: 6, entry: draft(), idempotencyKey: "different-draft")
            XCTFail("An existing different consumption must not be treated as this save")
        } catch APIError.http(let status, _) { XCTAssertEqual(status, 409) }
    }

    private func api() -> FitTrackerAPI { FitTrackerAPI(baseURL: URL(string: "https://diet.invalid/api")!, session: session) }
    private func auth() -> String { "{\"logged_in\":true,\"user\":\(user),\"csrf_token\":\"fresh-token\"}" }
    private func draft() -> NewDietEntry { NewDietEntry(date: "2026-10-07", mealType: "Almoço", description: "Arroz") }
    private func body(_ request: URLRequest) -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open(); defer { stream.close() }
        var output = Data(), buffer = [UInt8](repeating: 0, count: 1024)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count <= 0 { break }; output.append(buffer, count: count)
        }
        return output
    }
}

private final class DietStubProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            guard let handler = Self.handler else { throw URLError(.badServerResponse) }
            let (status, json) = try handler(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type":"application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(json.utf8)); client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() { }
}
