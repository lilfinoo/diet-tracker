import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class AuthPreflightResilienceTests: XCTestCase {
    private var session: URLSession!
    private let configurationJSON = "{\"apple_enabled\":true,\"google_client_id\":\"test-client\",\"legal\":{\"ai\":{\"version\":\"v1\"}}}"

    override func setUp() {
        super.setUp()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [AuthPreflightProtocol.self]
        session = URLSession(configuration: configuration)
        AuthPreflightProtocol.handler = nil
    }

    override func tearDown() {
        session.invalidateAndCancel()
        AuthPreflightProtocol.handler = nil
        super.tearDown()
    }

    func testConfigurationWaitsForDelayedHostUsingExtendedTimeout() async throws {
        AuthPreflightProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/auth/config")
            XCTAssertEqual(request.timeoutInterval, 90, accuracy: 0.1)
            return (200, self.configurationJSON, 0.2)
        }
        let configuration = try await api().authConfiguration()
        XCTAssertTrue(configuration.appleEnabled)
        XCTAssertEqual(configuration.googleClientId, "test-client")
    }

    func testSafePreflightRetriesTransientGatewayOnce() async throws {
        for status in [502, 503, 504] {
            var count = 0
            AuthPreflightProtocol.handler = { request in
                count += 1
                XCTAssertEqual(request.httpMethod, "GET")
                return (count == 1 ? status : 200, count == 1 ? "{}" : "{\"logged_in\":false}", 0)
            }
            let result = try await api().restoreSession()
            XCTAssertFalse(result.loggedIn)
            XCTAssertEqual(count, 2)
        }
    }

    func testSafePreflightRetriesTransportTimeoutOnce() async throws {
        var count = 0
        AuthPreflightProtocol.handler = { _ in
            count += 1
            if count == 1 { throw URLError(.timedOut) }
            return (200, self.configurationJSON, 0)
        }
        _ = try await api().authConfiguration()
        XCTAssertEqual(count, 2)
    }

    func testRepeatedGatewayFailureIsBounded() async throws {
        var count = 0
        AuthPreflightProtocol.handler = { _ in count += 1; return (503, "{}", 0) }
        do { _ = try await api().authConfiguration(); XCTFail("Expected unavailable host") }
        catch APIError.http(let status, _) { XCTAssertEqual(status, 503) }
        XCTAssertEqual(count, 2)
    }

    func testSocialPostTimeoutAndGatewayFailureAreNeverReplayed() async throws {
        for networkFailure in [false, true] {
            var posts = 0
            AuthPreflightProtocol.handler = { request in
                if request.httpMethod == "GET" { return (200, "{\"logged_in\":false}", 0) }
                posts += 1
                XCTAssertEqual(request.timeoutInterval, 30, accuracy: 0.1)
                if networkFailure { throw URLError(.timedOut) }
                return (503, "{}", 0)
            }
            do {
                _ = try await api().completeSocialSignup(provider: .apple, token: "test-token", name: "ana", aiConsent: true, aiConsentVersion: "v1")
                XCTFail("Expected failed write")
            } catch let error as URLError { XCTAssertTrue(networkFailure); XCTAssertEqual(error.code, .timedOut) }
            catch APIError.http(let status, _) { XCTAssertFalse(networkFailure); XCTAssertEqual(status, 503) }
            XCTAssertEqual(posts, 1)
        }
    }

    func testPlanGenerationAllowsFallbackTimeWithoutReplayingThePost() async throws {
        for path in ["diet_plans/generate", "workout_plans/generate"] {
            for networkFailure in [false, true] {
                var count = 0
                AuthPreflightProtocol.handler = { request in
                    count += 1
                    XCTAssertEqual(request.httpMethod, "POST")
                    XCTAssertEqual(request.timeoutInterval, 180, accuracy: 0.1)
                    XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Providers"), "gemini,openai")
                    if networkFailure { throw URLError(.timedOut) }
                    return (503, "{}", 0)
                }
                do {
                    let _: EmptyAuthResponse = try await api().request(path, method: "POST", as: EmptyAuthResponse.self)
                    XCTFail("Expected failed generation")
                } catch let error as URLError {
                    XCTAssertTrue(networkFailure)
                    XCTAssertEqual(error.code, .timedOut)
                } catch APIError.http(let status, _) {
                    XCTAssertFalse(networkFailure)
                    XCTAssertEqual(status, 503)
                }
                XCTAssertEqual(count, 1)
            }
        }
    }

    func testRegularReadDoesNotRetryOrExtendTimeout() async throws {
        var count = 0
        AuthPreflightProtocol.handler = { request in
            count += 1
            XCTAssertEqual(request.timeoutInterval, 30, accuracy: 0.1)
            return (503, "{}", 0)
        }
        do { _ = try await api().getProfile(); XCTFail("Expected unavailable host") }
        catch APIError.http(let status, _) { XCTAssertEqual(status, 503) }
        XCTAssertEqual(count, 1)
    }

    func testCancellationDuringBackoffPreventsRetry() async throws {
        let started = expectation(description: "preflight started")
        var count = 0
        AuthPreflightProtocol.handler = { _ in count += 1; started.fulfill(); return (503, "{}", 0) }
        let client = api()
        let task = Task { try await client.authConfiguration() }
        await fulfillment(of: [started], timeout: 2)
        try await Task.sleep(nanoseconds: 100_000_000)
        task.cancel()
        do { _ = try await task.value; XCTFail("Expected cancellation") }
        catch is CancellationError { }
        catch let error as URLError { XCTAssertEqual(error.code, .cancelled) }
        XCTAssertEqual(count, 1)
    }

    func testAuthenticationChangeDuringBackoffDiscardsOldPreflight() async throws {
        let started = expectation(description: "configuration started")
        var configurationCalls = 0
        AuthPreflightProtocol.handler = { request in
            if request.url!.path.hasSuffix("auth/config") {
                configurationCalls += 1
                started.fulfill()
                return (503, "{}", 0)
            }
            return (200, "{\"logged_in\":false}", 0)
        }
        let client = api()
        let task = Task { try await client.authConfiguration() }
        await fulfillment(of: [started], timeout: 2)
        try await Task.sleep(nanoseconds: 100_000_000)
        try await client.logout()
        do { _ = try await task.value; XCTFail("Expected stale preflight cancellation") }
        catch is CancellationError { }
        XCTAssertEqual(configurationCalls, 1)
    }

    private func api() -> FitTrackerAPI {
        FitTrackerAPI(baseURL: URL(string: "https://auth-preflight.invalid/api")!, session: session)
    }
}

private struct EmptyAuthResponse: Decodable {}

private final class AuthPreflightProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, String, TimeInterval))?
    private var delivery: DispatchWorkItem?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            guard let handler = Self.handler else { throw URLError(.badServerResponse) }
            let (status, json, delay) = try handler(request)
            let work = DispatchWorkItem { [weak self] in
                guard let self, self.delivery?.isCancelled == false else { return }
                let response = HTTPURLResponse(url: self.request.url!, statusCode: status, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
                self.client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
                self.client?.urlProtocol(self, didLoad: Data(json.utf8))
                self.client?.urlProtocolDidFinishLoading(self)
            }
            delivery = work
            DispatchQueue.global().asyncAfter(deadline: .now() + delay, execute: work)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() { delivery?.cancel() }
}
