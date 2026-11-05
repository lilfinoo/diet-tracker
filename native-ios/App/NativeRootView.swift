import SwiftUI
import UIKit
import FitTrackerCore

struct NativeRootView: View {
    @EnvironmentObject private var session: NativeSession
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    @State private var onboarding = false
    @State private var pendingFirstAction: (UUID, NativeFirstIntent)?
    @ObservedObject private var backgroundPlans = NativePlanBackground.shared
    @State private var readyPlan: NativePlanBackground.ReadyPlan?
    @State private var showingOpeningPremium = false
    @State private var openingOfferedTo: UUID?

    var body: some View {
        ZStack {
            Group {
                if let user = session.user {
                    NativeTabs(api: session.api, ownerId: user.id).id(session.user?.id)
                        .environment(\.timeZone, session.profile?.profile?.timezone.flatMap(TimeZone.init(identifier:)) ?? .current)
                } else if session.restored {
                    NativeLoginView()
                } else {
                    Color.fitBackground
                }
            }
            if !session.restored { NativeLaunchView().transition(.opacity) }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.fitBackground.ignoresSafeArea())
        .background(NativeXPWindowProbe())
        .onAppear { NativeXPEffects.shared.api = session.api }
        .overlay(alignment: .top) {
            if let ready = backgroundPlans.ready, session.user != nil, !onboarding {
                Button {
                    readyPlan = ready
                    backgroundPlans.ready = nil
                } label: {
                    Label(L("Seu plano está pronto. Toque para revisar."), systemImage: "checkmark.circle.fill")
                        .font(.subheadline.weight(.semibold)).padding(14)
                        .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
                }.padding(.horizontal, 16)
            }
        }
        .modifier(NativeAchievementPresenter())
        .onReceive(backgroundPlans.$opened) { plan in
            if let plan { readyPlan = plan; backgroundPlans.opened = nil }
        }
        .sheet(item: $readyPlan, onDismiss: offerPremiumOnOpening) { ready in
            NativePlanDetailView(kind: ready.kind, initialPlan: ready.plan, generatedPreview: true)
        }
        .sheet(isPresented: $showingOpeningPremium, onDismiss: openFirstAction) {
            NavigationView { NativeSubscriptionView(surface: "app_open") }.navigationViewStyle(.stack)
        }
        .animation(reduceMotion ? nil : .easeOut(duration: 0.4), value: session.restored)
        .onChange(of: session.user?.id) { _ in
            NativeXPEffects.shared.reset()
            pendingFirstAction = nil
            onboarding = needsOnboarding
            showingOpeningPremium = false
            offerPremiumOnOpening()
        }
        .onChange(of: session.restored) { ready in
            if ready { onboarding = needsOnboarding; offerPremiumOnOpening() }
        }
        .onChange(of: scenePhase) { phase in
            if phase == .background { openingOfferedTo = nil; NativeXPEffects.shared.suspend() }
            if phase == .active {
                NativeXPEffects.shared.resume()
                Task { try? await session.refreshFreeAccess(); offerPremiumOnOpening() }
            }
        }
        .fullScreenCover(isPresented: $onboarding, onDismiss: openFirstAction) {
            NativeOnboardingView { intent in
                if let owner = session.user?.id, let intent { pendingFirstAction = (owner, intent) }
                onboarding = false
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: FitTrackerAPI.sessionExpired).receive(on: DispatchQueue.main)) { _ in session.invalidate() }

    }

    private var needsOnboarding: Bool {
        guard let user = session.user else { return false }
        return !user.profileComplete && !NativeFirstDay.hasFinished(owner: user.id)
    }

    private func openFirstAction() {
        offerPremiumOnOpening()
        guard !showingOpeningPremium, let (owner, intent) = pendingFirstAction else { return }
        pendingFirstAction = nil
        guard session.user?.id == owner else { return }
        NotificationCenter.default.post(name: .nativeFirstAction, object: nil, userInfo: ["intent": intent.rawValue])
    }

