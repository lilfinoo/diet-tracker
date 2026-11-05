import Foundation

/// Nutrients come from the food table, whose reference quantity is 100 grams.
public struct MealFoodPortion: Identifiable, Equatable, Sendable {
    public let id: UUID
    public let name: String
    public var grams: Double
    public let caloriesPer100g: Double
    public let proteinPer100g: Double
    public let carbsPer100g: Double
    public let fatPer100g: Double

    public init(name: String, grams: Double, calories: Double, protein: Double, carbs: Double, fat: Double) {
        id = UUID(); self.name = name; self.grams = grams
        caloriesPer100g = calories; proteinPer100g = protein; carbsPer100g = carbs; fatPer100g = fat
    }
    public var calories: Double { caloriesPer100g * grams / 100 }
    public var protein: Double { proteinPer100g * grams / 100 }
    public var carbs: Double { carbsPer100g * grams / 100 }
    public var fat: Double { fatPer100g * grams / 100 }
}
