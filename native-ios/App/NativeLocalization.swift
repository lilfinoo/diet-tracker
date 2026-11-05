import Foundation

/// Uses the iOS app language, with Portuguese as the development-language fallback.
enum NativeLocalization {
    static var locale: Locale {
        Locale(identifier: Bundle.main.preferredLocalizations.first ?? "pt")
    }

    /// Localizes labels supplied by models and view helpers without interpreting user text as a format.
    static func display(_ value: String) -> String {
        let key = value.replacingOccurrences(of: "%", with: "%%")
        let translated = Bundle.main.localizedString(forKey: key, value: value, table: nil)
        return translated.replacingOccurrences(of: "%%", with: "%")
    }
}

/// Keeps interpolated values separate so translated sentences can retain their full context.
struct NativeLocalizedText: ExpressibleByStringLiteral, ExpressibleByStringInterpolation {
    let key: String
    let arguments: [CVarArg]

    init(stringLiteral value: String) {
        key = value.replacingOccurrences(of: "%", with: "%%")
        arguments = []
    }

    init(stringInterpolation: StringInterpolation) {
        key = stringInterpolation.key
        arguments = stringInterpolation.arguments
    }

    struct StringInterpolation: StringInterpolationProtocol {
        var key = ""
        var arguments: [CVarArg] = []

        init(literalCapacity: Int, interpolationCount: Int) {
            key.reserveCapacity(literalCapacity)
            arguments.reserveCapacity(interpolationCount)
        }

        mutating func appendLiteral(_ literal: String) {
            key += literal.replacingOccurrences(of: "%", with: "%%")
        }

        mutating func appendInterpolation<T>(_ value: T) {
            key += "%@"
            arguments.append(String(describing: value))
        }

        mutating func appendInterpolation<T: BinaryFloatingPoint>(_ value: T, specifier: String) {
            appendInterpolation(String(format: specifier, locale: NativeLocalization.locale, Double(value)))
        }
    }
}

func L(_ text: NativeLocalizedText) -> String {
    String(format: Bundle.main.localizedString(forKey: text.key, value: text.key, table: nil),
           locale: NativeLocalization.locale, arguments: text.arguments)
}
