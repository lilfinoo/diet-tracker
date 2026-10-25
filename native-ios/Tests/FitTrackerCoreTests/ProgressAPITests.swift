import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class ProgressAPITests: XCTestCase {
    private var session: URLSession!
    private var api: FitTrackerAPI!

    override func setUp() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ProgressStubProtocol.self]
        session = URLSession(configuration: configuration)
        api = FitTrackerAPI(baseURL: URL(string: "https://fittracker.invalid/api")!, session: session)
    }

    override func tearDown() {
        session.invalidateAndCancel()
        ProgressStubProtocol.handler = nil
    }

    func testOverviewPreservesMissingMetricAndNoWeeklyGoal() async throws {
        ProgressStubProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/progress/overview")
            XCTAssertEqual(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.query, "view=summary")
            return (200, """
            {"body":{"latest_date":null,"metrics":{"weight":{"latest":null,"previous":null,"change":null},
                "body_fat":{"latest":null,"previous":null,"change":null}}},
             "weekly":{"timezone":"America/Sao_Paulo","current":{"week_start":"2026-10-05","week_end":"2026-10-11",
                "completed":0,"target":null,"fulfilled":false,"streak":0}},
             "consistency":{"start_date":"2026-08-17","end_date":"2026-10-07","days":[]}}
            """)
        }
        let result = try await api.getProgressOverview()
        XCTAssertNil(result.body.metrics["weight"]?.latest)
        XCTAssertNotNil(result.body.metrics["body_fat"])
        XCTAssertNil(result.weekly.current.target)
        XCTAssertEqual(result.weekly.current.completed, 0)
    }

    func testConsistencyKeepsDietTrackingIndependentFromWorkout() async throws {
        ProgressStubProtocol.handler = { _ in
            (200, """
            {"body":{"latest_date":"2026-10-07","metrics":{"weight":{"latest":{"date":"2026-10-07","value":70.5},
                "previous":{"date":"2026-10-01","value":71},"change":-0.5}}},
             "weekly":{"timezone":"UTC","current":{"week_start":"2026-10-05","week_end":"2026-10-11",
                "completed":2,"target":3,"fulfilled":false,"streak":1}},
             "consistency":{"start_date":"2026-10-05","end_date":"2026-10-07",
                "days":[{"date":"2026-10-07","workout":false,"diet_tracked":true,"diet_source":"manual_entry"}]}}
            """)
        }
        let result = try await api.getProgressOverview()
        XCTAssertEqual(result.body.metrics["weight"]?.change, -0.5)
        XCTAssertEqual(result.consistency.days.first?.dietTracked, true)
        XCTAssertEqual(result.consistency.days.first?.workout, false)
    }

    func testMeasurementSeriesUsesMetricQueryAndPreservesRealDates() async throws {
        ProgressStubProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/measurements/summary")
            XCTAssertEqual(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.query, "metric=body_fat")
            return (200, "{\"points\":[{\"date\":\"2026-09-01\",\"value\":20},{\"date\":\"2026-10-07\",\"value\":18.5}],\"latest_date\":\"2026-10-07\"}")
        }
        let result = try await api.getBodyMetricSeries(metric: .bodyFat)
        XCTAssertEqual(result.points.map(\.date), ["2026-09-01", "2026-10-07"])
        XCTAssertEqual(result.points.last?.value, 18.5)
    }

    func testMissingMeasurementsIsEmptySeriesNotZero() async throws {
        ProgressStubProtocol.handler = { _ in (200, "{\"points\":[],\"latest_date\":null}") }
        let result = try await api.getBodyMetricSeries(metric: .weight)
        XCTAssertTrue(result.points.isEmpty)
        XCTAssertNil(result.latestDate)
    }

    func testHiddenAchievementsDoNotInventProgressOrUnlocks() async throws {
        ProgressStubProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/progress/achievements")
            return (200, """
            {"items":[{"code":"hidden","title":"Conquista oculta","description":"Continue evoluindo",
                "hidden":true,"progress":null,"unlocked":null},
             {"code":"first","title":"Primeiro treino","description":"Treino registrado","hidden":false,
                "progress":{"current":1,"target":1,"percentage":100},"unlocked":{"unlocked_at":"2026-10-07T12:00:00"}}]}
            """)
        }
        let result = try await api.getProgressAchievements()
        XCTAssertNil(result.items.first?.progress)
        XCTAssertNil(result.items.first?.unlocked)
        XCTAssertEqual(result.items.last?.progress?.percentage, 100)
        XCTAssertEqual(result.items.last?.unlocked?.unlockedAt, "2026-10-07T12:00:00")
    }
    func testExerciseHistoryPreservesIdentityWarmupsMissingLoadsAndPagination() async throws {
        ProgressStubProtocol.handler = { request in
            XCTAssertEqual(request.url?.path, "/api/progress/exercises/exercise-id:42")
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems!
            XCTAssertEqual(query.first { $0.name == "offset" }?.value, "20")
            XCTAssertEqual(query.first { $0.name == "view" }?.value, "sessions")
            return (200, """
            {"exercise_key":"exercise-id:42","exercise_name":"Exercício","max_load_kg":80,
            "sessions":{"items":[{"session_id":99,"completed_at":"2026-09-10T01:00:00","local_date":"2026-09-09",
            "sets":[{"repetitions":10,"load_kg":100,"is_warmup":true},{"repetitions":8,"load_kg":80,"is_warmup":false},
            {"repetitions":8,"load_kg":null,"is_warmup":false},{"repetitions":0,"load_kg":120,"is_warmup":false}]}],
            "offset":20,"limit":20,"has_more":true}}
            """)
        }
        let result = try await api.getExerciseProgress(key: "exercise-id:42", offset: 20)
        XCTAssertEqual(result.exerciseKey, "exercise-id:42")
        XCTAssertEqual(result.sessions.items[0].localDate, "2026-09-09")
        XCTAssertEqual(result.sessions.items[0].bestWorkingLoad, 80)
        XCTAssertNil(result.sessions.items[0].sets[2].loadKg)
        XCTAssertTrue(result.sessions.hasMore)
    }

    func testUnknownAndWarmupOnlyLoadsHaveNoChartPoint() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let item = try decoder.decode(ExerciseProgressSession.self, from: Data("""
        {"session_id":1,"completed_at":"2026-09-09T10:00:00","local_date":null,
        "sets":[{"repetitions":8,"load_kg":null,"is_warmup":false},
        {"repetitions":8,"load_kg":20,"is_warmup":true},{"repetitions":8,"load_kg":0,"is_warmup":false}]}
        """.utf8))
        XCTAssertNil(item.bestWorkingLoad)
    }

    func testDayActivitiesRequiresServerDateConfirmation() async throws {
        ProgressStubProtocol.handler = { request in
            XCTAssertEqual(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems?.first?.value, "2026-09-09")
            return (200, "{\"items\":[],\"offset\":0,\"has_more\":false}")
        }
        do {
            _ = try await api.getProgressDayActivities(date: "2026-09-09")
            XCTFail("Old servers must not silently return activities from every day")
        } catch APIError.http(let status, _) { XCTAssertEqual(status, 501) }
        ProgressStubProtocol.handler = { _ in (200, "{\"date\":\"2026-09-09\",\"items\":[],\"offset\":0,\"has_more\":false}") }
        let page = try await api.getProgressDayActivities(date: "2026-09-09")
        XCTAssertTrue(page.items.isEmpty)
        XCTAssertEqual(page.date, "2026-09-09")
    }

    func testPersonalRecordSearchKeepsFilterAcrossPages() async throws {
        ProgressStubProtocol.handler = { request in
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems!
            XCTAssertEqual(query.first { $0.name == "search" }?.value, "supino reto")
            XCTAssertEqual(query.first { $0.name == "offset" }?.value, "50")
            return (200, "{\"items\":[],\"limit\":50,\"offset\":50}")
        }
        let page = try await api.getPersonalRecords(offset: 50, search: "supino reto")
        XCTAssertTrue(page.items.isEmpty)
        XCTAssertEqual(page.offset, 50)
    }

}

private final class ProgressStubProtocol: URLProtocol {
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
