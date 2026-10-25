import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class FitTrackerAPITests: XCTestCase {
    private var session: URLSession!
    private let baseURL = URL(string: "https://fittracker.invalid/api")!
    private let user = """
    {"id":"00000000-0000-0000-0000-000000000001","username":"ana","name":"Ana","email":null,
    "is_banned":false,"banned_at":null,"created_at":null,"is_admin":false,"is_premium":true,
    "plan_code":"premium_student","ai_trial_uses":0,"has_password":true,"is_public":false,
    "avatar_url":null,"badges":[],"profile_highlights":[],"onboarding_status":"complete",
    "profile_missing_fields":[],"profile_complete":true}
    """

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        config.httpShouldSetCookies = true
        config.httpCookieStorage = HTTPCookieStorage.shared
        session = URLSession(configuration: config)
        StubProtocol.handler = nil
        for cookie in HTTPCookieStorage.shared.cookies(for: baseURL) ?? [] {
            HTTPCookieStorage.shared.deleteCookie(cookie)
        }
    }

    override func tearDown() {
        session.invalidateAndCancel()
        StubProtocol.handler = nil
        for cookie in HTTPCookieStorage.shared.cookies(for: baseURL) ?? [] {
            HTTPCookieStorage.shared.deleteCookie(cookie)
        }
        super.tearDown()
    }

    func testLoginWithExistingSessionSendsFreshCSRFAndDecodesUser() async throws {
        var paths: [String] = []
        StubProtocol.handler = { request in
            paths.append(request.url!.path)
            if paths.count == 1 {
                XCTAssertNil(request.value(forHTTPHeaderField: "X-CSRF-Token"))
                return (200, self.authJSON(token: "current-token"))
            }
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "current-token")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
            let body = self.requestBody(request)
            let fields = try JSONSerialization.jsonObject(with: body) as! [String: String]
            XCTAssertEqual(fields, ["username": "ana", "password": "test-only"])
            return (200, "{\"message\":\"Login bem-sucedido\",\"user\":\(self.user),\"csrf_token\":\"rotated-token\"}")
        }
        let result = try await api().login(username: "ana", password: "test-only")
        XCTAssertEqual(paths, ["/api/check_session", "/api/login"])
        XCTAssertTrue(result.loggedIn)
        XCTAssertEqual(result.user?.name, "Ana")
        XCTAssertEqual(result.csrfToken, "rotated-token")
    }

    func testUnauthenticatedLoginDoesNotSendCSRF() async throws {
        StubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, "{\"logged_in\":false}") }
            XCTAssertNil(request.value(forHTTPHeaderField: "X-CSRF-Token"))
            return (200, "{\"user\":\(self.user),\"csrf_token\":\"new-token\"}")
        }
        let result = try await api().login(username: "ana", password: "test-only")
        XCTAssertEqual(result.csrfToken, "new-token")
    }

    func testLogoutRefreshesTokenAndReloginDoesNotReuseIt() async throws {
        var paths: [String] = []
        StubProtocol.handler = { request in
            paths.append(request.url!.path)
            switch paths.count {
            case 1: return (200, self.authJSON(token: "logout-token"))
            case 2:
                XCTAssertEqual(request.httpMethod, "POST")
                XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "logout-token")
                return (200, "{\"message\":\"Logout bem-sucedido\"}")
            case 3: return (200, "{\"logged_in\":false}")
            default:
                XCTAssertNil(request.value(forHTTPHeaderField: "X-CSRF-Token"))
                return (200, "{\"user\":\(self.user),\"csrf_token\":\"next-account-token\"}")
            }
        }
        let client = api()
        try await client.logout()
        _ = try await client.login(username: "ana", password: "test-only")
        XCTAssertEqual(paths, ["/api/check_session", "/api/logout", "/api/check_session", "/api/login"])
    }

    func testLogoutWithoutSessionDoesNotPost() async throws {
        var count = 0
        StubProtocol.handler = { _ in count += 1; return (200, "{\"logged_in\":false}") }
        try await api().logout()
        XCTAssertEqual(count, 1)
    }

    func testRestorationKeepsOSCookieStorageAndFalse200IsNotAnError() async throws {
        let cookie = HTTPCookie(properties: [.name: "session", .value: "current-cookie",
                                           .domain: "fittracker.invalid", .path: "/", .secure: "TRUE"])!
        HTTPCookieStorage.shared.setCookie(cookie)
        // URLProtocol intercepts before the normal transport; inspect its configured
        // cookie store rather than claiming this stub validates cookies on the wire.
        let production = FitTrackerAPI.makeSession()
        defer { production.invalidateAndCancel() }
        XCTAssertTrue(production.configuration.httpShouldSetCookies)
        XCTAssertTrue(production.configuration.httpCookieStorage === HTTPCookieStorage.shared)
        XCTAssertTrue(production.configuration.httpCookieStorage?.cookies(for: baseURL)?.contains(where: {
            $0.name == "session" && $0.value == "current-cookie"
        }) == true)
        StubProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/check_session")
            XCTAssertNil(request.value(forHTTPHeaderField: "X-CSRF-Token"))
            return (200, "{\"logged_in\":false}")
        }
        let result = try await api().restoreSession()
        XCTAssertFalse(result.loggedIn)
        XCTAssertNil(result.user)
        XCTAssertNil(result.csrfToken)
    }

    func testCSRF403IsDistinctAndLogoutIsNotReplayed() async throws {
        var count = 0
        StubProtocol.handler = { _ in
            count += 1
            if count == 1 { return (200, self.authJSON(token: "token")) }
            return (403, "{\"error\":\"Token CSRF inválido.\"}")
        }
        do { try await api().logout(); XCTFail("Expected CSRF failure") }
        catch APIError.csrfMismatch { }
        catch { XCTFail("Unexpected error: \(error)") }
        XCTAssertEqual(count, 2)
    }

    func test401AndOther403AreNotReplayedOrMisclassified() async throws {
        for status in [401, 403] {
            var count = 0
            StubProtocol.handler = { _ in count += 1; return (status, "{\"error\":\"Acesso negado\"}") }
            do { _ = try await api().restoreSession(); XCTFail("Expected HTTP failure") }
            catch APIError.http(let actual, let message) {
                XCTAssertEqual(actual, status)
                XCTAssertEqual(message, "Acesso negado")
            } catch { XCTFail("Unexpected error: \(error)") }
            XCTAssertEqual(count, 1)
        }
    }

    func testNetworkFailureStopsLoginBeforeMutation() async throws {
        var count = 0
        StubProtocol.handler = { _ in count += 1; throw URLError(.notConnectedToInternet) }
        do { _ = try await api().login(username: "ana", password: "test-only"); XCTFail("Expected network failure") }
        catch let error as URLError { XCTAssertEqual(error.code, .notConnectedToInternet) }
        catch { XCTFail("Unexpected error: \(error)") }
        XCTAssertEqual(count, 1)
    }

    func testAuthenticatedResponseWithoutTokenStopsLogin() async throws {
        var count = 0
        StubProtocol.handler = { _ in count += 1; return (200, "{\"logged_in\":true,\"user\":\(self.user)}") }
        do { _ = try await api().login(username: "ana", password: "test-only"); XCTFail("Expected invalid response") }
        catch APIError.invalidResponse { }
        catch { XCTFail("Unexpected error: \(error)") }
        XCTAssertEqual(count, 1)
    }

    func testProfileCanBeAbsentForOnboarding() async throws {
        StubProtocol.handler = { request in
            XCTAssertEqual(request.url!.path, "/api/profile")
            return (200, "{\"profile\":null,\"onboarding_status\":\"new\",\"profile_missing_fields\":[\"goal\"],\"profile_complete\":false}")
        }
        let result = try await api().getProfile()
        XCTAssertNil(result.profile)
        XCTAssertEqual(result.profileMissingFields, ["goal"])
    }

    func testProfileDecodesBackendIDsAndOptionalMeasurements() async throws {
        StubProtocol.handler = { _ in
            (200, """
            {"profile":{"id":7,"user_id":"00000000-0000-0000-0000-000000000001",
            "age":30,"gender":"masculino","goal":"ganho_massa","activity_level":"moderado",
            "dietary_restrictions":null,"weight":80.5,"height":180,"timezone":"America/Sao_Paulo",
            "is_public":false,"avatar_url":null,"accepts_external_workout_reviews":true,
            "accepts_external_diet_reviews":true,"current_diet_plan_id":11,"current_workout_plan_id":12,
            "pending_workout_plan_id":null,"workout_schedule_effective_from":null,
            "workout_schedule_timezone":null,"created_at":null,"updated_at":null},
            "onboarding_status":"complete","profile_missing_fields":[],"profile_complete":true}
            """)
        }
        let result = try await api().getProfile()
        XCTAssertEqual(result.profile?.id, 7)
        XCTAssertEqual(result.profile?.currentDietPlanId, 11)
        XCTAssertEqual(result.profile?.currentWorkoutPlanId, 12)
        XCTAssertEqual(result.profile?.weight, 80.5)
        XCTAssertNil(result.profile?.dietaryRestrictions)
        XCTAssertTrue(result.profileComplete)
    }

    private func api() -> FitTrackerAPI { FitTrackerAPI(baseURL: baseURL, session: session) }
    private func authJSON(token: String) -> String {
        "{\"logged_in\":true,\"user\":\(user),\"csrf_token\":\"\(token)\"}"
    }
    private func requestBody(_ request: URLRequest) -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open()
        defer { stream.close() }
        var result = Data()
        var buffer = [UInt8](repeating: 0, count: 512)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count <= 0 { break }
            result.append(buffer, count: count)
        }
        return result
    }
}

private final class StubProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            guard let handler = Self.handler else { throw URLError(.badServerResponse) }
            let (status, json) = try handler(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                           headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(json.utf8))
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() { }
}
