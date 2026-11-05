import XCTest
@testable import FitTrackerCore

@MainActor
final class WaterTrackerTests: XCTestCase {
    private let owner = UUID()
    private let timestamp = Date(timeIntervalSince1970: 1793275200)
    private let date = "2026-10-29"
    private let timezone = "America/Sao_Paulo"
    private var storage: UserDefaults!
    private var suite: String!

    override func setUp() {
        super.setUp()
        suite = "water-tests-" + UUID().uuidString
        storage = UserDefaults(suiteName: suite)!
    }
    override func tearDown() {
        storage.removePersistentDomain(forName: suite)
        super.tearDown()
    }
    private func make(_ api: WaterMock, active: @escaping () -> Bool = { true }) -> WaterTracker {
        WaterTracker(api: api, ownerId: owner, defaults: storage, isCurrentOwner: active)
    }
    private func total(_ tracker: WaterTracker) -> Int { tracker.total(date: date, timezone: timezone) }
    private func waitUntil(_ condition: () -> Bool, file: StaticString = #filePath, line: UInt = #line) async {
        for _ in 0..<2000 { if condition() { return }; await Task.yield() }
        XCTFail("Asynchronous water operation did not finish", file: file, line: line)
    }

    func testRapidTapsAreImmediatelyVisibleAndInflightUndoNeverFlashesBack() async {
        let api = WaterMock(); api.holdAdds = true; api.holdDeletes = true
        let tracker = make(api)
        for _ in 0..<3 { tracker.record(200, at: timestamp) }
        XCTAssertEqual(total(tracker), 600)
        XCTAssertEqual(tracker.queue.writes.count, 3)
        let keys = tracker.queue.writes.map(\.id)
        XCTAssertEqual(Set(keys).count, 3)
        await waitUntil { api.addKeys.count == 1 }
        tracker.undoPending(keys[0])
        XCTAssertEqual(total(tracker), 400)
        api.releaseAdd(keys[0])
        await waitUntil { api.deleteIds.count == 1 }
        XCTAssertEqual(total(tracker), 400, "POST acknowledgment cannot resurrect an undone drink")
        api.releaseDelete()
        await waitUntil { api.addKeys.count == 2 }
        api.holdAdds = false
        api.releaseAdd(keys[1])
        await waitUntil { !tracker.saving && tracker.queue.writes.isEmpty }
        XCTAssertEqual(total(tracker), 400)
        XCTAssertEqual(api.addKeys, keys)
        XCTAssertEqual(api.deleteIds.count, 1)
    }

    func testUndoQueuedTapDoesNotSendItsPost() async {
        let api = WaterMock(); api.holdAdds = true
        let tracker = make(api)
        tracker.record(200, at: timestamp); tracker.record(300, at: timestamp)
        let keys = tracker.queue.writes.map(\.id)
        await waitUntil { api.addKeys.count == 1 }
        tracker.undoPending(keys[1])
        XCTAssertEqual(total(tracker), 200)
        api.releaseAdd(keys[0])
        await waitUntil { !tracker.saving }
        XCTAssertEqual(api.addKeys, [keys[0]])
        XCTAssertEqual(total(tracker), 200)
    }

    func testLostResponseRetainsKeyAndUndoReplaysReceiptThenDeletes() async {
        let api = WaterMock(); api.failFirstAddAfterCommit = true
        let tracker = make(api)
        tracker.record(300, at: timestamp)
        let key = tracker.queue.writes[0].id
        await waitUntil { tracker.error != nil && !tracker.saving }
        XCTAssertEqual(api.serverEntries.count, 1)
        XCTAssertEqual(total(tracker), 300)
        XCTAssertTrue(tracker.queue.writes[0].attempted)
        tracker.undoPending(key)
        XCTAssertEqual(total(tracker), 0)
        await waitUntil { tracker.queue.writes.isEmpty && !tracker.saving }
        XCTAssertEqual(api.addKeys, [key, key])
        XCTAssertEqual(api.serverEntries.count, 0)
        XCTAssertEqual(total(tracker), 0, "Cached POST summary must not restore the removed drink")
    }

