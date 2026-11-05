import Foundation

/// The confirmed analysis request survives process termination. Reuse its exact
/// payload/key until a result is reviewed, saved or explicitly discarded.
public struct NutritionAnalysisDraft: Codable, Sendable {
    public let requestKey: String
    public let date: String
    public let mealType: String
    public let description: String
    public let photoData: Data?
    public let freeRemaining: Int?
    public var jobId: UUID?
    public var estimate: NutritionEstimate?
    public let slotKey: String?
    public let planMealId: Int?

    public init(date: String, mealType: String, description: String, photoData: Data?, freeRemaining: Int?, slotKey: String? = nil, planMealId: Int? = nil) {
        requestKey = UUID().uuidString
        self.date = date; self.mealType = mealType; self.description = description
        self.photoData = photoData; self.freeRemaining = freeRemaining
        self.slotKey = slotKey; self.planMealId = planMealId
    }
}

public struct NutritionAnalysisRecovery {
    private let directory: URL

    public init(directory: URL? = nil) {
        self.directory = directory ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("FitTracker/NutritionRecovery", isDirectory: true)
    }

    public func load(owner: UUID) throws -> NutritionAnalysisDraft? {
        let url = file(owner)
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        return try JSONDecoder().decode(NutritionAnalysisDraft.self, from: Data(contentsOf: url))
    }

    public func save(_ draft: NutritionAnalysisDraft, owner: UUID) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var options: Data.WritingOptions = [.atomic]
        #if os(iOS)
        options.insert(.completeFileProtectionUnlessOpen)
        #endif
        let url = file(owner)
        try JSONEncoder().encode(draft).write(to: url, options: options)
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        var savedURL = url; try savedURL.setResourceValues(values)
    }

    public func clear(owner: UUID) throws {
        let url = file(owner)
        if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
    }

    private func file(_ owner: UUID) -> URL { directory.appendingPathComponent(owner.uuidString + ".json") }
}
