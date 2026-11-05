import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class WorkoutExecutionAPITests: XCTestCase {
    private var session: URLSession!
    private var api: FitTrackerAPI!
    private let record = """
    {"id":8,"workout_plan_id":1,"workout_day_id":2,"completed_at":null,"completed_exercise_ids":[],
     "draft_sets":{"3":[{"load_kg":"0","repetitions":"12","is_warmup":true,"completed":true}]},
     "overrides":[{"workout_exercise_id":3,"name":"Exercício substituído","sets":2,"reps":"10","weight":null,"rest_seconds":60,"notes":null}]}
    """
    private let authentication = """
    {"logged_in":true,"csrf_token":"fresh-token","user":{"id":"00000000-0000-0000-0000-000000000001",
     "username":"ana","name":"Ana","is_banned":false,"is_admin":false,"is_premium":true,"plan_code":"premium",
     "ai_trial_uses":0,"has_password":true,"is_public":false,"onboarding_status":"complete",
     "profile_missing_fields":[],"profile_complete":true}}
    """

    override func setUp() {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ExecutionStubProtocol.self]
        session = URLSession(configuration: config)
        api = FitTrackerAPI(baseURL: URL(string: "https://fittracker.invalid/api")!, session: session)
    }
    override func tearDown() { session.invalidateAndCancel(); ExecutionStubProtocol.handler = nil }

    func testOrderedOperationsPreserveReopenThenCompletionAfterPersistence() throws {
        var draft = WorkoutLocalDraft()
        draft.operationQueue = [
            WorkoutPendingOperation(kind: .complete, exerciseId: 3, sets: [], completionMode: "planned", key: "first"),
            WorkoutPendingOperation(kind: .reopen, exerciseId: 3, key: "second"),
            WorkoutPendingOperation(kind: .replace, exerciseId: 3, catalogKey: "replacement", key: "third"),
            WorkoutPendingOperation(kind: .complete, exerciseId: 3, sets: [], completionMode: "planned", key: "fourth"),
            WorkoutPendingOperation(kind: .finish, key: "fifth")
        ]
        let restored = try JSONDecoder().decode(WorkoutLocalDraft.self, from: JSONEncoder().encode(draft))
        XCTAssertEqual(restored.operationQueue.map(\.key), ["first", "second", "third", "fourth", "fifth"])
        XCTAssertEqual(restored.completedIds(onServer: []), Set([3]))
        var reopened = restored
        reopened.operationQueue = Array(restored.operationQueue.prefix(2))
        XCTAssertTrue(reopened.completedIds(onServer: [3]).isEmpty)
    }

    func testLegacyQueueMigrationPreservesCompletionAndFinishKeys() throws {
        var draft = WorkoutLocalDraft()
        draft.completionQueue = [WorkoutPendingCompletion(exerciseId: 3, sets: [], key: "complete-key")]
        draft.pendingReopenExerciseIds = [3]
        draft.pendingFinishKey = "finish-key"
        draft.operationQueue = draft.operationQueue
        let keys = draft.operationQueue.map(\.key)
        let restored = try JSONDecoder().decode(WorkoutLocalDraft.self, from: JSONEncoder().encode(draft))
        XCTAssertEqual(restored.operationQueue.map(\.key), keys)
        XCTAssertEqual(keys.first, "complete-key")
        XCTAssertEqual(keys.last, "finish-key")
        XCTAssertNil(restored.pendingCompletion)
        XCTAssertNil(restored.pendingReopenExerciseIds)
    }

    func testResumeUsesGETAndPreservesDraftsAndSubstitutions() async throws {
        ExecutionStubProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.path, "/api/workout_plans/1/days/2/sessions/active")
            return (200, "{\"session\":\(self.record)}")
        }
        let result = try await api.getWorkoutExecutionSession(planId: 1, dayId: 2)
        XCTAssertEqual(result?.draftSets["3"]?.first?.loadKg, "0")
        XCTAssertEqual(result?.overrides.first?.name, "Exercício substituído")
    }

    func testStartFetchesFreshTokenBeforePOST() async throws {
        var paths: [String] = []
        ExecutionStubProtocol.handler = { request in
            paths.append(request.url!.path)
            if request.url!.path.hasSuffix("check_session") { return (200, self.authentication) }
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh-token")
            return (201, "{\"session\":\(self.record)}")
        }
        let result = try await api.startWorkout(planId: 1, dayId: 2)
        XCTAssertEqual(result.id, 8)
        XCTAssertEqual(paths, ["/api/check_session", "/api/workout_plans/1/days/2/sessions"])
    }

    func testConsecutiveCompletionsReuseValidatedSessionAndRefreshAfterCSRFRejection() async throws {
        var checks = 0
        var writes = 0
        ExecutionStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") {
                checks += 1
                return (200, self.authentication)
            }
            writes += 1
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh-token")
            if writes == 3 { return (403, "{\"error\":\"Token CSRF inválido.\"}") }
            return (200, "{\"session\":\(self.record)}")
        }
        for id in [3, 4] {
            _ = try await api.completeWorkoutExercise(sessionId: 8, exerciseId: id, sets: [], idempotencyKey: "key-\(id)")
        }
        XCTAssertEqual(checks, 1)
        do {
            _ = try await api.completeWorkoutExercise(sessionId: 8, exerciseId: 5, sets: [], idempotencyKey: "retry-key")
            XCTFail("Expected rejection")
        } catch APIError.csrfMismatch { }
        XCTAssertEqual(writes, 3, "Rejected mutations must not be replayed automatically")
        _ = try await api.completeWorkoutExercise(sessionId: 8, exerciseId: 5, sets: [], idempotencyKey: "retry-key")
        XCTAssertEqual(checks, 2)
        XCTAssertEqual(writes, 4)
    }

    func testDraftSaveKeepsBlankAndWarmupValuesAndUsesPUT() async throws {
        ExecutionStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.authentication) }
            XCTAssertEqual(request.httpMethod, "PUT")
            let json = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            let row = (json["sets"] as! [[String: Any]])[0]
            XCTAssertEqual(row["load_kg"] as? String, "")
            XCTAssertEqual(row["is_warmup"] as? Bool, true)
            XCTAssertEqual(row["completed"] as? Bool, false)
            return (200, "{\"saved\":true,\"session\":\(self.record)}")
        }
        _ = try await api.saveWorkoutDraft(sessionId: 8, exerciseId: 3, sets: [WorkoutDraftSet(isWarmup: true)])
    }

    func testCompletionUsesKeyAndDoesNotReplayRejectedMutation() async throws {
        var posts = 0
        ExecutionStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.authentication) }
            posts += 1
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), "same-completion-key")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh-token")
            return (403, "{\"error\":\"Token CSRF inválido.\"}")
        }
        do {
            _ = try await api.completeWorkoutExercise(sessionId: 8, exerciseId: 3,
                sets: [WorkoutDraftSet(repetitions: "8", completed: true).performedSet()], idempotencyKey: "same-completion-key")
            XCTFail("Expected CSRF rejection")
        } catch APIError.csrfMismatch { }
        XCTAssertEqual(posts, 1)
    }

    func testUndoCompletionUsesDeleteAndRestoresSessionEnvelope() async throws {
        var paths: [String] = []
        ExecutionStubProtocol.handler = { request in
            paths.append(request.url!.path)
            if request.url!.path.hasSuffix("check_session") { return (200, self.authentication) }
            XCTAssertEqual(request.url?.path, "/api/workout_sessions/8/exercises/3/complete")
            XCTAssertEqual(request.httpMethod, "DELETE")
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-CSRF-Token"), "fresh-token")
            return (200, "{\"message\":\"Conclusão desfeita.\",\"session\":\(self.record)}")
        }
        let result = try await api.undoWorkoutExercise(sessionId: 8, exerciseId: 3)
        XCTAssertEqual(result.id, 8)
        XCTAssertEqual(paths, ["/api/check_session", "/api/workout_sessions/8/exercises/3/complete"])
    }

    func testSetValidationDistinguishesMissingZeroAndCommaLoad() throws {
        XCTAssertNil(try WorkoutDraftSet(repetitions: "10").performedSet().loadKg)
        XCTAssertEqual(try WorkoutDraftSet(loadKg: "0", repetitions: "10").performedSet().loadKg, 0)
        XCTAssertEqual(try WorkoutDraftSet(loadKg: "12,5", repetitions: "10").performedSet().loadKg, 12.5)
        XCTAssertThrowsError(try WorkoutDraftSet(loadKg: "nan", repetitions: "10").performedSet())
        XCTAssertThrowsError(try WorkoutDraftSet(repetitions: "8-12").performedSet())
        XCTAssertThrowsError(try WorkoutDraftSet(repetitions: "0").performedSet())
    }

    func testFinishUsesStableKeyAndCompletedSummaryFromServer() async throws {
        ExecutionStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.authentication) }
            XCTAssertEqual(request.url?.path, "/api/workout_sessions/8/finish")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), "finish-key")
            let finished = self.record.replacingOccurrences(of: "\"completed_at\":null", with: "\"completed_at\":\"2026-10-07T12:00:00\"")
            return (200, """
            {"session":\(finished),"summary":{"id":8,"workout_name":"Peito","plan_name":"Força","duration_seconds":90,
              "exercises_performed":0,"total_exercises":3,"sets_performed":0,"volume_total_kg":null,"exercises":[]}}
            """)
        }
        let result = try await api.finishWorkout(sessionId: 8, idempotencyKey: "finish-key")
        XCTAssertNotNil(result.session.completedAt)
        XCTAssertEqual(result.summary.exercisesPerformed, 0)
        XCTAssertEqual(result.summary.totalExercises, 3)
        XCTAssertNil(result.summary.energyEstimate)
    }

    func testFinishPreservesConfirmedDurationAfterOfflineDraftRestart() async throws {
        var draft = WorkoutLocalDraft()
        draft.confirmedDurationSeconds = 2400
        draft.operationQueue = [WorkoutPendingOperation(kind: .finish, durationSeconds: 2400,
            finishedAt: "2026-10-22T12:00:00Z", key: "confirmed-finish")]
        let restored = try JSONDecoder().decode(WorkoutLocalDraft.self, from: JSONEncoder().encode(draft))
        let operation = try XCTUnwrap(restored.operationQueue.first)
        XCTAssertEqual(restored.confirmedDurationSeconds, 2400)
        ExecutionStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.authentication) }
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), "confirmed-finish")
            let json = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            XCTAssertEqual(json["duration_seconds"] as? Int, 2400)
            XCTAssertEqual(json["finished_at"] as? String, "2026-10-22T12:00:00Z")
            return (200, """
            {"session":\(self.record),"summary":{"id":8,"workout_name":"A","plan_name":"Plano","duration_seconds":2400,
            "exercises_performed":1,"total_exercises":3,"sets_performed":3,"volume_total_kg":null,"exercises":[],
            "energy_estimate":{"active_kcal":140,"total_kcal":196,"weight_kg":80,"duration_seconds":2400,"met":3.5,"method":"met_v1"}}}
            """)
        }
        let result = try await api.finishWorkout(sessionId: 8, idempotencyKey: operation.key,
            durationSeconds: operation.durationSeconds, finishedAt: operation.finishedAt)
        XCTAssertEqual(result.summary.energyEstimate?.activeKcal, 140)
        XCTAssertEqual(result.summary.energyEstimate?.weightKg, 80)
        let legacy = Data("{\"kind\":\"finish\",\"key\":\"old-finish\"}".utf8)
        let oldOperation = try JSONDecoder().decode(WorkoutPendingOperation.self, from: legacy)
        XCTAssertNil(oldOperation.durationSeconds)
        XCTAssertNil(oldOperation.finishedAt)
    }

    func testUnavailableEnergyEstimateDoesNotBecomeZero() throws {
        let data = Data("{\"reason\":\"missing_weight\"}".utf8)
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let estimate = try decoder.decode(WorkoutEnergyEstimate.self, from: data)
        XCTAssertNil(estimate.activeKcal)
        XCTAssertEqual(estimate.reason, "missing_weight")
    }

    func testCompletionWithoutSetsMatchesWebContract() async throws {
        ExecutionStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.authentication) }
            let json = try JSONSerialization.jsonObject(with: self.body(request)) as! [String: Any]
            XCTAssertEqual((json["sets"] as? [Any])?.count, 0)
            XCTAssertEqual(request.value(forHTTPHeaderField: "Idempotency-Key"), "empty-sets-key")
            return (200, "{\"session\":\(self.record)}")
        }
        _ = try await api.completeWorkoutExercise(sessionId: 8, exerciseId: 3, sets: [], idempotencyKey: "empty-sets-key")
    }

    func testPlayerIncludesFilledRowsWithoutInventingBlankSets() throws {
        let rows = [WorkoutDraftSet(), WorkoutDraftSet(loadKg: "0", repetitions: "8", isWarmup: true),
                    WorkoutDraftSet(loadKg: "12,5", repetitions: "10", completed: false)]
        let sets = try workoutPerformedSets(rows)
        XCTAssertEqual(sets.count, 2)
        XCTAssertEqual(sets[0].loadKg, 0)
        XCTAssertTrue(sets[0].isWarmup)
        XCTAssertEqual(sets[1].loadKg, 12.5)
        XCTAssertTrue(try workoutPerformedSets([WorkoutDraftSet()]).isEmpty)
        XCTAssertThrowsError(try workoutPerformedSets([WorkoutDraftSet(loadKg: "10")]))
    }

    func testLocalDraftRoundTripPreservesPendingWriteAndWarmups() throws {
        var draft = WorkoutLocalDraft()
        draft.sets["3"] = [WorkoutDraftSet(loadKg: "0", repetitions: "12", isWarmup: true, completed: true)]
        draft.activeExerciseId = 3
        draft.pendingCompletion = WorkoutPendingCompletion(exerciseId: 3, sets: try workoutPerformedSets(draft.sets["3"]!), key: "stable-key")
        draft.pendingFinishKey = "stable-finish"
        draft.restUntil = Date(timeIntervalSince1970: 12345)
        draft.pendingReopenExerciseIds = [3]
        let restored = try JSONDecoder().decode(WorkoutLocalDraft.self, from: JSONEncoder().encode(draft))
        XCTAssertEqual(restored.sets, draft.sets)
        XCTAssertEqual(restored.activeExerciseId, 3)
        XCTAssertEqual(restored.pendingCompletion?.key, "stable-key")
        XCTAssertEqual(restored.pendingCompletion?.sets.first?.loadKg, 0)
        XCTAssertTrue(restored.pendingCompletion?.sets.first?.isWarmup == true)
        XCTAssertEqual(restored.pendingFinishKey, "stable-finish")
        XCTAssertEqual(restored.restUntil, draft.restUntil)
        XCTAssertEqual(restored.pendingReopenExerciseIds, [3])
    }

    func testOverrideCatalogKeyIsPreservedForCorrectAnimation() throws {
        let data = Data(record.replacingOccurrences(of: "\"name\":\"Exercício substituído\"", with: "\"catalog_key\":\"workoutx:123\",\"name\":\"Exercício substituído\"").utf8)
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        let result = try decoder.decode(WorkoutExecutionSession.self, from: data)
        XCTAssertEqual(result.overrides.first?.catalogKey, "workoutx:123")
    }

    func testSingleWorkingSetIsNeverImplicitlyRepeated() throws {
        let rows = [WorkoutDraftSet(loadKg: "80", repetitions: "8", completed: true),
                    WorkoutDraftSet(), WorkoutDraftSet(), WorkoutDraftSet()]
        let performed = try workoutPerformedSets(rows)
        XCTAssertEqual(performed.count, 1)
        XCTAssertEqual(performed.first?.loadKg, 80)
        XCTAssertEqual(performed.first?.repetitions, 8)
        XCTAssertEqual(rows.filter(\.completed).count, 1)
    }

    func testExplicitRepeatFillsOnlyRemainingEmptyWorkingSets() throws {
        let rows = [WorkoutDraftSet(loadKg: "20", repetitions: "12", isWarmup: true, completed: true),
                    WorkoutDraftSet(loadKg: "80", repetitions: "8", completed: true),
                    WorkoutDraftSet(), WorkoutDraftSet(), WorkoutDraftSet()]
        let repeated = try workoutRepeatingSet(rows, at: 1)
        XCTAssertEqual(repeated.count, rows.count)
        XCTAssertEqual(repeated[0], rows[0])
        XCTAssertEqual(repeated[1], rows[1])
        XCTAssertTrue(repeated.dropFirst(2).allSatisfy {
            $0.loadKg == "80" && $0.repetitions == "8" && $0.completed && !$0.isWarmup
        })
        XCTAssertEqual(try workoutPerformedSets(repeated).count, 5)
        XCTAssertEqual(rows.filter(\.completed).count, 2, "The input draft must remain unchanged")
    }

    func testExplicitRepeatPreservesExistingEntriesWarmupsAndEarlierBlanks() throws {
        let rows = [WorkoutDraftSet(),
                    WorkoutDraftSet(loadKg: "80", repetitions: "8", completed: true),
                    WorkoutDraftSet(loadKg: "75", repetitions: "10", completed: true),
                    WorkoutDraftSet(loadKg: "20", repetitions: "12", isWarmup: true),
                    WorkoutDraftSet(isWarmup: true),
                    WorkoutDraftSet(loadKg: "70"),
                    WorkoutDraftSet(repetitions: "6"),
                    WorkoutDraftSet()]
        let repeated = try workoutRepeatingSet(rows, at: 1)
        XCTAssertEqual(Array(repeated.prefix(7)), Array(rows.prefix(7)))
        XCTAssertEqual(repeated[7], WorkoutDraftSet(loadKg: "80", repetitions: "8", completed: true))
    }

    func testWarmupCannotBeRepeatedAsWorkingSets() throws {
        let rows = [WorkoutDraftSet(loadKg: "20", repetitions: "12", isWarmup: true, completed: true),
                    WorkoutDraftSet(), WorkoutDraftSet()]
        XCTAssertEqual(try workoutRepeatingSet(rows, at: 0), rows)
    }

    func testExplicitRepeatValidatesSourceAndPreservesUnknownLoad() throws {
        XCTAssertThrowsError(try workoutRepeatingSet([WorkoutDraftSet()], at: 0))
        XCTAssertThrowsError(try workoutRepeatingSet([WorkoutDraftSet(loadKg: "20")], at: 0))
        XCTAssertThrowsError(try workoutRepeatingSet([], at: 0))
        XCTAssertThrowsError(try workoutRepeatingSet([WorkoutDraftSet(repetitions: "8")], at: -1))
        let repeated = try workoutRepeatingSet([WorkoutDraftSet(repetitions: "8", completed: true), WorkoutDraftSet()], at: 0)
        let performed = try workoutPerformedSets(repeated)
        XCTAssertEqual(performed.count, 2)
        XCTAssertTrue(performed.allSatisfy { $0.loadKg == nil && $0.repetitions == 8 })
    }

    func testCompletionQueueSurvivesRestartWithStableKeysAndReadsLegacyDrafts() throws {
        var draft = WorkoutLocalDraft()
        draft.completionQueue = [WorkoutPendingCompletion(exerciseId: 3, sets: [], key: "first"),
                                 WorkoutPendingCompletion(exerciseId: 4, sets: [], key: "second")]
        var restored = try JSONDecoder().decode(WorkoutLocalDraft.self, from: JSONEncoder().encode(draft))
        XCTAssertEqual(restored.completionQueue.map(\.key), ["first", "second"])
        restored.completionQueue.removeFirst()
        XCTAssertEqual(restored.pendingCompletion?.exerciseId, 4)
        let legacy = Data("{\"sets\":{},\"pendingCompletion\":{\"exerciseId\":3,\"sets\":[],\"key\":\"legacy\"}}".utf8)
        XCTAssertEqual(try JSONDecoder().decode(WorkoutLocalDraft.self, from: legacy).completionQueue.first?.key, "legacy")
    }

    func testLostStartResponseIsRecoveredByReadWithoutAnotherStart() async throws {
        var starts = 0
        var reads = 0
        ExecutionStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.authentication) }
            if request.httpMethod == "POST" {
                starts += 1
                throw URLError(.networkConnectionLost)
            }
            reads += 1
            return (200, "{\"session\":\(self.record)}")
        }
        do { _ = try await api.startWorkout(planId: 1, dayId: 2); XCTFail("Expected lost response") }
        catch let error as URLError { XCTAssertEqual(error.code, .networkConnectionLost) }
        let recovered = try await api.getWorkoutExecutionSession(planId: 1, dayId: 2)
        XCTAssertEqual(recovered?.id, 8)
        XCTAssertEqual(starts, 1, "Checking an uncertain start must not repeat the POST")
        XCTAssertEqual(reads, 1)
    }

    func testLostCancellationResponseIsCheckedWithoutRepeatingDelete() async throws {
        var deletes = 0
        ExecutionStubProtocol.handler = { request in
            if request.url!.path.hasSuffix("check_session") { return (200, self.authentication) }
            if request.httpMethod == "DELETE" { deletes += 1; throw URLError(.networkConnectionLost) }
            return (200, "{\"session\":null}")
        }
        do { try await api.cancelWorkout(sessionId: 8); XCTFail("Expected lost response") }
        catch let error as URLError { XCTAssertEqual(error.code, .networkConnectionLost) }
        let active = try await api.getWorkoutExecutionSession(planId: 1, dayId: 2)
        XCTAssertNil(active)
        XCTAssertEqual(deletes, 1)
    }

    func testOfflineReadIsFailureAndOnlySuccessfulResponseIsEmpty() async throws {
        var reads = 0
        ExecutionStubProtocol.handler = { _ in reads += 1; throw URLError(.notConnectedToInternet) }
        do { _ = try await api.getWorkoutActivities(); XCTFail("Offline must not return an empty history") }
        catch let error as URLError { XCTAssertEqual(error.code, .notConnectedToInternet) }
        XCTAssertEqual(reads, 1)
        ExecutionStubProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            return (200, "{\"items\":[],\"offset\":0,\"limit\":20,\"has_more\":false}")
        }
        let history = try await api.getWorkoutActivities()
        XCTAssertTrue(history.items.isEmpty)
        XCTAssertFalse(history.hasMore)
    }

    private func body(_ request: URLRequest) -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open(); defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 512)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count <= 0 { break }
            data.append(buffer, count: count)
        }
        return data
    }
}

private final class ExecutionStubProtocol: URLProtocol {
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
