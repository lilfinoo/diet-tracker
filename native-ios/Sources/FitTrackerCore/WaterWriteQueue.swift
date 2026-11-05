import Foundation

public struct WaterQueuedWrite: Codable, Sendable, Identifiable {
    public var id: String { entry.key }
    public let entry: WaterPendingEntry
    public private(set) var attempted: Bool
    public private(set) var undone: Bool
    public private(set) var receipt: WaterEntry?

    fileprivate init(entry: WaterPendingEntry, attempted: Bool = false, undone: Bool = false, receipt: WaterEntry? = nil) {
        self.entry = entry; self.attempted = attempted; self.undone = undone; self.receipt = receipt
    }

    fileprivate mutating func start() { attempted = true }
    fileprivate mutating func undo() { undone = true }
    fileprivate mutating func acknowledge(_ value: WaterEntry) { receipt = value }
}

/// Account-specific water intents. Attempted writes survive uncertainty and undo.
public struct WaterWriteQueue: Codable, Sendable {
    public private(set) var writes: [WaterQueuedWrite] = []
    public init() { }

    public init(restoring data: Data?) throws {
        guard let data else { return }
        if let queue = try? JSONDecoder().decode(Self.self, from: data) {
            self = queue
        } else {
            // The previous app stored one pending drink; it may already exist remotely.
            let legacy = try JSONDecoder().decode(WaterPendingEntry.self, from: data)
            writes = [WaterQueuedWrite(entry: legacy, attempted: true)]
        }
    }

    public mutating func append(_ entry: WaterPendingEntry) { writes.append(WaterQueuedWrite(entry: entry)) }

    public mutating func markAttempted(_ key: String) {
        guard let index = writes.firstIndex(where: { $0.id == key }) else { return }
        writes[index].start()
    }

    public mutating func undo(_ key: String) {
        guard let index = writes.firstIndex(where: { $0.id == key }) else { return }
        if writes[index].attempted { writes[index].undo() } else { writes.remove(at: index) }
    }

    public mutating func removeConfirmed(_ entry: WaterEntry) {
        guard !writes.contains(where: { $0.receipt?.id == entry.id }) else { return }
        writes.append(WaterQueuedWrite(
            entry: WaterPendingEntry(amountMl: entry.amountMl, key: "delete-\(entry.id)"),
            attempted: true, undone: true, receipt: entry
        ))
    }

    /// Returns true when an undo still needs its compensating DELETE.
    @discardableResult public mutating func acknowledge(_ key: String, receipt: WaterEntry) -> Bool {
        guard let index = writes.firstIndex(where: { $0.id == key }) else { return false }
        if writes[index].undone {
            writes[index].acknowledge(receipt)
            return true
        }
        writes.remove(at: index)
        return false
    }

    public mutating func confirmRemoval(_ key: String) { writes.removeAll { $0.id == key } }

    public func visiblePending(date: String, timezone: String) -> [WaterQueuedWrite] {
        writes.filter { !$0.undone && Self.localDate($0.entry.occurredAt, timezone: timezone) == date }
    }

    public func visibleEntries(_ entries: [WaterEntry], date: String, timezone: String, confirmedDates: [Int: String] = [:]) -> [WaterEntry] {
        let removed = Set(writes.filter(\.undone).compactMap { $0.receipt?.id })
        return entries.filter { !removed.contains($0.id) && (confirmedDates[$0.id] ?? Self.localDate($0.occurredAt, timezone: timezone)) == date }
    }

    public func total(entries: [WaterEntry], date: String, timezone: String, confirmedDates: [Int: String] = [:]) -> Int {
        visibleEntries(entries, date: date, timezone: timezone, confirmedDates: confirmedDates).reduce(0) { $0 + $1.amountMl }
            + visiblePending(date: date, timezone: timezone).reduce(0) { $0 + $1.entry.amountMl }
    }

    public static func localDate(_ timestamp: String, timezone: String) -> String? {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = parser.date(from: timestamp) ?? ISO8601DateFormatter().date(from: timestamp) else { return nil }
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: timezone) ?? TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }
}