    func testRestartPreservesLegacyUncertaintyAndUndoTombstone() throws {
        let old = WaterPendingEntry(amountMl: 300, occurredAt: timestamp, key: "legacy-key")
        var queue = try WaterWriteQueue(restoring: JSONEncoder().encode(old))
        XCTAssertTrue(queue.writes[0].attempted)
        queue.undo("legacy-key")
        let restored = try WaterWriteQueue(restoring: JSONEncoder().encode(queue))
        XCTAssertEqual(restored.writes[0].id, "legacy-key")
        XCTAssertTrue(restored.writes[0].undone)
        XCTAssertTrue(restored.writes[0].attempted)
    }

    func testDeleteLostResponseKeepsUndoAnd404RetryConfirmsAbsence() async {
        let api = WaterMock(); api.failFirstDeleteAfterCommit = true
        let tracker = make(api)
        tracker.record(200, at: timestamp)
        await waitUntil { !tracker.saving && !tracker.entries.isEmpty }
        tracker.undoConfirmed(tracker.entries[0])
        XCTAssertEqual(total(tracker), 0)
        await waitUntil { !tracker.saving && tracker.error != nil }
        XCTAssertEqual(tracker.queue.writes.count, 1)
        await tracker.refresh()
        XCTAssertTrue(tracker.queue.writes.isEmpty)
        XCTAssertEqual(total(tracker), 0)
        XCTAssertEqual(api.deleteIds.count, 2)
    }

    func testLateGetCannotOverwriteNewTaps() async {
        let api = WaterMock(); api.holdNextGet = true; api.holdAdds = true
        let tracker = make(api)
        let loading = Task { await tracker.refresh() }
        await waitUntil { api.getHeld != nil }
        tracker.record(300, at: timestamp)
        XCTAssertEqual(total(tracker), 300)
        api.releaseGet()
        await loading.value
        XCTAssertEqual(total(tracker), 300)
        let key = tracker.queue.writes[0].id
        await waitUntil { api.addKeys.count == 1 }
        api.releaseAdd(key)
        await waitUntil { !tracker.saving }
        XCTAssertEqual(total(tracker), 300)
    }

    func testAccountSwitchStopsRemainingWritesAndKeepsSeparateStorage() async {
        let api = WaterMock(); api.holdAdds = true
        var active = true
        let tracker = make(api, active: { active })
        tracker.record(200, at: timestamp); tracker.record(300, at: timestamp)
        let first = tracker.queue.writes[0].id
        await waitUntil { api.addKeys.count == 1 }
        active = false
        api.releaseAdd(first)
        await waitUntil { !tracker.saving }
        XCTAssertEqual(api.addKeys.count, 1)
        XCTAssertEqual(tracker.queue.writes.count, 1)
        let other = WaterTracker(api: api, ownerId: UUID(), defaults: storage, isCurrentOwner: { true })
        XCTAssertTrue(other.queue.writes.isEmpty)
        XCTAssertEqual(total(other), 0)
        active = true; api.holdAdds = false
        await tracker.refresh()
        XCTAssertEqual(total(tracker), 500)
    }

    func testTenRapidTapsKeepFrozenVolumesWhileBottleChanges() async throws {
        let api = WaterMock(); api.holdAdds = true
        let tracker = make(api)
        for amount in [200, 750, 200, 750, 200, 750, 200, 750, 200, 750] { tracker.record(amount, at: timestamp) }
        XCTAssertEqual(total(tracker), 4750)
        let keys = tracker.queue.writes.map(\.id)
        XCTAssertEqual(Set(keys).count, 10)
        await waitUntil { api.addKeys.count == 1 }
        try await tracker.saveBottle(1000)
        XCTAssertEqual(total(tracker), 4750)
        api.holdAdds = false; api.releaseAdd(keys[0])
        await waitUntil { !tracker.saving && tracker.queue.writes.isEmpty }
        XCTAssertEqual(total(tracker), 4750)
        XCTAssertEqual(api.addKeys, keys)
        XCTAssertEqual(tracker.visibleEntries(date: date, timezone: timezone).first?.id, 10)
    }

    func testSavingBottleInvalidatesOlderGet() async throws {
        let api = WaterMock(); api.holdNextGet = true
        let tracker = make(api)
        let loading = Task { await tracker.refresh() }
        await waitUntil { api.getHeld != nil }
        try await tracker.saveBottle(1000)
        XCTAssertEqual(tracker.day?.bottleCapacityMl, 1000)
        api.releaseGet()
        await loading.value
        XCTAssertEqual(tracker.day?.bottleCapacityMl, 1000, "Earlier GET must not restore old capacity")
    }

