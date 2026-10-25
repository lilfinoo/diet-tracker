import XCTest
@testable import FitTrackerCore

final class BillingRecoveryTests: XCTestCase {
    func testUncertainPurchaseOnlyOffersVerificationAndBlocksAnotherPayment() {
        for state in [BillingRecovery.purchaseUnverified, .activationPending, .paymentPending] {
            XCTAssertTrue(state.blocksNewPurchase)
            XCTAssertEqual(state.action, .verifyPurchase)
        }
    }

    func testAcceptedPurchaseNeverBecomesAnotherBuyWhenServerHasNotActivatedIt() {
        XCTAssertEqual(BillingRecovery.afterVerification(premiumActive: false, storePurchaseActive: true, previous: nil), .activationPending)
        XCTAssertEqual(BillingRecovery.afterVerification(premiumActive: false, storePurchaseActive: false, previous: .activationPending), .activationPending)
    }

    func testPendingApprovalRemainsPendingWhenNoActiveSubscriptionAppearsYet() {
        XCTAssertEqual(BillingRecovery.afterVerification(premiumActive: false, storePurchaseActive: false, previous: .paymentPending), .paymentPending)
        XCTAssertEqual(BillingRecovery.afterVerification(premiumActive: true, storePurchaseActive: false, previous: .paymentPending), nil)
    }

    func testNoPurchasesDuringRestoreIsAnEmptyStateNotAClaimThatAppleConfirmedAPurchase() {
        let result = BillingRecovery.afterVerification(premiumActive: false, storePurchaseActive: false, previous: nil)
        XCTAssertEqual(result, .noActivePurchase)
        XCTAssertFalse(result!.blocksNewPurchase)
        XCTAssertNil(result!.action)
    }

    func testFreshVerificationCanResolveUncertainNetworkOutcomeWithoutStartingAPayment() {
        XCTAssertEqual(BillingRecovery.afterVerification(premiumActive: false, storePurchaseActive: false, previous: .purchaseUnverified), .noActivePurchase)
        XCTAssertEqual(BillingRecovery.afterVerification(premiumActive: true, storePurchaseActive: true, previous: .purchaseUnverified), nil)
    }

    func testRecoveryActionMatchesFailedOperation() {
        XCTAssertEqual(BillingRecovery.plansUnavailable.action, .reloadPlans)
        XCTAssertEqual(BillingRecovery.purchaseFailed.action, .retryPurchase)
        XCTAssertEqual(BillingRecovery.restoreFailed.action, .restorePurchases)
        XCTAssertNil(BillingRecovery.cancelled.action)
        XCTAssertFalse(BillingRecovery.cancelled.blocksNewPurchase)
        XCTAssertTrue(BillingRecovery.accountConflict.blocksNewPurchase)
    }
}
