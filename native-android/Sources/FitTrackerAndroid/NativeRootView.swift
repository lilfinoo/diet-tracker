import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
import FitTrackerCore

struct NativeRootView: View {
    @Environment(NativeSession.self) var session
    @Environment(\.accessibilityReduceMotion) var reduceMotion
    @State var onboarding = false
    @State var subscription = false
    @Bindable var backgroundPlans = NativePlanBackground.shared
    @State var readyPlan: NativePlanBackground.ReadyPlan?

    var body: some View {
        ZStack {
            Group {
                if let user = session.user {
                    NativeTabs(api: session.api, ownerId: user.id, allowsWorkoutSetup: !onboarding).id(session.user?.id)
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
        .overlay(alignment: .top) {
            if let ready = backgroundPlans.ready, session.user != nil, !onboarding {
                Button {
                    readyPlan = ready
                    backgroundPlans.ready = nil
                } label: {
                    Label("Seu plano está pronto. Toque para revisar.", systemImage: "checkmark.circle.fill")
                        .font(.subheadline.weight(.semibold)).padding(14)
                        .background(Color.fitSurface, in: RoundedRectangle(cornerRadius: 14))
                }.padding(.horizontal, 16)
            }
        }
        .onChange(of: backgroundPlans.opened?.id) { _ in
            let plan = backgroundPlans.opened
            if let plan { readyPlan = plan; backgroundPlans.opened = nil }
        }
        .sheet(item: $readyPlan) { ready in
            NativePlanDetailView(kind: ready.kind, initialPlan: ready.plan, generatedPreview: true)
        }
        .animation(reduceMotion ? nil : .easeOut(duration: 0.4), value: session.restored)
        .onChange(of: session.user?.id) { _ in
            readyPlan = nil
            subscription = false
            if let user = session.user, !user.profileComplete { onboarding = true }
            else { onboarding = false }
        }
        .onChange(of: session.restored) { ready in
            if ready, let user = session.user, !user.profileComplete { onboarding = true }
        }
        .fullScreenCover(isPresented: $onboarding) {
            NativeOnboardingView(onFinished: { onboarding = false }, onPremium: { subscription = true })
                .sheet(isPresented: $subscription) { NavigationStack { NativeSubscriptionView() } }
        }
        .onFitNotification(FitTrackerAPI.sessionExpired) { _ in session.invalidate() }
    }
}

struct NativeTabs: View {
    let allowsWorkoutSetup: Bool
    let ownerId: UUID
    @Environment(NativeSession.self) var session
    @Environment(\.scenePhase) var scenePhase
    @State var diary: NativeDietStore
    @State var tabData: NativeTabDataStore
    @State var selectedTab = 0

    init(api: FitTrackerAPI, ownerId: UUID, allowsWorkoutSetup: Bool) {
        self.ownerId = ownerId
        _diary = State(initialValue: NativeDietStore(ownerId: ownerId))
        self.allowsWorkoutSetup = allowsWorkoutSetup
        _tabData = State(initialValue: NativeTabDataStore(api: api))

    }

    var body: some View {
        TabView(selection: $selectedTab) {
            NativeHomeView(allowsWorkoutSetup: allowsWorkoutSetup, onOpenProgress: { selectedTab = 3 }, onOpenDiet: { selectedTab = 1 })
                .tabItem { Label("Início", systemImage: "house") }.tag(0)
            NativeDietView()
                .tabItem { Label("Dieta", systemImage: "fork.knife") }.tag(1)
            NativeWorkoutView()
                .tabItem { Label("Treino", systemImage: "dumbbell") }.tag(2)
            NativeProgressView()
                .tabItem { Label("Progresso", systemImage: "chart.xyaxis.line") }.tag(3)
            NativeProfileView().tabItem { Label("Perfil", systemImage: "person") }.tag(4)
        }
        .tint(FitTrackerTheme.electricBlue)
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            while !Task.isCancelled, session.user?.id == ownerId {
                await diary.resumePending(api: session.api, isCurrentOwner: { session.user?.id == ownerId })
                do { try await Task.sleep(nanoseconds: 15_000_000_000) } catch { return }
            }
        }
        .environment(diary)
        .environment(tabData)
        .task { await tabData.preload() }
    }
}

@MainActor
@Observable final class NativeTabDataStore {
    var workoutToday: WorkoutToday?
    var workoutLoading = false
    var workoutError: String?
    var progressOverview: ProgressOverview?
    var progressLoading = false
    var progressError: String?
    var progressFetchedAt: Date?

    let api: FitTrackerAPI
    var workoutRequest: Task<WorkoutToday, Error>?
    var progressRequest: Task<ProgressOverview, Error>?
    var workoutRefreshPending = false
    var progressRefreshPending = false

    init(api: FitTrackerAPI) { self.api = api }

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
        workoutLoading = true
        workoutError = nil
        let request = Task { try await api.getWorkoutToday() }
        workoutRequest = request
        do { workoutToday = try await request.value }
        catch { if !isNativeRequestCancellation(error) { workoutError = error.localizedDescription } }
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
            progressFetchedAt = Date()
        } catch { if !isNativeRequestCancellation(error) { progressError = error.localizedDescription } }
        progressRequest = nil
        if progressRefreshPending {
            progressRefreshPending = false
            await loadProgress(force: true)
        } else {
            progressLoading = false
        }
    }
}


func isNativeRequestCancellation(_ error: Error) -> Bool {
    if error is CancellationError { return true }
    return (error as? URLError)?.code == .cancelled
}