    private func offerPremiumOnOpening() {
        guard scenePhase == .active, session.restored, let owner = session.user?.id,
              !session.hasPremium, !onboarding, !needsOnboarding, readyPlan == nil,
              !session.billing.purchasing, openingOfferedTo != owner else { return }
        openingOfferedTo = owner
        showingOpeningPremium = true
    }
}

private struct NativeTabs: View {
    let ownerId: UUID
    @EnvironmentObject private var session: NativeSession
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var diary: NativeDietStore
    @StateObject private var tabData: NativeTabDataStore
    @State private var selectedTab = 0

    init(api: FitTrackerAPI, ownerId: UUID) {
        self.ownerId = ownerId
        _diary = StateObject(wrappedValue: NativeDietStore(ownerId: ownerId))
        _tabData = StateObject(wrappedValue: NativeTabDataStore(api: api))
        if #available(iOS 26.0, *) {
            // Let the system render its native Liquid Glass tab bar.
        } else {
            let appearance = UITabBarAppearance()
            appearance.configureWithDefaultBackground()
            appearance.backgroundEffect = UIBlurEffect(style: .systemThinMaterialDark)
            appearance.backgroundColor = UIColor(red: 0.025, green: 0.055, blue: 0.1, alpha: 0.55)
            appearance.shadowColor = UIColor.systemBlue.withAlphaComponent(0.18)
            for item in [appearance.stackedLayoutAppearance, appearance.inlineLayoutAppearance, appearance.compactInlineLayoutAppearance] {
                item.normal.iconColor = UIColor.white.withAlphaComponent(0.8)
                item.normal.titleTextAttributes = [.foregroundColor: UIColor.white.withAlphaComponent(0.8)]
                item.selected.iconColor = UIColor(red: 0.06, green: 0.58, blue: 1, alpha: 1)
                item.selected.titleTextAttributes = [.foregroundColor: UIColor(red: 0.06, green: 0.58, blue: 1, alpha: 1)]
            }
            UITabBar.appearance().standardAppearance = appearance
            UITabBar.appearance().scrollEdgeAppearance = appearance
        }
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            NativeHomeView(onOpenProgress: { selectedTab = 3 }, onOpenDiet: { selectedTab = 1 })
                .tabItem { Label(L("Início"), systemImage: "house") }.tag(0)
            NativeDietView()
                .tabItem { Label(L("Dieta"), systemImage: "fork.knife") }.tag(1)
            NativeWorkoutView()
                .tabItem { Label(L("Treino"), systemImage: "dumbbell") }.tag(2)
            NativeProgressView()
                .tabItem { Label(L("Progresso"), systemImage: "chart.xyaxis.line") }.tag(3)
            NativeProfileView().tabItem { Label(L("Perfil"), systemImage: "person") }.tag(4)
        }
        .tint(FitTrackerTheme.electricBlue)
        .onReceive(NotificationCenter.default.publisher(for: FitTrackerAPI.xpAwarded).receive(on: DispatchQueue.main)) { notification in
            if let notice = notification.object as? XPAwardNotice { tabData.acceptGamification(notice.summary) }
        }
        .onReceive(NotificationCenter.default.publisher(for: .nativeFirstAction)) { _ in selectedTab = 0 }
        .onReceive(NotificationCenter.default.publisher(for: Notification.Name("fitTrackerNavigate"))) { notification in
            switch notification.userInfo?["tab"] as? String {
            case "diet": selectedTab = 1
            case "workout": selectedTab = 2
            case "progress": selectedTab = 3
            case "profile": selectedTab = 4
            default: selectedTab = 0
            }
        }
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            await tabData.loadProgress(force: tabData.progressOverview != nil)
            await tabData.loadWorkout(force: tabData.workoutToday != nil)
            if tabData.workoutToday?.state == "rest" { try? await session.api.checkInRestDay() }
            while !Task.isCancelled, session.user?.id == ownerId {
                await diary.resumePending(api: session.api, isCurrentOwner: { session.user?.id == ownerId })
                do { try await Task.sleep(nanoseconds: 15_000_000_000) } catch { return }
            }
        }
        .environmentObject(diary)
        .environmentObject(tabData)
        .task {
            await tabData.preload()
            await diary.load(dietDate(Date(), timezone: session.profile?.profile?.timezone), api: session.api)
            await NativeWaterStores.preload(session: session, owner: ownerId)
        }
    }
}

