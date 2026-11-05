// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "FitTrackerNative",
    platforms: [.iOS(.v15), .macOS(.v12)],
    products: [.library(name: "FitTrackerCore", targets: ["FitTrackerCore"])],
    targets: [
        .target(name: "FitTrackerCore"),
        .testTarget(name: "FitTrackerCoreTests", dependencies: ["FitTrackerCore"])
    ]
)
