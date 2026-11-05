import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public struct XPAwardNotice: Sendable {
    public let xp: Int
    public let requestID: UUID
    public let summary: GamificationSummary?

    public init(xp: Int, requestID: UUID, summary: GamificationSummary?) {
        self.xp = xp
        self.requestID = requestID
        self.summary = summary
    }
}

public enum APIError: Error, LocalizedError, Sendable {
    case http(status: Int, message: String)
    case csrfMismatch
    case socialSignupRequired(token: String)
    case invalidResponse

    public var errorDescription: String? {
        switch self {
        case .http(_, let message): return message
        case .csrfMismatch:
            return "A sessão e o token de segurança não foram aceitos juntos pelo servidor. Nenhuma operação foi repetida. Entre novamente para revalidar a sessão."
        case .socialSignupRequired: return "Complete seu perfil de acesso para continuar."
        case .invalidResponse: return "O servidor retornou uma resposta inesperada."
        }
    }
}

/// Auth operations must be invoked serially by the app. The actor may reenter
/// while awaiting transport; it does not serialize an entire multi-request flow.
/// CSRF is obtained from the current cookie session and is never persisted alone.
public actor FitTrackerAPI {
    private let baseURL: URL
    private let session: URLSession
    private let language: String
    private let xpRewardDefaults: UserDefaults
    private var xpOwnerID: UUID?
    private var transports: [UUID: Task<(Data, URLResponse), Error>] = [:]
    private var changingAuthentication = false
    private var authenticationGeneration = 0
    private var announcedAchievements: Set<String> = []
    private var announcedXPAwards: Set<String> = []
    private var xpJobOrigins: [String: UUID] = [:]
    private var authenticated = false
    private var workoutSession: (response: SessionResponse, cookies: String, checkedAt: Date)?
    public nonisolated static let achievementUnlocked = Notification.Name("FitTrackerAchievementUnlocked")
    public nonisolated static let sessionExpired = Notification.Name("FitTrackerSessionExpired")
    public nonisolated static let xpRequestStarted = Notification.Name("FitTrackerXPRequestStarted")
    public nonisolated static let xpAwarded = Notification.Name("FitTrackerXPAwarded")

    /// Use the API root (for example https://host/api), not a screen URL.
    public init(baseURL: URL, session: URLSession = FitTrackerAPI.makeSession(), language: String? = nil, xpRewardDefaults: UserDefaults = .standard) {
        self.xpRewardDefaults = xpRewardDefaults
        self.baseURL = baseURL
        self.session = session
        self.language = language ?? Bundle.main.preferredLocalizations.first ?? "pt-BR"
    }

    /// OS cookie storage is enabled. Persistence across process termination must
    /// still be validated on device; restoring auth always checks the server.
    public nonisolated static func makeSession() -> URLSession {
        let configuration = URLSessionConfiguration.default
        configuration.httpShouldSetCookies = true
        configuration.httpCookieStorage = .shared
        configuration.httpCookieAcceptPolicy = .always
        configuration.timeoutIntervalForRequest = 30
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: configuration)
    }

    public func restoreSession() async throws -> SessionResponse {
        let result = try await request("check_session", as: SessionResponse.self)
        if result.loggedIn, result.user == nil || result.csrfToken?.isEmpty != false {
            throw APIError.invalidResponse
        }
        xpOwnerID = result.loggedIn ? result.user?.id : nil
        authenticated = result.loggedIn
        workoutSession = result.loggedIn ? (result, cookieSignature(), Date()) : nil
        return result
    }

    // Reuse only a recently validated token belonging to the same cookie session.
    // A rejected write is never replayed automatically.
    func workoutSessionForMutation() async throws -> SessionResponse {
        if !changingAuthentication, authenticated, let cached = workoutSession,
           cached.cookies == cookieSignature(), Date().timeIntervalSince(cached.checkedAt) < 60 {
            return cached.response
        }
        return try await restoreSession()
    }

    private func cookieSignature() -> String {
        (session.configuration.httpCookieStorage?.cookies(for: baseURL) ?? [])
            .map { "\($0.domain)|\($0.path)|\($0.name)|\($0.value)" }.sorted().joined(separator: "\n")
    }

    public func login(username: String, password: String) async throws -> SessionResponse {
        try await beginAuthenticationChange()
        defer { changingAuthentication = false }
        // An authenticated cookie makes even /login subject to CSRF protection.
        let current = try await restoreSession()
        let token = try csrfToken(for: current)
        let body = try JSONEncoder().encode(LoginRequest(username: username, password: password))
        let result = try await request("login", method: "POST", body: body,
                                       csrfToken: token, as: LoginResponse.self)
        authenticated = true
        workoutSession = nil
        return SessionResponse(loggedIn: true, user: result.user, csrfToken: result.csrfToken)
    }

    public func logout() async throws {
        try await beginAuthenticationChange()
        defer { clearSessionCookies(); authenticated = false; xpOwnerID = nil; changingAuthentication = false }
        let current = try await restoreSession()
        guard current.loggedIn else { return }
        let token = try csrfToken(for: current)
        _ = try await request("logout", method: "POST", csrfToken: token, as: MessageResponse.self)
    }

    public func getProfile() async throws -> ProfileResponse {
        try await request("profile", as: ProfileResponse.self)
    }

    func csrfToken(for current: SessionResponse) throws -> String? {
        guard current.loggedIn else { return nil }
        guard let token = current.csrfToken, !token.isEmpty else { throw APIError.invalidResponse }
        return token
    }

    func request<Response: Decodable>(
        _ path: String, method: String = "GET", body: Data? = nil,
        csrfToken: String? = nil, idempotencyKey: String? = nil,
        queryItems: [URLQueryItem] = [], allowEmptyResponse: Bool = false, backgroundPlan: Bool = false, as type: Response.Type
    ) async throws -> Response {
        let authPath = ["check_session", "auth/config", "login", "logout", "register", "auth/google", "auth/apple", "auth/apple/challenge"].contains(path) || (path == "account" && method == "DELETE")
        guard !changingAuthentication || authPath else { throw CancellationError() }
        let generation = authenticationGeneration
        guard var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false) else { throw APIError.invalidResponse }
        if !queryItems.isEmpty { components.queryItems = queryItems }
        guard let url = components.url else { throw APIError.invalidResponse }
        let planGeneration = method == "POST" && ["diet_plans/generate", "workout_plans/generate"].contains(path)
        var request = URLRequest(url: url,
                                 cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: planGeneration ? (backgroundPlan ? 60 : 180) : 30)
        request.httpMethod = method
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(language, forHTTPHeaderField: "Accept-Language")
        request.setValue("gemini,openai", forHTTPHeaderField: "X-AI-Providers")
        if backgroundPlan { request.setValue("plans", forHTTPHeaderField: "X-AI-Background") }
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        if let csrfToken { request.setValue(csrfToken, forHTTPHeaderField: "X-CSRF-Token") }
        if let idempotencyKey { request.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key") }
        // Only these read-only preflights may wait for a sleeping host or retry.
        // OAuth authorization codes and account writes must never be replayed.
        let resilientPreflight = method == "GET" && ["auth/config", "check_session"].contains(path)
        let requestID = UUID()
        let xpMutation = (method == "POST" && (["diet", "water", "diet/ai_macros"].contains(path) || path.hasSuffix("/finish") || planGeneration))
            || (method == "PUT" && path.hasPrefix("diet/") && path.hasSuffix("/outcome"))
        if xpMutation {
            var context = ["path": path]
            if let idempotencyKey { context["idempotencyKey"] = idempotencyKey }
            NotificationCenter.default.post(name: Self.xpRequestStarted, object: requestID, userInfo: context)
        }
        let (data, response) = try await send(request, generation: generation, resilientPreflight: resilientPreflight)
        guard let response = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(response.statusCode) else {
            if response.statusCode == 401, authenticated, !authPath {
                authenticated = false
                xpOwnerID = nil
                workoutSession = nil
                NotificationCenter.default.post(name: Self.sessionExpired, object: nil)
            }
            let failure = try? JSONDecoder().decode(ErrorResponse.self, from: data)
            if response.statusCode == 409, ["auth/google", "auth/apple"].contains(path), failure?.code == "username_required", let token = failure?.signup_token, !token.isEmpty {
                throw APIError.socialSignupRequired(token: token)
            }
            let message = failure?.error
            if response.statusCode == 403, message == "Token CSRF inválido." {
                workoutSession = nil
                throw APIError.csrfMismatch
            }
            throw APIError.http(status: response.statusCode,
                                message: message ?? "Não foi possível concluir a solicitação (\(response.statusCode)).")
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let result: Response
        do { result = try decoder.decode(type, from: allowEmptyResponse && response.statusCode == 204 ? Data("{}".utf8) : data) }
        catch { throw APIError.invalidResponse }
        if let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if ["login", "register", "auth/google", "auth/apple"].contains(path) {
                if payload["logged_in"] as? Bool == false { xpOwnerID = nil }
                else if let user = payload["user"] as? [String: Any], let id = user["id"] as? String {
                    xpOwnerID = UUID(uuidString: id)
                }
            }
            let jobID = (payload["job_id"] as? String)?.lowercased()
            if xpMutation, let jobID { xpJobOrigins[jobID] = requestID }
            let nested = payload["result"] as? [String: Any]
            let reward = nested ?? payload
            if let xp = (reward["xp_gained"] as? Int) ?? (payload["xp_gained"] as? Int), xp > 0 {
                let polledJobID = method == "GET" && path.hasPrefix("ai/tasks/")
                    ? String(path.dropFirst("ai/tasks/".count)).lowercased() : nil
                let origin = polledJobID.flatMap { xpJobOrigins[$0] } ?? requestID
                let totalXP = ((reward["gamification"] as? [String: Any]) ?? (payload["gamification"] as? [String: Any]))?["total_xp"] as? Int
                let stableKey = polledJobID.map { "job:\($0)" } ?? jobID.map { "job:\($0)" }
                    ?? idempotencyKey.map { "\(method):\(path):\($0)" }
                    ?? totalXP.map { "\(path):total:\($0)" }
                let awardKey = stableKey ?? "\(method):\(path):\(requestID.uuidString)"
                let persistedKey = xpOwnerID.flatMap { owner in
                    stableKey.map { "\(baseURL.absoluteString)|\(owner.uuidString)|\($0)" }
                }
                let storedAwards = xpRewardDefaults.stringArray(forKey: "FitTrackerAnnouncedXPAwards") ?? []
                if announcedXPAwards.insert("\(generation):\(awardKey)").inserted,
                   persistedKey.map({ !storedAwards.contains($0) }) ?? true {
                    if let persistedKey {
                        xpRewardDefaults.set(Array((storedAwards + [persistedKey]).suffix(256)), forKey: "FitTrackerAnnouncedXPAwards")
                    }
                    let summaryData = ((reward["gamification"] as? [String: Any]) ?? (payload["gamification"] as? [String: Any]))
                        .flatMap { try? JSONSerialization.data(withJSONObject: $0) }
                    let summary = summaryData.flatMap { try? decoder.decode(GamificationSummary.self, from: $0) }
                    NotificationCenter.default.post(name: Self.xpAwarded,
                                                    object: XPAwardNotice(xp: xp, requestID: origin, summary: summary))
                }
            }
        }
        if method != "GET", let envelope = try? decoder.decode(AchievementEnvelope.self, from: data) {
            for notice in envelope.achievementsUnlocked ?? [] where announcedAchievements.insert(notice.code).inserted {
                NotificationCenter.default.post(name: Self.achievementUnlocked, object: notice)
            }
        }
        return result
    }
    private func send(_ request: URLRequest, generation: Int, resilientPreflight: Bool) async throws -> (Data, URLResponse) {
        let deadline = Date().addingTimeInterval(resilientPreflight ? 90 : request.timeoutInterval)
        var attempt = 0
        while true {
            try Task.checkCancellation()
            guard generation == authenticationGeneration else { throw CancellationError() }
            let remaining = deadline.timeIntervalSinceNow
            guard remaining > 0 else { throw URLError(.timedOut) }
            var nextRequest = request
            nextRequest.timeoutInterval = remaining
            let result: (Data, URLResponse)
            do {
                result = try await transport(nextRequest)
            } catch {
                try Task.checkCancellation()
                guard generation == authenticationGeneration else { throw CancellationError() }
                let transientCodes: [URLError.Code] = [.timedOut, .networkConnectionLost, .cannotConnectToHost]
                guard resilientPreflight, attempt == 0, deadline.timeIntervalSinceNow > 1,
                      let networkError = error as? URLError, transientCodes.contains(networkError.code) else { throw error }
                attempt += 1
                try await Task.sleep(nanoseconds: 1_000_000_000)
                continue
            }
            try Task.checkCancellation()
            guard generation == authenticationGeneration else { throw CancellationError() }
            if resilientPreflight, attempt == 0, deadline.timeIntervalSinceNow > 1,
               let response = result.1 as? HTTPURLResponse, [502, 503, 504].contains(response.statusCode) {
                attempt += 1
                try await Task.sleep(nanoseconds: 1_000_000_000)
                continue
            }
            return result
        }
    }

    private func transport(_ request: URLRequest) async throws -> (Data, URLResponse) {
        let transportID = UUID()
        let transport = Task { [session] in try await session.data(for: request) }
        transports[transportID] = transport
        defer { transports[transportID] = nil }
        return try await withTaskCancellationHandler { try await transport.value } onCancel: { transport.cancel() }
    }

    func beginAuthenticationChange() async throws {
        guard !changingAuthentication else { throw CancellationError() }
        changingAuthentication = true
        announcedAchievements.removeAll()
        announcedXPAwards.removeAll()
        xpJobOrigins.removeAll()
        xpOwnerID = nil
        workoutSession = nil
        authenticationGeneration += 1
        let pending = Array(transports.values)
        pending.forEach { $0.cancel() }
        for task in pending { _ = await task.result }
    }

    func acceptAuthenticatedSession() { authenticated = true; workoutSession = nil }

    func endAuthenticationChange() { changingAuthentication = false }

    func clearSessionCookies() {
        workoutSession = nil
        for cookie in session.configuration.httpCookieStorage?.cookies(for: baseURL) ?? [] {
            session.configuration.httpCookieStorage?.deleteCookie(cookie)
        }
    }
}

private struct LoginRequest: Encodable { let username: String; let password: String }
private struct LoginResponse: Decodable { let user: SessionUser; let csrfToken: String }
struct MessageResponse: Decodable { let message: String }
private struct ErrorResponse: Decodable { let error: String; let code: String?; let signup_token: String? }

private struct AchievementEnvelope: Decodable {
    let achievementsUnlocked: [AchievementUnlockNotice]?
}
