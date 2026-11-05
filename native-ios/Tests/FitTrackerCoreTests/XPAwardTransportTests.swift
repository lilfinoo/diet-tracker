import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class XPAwardTransportTests: XCTestCase {
    private var session: URLSession!
    private var observers: [NSObjectProtocol] = []
    private var notices: [XPAwardNotice] = []
    private var defaults: UserDefaults!
    private var defaultsSuite: String!
    private var starts: [UUID] = []
    private var startContexts: [[AnyHashable: Any]] = []

    override func setUp() {
        super.setUp()
        defaultsSuite = "FitTrackerXPTests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: defaultsSuite)!
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [XPStubProtocol.self]
        session = URLSession(configuration: config)
        observers.append(NotificationCenter.default.addObserver(forName: FitTrackerAPI.xpAwarded, object: nil, queue: nil) { [weak self] notification in
            if let notice = notification.object as? XPAwardNotice { self?.notices.append(notice) }
        })
        observers.append(NotificationCenter.default.addObserver(forName: FitTrackerAPI.xpRequestStarted, object: nil, queue: nil) { [weak self] notification in
            if let id = notification.object as? UUID { self?.starts.append(id) }
            self?.startContexts.append(notification.userInfo ?? [:])
        })
    }

    override func tearDown() {
        observers.forEach(NotificationCenter.default.removeObserver)
        session.invalidateAndCancel()
        defaults.removePersistentDomain(forName: defaultsSuite)
        XPStubProtocol.handler = nil
        super.tearDown()
    }

    private func client() -> FitTrackerAPI {
        FitTrackerAPI(baseURL: URL(string: "https://xp.example.com/api")!, session: session, xpRewardDefaults: defaults)
    }

    func testAuthoritativeSummaryAndReplayDeduplication() async throws {
        XPStubProtocol.handler = { _ in (200, """
        {"xp_gained":100,"gamification":{"total_xp":600,"level":2,"rank":"Atleta","level_xp":100,"next_level_xp":500,"next_level":3,"current_streak":1,"best_streak":1,"active_days":1,"available_protections":0,"today":{"qualified":true,"meal":false,"water":false,"workout":true,"xp":100},"days":[]}}
        """) }
        let api = client()
        let _: Reply = try await api.request("workout_sessions/7/finish", method: "POST", idempotencyKey: "finish-once", as: Reply.self)
        let _: Reply = try await api.request("workout_sessions/7/finish", method: "POST", idempotencyKey: "finish-once", as: Reply.self)
        XCTAssertEqual(notices.count, 1)
        XCTAssertEqual(notices.first?.xp, 100)
        XCTAssertEqual(notices.first?.summary?.totalXp, 600)
        XCTAssertEqual(notices.first?.requestID, starts.first)
        XCTAssertEqual(starts.count, 2)
        XCTAssertEqual(startContexts.first?["path"] as? String, "workout_sessions/7/finish")
        XCTAssertEqual(startContexts.first?["idempotencyKey"] as? String, "finish-once")
    }

    func testQueuedResultRetainsOriginAndPollingDoesNotRepeatAward() async throws {
        XPStubProtocol.handler = { request in
            request.httpMethod == "POST" ? (202, "{\"job_id\":\"abc\"}") : (200, "{\"result\":{\"xp_gained\":500}}")
        }
        let api = client()
        let _: Reply = try await api.request("diet_plans/generate", method: "POST", as: Reply.self)
        let _: Reply = try await api.request("ai/tasks/abc", as: Reply.self)
        let _: Reply = try await api.request("ai/tasks/abc", as: Reply.self)
        XCTAssertEqual(notices.count, 1)
        XCTAssertEqual(notices.first?.requestID, starts.first)
        XCTAssertEqual(notices.first?.xp, 500)
    }

    func testPersistedReplayIsSuppressedAcrossClientsButScopedToOwner() async throws {
        var owner = UUID()
        XPStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") {
                return (200, """
                {"logged_in":true,"csrf_token":"csrf","user":{"id":"\(owner.uuidString)","username":"ana","name":"Ana","is_banned":false,"is_admin":false,"is_premium":true,"plan_code":"premium","ai_trial_uses":0,"has_password":true,"is_public":false,"onboarding_status":"complete","profile_missing_fields":[],"profile_complete":true}}
                """)
            }
            return (200, "{\"xp_gained\":100}")
        }
        let first = client()
        _ = try await first.restoreSession()
        let _: Reply = try await first.request("water", method: "POST", idempotencyKey: "same-entry", as: Reply.self)
        let restarted = client()
        _ = try await restarted.restoreSession()
        let _: Reply = try await restarted.request("water", method: "POST", idempotencyKey: "same-entry", as: Reply.self)
        XCTAssertEqual(notices.count, 1)
        owner = UUID()
        let differentOwner = client()
        _ = try await differentOwner.restoreSession()
        let _: Reply = try await differentOwner.request("water", method: "POST", idempotencyKey: "same-entry", as: Reply.self)
        XCTAssertEqual(notices.count, 2)
    }

    func testFailuresAndUndecodableResponsesNeverAwardXP() async throws {
        let api = client()
        XPStubProtocol.handler = { _ in (500, "{\"xp_gained\":100}") }
        do { let _: Reply = try await api.request("water", method: "POST", as: Reply.self); XCTFail("Expected HTTP failure") } catch { }
        XPStubProtocol.handler = { _ in (200, "{\"xp_gained\":100}") }
        do { let _: RequiredReply = try await api.request("water", method: "POST", as: RequiredReply.self); XCTFail("Expected decode failure") } catch { }
        XCTAssertTrue(notices.isEmpty)
    }

    func testAutomaticRestAwardHasNoClickOriginAndAuthChangeClearsDedup() async throws {
        XPStubProtocol.handler = { _ in (200, "{\"xp_gained\":100}") }
        let api = client()
        let _: Reply = try await api.request("workouts/rest-checkin", method: "POST", idempotencyKey: "today", as: Reply.self)
        XCTAssertTrue(starts.isEmpty)
        try await api.beginAuthenticationChange()
        await api.endAuthenticationChange()
        let _: Reply = try await api.request("workouts/rest-checkin", method: "POST", idempotencyKey: "today", as: Reply.self)
        XCTAssertEqual(notices.count, 2)
    }
}

private struct Reply: Decodable { }
private struct RequiredReply: Decodable { let required: String }
private final class XPStubProtocol: URLProtocol {
    static var handler: ((URLRequest) -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let handler = Self.handler else { return }
        let (status, json) = handler(request)
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() { }
}
