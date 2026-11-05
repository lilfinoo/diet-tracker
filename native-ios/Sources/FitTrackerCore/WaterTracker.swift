import Combine
import Foundation

public protocol WaterAPIClient: Sendable {
    func getWater(date: String?) async throws -> WaterDay
    func addWater(_ entry: WaterPendingEntry, ownerId: UUID) async throws -> WaterDay
    func deleteWater(entryId: Int, ownerId: UUID) async throws -> WaterDay
    func saveWaterBottle(capacityMl: Int, ownerId: UUID) async throws -> WaterDay
}
extension FitTrackerAPI: WaterAPIClient { }

@MainActor
public final class WaterTracker: ObservableObject {
    @Published public private(set) var day: WaterDay?
    @Published public private(set) var queue = WaterWriteQueue()
    @Published public private(set) var entries: [WaterEntry] = []
    @Published public private(set) var loading = false
    @Published public private(set) var saving = false
    @Published public private(set) var savingBottle = false
    @Published public private(set) var error: String?
    private let api: any WaterAPIClient
    private let ownerId: UUID
    private let isCurrentOwner: () -> Bool
    private let defaults: UserDefaults
    private let storageKey: String
    private var revision = 0
    private var confirmedDates: [Int: String] = [:]
    private var restored = false

    public init(api: any WaterAPIClient, ownerId: UUID, defaults: UserDefaults = .standard,
                isCurrentOwner: @escaping () -> Bool) {
        self.api = api; self.ownerId = ownerId; self.defaults = defaults
        self.isCurrentOwner = isCurrentOwner
        storageKey = "fittracker.native.water.pending.\(ownerId)"
        do {
            queue = try WaterWriteQueue(restoring: defaults.data(forKey: storageKey))
            restored = true
        } catch { self.error = "Não foi possível ler os registros pendentes. Seus dados foram preservados." }
    }

    public func record(_ amount: Int, at timestamp: Date = Date()) {
        guard restored, isCurrentOwner(), (1...10000).contains(amount) else { return }
        queue.append(WaterPendingEntry(amountMl: amount, occurredAt: timestamp))
        revision += 1; persist()
        Task { await synchronize() }
    }

    public func undoPending(_ key: String) {
        guard restored, isCurrentOwner() else { return }
        queue.undo(key)
        revision += 1; persist()
        Task { await synchronize() }
    }

    public func undoConfirmed(_ entry: WaterEntry) {
        guard restored, isCurrentOwner() else { return }
        queue.removeConfirmed(entry)
        revision += 1; persist()
        Task { await synchronize() }
    }

    public func total(date: String, timezone: String) -> Int { queue.total(entries: entries, date: date, timezone: timezone, confirmedDates: confirmedDates) }
    public func visibleEntries(date: String, timezone: String) -> [WaterEntry] {
        queue.visibleEntries(entries, date: date, timezone: timezone, confirmedDates: confirmedDates).sorted {
            $0.occurredAt == $1.occurredAt ? $0.id > $1.id : $0.occurredAt > $1.occurredAt
        }
    }

    public func refresh() async {
        guard restored, isCurrentOwner() else { return }
        if !queue.writes.isEmpty { await synchronize(); return }
        await load()
    }

    public func synchronize() async {
        guard restored, !saving, isCurrentOwner() else { return }
        saving = true; error = nil
        defer {
            saving = false
            if !queue.writes.isEmpty, error == nil, isCurrentOwner() {
                Task { await synchronize() }
            }
        }
        while let write = queue.writes.first {
            guard isCurrentOwner() else { return }
            queue.markAttempted(write.id); persist()
            do {
                if let receipt = write.receipt {
                    do { _ = try await api.deleteWater(entryId: receipt.id, ownerId: ownerId) }
                    catch APIError.http(let status, _) where status == 404 { }
                    // The request used the original owner's guarded API. Save its receipt
                    // even if the account switched while the network request was in flight.
                    confirmedDates.removeValue(forKey: receipt.id)
                    entries.removeAll { $0.id == receipt.id }
                    queue.confirmRemoval(write.id)
                } else {
                    let result = try await api.addWater(write.entry, ownerId: ownerId)
                    guard let receipt = result.entry else { throw APIError.invalidResponse }
                    confirmedDates[receipt.id] = result.date
                    let needsDelete = queue.acknowledge(write.id, receipt: receipt)
                    if !needsDelete, !entries.contains(where: { $0.id == receipt.id }) { entries.append(receipt) }
                    NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
                }
                revision += 1; persist()
            } catch {
                self.error = "Salvamento pendente. Tente novamente; seus registros e alterações foram preservados."
                return
            }
        }
        // POST replay contains a historical day snapshot; only a fresh GET can
        // reconcile the baseline, after all local intents have been acknowledged.
        await load()
    }

    public func saveBottle(_ capacity: Int) async throws {
        guard isCurrentOwner(), !savingBottle else { return }
        guard (1...10000).contains(capacity) else {
            throw APIError.http(status: 400, message: "Informe a capacidade de 1 a 10.000 ml.")
        }
        savingBottle = true
        defer { savingBottle = false }
        let result = try await api.saveWaterBottle(capacityMl: capacity, ownerId: ownerId)
        guard isCurrentOwner() else { return }
        revision += 1
        day = result // Metadata only: the response cannot replace optimistic entries.
    }

    private func load() async {
        guard isCurrentOwner(), !loading, queue.writes.isEmpty else { return }
        let expectedRevision = revision
        loading = true
        defer {
            loading = false
            if revision != expectedRevision, queue.writes.isEmpty, isCurrentOwner() {
                Task { await refresh() }
            }
        }
        do {
            let result = try await api.getWater(date: nil)
            guard isCurrentOwner(), revision == expectedRevision, queue.writes.isEmpty else { return }
            confirmedDates = Dictionary(uniqueKeysWithValues: result.entries.map { ($0.id, result.date) })
            day = result; entries = result.entries; error = nil
        } catch {
            if isCurrentOwner(), revision == expectedRevision { self.error = "Não foi possível atualizar a água de hoje. Tente novamente." }
        }
    }

    private func persist() {
        if queue.writes.isEmpty { defaults.removeObject(forKey: storageKey) }
        else if let data = try? JSONEncoder().encode(queue) { defaults.set(data, forKey: storageKey) }
    }
}
