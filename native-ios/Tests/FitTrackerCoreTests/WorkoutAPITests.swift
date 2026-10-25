import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class WorkoutAPITests: XCTestCase {
    private var session: URLSession!
    private var api: FitTrackerAPI!

    override func setUp() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [WorkoutStubProtocol.self]
        session = URLSession(configuration: configuration)
        api = FitTrackerAPI(baseURL: URL(string: "https://fittracker.invalid/api")!, session: session)
    }

    override func tearDown() {
        session.invalidateAndCancel()
        WorkoutStubProtocol.handler = nil
    }

    func testScheduledDayDecodesPrescriptionWithoutTurningNullLoadIntoZero() async throws {
        WorkoutStubProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.path, "/api/workouts/today")
            return (200, """
            {"state":"scheduled","timezone":"America/Sao_Paulo","local_date":"2026-10-07",
             "current_plan_id":1,"current_plan":{"id":1,"title":"Força","description":null,"session_duration":45},
             "current_day":{"id":2,"title":"Peito","focus":"Superior","exercises":[
                {"id":3,"name":"Supino","sets":3,"reps":"8-12","weight":null,"rest_seconds":90,"notes":null}]},
             "next_day":null,"week":[{"weekday":2,"label":"Qua","day_title":"Peito","active":true}]}
            """)
        }
        let today = try await api.getWorkoutToday()
        XCTAssertEqual(today.state, "scheduled")
        XCTAssertEqual(today.currentDay?.exercises.first?.reps, "8-12")
        XCTAssertNil(today.currentDay?.exercises.first?.weight)
        XCTAssertEqual(today.week.first?.active, true)
    }

    func testRestAndUnconfiguredStatesAcceptNoPlanOrDay() async throws {
        for state in ["rest", "unconfigured"] {
            WorkoutStubProtocol.handler = { _ in
                (200, "{\"state\":\"\(state)\",\"timezone\":\"UTC\",\"local_date\":\"2026-10-07\",\"current_plan\":null,\"current_day\":null,\"next_day\":null,\"week\":[]}")
            }
            let today = try await api.getWorkoutToday()
            XCTAssertEqual(today.state, state)
            XCTAssertNil(today.currentDay)
        }
    }

    func testActiveSessionUsesCompletedExerciseIDsFromServer() async throws {
        WorkoutStubProtocol.handler = { _ in
            (200, "{\"state\":\"active\",\"timezone\":\"UTC\",\"local_date\":\"2026-10-07\",\"session\":{\"id\":7,\"completed_exercise_ids\":[2,3]},\"week\":[]}")
        }
        let today = try await api.getWorkoutToday()
        XCTAssertEqual(today.session?.id, 7)
        XCTAssertEqual(today.session?.completedExerciseIds, [2, 3])
    }

    func testActivityPaginationUsesQueryAndServerHasMore() async throws {
        WorkoutStubProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/activities")
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems
            XCTAssertEqual(query?.first(where: { $0.name == "offset" })?.value, "20")
            XCTAssertEqual(query?.first(where: { $0.name == "limit" })?.value, "20")
            return (200, """
            {"items":[{"id":4,"workout_name":"Peito","plan_name":"Força","started_at":"2026-10-06T23:50:00",
             "completed_at":"2026-10-07T00:15:00","duration_seconds":1500,"exercises_performed":4,
             "total_exercises":6,"sets_performed":12,"volume_total_kg":null}],"limit":20,"offset":20,"has_more":true}
            """)
        }
        let page = try await api.getWorkoutActivities(offset: 20)
        XCTAssertTrue(page.hasMore)
        XCTAssertEqual(page.offset, 20)
        XCTAssertEqual(page.items.first?.exercisesPerformed, 4)
        XCTAssertEqual(page.items.first?.totalExercises, 6)
        XCTAssertNil(page.items.first?.volumeTotalKg)
    }

    func testActivityDetailDecodesPerformedSetsAndWarmup() async throws {
        WorkoutStubProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/activities/4")
            return (200, """
            {"activity":{"id":4,"workout_name":"Peito","plan_name":"Força","duration_seconds":1500,
             "exercises_performed":1,"total_exercises":6,"sets_performed":2,"volume_total_kg":null,
             "exercises":[{"exercise_id":3,"name":"Supino","sets":[
                {"set_order":1,"repetitions":10,"load_kg":0,"is_warmup":true},
                {"set_order":2,"repetitions":8,"load_kg":null,"is_warmup":false}]}]},"achievements":[]}
            """)
        }
        let detail = try await api.getWorkoutActivity(id: 4)
        XCTAssertEqual(detail.activity.exercises.first?.sets.first?.loadKg, 0)
        XCTAssertEqual(detail.activity.exercises.first?.sets.first?.isWarmup, true)
        XCTAssertNil(detail.activity.exercises.first?.sets.last?.loadKg)
        XCTAssertEqual(detail.activity.exercisesPerformed, 1)
    }

    func testFailedHistoryIsNotReturnedAsEmptySuccessfulPage() async throws {
        WorkoutStubProtocol.handler = { _ in (401, "{\"error\":\"Sessão expirada\"}") }
        do {
            _ = try await api.getWorkoutActivities()
            XCTFail("Expected server error")
        } catch let APIError.http(status, message) {
            XCTAssertEqual(status, 401)
            XCTAssertEqual(message, "Sessão expirada")
        }
    }
}

private final class WorkoutStubProtocol: URLProtocol {
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
