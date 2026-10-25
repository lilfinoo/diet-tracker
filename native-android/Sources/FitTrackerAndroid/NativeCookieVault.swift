import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
#if os(Android)
import SkipKeychain
#elseif canImport(Security)
import Security
#endif

/// Persist only this server's cookies. CSRF is always fetched from the server.
enum NativeCookieVault {
    struct StoredCookie: Codable {
        let name: String
        let value: String
        let domain: String
        let path: String
        let expires: Date?
        let secure: Bool
        let httpOnly: Bool
    }
    static let key = "fitTracker.session.\(NativeConfiguration.apiBaseURL.host!)"
    static let signedOutKey = key + ".signedOut"

    static func save() throws {
        let cookies = (HTTPCookieStorage.shared.cookies(for: NativeConfiguration.apiBaseURL) ?? []).map {
            StoredCookie(name: $0.name, value: $0.value, domain: $0.domain, path: $0.path,
                         expires: $0.expiresDate, secure: $0.isSecure, httpOnly: $0.isHTTPOnly)
        }
        guard !cookies.isEmpty else { clear(); return }
        let data = try JSONEncoder().encode(cookies)
        #if os(Android)
        try Keychain.shared.set(data.base64EncodedString(), forKey: key)
        #elseif canImport(Security)
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                   kSecAttrService as String: "ai.fittracker.app.session", kSecAttrAccount as String: key]
        let values: [String: Any] = [kSecValueData as String: data,
                                    kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        var result = SecItemUpdate(query as CFDictionary, values as CFDictionary)
        if result == errSecItemNotFound {
            result = SecItemAdd(query.merging(values) { _, new in new } as CFDictionary, nil)
        }
        guard result == errSecSuccess else { throw VaultError.unavailable }
        #endif
        UserDefaults.standard.set(false, forKey: signedOutKey)
    }

    static func restore() throws {
        if UserDefaults.standard.bool(forKey: signedOutKey) {
            for cookie in HTTPCookieStorage.shared.cookies(for: NativeConfiguration.apiBaseURL) ?? [] {
                HTTPCookieStorage.shared.deleteCookie(cookie)
            }
            return
        }
        let data: Data?
        #if os(Android)
        data = Keychain.shared.string(forKey: key).flatMap { Data(base64Encoded: $0) }
        #elseif canImport(Security)
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "ai.fittracker.app.session", kSecAttrAccount as String: key,
            kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw VaultError.unavailable }
        data = result as? Data
        #else
        data = nil
        #endif
        guard let data else { return }
        let saved = try JSONDecoder().decode([StoredCookie].self, from: data)
        let host = NativeConfiguration.apiBaseURL.host!
        for value in saved {
            guard value.expires.map({ $0 > Date() }) ?? true,
                  value.domain.trimmingCharacters(in: CharacterSet(charactersIn: ".")) == host else { continue }
            var properties: [HTTPCookiePropertyKey: Any] = [.name: value.name, .value: value.value,
                .domain: value.domain, .path: value.path]
            if let expires = value.expires { properties[.expires] = expires }
            if value.secure { properties[.secure] = "TRUE" }
            if value.httpOnly { properties[HTTPCookiePropertyKey("HttpOnly")] = "TRUE" }
            if let cookie = HTTPCookie(properties: properties) { HTTPCookieStorage.shared.setCookie(cookie) }
        }
    }

    static func clear() {
        // A failed secure-store deletion must never undo a local logout.
        UserDefaults.standard.set(true, forKey: signedOutKey)
        #if os(Android)
        try? Keychain.shared.removeValue(forKey: key)
        #elseif canImport(Security)
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "ai.fittracker.app.session", kSecAttrAccount as String: key]
        SecItemDelete(query as CFDictionary)
        #endif
    }
    enum VaultError: Error, LocalizedError {
        case unavailable
        var errorDescription: String? { "Não foi possível acessar o armazenamento seguro da sessão. Tente novamente." }
    }
}
