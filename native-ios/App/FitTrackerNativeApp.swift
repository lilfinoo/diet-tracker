import SwiftUI
import FitTrackerCore
import UserNotifications
import UIKit

@main
struct FitTrackerNativeApp: App {
    @UIApplicationDelegateAdaptor(NativePushDelegate.self) private var pushDelegate
    @StateObject private var session = NativeSession()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            NativeRootView()
                .environmentObject(session)
                .preferredColorScheme(.dark)
                .tint(.fitBlue)
                .task { await session.restore() }
                .onChange(of: session.user?.id) { owner in
                    NativePlanBackground.shared.resume(owner: owner, api: session.api)
                }
                .onChange(of: scenePhase) { phase in
                    if phase == .active {
                        session.resumeWorkoutSync()
                        NativePlanBackground.shared.resume(owner: session.user?.id, api: session.api)
                    } else { NativePlanBackground.shared.pause() }
                }
        }
    }
}

@MainActor
final class NativeSession: ObservableObject {
    @Published private(set) var user: SessionUser?
    @Published private(set) var profile: ProfileResponse?
    @Published private(set) var freeAccess: FreeAccessStatus?
    let billing = NativeBillingStore()
    @Published private(set) var busy = false
    @Published private(set) var restored = false
    @Published private(set) var error: String?

    let api: FitTrackerAPI

    var hasPremium: Bool { user?.hasPremium(currentUsage: freeAccess) ?? false }

    init() {
        let address = Bundle.main.object(forInfoDictionaryKey: "FitTrackerAPIBaseURL") as? String
        // Build configuration owns the environment; the user never enters a server URL.
        guard let address, let url = URL(string: address), url.scheme == "https" else {
            preconditionFailure("FitTrackerAPIBaseURL must be an HTTPS API root.")
        }
        api = FitTrackerAPI(baseURL: url)
    }

    func restore() async {
        guard !busy else { return }
        busy = true
        error = nil
        defer { busy = false; restored = true }
        user = nil; profile = nil; freeAccess = nil
        do {
            let response = try await api.restoreSession()
            user = response.loggedIn ? response.user : nil
            resumeWorkoutSync()
            profile = nil
            if user != nil { profile = try await api.getProfile() }
        } catch { if !isNativeRequestCancellation(error) { self.error = RequestFailure.message(error, fallback: L("Não conseguimos concluir o acesso agora. Tente novamente em instantes.")) } }
    }

    func invalidate() {
        user = nil; profile = nil; freeAccess = nil
        error = L("Sua sessão terminou. Entre novamente para continuar.")
    }

    func resumeWorkoutSync() {
        guard let ownerId = user?.id else { return }
        WorkoutExecutionSyncCoordinator.shared.resumePending(ownerId: ownerId, api: api,
            stillOwner: { [weak self] in self?.user?.id })
    }

    func refreshProfile() async throws {
        guard let owner = user?.id else { return }
        let result = try await api.getProfile()
        guard user?.id == owner else { throw CancellationError() }
        profile = result
    }

    func refreshFreeAccess() async throws {
        guard let owner = user?.id else { return }
        let result = try await api.freeAccessStatus()
        guard user?.id == owner else { return }
        freeAccess = result
    }

    func acceptSocialSession(_ response: SessionResponse) async throws {
        guard response.loggedIn, let authenticated = response.user else { throw APIError.invalidResponse }
        user = authenticated; profile = nil; freeAccess = nil; error = nil
        resumeWorkoutSync()
        do { try await refreshProfile() }
        catch {
            if user?.id == authenticated.id, !isNativeRequestCancellation(error) {
                self.error = L("Você entrou, mas o perfil ainda não carregou. Tente atualizar novamente.")
            }
        }
    }

    func refreshSubscription() async throws {
        guard let owner = user?.id else { return }
        do {
            let result = try await api.syncNativeSubscription()
            guard user?.id == owner else { return }
            user = result.user
            freeAccess = nil
            try await refreshFreeAccess()
        } catch {
            if user?.id == owner, case APIError.http(let status, _) = error, status == 409 {
                try? await refreshFreeAccess()
            }
            throw error
        }
    }

    func register(_ registration: Registration) async {
        guard !busy else { return }
        busy = true; error = nil
        defer { busy = false }
        do {
            let response = try await api.register(registration)
            user = response.user
            resumeWorkoutSync()
            profile = try await api.getProfile()
        } catch { if !isNativeRequestCancellation(error) { self.error = RequestFailure.message(error, fallback: L("Não conseguimos concluir o acesso agora. Tente novamente em instantes.")) } }
    }

