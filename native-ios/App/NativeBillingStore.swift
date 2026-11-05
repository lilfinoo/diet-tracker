import Foundation
import RevenueCat
import FitTrackerCore

@MainActor
final class NativeBillingStore: ObservableObject {
    @Published private(set) var packages: [RevenueCat.Package] = []
    @Published private(set) var sevenDayTrial = false
    @Published private(set) var loading = false
    @Published private(set) var purchasing = false
    @Published private(set) var feedback: BillingRecovery?
    private var owner: UUID?
    private var fetchedAt: Date?
    private var entitlementID: String?
    var canPurchase: Bool { feedback?.blocksNewPurchase != true }

    func load(session: NativeSession, force: Bool = false) async {
        guard !loading, !purchasing, let id = session.user?.id else { return }
        if owner == id, !force, let fetchedAt, Date().timeIntervalSince(fetchedAt) < 300 { return }
        loading = true
        if canPurchase { feedback = nil }
        if owner != id {
            packages = []; sevenDayTrial = false; fetchedAt = nil; entitlementID = nil
            feedback = UserDefaults.standard.string(forKey: recoveryKey(id)).flatMap(BillingRecovery.init(rawValue:))
            if feedback?.blocksNewPurchase != true { feedback = nil }
        }
        if session.hasPremium { feedback = nil; UserDefaults.standard.removeObject(forKey: recoveryKey(id)) }
        defer { loading = false }
        do {
            let configuration = try await session.api.nativeBillingConfiguration()
            try assertOwner(id, session)
            guard configuration.configured, let key = configuration.publicApiKey, key.hasPrefix("appl_") else {
                throw APIError.http(status: 503, message: L("As compras da Apple ainda não estão configuradas."))
            }
            if !Purchases.isConfigured { Purchases.configure(withAPIKey: key, appUserID: id.uuidString.lowercased()) }
            else if Purchases.shared.appUserID != id.uuidString.lowercased() { _ = try await Purchases.shared.logIn(id.uuidString.lowercased()) }
            try assertOwner(id, session)
            owner = id; entitlementID = configuration.entitlementId
            let offerings = try await Purchases.shared.offerings()
            try assertOwner(id, session)
            let allowed = ["ai.fittracker.premium.monthly", "ai.fittracker.premium.annual"]
            let available = offerings.current?.availablePackages.filter { allowed.contains($0.storeProduct.productIdentifier) } ?? []
            guard !available.isEmpty else { throw APIError.http(status: 503, message: L("Os planos ainda não estão disponíveis na App Store. Tente novamente mais tarde.")) }
            let eligibility = await Purchases.shared.checkTrialOrIntroDiscountEligibility(productIdentifiers: available.map { $0.storeProduct.productIdentifier })
            try assertOwner(id, session)
            let monthly = available.first { $0.storeProduct.productIdentifier == allowed[0] }?.storeProduct
            let intro = monthly?.introductoryDiscount
            sevenDayTrial = monthly.map { eligibility[$0.productIdentifier]?.status == .eligible } == true &&
                intro?.paymentMode == .freeTrial && intro?.numberOfPeriods == 1 &&
                ((intro?.subscriptionPeriod.unit == .week && intro?.subscriptionPeriod.value == 1) ||
                 (intro?.subscriptionPeriod.unit == .day && intro?.subscriptionPeriod.value == 7))
            packages = available; owner = id; fetchedAt = Date()
        } catch {
            guard session.user?.id == id, !isNativeRequestCancellation(error) else { return }
            if canPurchase { feedback = .plansUnavailable }
        }
    }

