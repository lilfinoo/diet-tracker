import XCTest
@testable import FitTrackerCore

final class DietPremiumPreferencesTests: XCTestCase {
    func testFreeGenerationDropsPremiumDraftOptionsAndPreservesSafety() {
        var preferences = DietPlanPreferences()
        preferences.goal = "fat_loss"; preferences.mealsPerDay = 7
        preferences.dietPattern = "vegetarian"; preferences.trainingDaysPerWeek = 5
        preferences.allergies = ["amendoim"]; preferences.intolerances = ["lactose"]
        preferences.preferredFoods = ["banana"]; preferences.dislikedFoods = ["berinjela"]
        preferences.availableIngredients = ["arroz"]
        preferences.budget = "economical"; preferences.prepMinutes = 15
        preferences.changePace = "moderate"; preferences.notes = "Treino às 19h"
        let result = preferences.forGeneration(hasPremium: false)
        XCTAssertEqual(result.goal, preferences.goal)
        XCTAssertEqual(result.mealsPerDay, 7)
        XCTAssertEqual(result.dietPattern, "vegetarian")
        XCTAssertEqual(result.trainingDaysPerWeek, 5)
        XCTAssertEqual(result.allergies, ["amendoim"])
        XCTAssertEqual(result.intolerances, ["lactose"])
        XCTAssertEqual(result.preferredFoods, [])
        XCTAssertEqual(result.dislikedFoods, [])
        XCTAssertEqual(result.availableIngredients, [])
        XCTAssertEqual(result.budget, "moderate")
        XCTAssertEqual(result.prepMinutes, 30)
        XCTAssertEqual(result.changePace, "conservative")
        XCTAssertEqual(result.notes, "")
        XCTAssertEqual(preferences.notes, "Treino às 19h")
    }

    func testPremiumGenerationKeepsAllOptions() {
        var preferences = DietPlanPreferences()
        preferences.budget = "economical"; preferences.prepMinutes = 15
        preferences.changePace = "moderate"; preferences.notes = "Almoço às 12h"
        preferences.preferredFoods = ["arroz"]; preferences.dislikedFoods = ["fígado"]
        XCTAssertEqual(preferences.forGeneration(hasPremium: true), preferences)
    }
}