    func login(username: String, password: String) async {
        guard !busy else { return }
        busy = true
        error = nil
        user = nil
        profile = nil; freeAccess = nil
        defer { busy = false }
        do {
            let response = try await api.login(username: username, password: password)
            user = response.user
            resumeWorkoutSync()
            profile = try await api.getProfile()
        } catch {
            guard !isNativeRequestCancellation(error) else { return }
            self.error = RequestFailure.message(error, fallback: L("Não conseguimos concluir o acesso agora. Tente novamente em instantes."))
        }
    }

    func logout() async {
        guard !busy else { return }
        busy = true
        error = nil
        // Hide account data immediately; a network failure must not expose the old account.
        user = nil
        profile = nil; freeAccess = nil
        defer { busy = false }
        do { try await api.logout() }
        catch {
            self.error = L("Você saiu deste iPhone. Não conseguimos confirmar a saída no servidor agora.")
        }
    }
}

extension Color {
    static let fitBackground = Color(red: 7/255, green: 14/255, blue: 25/255)
    static let fitSurface = Color(red: 15/255, green: 26/255, blue: 43/255)
    static let fitBlue = Color(red: 59/255, green: 130/255, blue: 246/255)
}

enum FitTrackerTheme {
    static let electricBlue = Color(red: 0.06, green: 0.58, blue: 1)
    static let cardRadius: CGFloat = 22
    static let pagePadding: CGFloat = 20
    static let pageTitle = Font.largeTitle.bold()
    static let sectionTitle = Font.title2.bold()
    static let cardTitle = Font.title3.bold()
    static let cardBorder = electricBlue.opacity(0.2)
    static let primaryGradient = LinearGradient(colors: [Color(red: 0.12, green: 0.56, blue: 1), Color(red: 0, green: 0.32, blue: 0.95)], startPoint: .top, endPoint: .bottom)
    static let cardGradient = LinearGradient(colors: [Color(red: 0.045, green: 0.09, blue: 0.16), Color(red: 0.025, green: 0.055, blue: 0.1)], startPoint: .topLeading, endPoint: .bottomTrailing)
    static var background: some View {
        Color.fitBackground.overlay(
            RadialGradient(colors: [Color.fitBlue.opacity(0.13), .clear], center: .top, startRadius: 10, endRadius: 450))
    }
}

struct PremiumCardModifier: ViewModifier {
    func body(content: Content) -> some View {
        content.background(FitTrackerTheme.cardGradient, in: RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius))
            .overlay(RoundedRectangle(cornerRadius: FitTrackerTheme.cardRadius).stroke(FitTrackerTheme.cardBorder, lineWidth: 1))
            .shadow(color: Color.fitBlue.opacity(0.06), radius: 12, y: 4)
    }
}

extension View {
    func fitPremiumCard() -> some View { modifier(PremiumCardModifier()) }
    func fitPrimarySurface(compact: Bool = false) -> some View { modifier(FitPrimarySurface(compact: compact)) }
    func fitGlassButton(prominent: Bool = false) -> some View { modifier(FitGlassButton(prominent: prominent)) }
    func fitGlassBar() -> some View { modifier(FitGlassBar()) }
}

private struct FitGlassButton: ViewModifier {
    let prominent: Bool
    @ViewBuilder func body(content: Content) -> some View {
        if #available(iOS 26.0, *) {
            if prominent { content.buttonStyle(.glassProminent) }
            else { content.buttonStyle(.glass) }
        } else {
            if prominent {
                content.buttonStyle(.borderedProminent)
                    .background(.ultraThinMaterial, in: Capsule())
            } else {
                content.buttonStyle(.bordered)
                    .background(.ultraThinMaterial, in: Capsule())
            }
        }
    }
}

private struct FitGlassBar: ViewModifier {
    @ViewBuilder func body(content: Content) -> some View {
        if #available(iOS 26.0, *) {
            content.background { Color.clear.glassEffect(in: .rect(cornerRadius: 20)) }
        } else {
            content.background(.ultraThinMaterial)
        }
    }
}

private struct FitPrimarySurface: ViewModifier {
    var compact = false
    @ViewBuilder func body(content: Content) -> some View {
        let label = content.font(compact ? .subheadline.weight(.semibold) : .headline)
            .foregroundColor(.white).padding(.horizontal, compact ? 14 : 20).padding(.vertical, compact ? 11 : 14)
        if #available(iOS 26.0, *) {
            label.glassEffect(.regular.tint(.fitBlue).interactive(), in: .rect(cornerRadius: compact ? 12 : 22))
        } else {
            label.background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: compact ? 12 : 22))
                .background(Color.fitBlue.opacity(0.55), in: RoundedRectangle(cornerRadius: compact ? 12 : 22))
                .overlay(RoundedRectangle(cornerRadius: compact ? 12 : 22).stroke(Color.white.opacity(0.2), lineWidth: 1))
        }
    }
}

