import Foundation
import SwiftUI
import Observation
import FitTrackerCore
#if os(Android)
import SkipFuse
import FitTrackerAuthBridge
#endif

enum NativeConfiguration {
    static let apiBaseURL = URL(string: "https://diet-tracker-6i67.onrender.com/api")!
}

@MainActor
@Observable final class NativeSession {
    var user: SessionUser?
    var profile: ProfileResponse?
    var freeAccess: FreeAccessStatus?
    let billing = NativeBillingStore()
    var busy = false
    var restored = false
    var error: String?

    let api: FitTrackerAPI

    var hasPremium: Bool { user?.isPremium == true || freeAccess?.premium == true }

    init() {
        api = FitTrackerAPI(baseURL: NativeConfiguration.apiBaseURL)
    }

    func restore() async {
        guard !busy else { return }
        busy = true
        error = nil
        defer { busy = false; restored = true }
        user = nil; profile = nil; freeAccess = nil
        do {
            try NativeCookieVault.restore()
            let response = try await api.restoreSession()
            if response.loggedIn { try NativeCookieVault.save() }
            else { NativeCookieVault.clear() }
            user = response.loggedIn ? response.user : nil
            resumeWorkoutSync()
            profile = nil
            if user != nil { profile = try await api.getProfile() }
        } catch { if !isNativeRequestCancellation(error) { self.error = error.localizedDescription } }
    }

    func invalidate() {
        NativeCookieVault.clear()
        user = nil; profile = nil; freeAccess = nil
        error = "Sua sessão terminou. Entre novamente para continuar."
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
        try NativeCookieVault.save()
        user = authenticated; profile = nil; freeAccess = nil; error = nil
        resumeWorkoutSync()
        do { try await refreshProfile() }
        catch {
            if user?.id == authenticated.id, !isNativeRequestCancellation(error) {
                self.error = "Você entrou, mas o perfil ainda não carregou. Tente atualizar novamente."
            }
        }
    }

    func refreshSubscription() async throws {
        guard let owner = user?.id else { return }
        let result = try await api.syncNativeSubscription()
        guard user?.id == owner else { return }
        user = result.user
        try await refreshFreeAccess()
    }

    func register(_ registration: Registration) async {
        guard !busy else { return }
        busy = true; error = nil
        defer { busy = false }
        do {
            let response = try await api.register(registration)
            try NativeCookieVault.save()
            user = response.user
            resumeWorkoutSync()
            profile = try await api.getProfile()
        } catch { if !isNativeRequestCancellation(error) { self.error = error.localizedDescription } }
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
            try NativeCookieVault.save()
            user = response.user
            resumeWorkoutSync()
            profile = try await api.getProfile()
        } catch {
            guard !isNativeRequestCancellation(error) else { return }
            self.error = error.localizedDescription
        }
    }

    func logout() async {
        guard !busy else { return }
        busy = true
        error = nil
        // Hide account data immediately; a network failure must not expose the old account.
        NativeCookieVault.clear()
        user = nil
        profile = nil; freeAccess = nil
        defer { busy = false }
        defer { NativeCookieVault.clear() }
        #if os(Android)
        try? await AndroidAuthBridge.clearCredentialState()
        #endif
        do { try await api.logout() }
        catch {
            self.error = "Não foi possível confirmar a saída no servidor. \(error.localizedDescription)"
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
    static let cardRadius: Double = 22
    static let pagePadding: Double = 20
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
}

struct FitPrimarySurface: ViewModifier {
    var compact = false
    func body(content: Content) -> some View {
        content.font(compact ? .subheadline.weight(.semibold) : .headline)
            .foregroundColor(.white).padding(.horizontal, compact ? 14 : 20).padding(.vertical, compact ? 11 : 14)
            .background(FitTrackerTheme.primaryGradient, in: RoundedRectangle(cornerRadius: compact ? 12 : 22))
            .overlay(RoundedRectangle(cornerRadius: compact ? 12 : 22).stroke(Color.cyan.opacity(0.5), lineWidth: 1))
            .shadow(color: Color.fitBlue.opacity(compact ? 0.15 : 0.3), radius: compact ? 6 : 13, y: 3)
    }
}

