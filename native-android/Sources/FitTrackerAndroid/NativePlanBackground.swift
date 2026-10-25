import Foundation
import SwiftUI
import Observation
import FitTrackerCore
#if os(Android)
import SkipFuse
import FitTrackerAuthBridge
#endif

@MainActor
@Observable final class NativePlanBackground {
    static let shared = NativePlanBackground()
    var completed: [UUID: NativePlan] = [:]
    var failures: [UUID: String] = [:]
    var ready: ReadyPlan?
    var opened: ReadyPlan?
    struct ReadyPlan: Identifiable { let id: UUID; let kind: NativePlanKind; let plan: NativePlan }
    var owner: UUID?
    var api: FitTrackerAPI?
    var kinds: [UUID: NativePlanKind] = [:]
    var monitor: Task<Void, Never>?
    var monitorID: UUID?
    var notificationsAvailable = false
    var pendingNotification: UUID?


    func requestKey(owner: UUID, kind: NativePlanKind) -> String? {
        UserDefaults.standard.string(forKey: "fitTracker.planRequest.\(owner.uuidString).\(kind.rawValue)")
    }
    func beginRequest(owner: UUID, kind: NativePlanKind, key: String) {
        UserDefaults.standard.set(key, forKey: "fitTracker.planRequest.\(owner.uuidString).\(kind.rawValue)")
    }
    func clearRequest(owner: UUID, kind: NativePlanKind) {
        UserDefaults.standard.removeObject(forKey: "fitTracker.planRequest.\(owner.uuidString).\(kind.rawValue)")
    }
    func track(id: UUID, kind: NativePlanKind, owner: UUID?, api: FitTrackerAPI) {
        guard let owner else { return }
        if self.owner != owner { pause(); kinds = [:]; completed = [:]; failures = [:]; ready = nil; opened = nil }
        self.owner = owner; self.api = api
        kinds[id] = kind
        UserDefaults.standard.set(id.uuidString, forKey: key(owner, kind))
        startMonitoring()
    }
    func key(_ owner: UUID, _ kind: NativePlanKind) -> String {
        "fitTracker.pendingPlan.\(owner.uuidString).\(kind == .diet ? "diet" : "workout")"
    }
    func pause() { monitor?.cancel(); monitor = nil; monitorID = nil }
    func resume(owner: UUID?, api: FitTrackerAPI) {
        if self.owner != owner { pause(); kinds = [:]; completed = [:]; failures = [:]; ready = nil; opened = nil }
        self.owner = owner; self.api = api
        notificationsAvailable = false
        guard let owner else { return }
        for kind in [NativePlanKind.diet, .workout] {
            if let saved = UserDefaults.standard.string(forKey: key(owner, kind)), let id = UUID(uuidString: saved) { kinds[id] = kind }
        }
        startMonitoring()
        Task {
            guard let status = try? await api.planBackgroundStatus(), self.owner == owner else { return }
            for job in status.tasks {
                let kind: NativePlanKind = job.operation == "diet_plan" ? .diet : .workout
                if job.status == "queued" || job.status == "running" || (job.requestKey != nil && job.requestKey == requestKey(owner: owner, kind: kind)) {
                    track(id: job.jobId, kind: kind, owner: owner, api: api)
                }
            }
            if let id = pendingNotification { pendingNotification = nil; await openNotification(taskId: id) }
        }
    }
    func startMonitoring() {
        guard monitor == nil, !kinds.isEmpty, let owner, let api else { return }
        let generation = UUID(); monitorID = generation
        monitor = Task {
            while !Task.isCancelled, self.owner == owner, !kinds.isEmpty {
                for (id, kind) in kinds {
                    guard !Task.isCancelled, self.owner == owner else { return }
                    if let task = try? await api.getPlanGenerationTask(id: id), !Task.isCancelled, self.owner == owner {
                        if let plan = task.plan {
                            completed[id] = plan
                            ready = ReadyPlan(id: id, kind: kind, plan: plan)
                            kinds[id] = nil
                            UserDefaults.standard.removeObject(forKey: key(owner, kind))
                            clearRequest(owner: owner, kind: kind)
                            NotificationCenter.default.post(name: .nativeWorkoutChanged, object: nil)
                            NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
                        } else if task.status == "failed" || task.status == "cancelled" {
                            failures[id] = task.error ?? "Não foi possível concluir este pedido. Você pode tentar novamente."
                            kinds[id] = nil
                            UserDefaults.standard.removeObject(forKey: key(owner, kind))
                            clearRequest(owner: owner, kind: kind)
                        }
                    }
                }
                do { try await Task.sleep(nanoseconds: 3_000_000_000) } catch { return }
            }
            if monitorID == generation { monitor = nil; monitorID = nil }
        }
    }
    func prepareNotifications(api: FitTrackerAPI, owner: UUID?, enabled: Bool) async {
        // Android has no APNs token. Until FCM is configured, persisted jobs are
        // resumed in-app; never advertise delivery after closing the process.
        guard self.owner == owner || self.owner == nil else { return }
        self.owner = owner; self.api = api
        notificationsAvailable = false
    }
    func openNotification(taskId: UUID) async {
        guard owner != nil else { pendingNotification = taskId; return }
        guard let owner, let api,
              let task = try? await api.getPlanGenerationTask(id: taskId), self.owner == owner, let plan = task.plan else { return }
        opened = ReadyPlan(id: taskId, kind: plan.meals != nil ? .diet : .workout, plan: plan)
    }
}
