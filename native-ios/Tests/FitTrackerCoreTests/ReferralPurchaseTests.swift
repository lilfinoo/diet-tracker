import XCTest
@testable import FitTrackerCore

final class ReferralPurchaseTests: XCTestCase {
    @MainActor
    func testInvalidCodeNeverStartsPurchase() async {
        var purchases = 0
        do {
            try await ReferralPurchase.run(code: "INVALID", restore: false, isCurrentAccount: { true },
                apply: { _ in throw APIError.http(status: 400, message: "Código inválido") },
                purchase: { purchases += 1 })
            XCTFail("Invalid code must stop checkout")
        } catch { }
        XCTAssertEqual(purchases, 0)
    }

    @MainActor
    func testBlankCodePurchasesWithoutApplying() async throws {
        var purchases = 0
        try await ReferralPurchase.run(code: " \n\t ", restore: false, isCurrentAccount: { true },
            apply: { _ in XCTFail("Blank code must not attribute") }, purchase: { purchases += 1 })
        XCTAssertEqual(purchases, 1)
    }

    @MainActor
    func testPartnerValidationFinishesBeforeStorePurchase() async throws {
        var events: [String] = []
        try await ReferralPurchase.run(code: " aNa fIt ", restore: false, isCurrentAccount: { true },
            apply: { code in
                XCTAssertEqual(code, "ANAFIT")
                events.append("applied")
            }, purchase: { events.append("purchase") })
        XCTAssertEqual(events, ["applied", "purchase"])
    }

    @MainActor
    func testRestoreNeverAppliesTypedCode() async throws {
        var restores = 0
        try await ReferralPurchase.run(code: "ANAFIT", restore: true, isCurrentAccount: { true },
            apply: { _ in XCTFail("Restoring is not a referral action") }, purchase: { restores += 1 })
        XCTAssertEqual(restores, 1)
    }

    @MainActor
    func testAccountSwitchDuringApplicationNeverPurchases() async {
        var currentAccount = true
        var purchases = 0
        do {
            try await ReferralPurchase.run(code: "ANAFIT", restore: false, isCurrentAccount: { currentAccount },
                apply: { _ in currentAccount = false }, purchase: { purchases += 1 })
            XCTFail("Changed account must stop checkout")
        } catch APIError.http(let status, _) { XCTAssertEqual(status, 401) }
        catch { XCTFail("Unexpected error: \(error)") }
        XCTAssertEqual(purchases, 0)
    }

    @MainActor
    func testAlreadyChangedAccountPerformsNeitherOperation() async {
        do {
            try await ReferralPurchase.run(code: "ANAFIT", restore: false, isCurrentAccount: { false },
                apply: { _ in XCTFail("Must not apply for another account") },
                purchase: { XCTFail("Must not buy for another account") })
            XCTFail("Changed account must fail")
        } catch { }
    }
}
