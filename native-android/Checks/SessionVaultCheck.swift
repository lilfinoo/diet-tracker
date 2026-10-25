import Foundation

// Standalone check: never use a real API host, account or credential.
enum NativeConfiguration {
    static let apiBaseURL = URL(string: "https://vault-test.invalid/api")!
}

@main enum SessionVaultCheck {
    static func main() throws {
        let storage = HTTPCookieStorage.shared
        let own = HTTPCookie(properties: [.name: "session", .value: "test-only", .domain: "vault-test.invalid", .path: "/"])!
        let other = HTTPCookie(properties: [.name: "session", .value: "other-test", .domain: "unrelated-test.invalid", .path: "/"])!
        defer {
            storage.deleteCookie(own)
            storage.deleteCookie(other)
            UserDefaults.standard.removeObject(forKey: NativeCookieVault.signedOutKey)
        }
        storage.setCookie(own)
        storage.setCookie(other)
        NativeCookieVault.clear()
        precondition(UserDefaults.standard.bool(forKey: NativeCookieVault.signedOutKey))
        try NativeCookieVault.restore()
        precondition((storage.cookies(for: NativeConfiguration.apiBaseURL) ?? []).isEmpty,
                     "A local logout must prevent automatic session restoration.")
        precondition(storage.cookies(for: URL(string: "https://unrelated-test.invalid")!)?.contains(where: { $0.value == "other-test" }) == true,
                     "Unrelated server cookies must remain untouched.")
        print("Session vault: local logout and server isolation passed.")
    }
}