@MainActor
final class NativeTabDataStore: ObservableObject {
    @Published private(set) var workoutToday: WorkoutToday?
    @Published private(set) var workoutLoading = false
    @Published private(set) var workoutError: String?
    @Published private(set) var workoutVersion = 0
    let workoutWeek: WorkoutWeekDataCache
    @Published private(set) var gamification: GamificationSummary?
    @Published private(set) var progressOverview: ProgressOverview?
    @Published private(set) var progressLoading = false
    @Published private(set) var progressError: String?
    @Published private(set) var progressFetchedAt: Date?

    private let api: FitTrackerAPI
    private var workoutRequest: Task<WorkoutToday, Error>?
    private var progressRequest: Task<ProgressOverview, Error>?
    private var workoutRefreshPending = false
    private var progressRefreshPending = false

    init(api: FitTrackerAPI) { self.api = api; workoutWeek = WorkoutWeekDataCache(api: api) }

    func acceptGamification(_ summary: GamificationSummary?) {
        guard let summary else { return }
        gamification = summary
    }

    func preload() async {
        async let workout: Void = loadWorkout()
        async let progress: Void = loadProgress()
        _ = await (workout, progress)
    }

    func loadWorkout(force: Bool = false) async {
        if let workoutRequest {
            if force { workoutRefreshPending = true }
            _ = try? await workoutRequest.value
            return
        }
        guard force || workoutToday == nil else { return }
        if force { workoutWeek.invalidate() }
        workoutLoading = true
        workoutError = nil
        let request = Task { try await api.getWorkoutToday() }
        workoutRequest = request
        do { workoutToday = try await request.value; workoutVersion += 1 }
        catch { if !isNativeRequestCancellation(error) { workoutError = RequestFailure.message(error, fallback: L("Não conseguimos atualizar seu treino agora. Tente novamente em instantes.")) } }
        workoutRequest = nil
        if workoutRefreshPending {
            workoutRefreshPending = false
            await loadWorkout(force: true)
        } else {
            workoutLoading = false
        }
    }

    func loadProgress(force: Bool = false) async {
        if let progressRequest {
            if force { progressRefreshPending = true }
            _ = try? await progressRequest.value
            return
        }
        guard force || progressOverview == nil else { return }
        progressLoading = true
        progressError = nil
        let request = Task { try await api.getProgressOverview() }
        progressRequest = request
        do {
            progressOverview = try await request.value
            acceptGamification(progressOverview?.gamification)
            progressFetchedAt = Date()
        } catch { if !isNativeRequestCancellation(error) { progressError = RequestFailure.message(error, fallback: L("Seu progresso não carregou agora. Tente novamente em instantes.")) } }
        progressRequest = nil
        if progressRefreshPending {
            progressRefreshPending = false
            await loadProgress(force: true)
        } else {
            progressLoading = false
        }
    }
}

struct NativeRecoveryCard: View {
    let title: String
    let message: String
    var systemImage: String = "arrow.clockwise"
    var actionTitle: String? = nil
    var action: (() -> Void)? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: systemImage).font(.system(size: 20, weight: .medium))
                    .foregroundColor(Color(red: 0.59, green: 0.91, blue: 0.83))
                    .frame(width: 40, height: 40)
                    .background(Color.mint.opacity(0.1), in: RoundedRectangle(cornerRadius: 13))
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 6) {
                    Text(title).font(.subheadline.weight(.semibold)).foregroundColor(.primary)
                    Text(NativeLocalization.display(message)).font(.subheadline).foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if let actionTitle, let action {
                Button(action: action) {
                    Text(NativeLocalization.display(actionTitle)).font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity, minHeight: 44)
                }.fitGlassButton().tint(.mint)
            }
        }
        .padding(18).frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(Color.mint.opacity(0.13), lineWidth: 1))
        .accessibilityElement(children: .contain)
    }
}


func isNativeRequestCancellation(_ error: Error) -> Bool {
    if error is CancellationError { return true }
    return (error as? URLError)?.code == .cancelled
}
