import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class PaywallAPITests: XCTestCase {
    private var session: URLSession!
    private let auth = """
    {"logged_in":true,"csrf_token":"paywall-csrf","user":{"id":"00000000-0000-0000-0000-000000000001","username":"ana","name":"Ana","is_banned":false,"is_admin":false,"is_premium":false,"plan_code":"free","ai_trial_uses":0,"has_password":true,"is_public":false,"onboarding_status":"complete","profile_missing_fields":[],"profile_complete":true}}
    """

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [PaywallProtocol.self]
        session = URLSession(configuration: config)
    }

    override func tearDown() {
        session.invalidateAndCancel()
        PaywallProtocol.handler = nil
        super.tearDown()
    }

    private func client() -> FitTrackerAPI {
        FitTrackerAPI(baseURL: URL(string: "https://paywall.invalid/api")!, session: session)
    }

    func testExperimentUsesSessionCSRFAndServerAssignment() async throws {
        var paths: [String] = []
        PaywallProtocol.handler = { request in
            paths.append(request.url!.path)
            if request.url!.path.hasSuffix("check_session") { return (200, self.auth) }
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "paywall-csrf")
            let body = try self.json(request)
            XCTAssertEqual(body as? [String: String], ["surface": "diet_plans", "platform": "ios"])
            return (200, "{\"experiment\":{\"experiment_id\":\"paywall_message_v1\",\"variant\":\"B\"}}")
        }
        let experiment = try await client().paywallExperiment(surface: "diet_plans")
        XCTAssertEqual(experiment?.experimentId, "paywall_message_v1")
        XCTAssertEqual(experiment?.variant, "B")
        XCTAssertEqual(paths, ["/api/check_session", "/api/analytics/paywall"])
    }

    func testNullExperimentDoesNotInventAssignment() async throws {
        PaywallProtocol.handler = { request in
            (200, request.url!.path.hasSuffix("check_session") ? self.auth : "{\"experiment\":null}")
        }
        let experiment = try await client().paywallExperiment(surface: "app_open")
        XCTAssertNil(experiment)
    }

    func testEventsContainOnlyAllowedPropertiesAndNoClientAttribution() async throws {
        var events: [[String: Any]] = []
        PaywallProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.auth) }
            XCTAssertEqual(request.url!.path, "/api/analytics/events")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "paywall-csrf")
            let body = try self.json(request)
            XCTAssertEqual(Set(body.keys), ["events"])
            let event = try XCTUnwrap((body["events"] as? [[String: Any]])?.first)
            XCTAssertEqual(Set(event.keys), ["name", "anonymous_id", "properties"])
            let id = try XCTUnwrap(event["anonymous_id"] as? String)
            XCTAssertNotNil(UUID(uuidString: id))
            XCTAssertEqual(id.split(separator: "-")[2].first, "4")
            events.append(event)
            return (200, "{\"accepted\":1}")
        }
        let api = client()
        try await api.trackPaywallView(surface: "workout_plans")
        try await api.trackPaywallPurchase(planCode: "premium_monthly")
        XCTAssertEqual(events.count, 2)
        XCTAssertEqual(events[0]["name"] as? String, "paywall_viewed")
        XCTAssertEqual(events[0]["properties"] as? [String: String], ["surface": "workout_plans"])
        XCTAssertEqual(events[1]["name"] as? String, "paywall_cta_clicked")
        XCTAssertEqual(events[1]["properties"] as? [String: String], ["plan_code": "premium_monthly", "platform": "ios"])
    }

    func testLoggedOutSessionDoesNotSendAnalytics() async throws {
        PaywallProtocol.handler = { request in
            XCTAssertEqual(request.url!.path, "/api/check_session")
            return (200, "{\"logged_in\":false}")
        }
        do {
            try await client().trackPaywallView(surface: "app_open")
            XCTFail("Expected authentication failure")
        } catch APIError.http(let status, _) { XCTAssertEqual(status, 401) }
    }

    func testControlCopyAndFallbackRemainOriginal() {
        let control = PaywallMessage.forSurface("photos", variant: "A")
        XCTAssertEqual(control.title, "Mais foco na sua evolução.")
        XCTAssertEqual(control.detail, "Treino e alimentação personalizados para acompanhar sua rotina.")
        XCTAssertEqual(control.benefits, ["Mais gerações de treino e dieta", "Mais análises de refeições por foto", "Ajustes de planos com IA"])
        XCTAssertEqual(PaywallMessage.forSurface("diet_plans", variant: nil), control)
        XCTAssertEqual(PaywallMessage.forSurface("app_open", variant: "unexpected"), control)
    }

    func testTreatmentCopyMatchesRequestedAction() {
        XCTAssertTrue(PaywallMessage.forSurface("photos", variant: "B").title.contains("foto"))
        XCTAssertTrue(PaywallMessage.forSurface("diet_plans", variant: "B").benefits.contains("Alimentos que você gosta"))
        XCTAssertFalse(PaywallMessage.forSurface("diet_plans", variant: "B").detail.contains("texto"))
        XCTAssertTrue(PaywallMessage.forSurface("workout_plans", variant: "B").benefits.contains("Ajustes do treino por texto com IA"))
        XCTAssertTrue(PaywallMessage.forSurface("chat", variant: "B").title.contains("conversa"))
        XCTAssertEqual(PaywallMessage.forSurface("premium", variant: "B"), PaywallMessage.forSurface("app_open", variant: "B"))
        XCTAssertFalse(PaywallMessage.forSurface("unknown", variant: "B").benefits.isEmpty)
    }

    private func json(_ request: URLRequest) throws -> [String: Any] {
        let data: Data
        if let body = request.httpBody { data = body }
        else if let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 1024)
            var result = Data()
            while stream.hasBytesAvailable {
                let count = stream.read(&buffer, maxLength: buffer.count)
                guard count > 0 else { break }
                result.append(buffer, count: count)
            }
            data = result
        } else { throw APIError.invalidResponse }
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }
}

private final class PaywallProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, body) = try Self.handler!(request)
            client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() { }
}
