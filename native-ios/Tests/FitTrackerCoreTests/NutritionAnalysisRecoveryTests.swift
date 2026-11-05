import XCTest
@testable import FitTrackerCore

final class NutritionAnalysisRecoveryTests: XCTestCase {
    private var directory: URL!
    override func setUp() {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    }
    override func tearDown() {
        try? FileManager.default.removeItem(at: directory)
    }

    func testReopeningPreservesExactConfirmedPayloadAndRequestKey() throws {
        let owner = UUID()
        let photo = Data([0xff, 0xd8, 0xff, 42])
        let draft = NutritionAnalysisDraft(date: "2026-10-21", mealType: "Jantar", description: "Arroz e feijão", photoData: photo, freeRemaining: 1)
        try NutritionAnalysisRecovery(directory: directory).save(draft, owner: owner)
        let restored = try XCTUnwrap(NutritionAnalysisRecovery(directory: directory).load(owner: owner))
        XCTAssertEqual(restored.requestKey, draft.requestKey)
        XCTAssertEqual(restored.photoData, photo)
        XCTAssertEqual(restored.description, "Arroz e feijão")
        XCTAssertEqual(restored.mealType, "Jantar")
        XCTAssertEqual(restored.date, "2026-10-21")
        XCTAssertEqual(restored.freeRemaining, 1)
    }

    func testQueuedJobAndCompletedEstimateSurviveRestartWithoutInventingMacros() throws {
        let owner = UUID(), job = UUID()
        let store = NutritionAnalysisRecovery(directory: directory)
        var draft = NutritionAnalysisDraft(date: "2026-10-21", mealType: "Almoço", description: "Arroz", photoData: nil, freeRemaining: nil)
        draft.jobId = job
        try store.save(draft, owner: owner)
        var restored = try XCTUnwrap(store.load(owner: owner))
        XCTAssertEqual(restored.jobId, job)
        restored.estimate = try JSONDecoder().decode(NutritionEstimate.self, from: Data("{\"description\":\"Arroz\",\"calories\":120}".utf8))
        try store.save(restored, owner: owner)
        let completed = try XCTUnwrap(NutritionAnalysisRecovery(directory: directory).load(owner: owner))
        XCTAssertEqual(completed.requestKey, draft.requestKey)
        XCTAssertEqual(completed.estimate?.calories, 120)
        XCTAssertNil(completed.estimate?.protein)
        XCTAssertNil(completed.photoData)
    }

    func testAccountsRemainIsolatedAndDiscardOnlyRemovesOwningDraft() throws {
        let alice = UUID(), bob = UUID()
        let store = NutritionAnalysisRecovery(directory: directory)
        let draft = NutritionAnalysisDraft(date: "2026-10-21", mealType: "Almoço", description: "Privado", photoData: nil, freeRemaining: 3)
        try store.save(draft, owner: alice)
        XCTAssertNil(try store.load(owner: bob))
        try store.save(draft, owner: bob)
        try store.clear(owner: alice)
        XCTAssertNil(try store.load(owner: alice))
        XCTAssertEqual(try store.load(owner: bob)?.description, "Privado")
    }

    func testRecoveredAnalysisPreservesItsPlannedMealLink() throws {
        let owner = UUID(), store = NutritionAnalysisRecovery(directory: directory)
        let draft = NutritionAnalysisDraft(date: "2026-10-21", mealType: "Almoço", description: "Arroz", photoData: nil, freeRemaining: 1, slotKey: "almoco", planMealId: 42)
        try store.save(draft, owner: owner)
        let restored = try XCTUnwrap(store.load(owner: owner))
        XCTAssertEqual(restored.slotKey, "almoco")
        XCTAssertEqual(restored.planMealId, 42)
    }

    func testLegacyAnalysisWithoutSlotRemainsAnIndependentEntry() throws {
        let data = Data("{\"requestKey\":\"old\",\"date\":\"2026-10-21\",\"mealType\":\"Almoço\",\"description\":\"Arroz\"}".utf8)
        let restored = try JSONDecoder().decode(NutritionAnalysisDraft.self, from: data)
        XCTAssertNil(restored.slotKey)
        XCTAssertNil(restored.planMealId)
    }

    func testUnreadableDraftIsNotSilentlyTreatedAsNoPendingAnalysis() throws {
        let owner = UUID()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try Data("broken".utf8).write(to: directory.appendingPathComponent(owner.uuidString + ".json"))
        XCTAssertThrowsError(try NutritionAnalysisRecovery(directory: directory).load(owner: owner))
    }

    func testFailedPersistenceIsReportedBeforeRequestCanBeSent() throws {
        try Data().write(to: directory)
        let draft = NutritionAnalysisDraft(date: "2026-10-21", mealType: "Almoço", description: "Arroz", photoData: nil, freeRemaining: 3)
        XCTAssertThrowsError(try NutritionAnalysisRecovery(directory: directory).save(draft, owner: UUID()))
    }
}
