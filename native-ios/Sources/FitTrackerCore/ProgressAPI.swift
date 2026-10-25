import Foundation

extension FitTrackerAPI {
    public func getPersonalRecords(offset: Int = 0, search: String = "") async throws -> PersonalRecordPage {
        var queryItems = [
            URLQueryItem(name: "limit", value: "50"),
            URLQueryItem(name: "offset", value: String(max(0, offset)))
        ]
        if !search.isEmpty { queryItems.append(URLQueryItem(name: "search", value: search)) }
        return try await request("progress/personal-records", queryItems: queryItems, as: PersonalRecordPage.self)
    }

    public func getProgressOverview() async throws -> ProgressOverview {
        try await request("progress/overview", queryItems: [URLQueryItem(name: "view", value: "summary")],
                          as: ProgressOverview.self)
    }

    public func getBodyMetricSeries(metric: BodyMetric) async throws -> BodyMetricSeries {
        try await request("measurements/summary", queryItems: [URLQueryItem(name: "metric", value: metric.rawValue)],
                          as: BodyMetricSeries.self)
    }

    public func getProgressAchievements() async throws -> ProgressAchievements {
        try await request("progress/achievements", as: ProgressAchievements.self)
    }

    public func getBodyProgressSummary() async throws -> BodyProgressSummary {
        try await request("measurements/summary", as: BodyProgressSummary.self)
    }

    public func getExerciseProgressOptions() async throws -> ExerciseProgressOptions {
        try await request("progress/exercises", as: ExerciseProgressOptions.self)
    }

    public func getExerciseProgress(key: String, offset: Int = 0) async throws -> ExerciseProgressHistory {
        try await request("progress/exercises/\(key)", queryItems: [
            URLQueryItem(name: "view", value: "sessions"),
            URLQueryItem(name: "limit", value: "20"),
            URLQueryItem(name: "offset", value: String(max(0, offset)))
        ], as: ExerciseProgressHistory.self)
    }

    public func getProgressDayActivities(date: String, offset: Int = 0) async throws -> ProgressDayActivities {
        let response = try await request("activities", queryItems: [
            URLQueryItem(name: "date", value: date),
            URLQueryItem(name: "limit", value: "20"),
            URLQueryItem(name: "offset", value: String(max(0, offset)))
        ], as: ProgressDayActivities.self)
        guard response.date == date else {
            throw APIError.http(status: 501, message: "Os detalhes de treino por dia precisam de uma atualização do servidor. Seu histórico continua disponível na aba Treino.")
        }
        return response
    }
}
