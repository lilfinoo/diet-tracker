import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class WaterAPITests: XCTestCase {
    private var session: URLSession!
    private let owner = UUID(uuidString: "00000000-0000-0000-0000-000000000001")!
    private let day = """
    {"date":"2026-10-22","timezone":"America/Sao_Paulo","total_ml":300,"bottle_capacity_ml":750,
     "entries":[{"id":3,"amount_ml":300,"occurred_at":"2026-10-22T12:00:00Z"}]}
    """
    private let auth = """
    {"logged_in":true,"csrf_token":"water-csrf","user":{"id":"00000000-0000-0000-0000-000000000001","username":"ana","name":"Ana","is_banned":false,"is_admin":false,"is_premium":true,"plan_code":"premium","ai_trial_uses":0,"has_password":true,"is_public":false,"onboarding_status":"complete","profile_missing_fields":[],"profile_complete":true}}
    """

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [WaterStubProtocol.self]
        session = URLSession(configuration: config)
    }
    override func tearDown() {
        session.invalidateAndCancel(); WaterStubProtocol.handler = nil
        super.tearDown()
    }
    private func client() -> FitTrackerAPI { FitTrackerAPI(baseURL: URL(string: "https://example.com/api")!, session: session) }

    func testDayResponseAndDateQuery() async throws {
        WaterStubProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.query, "date=2026-10-22")
            return (200, self.day)
        }
        let result = try await client().getWater(date: "2026-10-22")
        XCTAssertEqual(result.totalMl, 300)
        XCTAssertEqual(result.bottleCapacityMl, 750)
        XCTAssertEqual(result.entries.first?.id, 3)
    }

    func testLostWriteAndExplicitRetryPreserveVolumeTimestampAndKey() async throws {
        let api = client()
        let pending = WaterPendingEntry(amountMl: 300, occurredAt: Date(timeIntervalSince1970: 1792670400), key: "same-water")
        let restored = try JSONDecoder().decode(WaterPendingEntry.self, from: JSONEncoder().encode(pending))
        var writes: [[String: Any]] = []
        WaterStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.auth) }
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "water-csrf")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), "same-water")
            let json = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            writes.append(json)
            if writes.count == 1 { throw URLError(.networkConnectionLost) }
            return (201, self.day)
        }
        do { _ = try await api.addWater(pending, ownerId: owner); XCTFail("Expected lost response") }
        catch let error as URLError { XCTAssertEqual(error.code, .networkConnectionLost) }
        XCTAssertEqual(writes.count, 1, "No automatic write retry")
        _ = try await api.addWater(restored, ownerId: owner)
        XCTAssertEqual(writes.count, 2)
        XCTAssertEqual(writes[0]["amount_ml"] as? Int, 300)
        XCTAssertEqual(writes[0]["occurred_at"] as? String, writes[1]["occurred_at"] as? String)
        XCTAssertEqual(writes[0].count, 2)
    }

    func testDifferentAccountNeverReceivesPendingEntry() async throws {
        var writes = 0
        WaterStubProtocol.handler = { request in
            if request.httpMethod != "GET" { writes += 1 }
            return (200, self.auth)
        }
        do { _ = try await client().addWater(WaterPendingEntry(amountMl: 200), ownerId: UUID()); XCTFail("Must reject owner mismatch") }
        catch APIError.http(let status, _) { XCTAssertEqual(status, 401) }
        XCTAssertEqual(writes, 0)
    }

    func testBottleOnlyUpdatesCapacityAndDeleteTargetsEntry() async throws {
        var paths: [String] = []
        WaterStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.auth) }
            paths.append(request.url!.path)
            if request.httpMethod == "POST" {
                let json = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Int]
                XCTAssertEqual(json, ["bottle_capacity_ml": 750])
            } else { XCTAssertEqual(request.httpMethod, "DELETE") }
            return (200, self.day)
        }
        let api = client()
        _ = try await api.saveWaterBottle(capacityMl: 750, ownerId: owner)
        _ = try await api.deleteWater(entryId: 3, ownerId: owner)
        XCTAssertEqual(paths, ["/api/water/bottle", "/api/water/3"])
    }

    func testInvalidVolumesFailBeforeNetwork() async {
        var calls = 0
        WaterStubProtocol.handler = { _ in calls += 1; return (500, "{}") }
        for amount in [0, -1, 10001] {
            do { _ = try await client().addWater(WaterPendingEntry(amountMl: amount), ownerId: owner); XCTFail("Expected validation") } catch { }
            do { _ = try await client().saveWaterBottle(capacityMl: amount, ownerId: owner); XCTFail("Expected validation") } catch { }
        }
        XCTAssertEqual(calls, 0)
    }

    private func body(_ request: URLRequest) -> Data {
        if let data = request.httpBody { return data }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open(); defer { stream.close() }
        var data = Data(); var buffer = [UInt8](repeating: 0, count: 512)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count <= 0 { break }; data.append(buffer, count: count)
        }
        return data
    }
}

private final class WaterStubProtocol: URLProtocol {
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
