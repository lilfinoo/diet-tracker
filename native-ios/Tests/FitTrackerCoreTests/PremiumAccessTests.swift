import XCTest
@testable import FitTrackerCore

final class PremiumAccessTests: XCTestCase {
    func testCurrentFreeUsageOverridesPremiumCachedAtSignIn() throws {
        XCTAssertFalse(try user(premium: true).hasPremium(currentUsage: usage(premium: false)))
    }

    func testCurrentPaidUsageOverridesFreeSession() throws {
        XCTAssertTrue(try user(premium: false).hasPremium(currentUsage: usage(premium: true)))
    }

    func testSessionRemainsFallbackUntilUsageLoads() throws {
        XCTAssertTrue(try user(premium: true).hasPremium(currentUsage: nil))
        XCTAssertFalse(try user(premium: false).hasPremium(currentUsage: nil))
    }

    private func user(premium: Bool) throws -> SessionUser {
        let json = """
        {"id":"00000000-0000-0000-0000-000000000001","username":"ana","name":"Ana",
        "is_banned":false,"is_admin":false,"is_premium":\(premium),"plan_code":"free",
        "ai_trial_uses":0,"has_password":true,"is_public":false,"onboarding_status":"complete",
        "profile_missing_fields":[],"profile_complete":true}
        """
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(SessionUser.self, from: Data(json.utf8))
    }

    private func usage(premium: Bool) throws -> FreeAccessStatus {
        let json = """
        {"premium":\(premium),"policy":"lifetime","plans":{"limit":2,"used":0,"remaining":2},
        "photos":{"limit":3,"used":2,"remaining":1},"manual_logging":true}
        """
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FreeAccessStatus.self, from: Data(json.utf8))
    }
}
