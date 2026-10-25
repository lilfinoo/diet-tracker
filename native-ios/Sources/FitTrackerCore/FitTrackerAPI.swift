import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

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
    private var transports: [UUID: Task<(Data, URLResponse), Error>] = [:]
    private var changingAuthentication = false
    private var authenticationGeneration = 0
    private var authenticated = false
    private var workoutSession: (response: SessionResponse, cookies: String, checkedAt: Date)?
    public nonisolated static let sessionExpired = Notification.Name("FitTrackerSessionExpired")

    /// Use the API root (for example https://host/api), not a screen URL.
    public init(baseURL: URL, session: URLSession = FitTrackerAPI.makeSession()) {
        self.baseURL = baseURL
        self.session = session
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
        defer { clearSessionCookies(); authenticated = false; changingAuthentication = false }
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
        request.setValue("gemini,openai", forHTTPHeaderField: "X-AI-Providers")
        if backgroundPlan { request.setValue("plans", forHTTPHeaderField: "X-AI-Background") }
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        if let csrfToken { request.setValue(csrfToken, forHTTPHeaderField: "X-CSRF-Token") }
        if let idempotencyKey { request.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key") }
        // Only these read-only preflights may wait for a sleeping host or retry.
        // OAuth authorization codes and account writes must never be replayed.
        let resilientPreflight = method == "GET" && ["auth/config", "check_session"].contains(path)
        let (data, response) = try await send(request, generation: generation, resilientPreflight: resilientPreflight)
        guard let response = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(response.statusCode) else {
            if response.statusCode == 401, authenticated, !authPath {
                authenticated = false
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
        do { return try decoder.decode(type, from: allowEmptyResponse && response.statusCode == 204 ? Data("{}".utf8) : data) }
        catch { throw APIError.invalidResponse }
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
