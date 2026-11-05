import Foundation

/// Validate an optional partner code before handing control to the existing store.
@MainActor
public enum ReferralPurchase {
    public static func run(
        code: String, restore: Bool, isCurrentAccount: () -> Bool,
        apply: (String) async throws -> Void, purchase: () async throws -> Void
    ) async throws {
        func verifyAccount() throws {
            guard isCurrentAccount() else {
                throw APIError.http(status: 401, message: "Entre novamente na mesma conta para continuar.")
            }
        }
        try verifyAccount()
        let normalized = code.components(separatedBy: .whitespacesAndNewlines).joined().uppercased()
        if !restore && !normalized.isEmpty {
            try await apply(normalized)
            try verifyAccount()
        }
        try await purchase()
    }
}
