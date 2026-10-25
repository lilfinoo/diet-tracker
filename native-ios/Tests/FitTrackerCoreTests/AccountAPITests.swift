import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class AccountAPITests: XCTestCase {
    private var session: URLSession!
    private let user = """
    {"id":"00000000-0000-0000-0000-000000000001","username":"ana","name":"Ana","email":null,"is_banned":false,"is_admin":false,"is_premium":false,"plan_code":"free","ai_trial_uses":0,"has_password":true,"is_public":false,"onboarding_status":"pending","profile_missing_fields":[],"profile_complete":false}
    """
    private var authenticatedJSON: String { "{\"logged_in\":true,\"csrf_token\":\"fresh\",\"user\":\(user)}" }
    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [AccountProtocol.self]
        session = URLSession(configuration: config)
    }
    override func tearDown() { session.invalidateAndCancel(); AccountProtocol.handler = nil; AccountProtocol.stopped = nil; super.tearDown() }
    private func api() -> FitTrackerAPI { FitTrackerAPI(baseURL: URL(string: "https://account.invalid/api")!, session: session) }

    func testLinkSocialIdentityUsesAuthenticatedSessionAndCredentialProof() async throws {
        AccountProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.authenticatedJSON) }
            XCTAssertEqual(request.url!.path, "/api/account/identities/google")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh")
            let fields = try self.fields(request)
            XCTAssertEqual(fields["credential"] as? String, "verified-id-token")
            XCTAssertNil(fields["username"])
            XCTAssertNil(fields["referral_code"])
            return (200, "{\"providers\":[\"google\"]}")
        }
        let result = try await api().linkSocialIdentity(provider: .google, credential: "verified-id-token")
        XCTAssertEqual(result.providers, ["google"])
    }
    func testSocialFirstLoginRetainsSignupTokenWithoutAuthenticatedSession() async throws {
        AccountProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, "{\"logged_in\":false}") }
            XCTAssertEqual(request.url!.path, "/api/auth/google")
            XCTAssertEqual(try self.fields(request)["credential"] as? String, "provider-id-token")
            return (409, "{\"error\":\"Nome de usuário necessário\",\"code\":\"username_required\",\"signup_token\":\"signed-signup\"}")
        }
        do { _ = try await api().socialLogin(provider: .google, credential: "provider-id-token"); XCTFail("signup required") }
        catch APIError.socialSignupRequired(let token) { XCTAssertEqual(token, "signed-signup") }
    }
    func testSocialSignupSendsExplicitConsentAndFreshCSRF() async throws {
        AccountProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.authenticatedJSON) }
            XCTAssertEqual(request.url!.path, "/api/auth/apple")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh")
            let fields = try self.fields(request)
            XCTAssertEqual(fields["signup_token"] as? String, "signed-signup")
            XCTAssertEqual(fields["name"] as? String, "ana")
            let handle = try XCTUnwrap(fields["username"] as? String)
            XCTAssertNotNil(handle.range(of: "^user_[0-9a-f]{32}$", options: .regularExpression))
            XCTAssertEqual(fields["ai_consent"] as? Bool, false)
            XCTAssertEqual(fields["ai_consent_version"] as? String, "current")
            XCTAssertNil(fields["password"])
            XCTAssertNil(fields["referral_code"])
            return (201, "{\"user\":\(self.user),\"csrf_token\":\"new\"}")
        }
        let response = try await api().completeSocialSignup(provider: .apple, token: "signed-signup", name: "ana", aiConsent: false, aiConsentVersion: "current")
        XCTAssertTrue(response.loggedIn)
    }
    func testLegacySignupAcceptsRepeatedLongNamesForBothProviders() async throws {
        let name = String(repeating: "Ana Júlia ", count: 12)
        var handles: [String] = []
        AccountProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, "{\"logged_in\":false}") }
            let fields = try self.fields(request)
            guard let handle = fields["username"] as? String, !handle.isEmpty, handle.count <= 80 else {
                return (400, "{\"error\":\"Nome de usuário deve ter entre 1 e 80 caracteres\"}")
            }
            handles.append(handle)
            XCTAssertEqual(fields["name"] as? String, name)
            XCTAssertFalse(handle.contains("Ana"))
            XCTAssertEqual(fields["ai_consent"] as? Bool, false)
            return (201, "{\"user\":\(self.user),\"csrf_token\":\"new\"}")
        }
        for provider in [SocialProvider.apple, .google] {
            let result = try await api().completeSocialSignup(provider: provider, token: "signed-\(provider.rawValue)", name: name, aiConsent: false, aiConsentVersion: "current")
            XCTAssertTrue(result.loggedIn)
        }
        XCTAssertEqual(handles.count, 2)
        XCTAssertEqual(Set(handles).count, 2)
    }
    func testSocialSignupSendsNormalizedReferralOnlyOnCompletionForBothProviders() async throws {
        var paths: [String] = []
        AccountProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.authenticatedJSON) }
            paths.append(request.url!.path)
            let fields = try self.fields(request)
            if fields["signup_token"] != nil {
                XCTAssertEqual(fields["referral_code"] as? String, "FITABC12")
            } else {
                XCTAssertNil(fields["referral_code"], "Login and linking cannot attribute invitations")
            }
            if request.url!.path.contains("identities") { return (200, "{\"providers\":[\"apple\",\"google\"]}") }
            return (200, "{\"user\":\(self.user),\"csrf_token\":\"new\"}")
        }
        for provider in [SocialProvider.apple, .google] {
            let client = api()
            _ = try await client.completeSocialSignup(provider: provider, token: "signup", name: "Ana", aiConsent: false, aiConsentVersion: "current", referralCode: " \nfitabc12\t ")
            _ = try await client.socialLogin(provider: provider, credential: "verified")
            _ = try await client.linkSocialIdentity(provider: provider, credential: "verified")
        }
        XCTAssertEqual(paths.count, 6)
    }
    func testSocialSignupOmitsBlankReferralForBothProviders() async throws {
        var signups = 0
        AccountProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, "{\"logged_in\":false}") }
            signups += 1
            XCTAssertNil(try self.fields(request)["referral_code"])
            return (201, "{\"user\":\(self.user),\"csrf_token\":\"new\"}")
        }
        for provider in [SocialProvider.apple, .google] {
            _ = try await api().completeSocialSignup(provider: provider, token: "signup", name: "Ana", aiConsent: false, aiConsentVersion: "current", referralCode: " \n\t ")
        }
        XCTAssertEqual(signups, 2)
    }
    func testAppleLoginSendsChallengeAndAuthorizationCode() async throws {
        AccountProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, "{\"logged_in\":false}") }
            if request.url!.path.hasSuffix("challenge") { XCTAssertEqual(request.httpMethod, "POST"); return (200, "{\"nonce\":\"server-nonce\"}") }
            let fields = try self.fields(request)
            XCTAssertEqual(fields["nonce"] as? String, "server-nonce")
            XCTAssertEqual(fields["authorization_code"] as? String, "single-use-code")
            return (200, "{\"user\":\(self.user),\"csrf_token\":\"new\"}")
        }
        let client = api(); let challenge = try await client.appleAuthChallenge()
        _ = try await client.socialLogin(provider: .apple, credential: "identity-token", nonce: challenge.nonce, authorizationCode: "single-use-code")
    }
    func testRegistrationPreservesExplicitDeclinedConsentAndVersion() async throws {
        AccountProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, "{\"logged_in\":false}") }
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url!.path, "/api/register")
            let fields = try self.fields(request)
            XCTAssertEqual(fields["ai_consent"] as? Bool, false)
            XCTAssertEqual(fields["ai_consent_version"] as? String, "current")
            XCTAssertNil(fields["referral_code"])
            XCTAssertNil(request.value(forHTTPHeaderField: "X-CSRF-Token"))
            return (201, "{\"user\":\(self.user),\"csrf_token\":\"new\"}")
        }
        let result = try await api().register(Registration(username: "ana", password: "test-only-password", name: "Ana", email: nil, aiConsent: false, aiConsentVersion: "current"))
        XCTAssertEqual(result.user?.username, "ana")
    }
    func testRegistrationSendsNormalizedReferralAndOmitsBlankCode() async throws {
        var referrals: [String?] = []
        AccountProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, "{\"logged_in\":false}") }
            XCTAssertEqual(request.url!.path, "/api/register")
            referrals.append(try self.fields(request)["referral_code"] as? String)
            return (201, "{\"user\":\(self.user),\"csrf_token\":\"new\"}")
        }
        for code in [" \nfitabc12\t ", " \n\t "] {
            _ = try await api().register(Registration(username: "ana", password: "test-only-password", name: "Ana", email: nil, aiConsent: false, aiConsentVersion: "current", referralCode: code))
        }
        XCTAssertEqual(referrals, ["FITABC12", nil])
    }
    func testReferralStatusDecodesCurrentMonthProgressAndRewardWithoutBankedBonuses() async throws {
        let client = api()
        AccountProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url!.path, "/api/referrals")
            XCTAssertNil(request.httpBody)
            return (200, "{\"code\":\"FITABC12\",\"qualified_invites\":300,\"rewarded_this_month\":true,\"period\":\"2026-10\",\"period_ends_at\":\"2026-11-01T03:00:00Z\",\"target\":3,\"progress\":3,\"premium_until\":\"2026-11-25T12:00:00Z\"}")
        }
        let rewarded = try await client.referralStatus()
        XCTAssertEqual(rewarded.code, "FITABC12")
        XCTAssertEqual(rewarded.qualifiedInvites, 300)
        XCTAssertTrue(rewarded.rewardedThisMonth)
        XCTAssertEqual(rewarded.period, "2026-10")
        XCTAssertEqual(rewarded.periodEndsAt, "2026-11-01T03:00:00Z")
        XCTAssertEqual(rewarded.target, 3)
        XCTAssertEqual(rewarded.progress, 3)
        XCTAssertEqual(rewarded.premiumUntil, "2026-11-25T12:00:00Z")
        AccountProtocol.handler = { _ in
            (200, "{\"code\":\"FITABC12\",\"qualified_invites\":0,\"rewarded_this_month\":false,\"period\":\"2026-11\",\"period_ends_at\":\"2026-12-01T03:00:00Z\",\"target\":3,\"progress\":0,\"premium_until\":null}")
        }
        let nextMonth = try await client.referralStatus()
        XCTAssertEqual(nextMonth.period, "2026-11")
        XCTAssertEqual(nextMonth.qualifiedInvites, 0)
        XCTAssertEqual(nextMonth.progress, 0)
        XCTAssertFalse(nextMonth.rewardedThisMonth)
        XCTAssertNil(nextMonth.premiumUntil)
    }
    func testProfilePatchOmitsUnchangedMeasurements() async throws {
        AccountProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.authenticatedJSON) }
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh")
            let fields = try self.fields(request)
            XCTAssertNil(fields["weight"]); XCTAssertNil(fields["height"])
            XCTAssertEqual(fields["goal"] as? String, "manter peso")
            return (200, "{\"profile\":null,\"onboarding_status\":\"pending\",\"profile_missing_fields\":[],\"profile_complete\":false}")
        }
        _ = try await api().updateProfile(ProfileChanges(age: nil, gender: nil, goal: "manter peso", activityLevel: nil, dietaryRestrictions: nil, weight: nil, height: nil))
    }
    func testConsentRevocationSendsExplicitFalseAndFreshCSRF() async throws {
        AccountProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.authenticatedJSON) }
            XCTAssertEqual(request.httpMethod, "PUT")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh")
            XCTAssertEqual(try self.fields(request)["ai_consent"] as? Bool, false)
            return (200, "{\"versions\":{\"ai\":{\"version\":\"v2\"}},\"ai\":{\"accepted\":false,\"version\":null}}")
        }
        let result = try await api().updateConsent(granted: false, version: "v2")
        XCTAssertFalse(result.ai.accepted)
    }
    func testDeletionPassesExactConfirmationAndDoesNotReplayRejection() async throws {
        var deletes = 0
        AccountProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.authenticatedJSON) }
            deletes += 1
            XCTAssertEqual(request.httpMethod, "DELETE")
            let fields = try self.fields(request)
            XCTAssertEqual(fields["username"] as? String, "ana")
            XCTAssertEqual(fields["confirm_delete"] as? Bool, true)
            return (409, "{\"error\":\"Assinatura ativa\"}")
        }
        do { try await api().deleteAccount(username: "ana", password: "test-only"); XCTFail("must fail") }
        catch APIError.http(let status, _) { XCTAssertEqual(status, 409) }
        XCTAssertEqual(deletes, 1)
    }
    func testFailedLogoutRemovesOnlyServerCookies() async throws {
        let own = HTTPCookie(properties: [.name: "session", .value: "old", .domain: "account.invalid", .path: "/"])!
        let other = HTTPCookie(properties: [.name: "session", .value: "unrelated", .domain: "other.invalid", .path: "/"])!
        let store = session.configuration.httpCookieStorage!
        store.setCookie(own); store.setCookie(other)
        defer { store.deleteCookie(own); store.deleteCookie(other) }
        AccountProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.authenticatedJSON) }
            throw URLError(.notConnectedToInternet)
        }
        do { try await api().logout(); XCTFail("must fail") } catch { }
        XCTAssertFalse(store.cookies?.contains(where: { $0.domain == "account.invalid" }) ?? false)
        XCTAssertTrue(store.cookies?.contains(where: { $0.domain == "other.invalid" }) ?? false)
    }
    func testLogoutCancelsPendingResponseBeforeClearingCookie() async throws {
        let started = expectation(description: "profile request started")
        let stopped = expectation(description: "profile transport cancelled")
        AccountProtocol.stopped = { stopped.fulfill() }
        AccountProtocol.handler = { request in
            switch request.url!.lastPathComponent {
            case "profile": started.fulfill(); return (-1, "")
            case "check_session": return (200, self.authenticatedJSON)
            default: return (200, "{\"message\":\"ok\"}")
            }
        }
        let client = api()
        let pending = Task { try await client.getProfile() }
        await fulfillment(of: [started], timeout: 2)
        try await client.logout()
        await fulfillment(of: [stopped], timeout: 2)
        do { _ = try await pending.value; XCTFail("old request must not complete") } catch { }
    }

    private func fields(_ request: URLRequest) throws -> [String: Any] {
        var data = request.httpBody ?? Data()
        if let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 1024)
            while stream.hasBytesAvailable { let count = stream.read(&buffer, maxLength: buffer.count); if count <= 0 { break }; data.append(buffer, count: count) }
        }
        return try JSONSerialization.jsonObject(with: data) as! [String: Any]
    }
}
private final class AccountProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, String))?
    static var stopped: (() -> Void)?
    private var heldRequestStopped: (() -> Void)?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, json) = try Self.handler!(request)
            if status == -1 { heldRequestStopped = Self.stopped; return }
            client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(json.utf8)); client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {
        let callback = heldRequestStopped
        heldRequestStopped = nil
        callback?()
    }
}
