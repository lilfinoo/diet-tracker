import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

@MainActor
final class WorkoutWeekDataCacheTests: XCTestCase {
    private var session: URLSession!
    private var cache: WorkoutWeekDataCache!
    private let plan = "{\"id\":7,\"title\":\"Semana\",\"days\":[]}"
    private let activities = "{\"items\":[],\"limit\":20,\"offset\":0,\"has_more\":false}"

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [WeekCacheProtocol.self]
        session = URLSession(configuration: config)
        cache = WorkoutWeekDataCache(api: FitTrackerAPI(baseURL: URL(string: "https://example.com/api")!, session: session))
    }

    override func tearDown() {
        session.invalidateAndCancel()
        WeekCacheProtocol.handler = nil
        super.tearDown()
    }

    func testRevisitingDaysReusesPlanAndHistory() async throws {
        var paths: [String] = []
        WeekCacheProtocol.handler = { request in
            paths.append(request.url!.path)
            return (200, request.url!.path.hasSuffix("activities") ? self.activities : self.plan)
        }
        _ = try await cache.loadPlan(id: 7)
        _ = try await cache.loadActivities()
        _ = try await cache.loadPlan(id: 7)
        _ = try await cache.loadActivities()
        XCTAssertEqual(cache.cachedPlan(id: 7)?.title, "Semana")
        XCTAssertNil(cache.cachedPlan(id: 8))
        XCTAssertEqual(paths, ["/api/workout_plans/7", "/api/activities"])
    }

    func testConcurrentSelectionsShareRequests() async throws {
        var calls = 0
        WeekCacheProtocol.handler = { _ in calls += 1; return (200, self.plan) }
        async let first = cache.loadPlan(id: 7)
        async let second = cache.loadPlan(id: 7)
        _ = try await (first, second)
        XCTAssertEqual(calls, 1)
    }

    func testRefreshInvalidatesPlanAndCompletionStatus() async throws {
        var calls = 0
        WeekCacheProtocol.handler = { request in
            calls += 1
            return (200, request.url!.path.hasSuffix("activities") ? self.activities : self.plan)
        }
        _ = try await cache.loadPlan(id: 7)
        _ = try await cache.loadActivities()
        cache.invalidate()
        XCTAssertNil(cache.cachedPlan(id: 7))
        XCTAssertNil(cache.activities)
        _ = try await cache.loadPlan(id: 7)
        _ = try await cache.loadActivities()
        XCTAssertEqual(calls, 4)
    }

    func testFailedLoadCanBeRetried() async throws {
        WeekCacheProtocol.handler = { _ in (500, "{}") }
        do { _ = try await cache.loadPlan(id: 7); XCTFail("Expected failure") } catch { }
        XCTAssertNil(cache.cachedPlan(id: 7))
        WeekCacheProtocol.handler = { _ in (200, self.plan) }
        let result = try await cache.loadPlan(id: 7)
        XCTAssertEqual(result.id, 7)
    }

    func testInvalidatedInFlightResponseCannotRestoreOldCache() async throws {
        let started = expectation(description: "Request started")
        let release = DispatchSemaphore(value: 0)
        WeekCacheProtocol.handler = { _ in
            started.fulfill()
            _ = release.wait(timeout: .now() + 5)
            return (200, self.plan)
        }
        let request = Task { try await cache.loadPlan(id: 7) }
        await fulfillment(of: [started], timeout: 2)
        cache.invalidate()
        release.signal()
        _ = try await request.value
        XCTAssertNil(cache.cachedPlan(id: 7))
    }
}

private final class WeekCacheProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, body) = try Self.handler!(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() { }
}