    func testConfirmedEntryKeepsServerDayAfterProfileTimezoneChanges() async {
        let api = WaterMock()
        api.serverEntries = [WaterEntry(id: 5, amountMl: 300, occurredAt: "2026-10-28T18:00:00Z")]
        let tracker = make(api)
        await tracker.refresh()
        XCTAssertEqual(total(tracker), 300, "Server local_date belongs to the summary, not recomputed using the new timezone")
        XCTAssertEqual(tracker.total(date: "2026-10-28", timezone: timezone), 0)
    }

    func testUnreadablePendingStorageIsPreservedInsteadOfOverwritten() async {
        let key = "fittracker.native.water.pending.\(owner)"
        let original = Data("unreadable pending data".utf8)
        storage.set(original, forKey: key)
        let api = WaterMock(); let tracker = make(api)
        tracker.record(200, at: timestamp)
        await tracker.refresh()
        XCTAssertEqual(storage.data(forKey: key), original)
        XCTAssertNotNil(tracker.error)
        XCTAssertTrue(api.addKeys.isEmpty)
    }

    func testPendingVolumesRespectOriginalTimestampAndTimezoneAcrossMidnight() {
        var queue = WaterWriteQueue()
        let timestamp = ISO8601DateFormatter().date(from: "2026-10-29T02:59:59Z")!
        queue.append(WaterPendingEntry(amountMl: 750, occurredAt: timestamp))
        XCTAssertEqual(queue.total(entries: [], date: "2026-10-28", timezone: timezone), 750)
        XCTAssertEqual(queue.total(entries: [], date: "2026-10-29", timezone: timezone), 0)
        XCTAssertEqual(queue.total(entries: [], date: "2026-10-29", timezone: "UTC"), 750)
    }
}

@MainActor
private final class WaterMock: WaterAPIClient {
    var serverEntries: [WaterEntry] = []
    var capacity = 750
    var addKeys: [String] = []
    var deleteIds: [Int] = []
    var holdAdds = false
    var holdDeletes = false
    var holdNextGet = false
    var failFirstAddAfterCommit = false
    var failFirstDeleteAfterCommit = false
    var getHeld: CheckedContinuation<Void, Never>?
    private var adds: [String: CheckedContinuation<Void, Never>] = [:]
    private var deleteHeld: CheckedContinuation<Void, Never>?
    private var receipts: [String: WaterDay] = [:]
    private var nextId = 1

    private func summary(entry: WaterEntry? = nil) -> WaterDay {
        WaterDay(date: "2026-10-29", timezone: "America/Sao_Paulo", totalMl: serverEntries.reduce(0) { $0 + $1.amountMl }, bottleCapacityMl: capacity, entries: serverEntries, entry: entry)
    }
    func getWater(date: String?) async throws -> WaterDay {
        let result = summary()
        if holdNextGet {
            holdNextGet = false
            await withCheckedContinuation { getHeld = $0 }
        }
        return result
    }
    func addWater(_ entry: WaterPendingEntry, ownerId: UUID) async throws -> WaterDay {
        addKeys.append(entry.key)
        if holdAdds { await withCheckedContinuation { adds[entry.key] = $0 } }
        if let receipt = receipts[entry.key] { return receipt }
        let receipt = WaterEntry(id: nextId, amountMl: entry.amountMl, occurredAt: entry.occurredAt)
        nextId += 1; serverEntries.append(receipt)
        let result = summary(entry: receipt); receipts[entry.key] = result
        if failFirstAddAfterCommit { failFirstAddAfterCommit = false; throw URLError(.networkConnectionLost) }
        return result
    }
    func deleteWater(entryId: Int, ownerId: UUID) async throws -> WaterDay {
        deleteIds.append(entryId)
        if holdDeletes { await withCheckedContinuation { deleteHeld = $0 } }
        guard serverEntries.contains(where: { $0.id == entryId }) else { throw APIError.http(status: 404, message: "Ausente") }
        serverEntries.removeAll { $0.id == entryId }
        if failFirstDeleteAfterCommit { failFirstDeleteAfterCommit = false; throw URLError(.networkConnectionLost) }
        return summary()
    }
    func saveWaterBottle(capacityMl: Int, ownerId: UUID) async throws -> WaterDay { capacity = capacityMl; return summary() }
    func releaseAdd(_ key: String) { adds.removeValue(forKey: key)?.resume() }
    func releaseDelete() { deleteHeld?.resume(); deleteHeld = nil }
    func releaseGet() { getHeld?.resume(); getHeld = nil }
}
