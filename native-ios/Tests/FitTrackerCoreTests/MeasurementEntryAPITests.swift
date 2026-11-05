import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class MeasurementEntryAPITests: XCTestCase {
    private var session: URLSession!
    private let user = """
    {"id":"00000000-0000-0000-0000-000000000001","username":"ana","name":"Ana",
    "is_banned":false,"is_admin":false,"is_premium":true,"plan_code":"premium",
    "ai_trial_uses":0,"has_password":true,"is_public":false,"onboarding_status":"complete",
    "profile_missing_fields":[],"profile_complete":true}
    """
    private let saved = """
    {"message":"Medida adicionada","measurement":{"id":17,"date":"2026-10-07",
    "weight":72.5,"height":175,"body_fat":21.2,"muscle_mass":30,"waist":80,
    "chest":95,"arm":32,"thigh":54,"notes":null,"created_at":"2026-10-07T12:00:00"}}
    """

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MeasurementStubProtocol.self]
        session = URLSession(configuration: config)
    }
    override func tearDown() {
        session.invalidateAndCancel()
        MeasurementStubProtocol.handler = nil
        super.tearDown()
    }

    func testSaveMatchesEightFieldsFreshCSRFAndResponseEnvelope() async throws {
        var paths: [String] = []
        MeasurementStubProtocol.handler = { request in
            paths.append(request.url!.path)
            if request.httpMethod == "GET" { return (200, self.auth()) }
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), "draft-1")
            let json = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            XCTAssertEqual(json.count, 9)
            XCTAssertEqual(json["date"] as? String, "2026-10-07")
            for (key, value) in ["weight":72.5, "height":175, "body_fat":21.2, "muscle_mass":30, "waist":80, "chest":95, "arm":32, "thigh":54] {
                XCTAssertEqual(json[key] as? Double, value)
            }
            return (201, self.saved)
        }
        let result = try await client().addMeasurementEntry(NewMeasurementEntry(date: "2026-10-07",
            weight: 72.5, height: 1.75, bodyFat: 21.2, muscleMass: 30, waist: 80, chest: 95, arm: 32, thigh: 54), idempotencyKey: "draft-1")
        XCTAssertEqual(paths, ["/api/check_session", "/api/measurements"])
        XCTAssertEqual(result.id, 17)
        XCTAssertEqual(result.bodyFat, 21.2)
        XCTAssertEqual(result.muscleMass, 30)
    }

    func testUnknownValuesAreOmittedRatherThanEncodedAsZero() async throws {
        MeasurementStubProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, self.auth()) }
            let json = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            XCTAssertEqual(json.count, 1)
            XCTAssertEqual(json["date"] as? String, "2026-10-07")
            return (201, "{\"measurement\":{\"id\":18,\"date\":\"2026-10-07\",\"weight\":null,\"body_fat\":null}}")
        }
        let result = try await client().addMeasurementEntry(NewMeasurementEntry(date: "2026-10-07"), idempotencyKey: "empty-values")
        XCTAssertNil(result.weight)
        XCTAssertNil(result.bodyFat)
    }

    func testInvalidRangesFailBeforeAnyNetworkRequest() async {
        var calls = 0
        MeasurementStubProtocol.handler = { _ in calls += 1; return (500, "{}") }
        let invalid = [NewMeasurementEntry(date: "2026-10-07", weight: 0),
            NewMeasurementEntry(date: "2026-10-07", weight: 500.1),
            NewMeasurementEntry(date: "2026-10-07", height: 300.1),
            NewMeasurementEntry(date: "2026-10-07", bodyFat: 100.1),
            NewMeasurementEntry(date: "2026-10-07", muscleMass: -1),
            NewMeasurementEntry(date: "2026-10-07", waist: .nan),
            NewMeasurementEntry(date: "2026-10-07", chest: .infinity),
            NewMeasurementEntry(date: "2026-10-07", arm: 0),
            NewMeasurementEntry(date: "2026-10-07", thigh: 501)]
        for entry in invalid {
            do { _ = try await client().addMeasurementEntry(entry, idempotencyKey: "invalid"); XCTFail("Expected validation") }
            catch APIError.http(let status, _) { XCTAssertEqual(status, 400) }
            catch { XCTFail("Unexpected error: \(error)") }
        }
        XCTAssertEqual(calls, 0)
    }

    func testExpiredSessionNeverPosts() async {
        var calls = 0
        MeasurementStubProtocol.handler = { request in
            calls += 1
            XCTAssertEqual(request.httpMethod, "GET")
            return (200, "{\"logged_in\":false}")
        }
        do { _ = try await client().addMeasurementEntry(NewMeasurementEntry(date: "2026-10-07"), idempotencyKey: "draft"); XCTFail("Expected auth failure") }
        catch APIError.http(let status, _) { XCTAssertEqual(status, 401) }
        catch { XCTFail("Unexpected error: \(error)") }
        XCTAssertEqual(calls, 1)
    }

    func testTransportFailureHasNoAutomaticReplayAndExplicitRetryKeepsKeyAndPayload() async throws {
        var posts = 0
        var bodies: [[String: Any]] = []
        var restores = 0
        MeasurementStubProtocol.handler = { request in
            if request.httpMethod == "GET" { restores += 1; return (200, self.auth()) }
            posts += 1
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), "stable-draft")
            bodies.append(try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any])
            if posts == 1 { throw URLError(.timedOut) }
            return (201, self.saved)
        }
        let api = client()
        let entry = NewMeasurementEntry(date: "2026-10-07", weight: 72.5)
        do { _ = try await api.addMeasurementEntry(entry, idempotencyKey: "stable-draft"); XCTFail("Expected timeout") }
        catch let error as URLError { XCTAssertEqual(error.code, .timedOut) }
        XCTAssertEqual(posts, 1)
        _ = try await api.addMeasurementEntry(entry, idempotencyKey: "stable-draft")
        XCTAssertEqual(posts, 2)
        XCTAssertEqual(restores, 2)
        XCTAssertEqual(bodies[0] as NSDictionary, bodies[1] as NSDictionary)
    }

    func testCSRFRejectionNeverReplaysPOST() async {
        var calls = 0
        MeasurementStubProtocol.handler = { request in
            calls += 1
            return request.httpMethod == "GET" ? (200, self.auth()) : (403, "{\"error\":\"Token CSRF inválido.\"}")
        }
        do { _ = try await client().addMeasurementEntry(NewMeasurementEntry(date: "2026-10-07"), idempotencyKey: "draft"); XCTFail("Expected rejection") }
        catch APIError.csrfMismatch { }
        catch { XCTFail("Unexpected error: \(error)") }
        XCTAssertEqual(calls, 2)
    }

    func testListDecodesMeasurementFieldsAndSendsPagination() async throws {
        var calls = 0
        MeasurementStubProtocol.handler = { request in
            calls += 1
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.path, "/api/measurements")
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems!
            XCTAssertEqual(query.first { $0.name == "limit" }?.value, "50")
            XCTAssertEqual(query.first { $0.name == "offset" }?.value, "50")
            return (200, "[{\"id\":17,\"date\":\"2026-10-07\",\"weight\":72.5,\"height\":175,\"body_fat\":21.2,\"muscle_mass\":30,\"waist\":80,\"chest\":95,\"arm\":32,\"thigh\":54,\"notes\":\"Após acordar\"}]")
        }
        let entries = try await client().getMeasurementEntries(offset: 50)
        XCTAssertEqual(calls, 1)
        XCTAssertEqual(entries.count, 1)
        let entry = try XCTUnwrap(entries.first)
        XCTAssertEqual(entry.id, 17)
        XCTAssertEqual(entry.date, "2026-10-07")
        XCTAssertEqual(entry.weight, 72.5)
        XCTAssertEqual(entry.height, 175)
        XCTAssertEqual(entry.bodyFat, 21.2)
        XCTAssertEqual(entry.muscleMass, 30)
        XCTAssertEqual(entry.waist, 80)
        XCTAssertEqual(entry.chest, 95)
        XCTAssertEqual(entry.arm, 32)
        XCTAssertEqual(entry.thigh, 54)
        XCTAssertEqual(entry.entry.notes, "Após acordar")
    }

    func testUpdateEncodesNullToClearFieldsAndKeepsFreshCSRFAndStableKey() async throws {
        var paths: [String] = []
        MeasurementStubProtocol.handler = { request in
            paths.append(request.url!.path)
            if request.httpMethod == "GET" { return (200, self.auth()) }
            XCTAssertEqual(request.httpMethod, "PUT")
            XCTAssertEqual(request.url?.path, "/api/measurements/17")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), "edit-17")
            let json = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            XCTAssertEqual(json["date"] as? String, "2026-10-08")
            XCTAssertEqual(json["weight"] as? Double, 73)
            for key in ["height", "body_fat", "muscle_mass", "waist", "chest", "arm", "thigh"] {
                XCTAssertTrue(json[key] is NSNull, "Clearing \(key) must send null")
            }
            XCTAssertNil(json["notes"], "Editing measurements must preserve existing notes")
            return (200, self.saved)
        }
        let result = try await client().updateMeasurementEntry(id: 17,
            entry: NewMeasurementEntry(date: "2026-10-08", weight: 73), idempotencyKey: "edit-17",
            ownerId: UUID(uuidString: "00000000-0000-0000-0000-000000000001")!)
        XCTAssertEqual(result.id, 17)
        XCTAssertEqual(paths, ["/api/check_session", "/api/measurements/17"])
    }

    func testOwnerMismatchBlocksBothUpdateAndDelete() async {
        var reads = 0
        var mutations = 0
        MeasurementStubProtocol.handler = { request in
            if request.httpMethod == "GET" { reads += 1; return (200, self.auth()) }
            mutations += 1
            return (200, self.saved)
        }
        let otherOwner = UUID(uuidString: "00000000-0000-0000-0000-000000000002")!
        do {
            _ = try await client().updateMeasurementEntry(id: 17,
                entry: NewMeasurementEntry(date: "2026-10-07", weight: 72), idempotencyKey: "edit",
                ownerId: otherOwner)
            XCTFail("Expected owner mismatch")
        } catch APIError.http(let status, _) { XCTAssertEqual(status, 401) }
        catch { XCTFail("Unexpected error: \(error)") }
        do {
            try await client().deleteMeasurementEntry(id: 17, ownerId: otherOwner)
            XCTFail("Expected owner mismatch")
        } catch APIError.http(let status, _) { XCTAssertEqual(status, 401) }
        catch { XCTFail("Unexpected error: \(error)") }
        XCTAssertEqual(reads, 2)
        XCTAssertEqual(mutations, 0)
    }

    func testDeleteAlreadyMissingRecordSucceedsWithoutReplay() async throws {
        var deletes = 0
        MeasurementStubProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, self.auth()) }
            deletes += 1
            XCTAssertEqual(request.httpMethod, "DELETE")
            XCTAssertEqual(request.url?.path, "/api/measurements/17")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh")
            return (404, "{\"error\":\"Medida não encontrada\"}")
        }
        try await client().deleteMeasurementEntry(id: 17,
            ownerId: UUID(uuidString: "00000000-0000-0000-0000-000000000001")!)
        XCTAssertEqual(deletes, 1)
    }

    func testDeleteTransportFailureRequiresExplicitRetryAndNeverReplaysAutomatically() async throws {
        var deletes = 0
        var reads = 0
        MeasurementStubProtocol.handler = { request in
            if request.httpMethod == "GET" { reads += 1; return (200, self.auth()) }
            deletes += 1
            XCTAssertEqual(request.httpMethod, "DELETE")
            XCTAssertEqual(request.url?.path, "/api/measurements/17")
            if deletes == 1 { throw URLError(.timedOut) }
            return (404, "{\"error\":\"Medida não encontrada\"}")
        }
        let api = client()
        let owner = UUID(uuidString: "00000000-0000-0000-0000-000000000001")!
        do { try await api.deleteMeasurementEntry(id: 17, ownerId: owner); XCTFail("Expected timeout") }
        catch let error as URLError { XCTAssertEqual(error.code, .timedOut) }
        XCTAssertEqual(deletes, 1)
        try await api.deleteMeasurementEntry(id: 17, ownerId: owner)
        XCTAssertEqual(deletes, 2)
        XCTAssertEqual(reads, 2)
    }

    private func client() -> FitTrackerAPI { FitTrackerAPI(baseURL: URL(string: "https://measurements.invalid/api")!, session: session) }
    private func auth() -> String { "{\"logged_in\":true,\"user\":\(user),\"csrf_token\":\"fresh\"}" }
    private func body(_ request: URLRequest) -> Data {
        if let data = request.httpBody { return data }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open(); defer { stream.close() }
        var data = Data(), buffer = [UInt8](repeating: 0, count: 1024)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count <= 0 { break }
            data.append(buffer, count: count)
        }
        return data
    }
}

private final class MeasurementStubProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            guard let handler = Self.handler else { throw URLError(.badServerResponse) }
            let (status, json) = try handler(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(json.utf8))
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() { }
}
