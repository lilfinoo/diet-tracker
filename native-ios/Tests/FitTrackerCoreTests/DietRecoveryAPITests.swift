import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class DietRecoveryAPITests: XCTestCase {
    private var session: URLSession!
    private let user = """
    {"id":"00000000-0000-0000-0000-000000000001","username":"ana","name":"Ana",
    "is_banned":false,"is_admin":false,"is_premium":false,"plan_code":"free",
    "ai_trial_uses":0,"has_password":true,"is_public":false,"onboarding_status":"complete",
    "profile_missing_fields":[],"profile_complete":true}
    """
    private let savedEntry = """
    {"id":9,"date":"2026-10-20","meal_type":"Almoço","description":"Arroz e feijão",
    "calories":400,"protein":null,"carbs":null,"fat":null,"notes":null,"source":"manual","daily_meal_state_id":null}
    """

    override func setUp() {
        super.setUp()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [DietRecoveryProtocol.self]
        session = URLSession(configuration: configuration)
    }
    override func tearDown() {
        session.invalidateAndCancel(); DietRecoveryProtocol.handler = nil
        super.tearDown()
    }

    func testLostResponseAfterCommittedMealExplicitRetryUsesIdenticalPayloadAndKey() async throws {
        var persisted: [String: Data] = [:]
        var attempts = 0
        DietRecoveryProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, self.auth()) }
            attempts += 1
            let key = try XCTUnwrap(request.value(forHTTPHeaderField: "Idempotency-Key"))
            let body = self.body(request)
            if let original = persisted[key] {
                let sent = try JSONSerialization.jsonObject(with: body) as? NSDictionary
                let saved = try JSONSerialization.jsonObject(with: original) as? NSDictionary
                XCTAssertEqual(sent, saved)
            }
            else { persisted[key] = body }
            if attempts == 1 { throw URLError(.networkConnectionLost) }
            return (201, "{\"entry\":\(self.savedEntry)}")
        }
        let client = api()
        let draft = NewDietEntry(date: "2026-10-20", mealType: "Almoço", description: "Arroz e feijão", calories: 400)
        do { _ = try await client.addDietEntry(draft, idempotencyKey: "same-open-draft"); XCTFail("Expected lost response") }
        catch let error as URLError { XCTAssertEqual(error.code, .networkConnectionLost) }
        XCTAssertEqual(attempts, 1, "A write must not retry itself")
        let entry = try await client.addDietEntry(draft, idempotencyKey: "same-open-draft")
        XCTAssertEqual(entry.id, 9)
        XCTAssertEqual(persisted.count, 1)
        XCTAssertEqual(attempts, 2)
    }

    func testQueuedAnalysisCanResumePollingAfterNetworkFailureWithoutAnotherAnalysisPost() async throws {
        let jobID = UUID(uuidString: "00000000-0000-0000-0000-000000000123")!
        var posts = 0, polls = 0
        DietRecoveryProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.auth()) }
            if request.httpMethod == "POST" {
                posts += 1
                return (202, "{\"job_id\":\"\(jobID)\",\"status\":\"queued\"}")
            }
            polls += 1
            if polls == 1 { throw URLError(.notConnectedToInternet) }
            return (200, "{\"job_id\":\"\(jobID)\",\"status\":\"succeeded\",\"http_status\":200,\"result\":{\"description\":\"Arroz\",\"calories\":120},\"error\":null}")
        }
        let client = api()
        guard case .queued(let acceptedID) = try await client.analyzeNutrition(description: "Arroz") else { return XCTFail("Expected queue") }
        do { _ = try await client.getNutritionAnalysisTask(jobId: acceptedID); XCTFail("Expected offline polling") }
        catch let error as URLError { XCTAssertEqual(error.code, .notConnectedToInternet) }
        let result = try await client.getNutritionAnalysisTask(jobId: acceptedID)
        XCTAssertEqual(result.result?.calories, 120)
        XCTAssertEqual(posts, 1, "Checking an accepted job must not spend another credit")
        XCTAssertEqual(polls, 2)
    }

    func testLostAnalysisResponseReusesPersistedKeyAndExactPhotoAfterRestart() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let owner = UUID()
        let draft = NutritionAnalysisDraft(date: "2026-10-21", mealType: "Almoço", description: "Arroz", photoData: Data([1, 2, 3]), freeRemaining: 1)
        let store = NutritionAnalysisRecovery(directory: folder)
        try store.save(draft, owner: owner)
        var bodies: [Data] = [], keys: [String] = []
        DietRecoveryProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, self.auth()) }
            bodies.append(self.body(request))
            keys.append(request.value(forHTTPHeaderField: "Idempotency-Key") ?? "")
            if bodies.count == 1 { throw URLError(.networkConnectionLost) }
            return (200, "{\"description\":\"Arroz\",\"calories\":120}")
        }
        do {
            _ = try await api().analyzeNutrition(description: draft.description,
                image: draft.photoData.map { NutritionImage(data: $0, mimeType: "image/jpeg") }, idempotencyKey: draft.requestKey)
            XCTFail("Expected lost response")
        } catch let error as URLError { XCTAssertEqual(error.code, .networkConnectionLost) }
        XCTAssertEqual(bodies.count, 1, "The transport cannot repeat a credit-consuming POST automatically")
        let restored = try XCTUnwrap(NutritionAnalysisRecovery(directory: folder).load(owner: owner))
        let result = try await api().analyzeNutrition(description: restored.description,
            image: restored.photoData.map { NutritionImage(data: $0, mimeType: "image/jpeg") }, idempotencyKey: restored.requestKey)
        guard case .estimate(let estimate) = result else { return XCTFail("Expected original result") }
        XCTAssertEqual(estimate.calories, 120)
        XCTAssertEqual(keys, [draft.requestKey, draft.requestKey])
        XCTAssertEqual(try JSONSerialization.jsonObject(with: bodies[0]) as? NSDictionary,
                       try JSONSerialization.jsonObject(with: bodies[1]) as? NSDictionary)
    }

    func testAnalysisInProgressDoesNotAutomaticallyRetryThePost() async throws {
        var posts = 0
        DietRecoveryProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, self.auth()) }
            posts += 1
            return (425, "{\"error\":\"Sua análise está em andamento.\"}")
        }
        do {
            _ = try await api().analyzeNutrition(description: "Arroz", idempotencyKey: "same-analysis")
            XCTFail("Expected pending response")
        } catch APIError.http(let status, _) { XCTAssertEqual(status, 425) }
        XCTAssertEqual(posts, 1)
    }

    func testUnavailableDiaryThrowsWhileSuccessfulEmptyDiaryRemainsValid() async throws {
        var available = false
        DietRecoveryProtocol.handler = { _ in
            if !available { return (503, "{\"error\":\"Temporariamente indisponível\"}") }
            return (200, "{\"date\":\"2026-10-20\",\"plan\":null,\"slots\":[],\"manual_entries\":[],\"totals\":{},\"targets\":{}}")
        }
        let client = api()
        do { _ = try await client.getDietDay(date: "2026-10-20"); XCTFail("A failed day cannot become an empty day") }
        catch APIError.http(let status, _) { XCTAssertEqual(status, 503) }
        available = true
        let day = try await client.getDietDay(date: "2026-10-20")
        XCTAssertTrue(day.entries.isEmpty); XCTAssertTrue(day.slots.isEmpty)
        XCTAssertNil(day.totals.calories, "Missing totals are not fabricated as zero")
    }

    private func api() -> FitTrackerAPI { FitTrackerAPI(baseURL: URL(string: "https://diet-recovery.invalid/api")!, session: session) }
    private func auth() -> String { "{\"logged_in\":true,\"user\":\(user),\"csrf_token\":\"fresh-token\"}" }
    private func body(_ request: URLRequest) -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open(); defer { stream.close() }
        var data = Data(), buffer = [UInt8](repeating: 0, count: 1024)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count <= 0 { break }; data.append(buffer, count: count)
        }
        return data
    }
}

private final class DietRecoveryProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            guard let handler = Self.handler else { throw URLError(.badServerResponse) }
            let (status, json) = try handler(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(json.utf8)); client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() { }
}