struct FitPrimaryButtonStyle: ButtonStyle {
    var compact = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.fitPrimarySurface(compact: compact)
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.98 : 1)
            .opacity(isEnabled ? 1 : 0.5)
            .animation(reduceMotion ? nil : .easeOut(duration: 0.15), value: configuration.isPressed)
    }
}

@MainActor
final class NativePlanBackground: ObservableObject {
    static let shared = NativePlanBackground()
    @Published var completed: [UUID: NativePlan] = [:]
    @Published var failures: [UUID: String] = [:]
    @Published var ready: ReadyPlan?
    @Published var opened: ReadyPlan?
    struct ReadyPlan: Identifiable { let id: UUID; let kind: NativePlanKind; let plan: NativePlan }
    private var owner: UUID?
    private var api: FitTrackerAPI?
    private var kinds: [UUID: NativePlanKind] = [:]
    private var monitor: Task<Void, Never>?
    private var monitorID: UUID?
    private var deviceToken: String?
    @Published private(set) var notificationsAvailable = false
    private var pushEnabled = false
    private var pendingNotification: UUID?
    private let installationId: UUID = {
        let key = "fitTracker.pushInstallation"
        if let saved = UserDefaults.standard.string(forKey: key), let id = UUID(uuidString: saved) { return id }
        let id = UUID(); UserDefaults.standard.set(id.uuidString, forKey: key); return id
    }()

    func requestKey(owner: UUID, kind: NativePlanKind) -> String? {
        UserDefaults.standard.string(forKey: "fitTracker.planRequest.\(owner.uuidString).\(kind.rawValue)")
    }
    func beginRequest(owner: UUID, kind: NativePlanKind, key: String) {
        UserDefaults.standard.set(key, forKey: "fitTracker.planRequest.\(owner.uuidString).\(kind.rawValue)")
    }
    private func clearRequest(owner: UUID, kind: NativePlanKind) {
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
    private func key(_ owner: UUID, _ kind: NativePlanKind) -> String {
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
            pushEnabled = status.pushEnabled == true
            for job in status.tasks {
                let kind: NativePlanKind = job.operation == "diet_plan" ? .diet : .workout
                if job.status == "queued" || job.status == "running" || (job.requestKey != nil && job.requestKey == requestKey(owner: owner, kind: kind)) {
                    track(id: job.jobId, kind: kind, owner: owner, api: api)
                }
            }
            await registerToken()
            if let id = pendingNotification { pendingNotification = nil; await openNotification(taskId: id) }
        }
    }
    private func startMonitoring() {
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
                            failures[id] = task.error ?? L("Não foi possível concluir este pedido. Você pode tentar novamente.")
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
        guard self.owner == owner || self.owner == nil else { return }
        self.owner = owner; self.api = api; pushEnabled = enabled
        guard enabled, owner != nil else { return }
        let authorized = (try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])) == true
        if authorized {
            UIApplication.shared.registerForRemoteNotifications()
            await registerToken()
        }
    }
    func receivedToken(_ data: Data) {
        deviceToken = data.map { String(format: "%02x", $0) }.joined()
        Task { await registerToken() }
    }
    private func registerToken() async {
        guard pushEnabled, owner != nil, let api, let deviceToken else { return }
        #if DEBUG
        let environment = "sandbox"
        #else
        let environment = "production"
        #endif
        let currentOwner = owner
        do {
            let registered = try await api.registerPushDevice(token: deviceToken, environment: environment, installationId: installationId)
            if owner == currentOwner { notificationsAvailable = registered }
        } catch { notificationsAvailable = false }
    }
    func openNotification(taskId: UUID) async {
        guard owner != nil else { pendingNotification = taskId; return }
        guard let owner, let api,
              let task = try? await api.getPlanGenerationTask(id: taskId), self.owner == owner, let plan = task.plan else { return }
        opened = ReadyPlan(id: taskId, kind: plan.meals != nil ? .diet : .workout, plan: plan)
    }
}

final class NativePushDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }
    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        Task { @MainActor in NativePlanBackground.shared.receivedToken(deviceToken) }
    }
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        if let value = response.notification.request.content.userInfo["task_id"] as? String, let id = UUID(uuidString: value) {
            Task { @MainActor in await NativePlanBackground.shared.openNotification(taskId: id) }
        }
        completionHandler()
    }
}
