import Foundation
import FitTrackerCore
import Observation
#if os(Android)
import SkipFuse
#else
import OSLog
#endif
import SwiftUI

/// A logger for the FitTrackerAndroid module.
let logger: Logger = Logger(subsystem: "ai.fittracker.app", category: "FitTrackerAndroid")

/// The shared top-level view for the app, loaded from the platform-specific App delegates below.
///
/* SKIP @bridge */public struct FitTrackerAndroidRootView : View {
    @State var session = NativeSession()
    @Environment(\.scenePhase) var scenePhase
    /* SKIP @bridge */public init() {
    }

    public var body: some View {
        NativeRootView()
            .environment(session)
            .preferredColorScheme(.dark)
            .tint(.fitBlue)
            .task { await session.restore() }
            .onChange(of: session.user?.id) { owner in
                NativePlanBackground.shared.resume(owner: owner, api: session.api)
            }
            .onChange(of: scenePhase) { phase in
                if phase == .active {
                    session.resumeWorkoutSync()
                    NativePlanBackground.shared.resume(owner: session.user?.id, api: session.api)
                } else { NativePlanBackground.shared.pause() }
            }
    }
}

/// Global application delegate functions.
///
/// These functions can update a shared observable object to communicate app state changes to interested views.
/* SKIP @bridge */public final class FitTrackerAndroidAppDelegate : Sendable {
    /* SKIP @bridge */public static let shared = FitTrackerAndroidAppDelegate()

    private init() {
    }

    /* SKIP @bridge */public func onInit() {
        logger.debug("onInit")
    }

    /* SKIP @bridge */public func onLaunch() {
        logger.debug("onLaunch")
    }

    /* SKIP @bridge */public func onResume() {
        logger.debug("onResume")
    }

    /* SKIP @bridge */public func onPause() {
        logger.debug("onPause")
    }

    /* SKIP @bridge */public func onStop() {
        logger.debug("onStop")
    }

    /* SKIP @bridge */public func onDestroy() {
        logger.debug("onDestroy")
    }

    /* SKIP @bridge */public func onLowMemory() {
        logger.debug("onLowMemory")
    }
}
