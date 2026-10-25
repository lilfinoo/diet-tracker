import Foundation
import Observation
#if os(Android)
import SkipFuse
#endif
import SkipRevenue
import FitTrackerAuthBridge
import FitTrackerCore

@MainActor
@Observable final class NativeBillingStore {
    var packages: [RCFusePackage] = []
    var loading = false
    var purchasing = false
    var error: String?
    var owner: UUID?
    var fetchedAt: Date?

    func load(session: NativeSession, force: Bool = false) async {
        guard !loading, !purchasing, let id = session.user?.id else { return }
        if owner == id, !force, let fetchedAt, Date().timeIntervalSince(fetchedAt) < 300 { return }
        loading = true; error = nil
        if owner != id { packages = []; fetchedAt = nil; owner = nil }
        defer { loading = false }
        do {
            let configuration = try await session.api.nativeBillingConfiguration(platform: "android")
            try assertOwner(id, session)
            guard configuration.configured, let key = configuration.publicApiKey, key.hasPrefix("goog_") else {
                throw APIError.http(status: 503, message: "As compras da Google Play ainda não estão configuradas.")
            }
            let purchases = RevenueCatFuse.shared
            let userID = id.uuidString.lowercased()
            if !purchases.isConfigured { purchases.configure(apiKey: key, appUserID: userID) }
            else if purchases.appUserID != userID { try await purchases.loginUser(userId: userID) }
            try assertOwner(id, session)
            guard purchases.appUserID == userID else { throw CancellationError() }
            owner = id
            let offerings = try await purchases.loadOfferings()
            try assertOwner(id, session)
            let available = offerings.current?.availablePackages.filter {
                ($0.packageType == .monthly || $0.packageType == .annual) &&
                    (configuration.productIdentifiers?.contains($0.storeProduct.productIdentifier) ?? true)
            } ?? []
            guard !available.isEmpty else {
                throw APIError.http(status: 503, message: "Os planos ainda não estão disponíveis na Google Play. Tente novamente mais tarde.")
            }
            packages = available; fetchedAt = Date()
        } catch { if !isNativeRequestCancellation(error) { self.error = error.localizedDescription } }
    }

    func transact(package: RCFusePackage?, restore: Bool, session: NativeSession) async {
        guard !purchasing, !loading, let id = session.user?.id, owner == id else { return }
        purchasing = true; error = nil
        defer { purchasing = false }
        do {
            try assertOwner(id, session)
            let purchases = RevenueCatFuse.shared
            guard purchases.isConfigured, purchases.appUserID == id.uuidString.lowercased() else { throw CancellationError() }
            if restore { _ = try await purchases.restorePurchases() }
            else if let package, packages.contains(where: { $0.identifier == package.identifier }) {
                #if os(Android)
                _ = try await purchases.purchase(package: package, activity: RCFuseAndroidActivity(AndroidAuthBridge.currentActivity()))
                #else
                throw APIError.http(status: 503, message: "Abra o aplicativo Android para concluir a compra pela Google Play.")
                #endif
            } else { return }
            try assertOwner(id, session)
            // Only the API's verified RevenueCat state can grant access to this account.
            try await session.refreshSubscription()
            try assertOwner(id, session)
            guard session.user?.isPremium == true else {
                throw APIError.http(status: 409, message: "Nenhuma assinatura Premium foi confirmada pelo servidor para esta conta. Se a Google Play confirmou sua compra, toque em Restaurar compras ou fale com o suporte.")
            }
            fetchedAt = nil
        } catch StoreError.userCancelled { return }
        catch {
            guard !isNativeRequestCancellation(error) else { return }
            if RCFuseErrorCode(error: error) == .purchaseCancelledError { return }
            self.error = error.localizedDescription
        }
    }

    func canRestore(session: NativeSession) -> Bool {
        owner == session.user?.id && RevenueCatFuse.shared.isConfigured &&
            RevenueCatFuse.shared.appUserID == session.user?.id.uuidString.lowercased()
    }

    func assertOwner(_ id: UUID, _ session: NativeSession) throws {
        guard session.user?.id == id else { throw CancellationError() }
    }
}
