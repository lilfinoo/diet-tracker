import Foundation
import SwiftUI

struct FitNotification: @unchecked Sendable { let value: Notification }
final class FitNotificationObserver: @unchecked Sendable {
    let token: NSObjectProtocol
    init(_ token: NSObjectProtocol) { self.token = token }
}

func fitNotifications(named name: Notification.Name) -> AsyncStream<FitNotification> {
    AsyncStream { continuation in
        let observer = FitNotificationObserver(NotificationCenter.default.addObserver(forName: name, object: nil, queue: nil) {
            continuation.yield(FitNotification(value: $0))
        })
        continuation.onTermination = { _ in NotificationCenter.default.removeObserver(observer.token) }
    }
}

extension View {
    func onFitNotification(_ name: Notification.Name, perform: @escaping @MainActor (Notification) -> Void) -> some View {
        task {
            for await event in fitNotifications(named: name) {
                guard !Task.isCancelled else { return }
                perform(event.value)
            }
        }
    }
}
