import Foundation

public struct NutrientValues: Decodable, Sendable {
    public let calories: Double?
    public let protein: Double?
    public let carbs: Double?
    public let fat: Double?
}

public struct DietDayResponse: Decodable, Sendable {
    public let date: String
    public let plan: DietPlanSummary?
    public let slots: [DietDaySlot]
    public let manualEntries: [DietEntry]
    public let totals: NutrientValues
    public let targets: NutrientValues

    /// Includes consumption linked to planned slots as well as manual entries.
    public var entries: [DietEntry] { manualEntries + slots.compactMap(\.entry) }

    /// Local feedback while the server confirms a planned consumption.
    /// Unknown totals remain unknown; an entry is only supplied by the server.
    public func applyingPlannedOutcome(slotKey: String, outcome: DietSlotOutcome) -> DietDayResponse {
        guard let slot = slots.first(where: { $0.slotKey == slotKey && $0.result == "pending" }),
              let meal = slot.alternatives.first(where: { $0.id == slot.selectedPlanMealId }) else { return self }
        let updatedSlots = slots.map { value in
            value.slotKey == slotKey ? DietDaySlot(slotKey: value.slotKey, label: value.label,
                alternatives: value.alternatives, selectedPlanMealId: value.selectedPlanMealId,
                result: outcome.rawValue, entry: nil) : value
        }
        func add(_ total: Double?, _ amount: Double?) -> Double? {
            guard outcome == .consumedPlanned, let total, let amount else { return total }
            return total + amount
        }
        return DietDayResponse(date: date, plan: plan, slots: updatedSlots, manualEntries: manualEntries,
            totals: NutrientValues(calories: add(totals.calories, meal.calories),
                protein: add(totals.protein, meal.protein), carbs: add(totals.carbs, meal.carbs),
                fat: add(totals.fat, meal.fat)), targets: targets)
    }

    /// Replace the pending slot with the authoritative write response, without
    /// counting a planned consumption twice when optimistic feedback is visible.
    public func applyingConfirmedOutcome(_ state: DietSlotState) -> DietDayResponse {
        guard let slot = slots.first(where: { $0.slotKey == state.slotKey }) else { return self }
        let planned = slot.alternatives.first(where: { $0.id == slot.selectedPlanMealId })
        func adjust(_ total: Double?, _ old: Double?, _ new: Double?) -> Double? {
            guard let total else { return nil }
            return total - (old ?? 0) + (new ?? 0)
        }
        let old = slot.entry.map { NutrientValues(calories: $0.calories, protein: $0.protein, carbs: $0.carbs, fat: $0.fat) }
            ?? (slot.result == "consumed_planned" ? planned.map { NutrientValues(calories: $0.calories, protein: $0.protein, carbs: $0.carbs, fat: $0.fat) } : nil)
        let updated = slots.map { value in
            value.slotKey == state.slotKey ? DietDaySlot(slotKey: value.slotKey, label: value.label,
                alternatives: value.alternatives, selectedPlanMealId: state.selectedPlanMealId,
                result: state.result, entry: state.entry) : value
        }
        return DietDayResponse(date: date, plan: plan, slots: updated, manualEntries: manualEntries,
            totals: NutrientValues(calories: adjust(totals.calories, old?.calories, state.entry?.calories),
                protein: adjust(totals.protein, old?.protein, state.entry?.protein),
                carbs: adjust(totals.carbs, old?.carbs, state.entry?.carbs),
                fat: adjust(totals.fat, old?.fat, state.entry?.fat)), targets: targets)
    }

}

public struct DietPlanSummary: Decodable, Sendable, Identifiable {
    public let id: Int
    public let title: String
    public let description: String?
    public let mealsCount: Int
}

public struct DietDaySlot: Decodable, Sendable, Identifiable {
    public var id: String { slotKey }
    public let slotKey: String
    public let label: String
    public let alternatives: [DietMealAlternative]
    public let selectedPlanMealId: Int
    public let result: String
    public let entry: DietEntry?
}

public struct DietMealAlternative: Decodable, Sendable, Identifiable {
    public let id: Int
    public let mealType: String
    public let description: String
    public let calories: Double?
    public let protein: Double?
    public let carbs: Double?
    public let fat: Double?
    public let notes: String?
    public let option: Int?
}

public struct DietEntry: Decodable, Sendable, Identifiable {
    public let id: Int
    public let date: String
    public let mealType: String
    public let description: String
    public let calories: Double?
    public let protein: Double?
    public let carbs: Double?
    public let fat: Double?
    public let notes: String?
    public let source: String?
    public let dailyMealStateId: UUID?
}

public struct NewDietEntry: Encodable, Sendable {
    public let date: String
    public let mealType: String
    public let description: String
    public let calories: Double?
    public let protein: Double?
    public let carbs: Double?
    public let fat: Double?
    public let notes: String?

    public init(date: String, mealType: String, description: String,
                calories: Double? = nil, protein: Double? = nil,
                carbs: Double? = nil, fat: Double? = nil, notes: String? = nil) {
        self.date = date; self.mealType = mealType; self.description = description
        self.calories = calories; self.protein = protein; self.carbs = carbs
        self.fat = fat; self.notes = notes
    }
}

public struct NutritionEstimate: Codable, Sendable {
    public let description: String
    public let calories: Double?
    public let protein: Double?
    public let carbs: Double?
    public let fat: Double?
}

public struct NutritionImage: Encodable, Sendable {
    public let data: String
    public let mimeType: String
    public init(data: Data, mimeType: String) {
        self.data = data.base64EncodedString(); self.mimeType = mimeType
    }
}

/// Analysis never creates a diary entry. The caller must review and save explicitly.
public enum NutritionAnalysisResponse: Decodable, Sendable {
    case estimate(NutritionEstimate)
    case queued(jobId: UUID)

    private enum CodingKeys: String, CodingKey { case jobId }
    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        if let id = try container.decodeIfPresent(UUID.self, forKey: .jobId) {
            self = .queued(jobId: id)
        } else {
            self = .estimate(try NutritionEstimate(from: decoder))
        }
    }
}

public struct NutritionAnalysisTask: Decodable, Sendable {
    public let jobId: UUID
    public let status: String
    public let httpStatus: Int?
    public let result: NutritionEstimate?
    public let error: String?

    private enum CodingKeys: String, CodingKey { case jobId, status, httpStatus, result, error }
    public init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        jobId = try values.decode(UUID.self, forKey: .jobId)
        status = try values.decode(String.self, forKey: .status)
        httpStatus = try values.decodeIfPresent(Int.self, forKey: .httpStatus)
        error = try values.decodeIfPresent(String.self, forKey: .error)
        result = status == "succeeded" ? try values.decode(NutritionEstimate.self, forKey: .result) : nil
    }
}