    func transact(package: RevenueCat.Package?, restore: Bool, session: NativeSession) async {
        guard !purchasing, !loading, let id = session.user?.id, owner == id, restore || canPurchase else { return }
        let previous = feedback
        purchasing = true; feedback = nil
        var purchaseReceived = false
        if !restore { UserDefaults.standard.set(BillingRecovery.purchaseUnverified.rawValue, forKey: recoveryKey(id)) }
        defer { purchasing = false; if session.user?.id == id { persistRecovery(for: id) } }
        do {
            try assertOwner(id, session)
            guard Purchases.shared.appUserID == id.uuidString.lowercased() else { throw CancellationError() }
            if restore {
                let info = try await Purchases.shared.restorePurchases()
                purchaseReceived = hasActivePurchase(info)
            } else if let package {
                let result = try await Purchases.shared.purchase(package: package)
                try assertOwner(id, session)
                if result.userCancelled { feedback = .cancelled; return }
                purchaseReceived = true
            } else { return }
            try assertOwner(id, session)
            try await session.refreshSubscription()
            try assertOwner(id, session)
            feedback = BillingRecovery.afterVerification(premiumActive: session.hasPremium, storePurchaseActive: purchaseReceived, previous: previous)
            if session.hasPremium { fetchedAt = nil }
        } catch {
            guard session.user?.id == id else { return }
            if session.hasPremium { feedback = nil; fetchedAt = nil; return }
            if purchaseReceived { feedback = .activationPending; return }
            if isNativeRequestCancellation(error) { feedback = previous; return }
            if let code = error as? RevenueCat.ErrorCode {
                switch code {
                case .purchaseCancelledError: feedback = .cancelled
                case .paymentPendingError: feedback = .paymentPending
                case .productAlreadyPurchasedError, .operationAlreadyInProgressForProductError: feedback = .purchaseUnverified
                case .networkError, .offlineConnectionError: feedback = restore ? (previous?.blocksNewPurchase == true ? previous : .restoreFailed) : .purchaseUnverified
                case .purchaseNotAllowedError, .insufficientPermissionsError: feedback = .purchaseNotAllowed
                case .purchaseInvalidError, .testStoreSimulatedPurchaseError: feedback = restore ? .restoreFailed : .purchaseFailed
                case .productNotAvailableForPurchaseError, .configurationError: feedback = restore ? .restoreFailed : .plansUnavailable
                case .receiptAlreadyInUseError, .receiptInUseByOtherSubscriberError, .purchaseBelongsToOtherUser: feedback = .accountConflict
                default: feedback = restore ? .restoreFailed : .purchaseUnverified
                }
            } else if restore { feedback = previous?.blocksNewPurchase == true ? previous : .restoreFailed }
            else { feedback = .purchaseUnverified }
        }
    }

    func verifyPurchase(session: NativeSession) async {
        guard !purchasing, !loading, let id = session.user?.id else { return }
        if owner != id || !Purchases.isConfigured || Purchases.shared.appUserID != id.uuidString.lowercased() {
            await load(session: session, force: true)
        }
        guard owner == id, Purchases.isConfigured, session.user?.id == id else { return }
        let previous = feedback
        purchasing = true
        defer { purchasing = false; if session.user?.id == id { persistRecovery(for: id) } }
        do {
            try assertOwner(id, session)
            guard Purchases.shared.appUserID == id.uuidString.lowercased() else { throw CancellationError() }
            let info = try await Purchases.shared.customerInfo(fetchPolicy: .fetchCurrent)
            try assertOwner(id, session)
            try await session.refreshSubscription()
            try assertOwner(id, session)
            feedback = BillingRecovery.afterVerification(premiumActive: session.hasPremium, storePurchaseActive: hasActivePurchase(info), previous: previous)
            if session.hasPremium { fetchedAt = nil }
        } catch {
            guard session.user?.id == id, !isNativeRequestCancellation(error) else { return }
            if session.hasPremium { feedback = nil; fetchedAt = nil }
            else { feedback = previous?.blocksNewPurchase == true ? previous : .purchaseUnverified }
        }
    }

    private func hasActivePurchase(_ info: CustomerInfo) -> Bool {
        guard let entitlementID else { return false }
        return info.entitlements.active[entitlementID] != nil
    }

    private func recoveryKey(_ id: UUID) -> String { "fittracker.billing.recovery.\(id.uuidString)" }

    private func persistRecovery(for id: UUID) {
        guard owner == id else { return }
        if let feedback, feedback.blocksNewPurchase { UserDefaults.standard.set(feedback.rawValue, forKey: recoveryKey(id)) }
        else { UserDefaults.standard.removeObject(forKey: recoveryKey(id)) }
    }

    func canRestore(session: NativeSession) -> Bool {
        guard let id = session.user?.id, owner == id, Purchases.isConfigured else { return false }
        return Purchases.shared.appUserID == id.uuidString.lowercased()
    }

    private func assertOwner(_ id: UUID, _ session: NativeSession) throws {
        guard session.user?.id == id else { throw CancellationError() }
    }
}
