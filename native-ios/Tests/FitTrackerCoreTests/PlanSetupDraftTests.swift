import XCTest
@testable import FitTrackerCore

final class PlanSetupDraftTests: XCTestCase {
    func testReopeningPreservesRestrictionsProgressAndRequestIdentity() throws {
        let suite = "PlanSetupDraftTests.\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let owner = UUID()
        let store = PlanSetupDraftStore(defaults: defaults)
        var draft = PlanSetupDraft()
        draft.step = 2
        draft.diet.goal = "fat_loss"
        draft.diet.dietPattern = "vegetarian"
        draft.allergies = "amendoim, frutos do mar"
        draft.intolerances = "lactose"
        draft.routine = "Treino às 19h"
        try store.save(draft, owner: owner, kind: .diet)

        let reopened = PlanSetupDraftStore(defaults: defaults)
        XCTAssertEqual(try reopened.load(owner: owner, kind: .diet), draft)
        XCTAssertEqual(try reopened.load(owner: owner, kind: .diet)?.requestKey, draft.requestKey)
    }

    func testAccountsAndPlanTypesHaveIndependentDrafts() throws {
        let suite = "PlanSetupDraftTests.\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let store = PlanSetupDraftStore(defaults: defaults)
        let first = UUID(), second = UUID()
        var diet = PlanSetupDraft()
        diet.allergies = "amendoim"
        var workout = PlanSetupDraft()
        workout.workout.limitations = "Evitar impacto"
        try store.save(diet, owner: first, kind: .diet)
        try store.save(workout, owner: first, kind: .workout)
        try store.save(PlanSetupDraft(), owner: second, kind: .diet)

        store.clear(owner: first, kind: .diet)

        XCTAssertNil(try store.load(owner: first, kind: .diet))
        XCTAssertEqual(try store.load(owner: first, kind: .workout), workout)
        XCTAssertNotNil(try store.load(owner: second, kind: .diet))
        XCTAssertNil(try store.load(owner: second, kind: .workout))
    }
}
