// swift-tools-version: 6.1
// This is a Skip (https://skip.dev) package.
import PackageDescription

let package = Package(
    name: "native-android",
    defaultLocalization: "pt-BR",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "FitTrackerAndroid", type: .dynamic, targets: ["FitTrackerAndroid"]),
    ],
    dependencies: [
        .package(path: "../native-ios"),
        .package(url: "https://github.com/skiptools/skip.git", from: "1.9.16"),
        .package(url: "https://github.com/skiptools/skip-fuse-ui.git", from: "1.0.0"),
        .package(url: "https://github.com/skiptools/skip-ui.git", from: "1.0.0"),
        .package(url: "https://github.com/skiptools/skip-revenue.git", from: "0.3.1"),
        .package(url: "https://github.com/skiptools/skip-keychain.git", from: "0.3.4")
    ],
    targets: [
        .target(name: "FitTrackerAndroid", dependencies: [
            "FitTrackerAuthBridge",
            .product(name: "FitTrackerCore", package: "native-ios"),
            .product(name: "SkipFuseUI", package: "skip-fuse-ui"),
            .product(name: "SkipRevenue", package: "skip-revenue"),
            .product(name: "SkipKeychain", package: "skip-keychain")
        ], resources: [.process("Resources")], plugins: [.plugin(name: "skipstone", package: "skip")]),
        .target(name: "FitTrackerAuthBridge", dependencies: [
            .product(name: "SkipUI", package: "skip-ui"),
            .product(name: "SkipFuseUI", package: "skip-fuse-ui")
        ], plugins: [.plugin(name: "skipstone", package: "skip")]),
    ],
    swiftLanguageModes: [.v5]
)
