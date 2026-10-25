import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class PlanAPITests: XCTestCase {
    private var session: URLSession!
    private let user = """
    {"id":"00000000-0000-0000-0000-000000000001","username":"ana","name":"Ana",
    "is_banned":false,"is_admin":false,"is_premium":true,"plan_code":"premium",
    "ai_trial_uses":0,"has_password":true,"is_public":false,"onboarding_status":"complete",
    "profile_missing_fields":[],"profile_complete":true}
    """
    private let plan = "{\"id\":8,\"title\":\"Alternativa\",\"description\":null,\"is_current\":false,\"meals\":[]}"
    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [PlanStubProtocol.self]
        session = URLSession(configuration: config)
    }
    override func tearDown() { session.invalidateAndCancel(); PlanStubProtocol.handler = nil; super.tearDown() }

    func testTemplateSourceAndLegacyPlanDecode() throws {
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        XCTAssertNil(try decoder.decode(NativePlan.self, from: Data(plan.utf8)).source)
        let ready = plan.replacingOccurrences(of: "\"id\":8", with: "\"id\":8,\"source\":\"template\"")
        XCTAssertEqual(try decoder.decode(NativePlan.self, from: Data(ready.utf8)).source, "template")
    }

    func testDeletePlanUsesEachLibraryRouteAndFreshCSRF() async throws {
        for kind in NativePlanKind.allCases {
            var paths: [String] = []
            PlanStubProtocol.handler = { request in
                paths.append(request.url!.path)
                if request.httpMethod == "GET" { return (200, self.auth()) }
                XCTAssertEqual(request.httpMethod, "DELETE")
                XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh")
                return (200, "{\"message\":\"Plano removido. O histórico foi preservado.\"}")
            }
            let message = try await client().deletePlan(kind: kind, id: 8)
            XCTAssertEqual(paths, ["/api/check_session", "/api/\(kind.path)/8"])
            XCTAssertEqual(message, "Plano removido. O histórico foi preservado.")
        }
    }

    func testDeletePlanReportsActiveWorkoutAndNeverRepeatsDelete() async throws {
        var deletes = 0
        PlanStubProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, self.auth()) }
            deletes += 1
            return (409, "{\"error\":\"Finalize o treino em andamento antes de excluir este plano.\"}")
        }
        do {
            _ = try await client().deletePlan(kind: .workout, id: 8)
            XCTFail("Expected active workout protection")
        } catch APIError.http(let status, let message) {
            XCTAssertEqual(status, 409)
            XCTAssertTrue(message.contains("Finalize o treino"))
        }
        XCTAssertEqual(deletes, 1)
    }

    func testDeletePlanRequiresAuthenticatedSession() async throws {
        var paths: [String] = []
        PlanStubProtocol.handler = { request in
            paths.append(request.url!.path)
            return (200, "{\"logged_in\":false}")
        }
        do {
            _ = try await client().deletePlan(kind: .workout, id: 8)
            XCTFail("Expected authentication")
        } catch APIError.http(let status, _) { XCTAssertEqual(status, 401) }
        XCTAssertEqual(paths, ["/api/check_session"])
    }

    func testPlanLibraryPaginationAndAlternativeGenerationNeverActivateCurrent() async throws {
        var paths: [String] = []
        PlanStubProtocol.handler = { request in
            paths.append(request.url!.path)
            switch paths.count {
            case 1:
                XCTAssertEqual(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems, [URLQueryItem(name: "limit", value: "30"),URLQueryItem(name: "offset", value: "30")])
                return (200, "[\(self.plan)]")
            case 2: return (200, self.auth())
            default:
                XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh")
                let body = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
                XCTAssertEqual(body["meals_per_day"] as? Int, 3)
                XCTAssertEqual(body["diet_pattern"] as? String, "omnivore")
                return (201, "{\"plan\":\(self.plan),\"plan_id\":8}")
            }
        }
        let api = client()
        _ = try await api.getPlans(kind: .diet, offset: 30)
        guard case .plan(let result) = try await api.generateDietPlan(DietPlanPreferences()) else { return XCTFail("Expected plan") }
        XCTAssertEqual(result.id, 8)
        XCTAssertEqual(paths, ["/api/diet_plans", "/api/check_session", "/api/diet_plans/generate"])
        XCTAssertEqual(result.isCurrent, false)
    }
    func testWorkoutActivationSendsExplicitWeekdaysAndPreservesEffectiveDate() async throws {
        PlanStubProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, self.auth()) }
            XCTAssertEqual(request.httpMethod, "PUT")
            XCTAssertEqual(request.url!.path, "/api/workout_plans/8/current")
            let body = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: [Int]]
            XCTAssertEqual(body["weekdays"], [0,2,4])
            return (200, "{\"message\":\"Agenda atualizada.\",\"current_plan_id\":7,\"pending_plan_id\":8,\"effective_from\":\"2026-10-12\"}")
        }
        let response = try await client().activatePlan(kind: .workout, id: 8, weekdays: [0,2,4])
        XCTAssertEqual(response.effectiveFrom, "2026-10-12")
    }
    func testWorkoutGenerationLetsServerRecommendSplit() async throws {
        PlanStubProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, self.auth()) }
            let body = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            XCTAssertNil(body["split_type"])
            XCTAssertEqual(body["days_per_week"] as? Int, 3)
            XCTAssertEqual(body["equipment"] as? [String], ["full_gym"])
            return (202, "{\"job_id\":\"00000000-0000-0000-0000-000000000123\",\"status\":\"queued\"}")
        }
        guard case .queued = try await client().generateWorkoutPlan(WorkoutPlanPreferences()) else { return XCTFail("Expected queued") }
    }
    func testBackgroundGenerationUsesReceiptTimeoutAndStableKey() async throws {
        let id = UUID()
        PlanStubProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, self.auth()) }
            XCTAssertEqual(request.timeoutInterval, 60, accuracy: 0.1)
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-AI-Background"), "plans")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), "generation-1")
            return (202, "{\"job_id\":\"\(id.uuidString)\",\"status\":\"queued\"}")
        }
        guard case .queued(let received) = try await client().generateWorkoutPlan(WorkoutPlanPreferences(),
            background: true, idempotencyKey: "generation-1") else { return XCTFail("Expected durable receipt") }
        XCTAssertEqual(received, id)
    }
    func testBackgroundCapabilitiesAndOwnershipDiscoveryDecode() async throws {
        PlanStubProtocol.handler = { _ in
            (200, "{\"plan_background_enabled\":true,\"push_enabled\":false,\"tasks\":[{\"job_id\":\"00000000-0000-0000-0000-000000000123\",\"operation\":\"diet_plan\",\"status\":\"running\"}]}")
        }
        let status = try await client().planBackgroundStatus()
        XCTAssertTrue(status.planBackgroundEnabled)
        XCTAssertEqual(status.pushEnabled, false)
        XCTAssertEqual(status.tasks.first?.operation, "diet_plan")
    }
    func testFailedGenerationTaskDoesNotDecodeErrorAsPlan() async throws {
        PlanStubProtocol.handler = { _ in (200, "{\"status\":\"failed\",\"error\":\"Indisponível\",\"result\":{\"error\":\"Indisponível\"}}") }
        let response = try await client().getPlanGenerationTask(id: UUID())
        XCTAssertNil(response.plan); XCTAssertEqual(response.error, "Indisponível")
    }
    func testPrescriptionEditUsesReturnedVersionedPlanIds() async throws {
        PlanStubProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, self.auth()) }
            XCTAssertEqual(request.httpMethod, "PATCH")
            let body = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            XCTAssertEqual(body["catalog_key"] as? String, "supino_reto_barra")
            XCTAssertEqual(body["rest_seconds"] as? Int, 90)
            return (200, "{\"plan\":{\"id\":99,\"title\":\"Nova versão\",\"days\":[{\"id\":100,\"title\":\"A\",\"exercises\":[{\"id\":101,\"name\":\"Supino\",\"catalog_key\":\"supino_reto_barra\",\"sets\":4,\"reps\":\"8-12\",\"weight\":null,\"rest_seconds\":90}]}]}}")
        }
        let result = try await client().editWorkoutPrescription(planId: 8, exerciseId: 9, catalogKey: "supino_reto_barra", sets: 4, reps: "8-12", weight: "", restSeconds: 90)
        XCTAssertEqual(result.id, 99); XCTAssertEqual(result.days?.first?.exercises.first?.id, 101)
    }
    func testDietMealEditSendsUpdatedNutritionAndCSRF403NeverReplays() async throws {
        var count = 0
        PlanStubProtocol.handler = { request in
            count += 1
            if count == 1 { return (200, self.auth()) }
            XCTAssertEqual(request.httpMethod, "PATCH")
            let body = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            XCTAssertEqual(body["description"] as? String, "Arroz")
            XCTAssertEqual(body["calories"] as? Double, 0)
            XCTAssertNil(body["protein"])
            return (403, "{\"error\":\"Token CSRF inválido.\"}")
        }
        do { try await client().editDietPlanMeal(planId: 8, mealId: 9, description: "Arroz", calories: 0); XCTFail("Expected rejection") }
        catch APIError.csrfMismatch { }
        XCTAssertEqual(count, 2)
    }
    private func client() -> FitTrackerAPI { FitTrackerAPI(baseURL: URL(string: "https://plans.invalid/api")!, session: session) }
    func testManualPlansUseDedicatedEndpointsAndPreserveCustomExercises() async throws {
        var paths: [String] = []
        PlanStubProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, self.auth()) }
            paths.append(request.url!.path)
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh")
            let body = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            if request.url!.path.contains("workout") {
                let days = body["days"] as! [[String: Any]]
                let exercises = days[0]["exercises"] as! [[String: Any]]
                XCTAssertNil(exercises[0]["catalog_key"])
                XCTAssertEqual(exercises[0]["name"] as? String, "Exercício próprio")
                XCTAssertEqual(exercises[1]["catalog_key"] as? String, "supino_reto_halteres")
                XCTAssertNil(exercises[0]["id"])
            } else {
                let meals = body["meals"] as! [[String: Any]]
                XCTAssertEqual(meals[0]["description"] as? String, "Arroz e feijão")
                XCTAssertNil(meals[0]["calories"])
            }
            return (201, "{\"plan\":\(self.plan),\"plan_id\":8}")
        }
        var custom = ManualPlanExercise(); custom.name = "Exercício próprio"
        var catalog = ManualPlanExercise(); catalog.name = "Supino"; catalog.catalogKey = "supino_reto_halteres"
        var day = ManualPlanDay(); day.exercises = [custom, catalog]
        _ = try await client().createManualWorkout(title: "Treino", days: [day])
        var meal = ManualPlanMeal(); meal.description = "Arroz e feijão"
        _ = try await client().createManualDiet(title: "Dieta", meals: [meal])
        XCTAssertEqual(paths, ["/api/workout_plans/manual", "/api/diet_plans/manual"])
    }

    func testFreeQuotaDecodingSeparatesWorkoutAndDiet() throws {
        let data = Data("""
        {"premium":false,"policy":"lifetime","plans":{"limit":2,"used":1,"remaining":1},
        "workout_plans":{"limit":1,"used":1,"remaining":0},"diet_plans":{"limit":1,"used":0,"remaining":1},
        "photos":{"limit":3,"used":2,"remaining":1},"manual_logging":true}
        """.utf8)
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let status = try decoder.decode(FreeAccessStatus.self, from: data)
        XCTAssertEqual(status.remainingPlans(for: .workout), 0)
        XCTAssertEqual(status.remainingPlans(for: .diet), 1)
        XCTAssertEqual(status.photos.remaining, 1)
    }

    private func auth() -> String { "{\"logged_in\":true,\"user\":\(user),\"csrf_token\":\"fresh\"}" }
    private func body(_ request: URLRequest) -> Data {
        if let data = request.httpBody { return data }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open(); defer { stream.close() }
        var result = Data(), buffer = [UInt8](repeating: 0, count: 2048)
        while stream.hasBytesAvailable { let count = stream.read(&buffer, maxLength: buffer.count); if count <= 0 { break }; result.append(buffer, count: count) }
        return result
    }
}
private final class PlanStubProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            guard let handler = Self.handler else { throw URLError(.badServerResponse) }
            let (status, json) = try handler(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(json.utf8)); client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() { }
}
