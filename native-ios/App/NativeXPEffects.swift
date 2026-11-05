import SwiftUI
import UIKit
import FitTrackerCore

private struct NativeXPValues {
    let level: Int
    let xp: Int
    let required: Int
    var fraction: CGFloat { CGFloat(xp) / CGFloat(required) }
    var rank: String { level >= 50 ? "Mestre" : level >= 30 ? "Diamante" : level >= 20 ? "Platina" : level >= 10 ? "Ouro" : level >= 5 ? "Prata" : "Bronze" }

    init(total: Int) {
        var level = 1, remaining = max(0, total)
        while remaining >= 100 + 25 * (level - 1) {
            remaining -= 100 + 25 * (level - 1)
            level += 1
        }
        self.level = level; xp = remaining; required = 100 + 25 * (level - 1)
    }
}

private struct NativeXPFlight {
    let id = UUID()
    let started = Date()
    let origin: CGPoint
    let bar: CGRect
    let nutritionTargets: [CGRect]
    let xp: Int
    let total: Int
    let floating: Bool
    let automatic: Bool
    let reduced: Bool
    let safeTop: CGFloat
    static let count = 76

    func elapsed(_ date: Date) -> Double { max(0, date.timeIntervalSince(started)) }
    func delay(_ i: Int) -> Double { Double(i) * 0.005 + seed(i, 3) * 0.09 }
    func duration(_ i: Int) -> Double { 1.18 + seed(i, 7) * 0.28 }
    func seed(_ i: Int, _ salt: Int) -> Double { Double((i * 7919 + salt * 104729) % 65521) / 65521 }
    func progress(_ date: Date) -> Double {
        let time = elapsed(date)
        if reduced { return min(1, max(0, (time - 0.12) / 0.18)) }
        let xpParticles = (0..<Self.count).filter { nutritionTargets.isEmpty || $0 % 5 != 0 }
        return Double(xpParticles.filter { time >= delay($0) + 0.26 + duration($0) }.count) / Double(xpParticles.count)
    }
    func values(_ date: Date) -> NativeXPValues { NativeXPValues(total: max(0, total - xp) + Int((Double(xp) * progress(date)).rounded())) }
    func point(_ i: Int, _ time: Double, destination: CGPoint) -> CGPoint? {
        let age = time - delay(i)
        guard age >= 0, age <= 0.26 + duration(i) else { return nil }
        let angle = seed(i, 11) * .pi * 2
        let radius = (automatic ? 42.0 : 24.0) + seed(i, 17) * (automatic ? 65 : 35)
        let burst = CGPoint(x: origin.x + cos(angle) * radius, y: origin.y + sin(angle) * radius)
        if age < 0.26 {
            let t = 1 - pow(1 - age / 0.26, 3)
            return CGPoint(x: origin.x + (burst.x - origin.x) * t, y: origin.y + (burst.y - origin.y) * t)
        }
        let target = !nutritionTargets.isEmpty && i % 5 == 0
            ? CGPoint(x: nutritionTargets[(i / 5) % nutritionTargets.count].midX, y: nutritionTargets[(i / 5) % nutritionTargets.count].midY)
            : destination
        let t = min(1, (age - 0.26) / duration(i)), u = t * t * (3 - 2 * t), q = 1 - u
        let bias = (seed(i, 23) - 0.5) * 100
        return CGPoint(x: q*q*q*burst.x + 3*q*q*u*(burst.x+bias) + 3*q*u*u*(target.x+bias*0.35) + u*u*u*target.x,
                       y: q*q*q*burst.y + 3*q*q*u*(burst.y-90) + 3*q*u*u*(target.y+80) + u*u*u*target.y)
    }
}

@MainActor
final class NativeXPEffects: NSObject, ObservableObject {
    static let shared = NativeXPEffects()
    @Published fileprivate var flight: NativeXPFlight?
    fileprivate var activeBars: Set<UUID> = []
    fileprivate var bars: [UUID: WeakXPView] = [:]
    fileprivate var nutritionProbes: [UUID: (Int, WeakXPView)] = [:]
    private weak var appWindow: UIWindow?
    private var overlayWindow: NativeXPWindow?
    private var touchObserver: NativeXPTouchObserver?
    private var observers: [NSObjectProtocol] = []
    private var lastTouch: (point: CGPoint, time: TimeInterval)?
    private var requestOrigins: [UUID: CGPoint] = [:]
    private var actionOrigins: [String: CGPoint] = [:]
    private var fetchingSummary = false
    private var pending: [(XPAwardNotice, CGPoint?)] = []
    private var generation = UUID()
    var api: FitTrackerAPI?

    private override init() {
        super.init()
        observers.append(NotificationCenter.default.addObserver(forName: FitTrackerAPI.xpRequestStarted, object: nil, queue: .main) { [weak self] notification in
            guard let id = notification.object as? UUID else { return }
            let key = notification.userInfo?["idempotencyKey"] as? String
            Task { @MainActor in self?.captureRequest(id, key: key) }
        })
        observers.append(NotificationCenter.default.addObserver(forName: FitTrackerAPI.xpAwarded, object: nil, queue: .main) { [weak self] notification in
            guard let notice = notification.object as? XPAwardNotice else { return }
            Task { @MainActor in self?.receive(notice) }
        })
    }

    func reset() {
        generation = UUID(); pending.removeAll(); requestOrigins.removeAll(); actionOrigins.removeAll(); lastTouch = nil; fetchingSummary = false
        flight = nil; overlayWindow?.isHidden = true
    }
    func suspend() {
        generation = UUID(); fetchingSummary = false; flight = nil; overlayWindow?.isHidden = true
        requestOrigins.removeAll(); actionOrigins.removeAll(); lastTouch = nil
        pending = pending.map { ($0.0, nil) }
    }
    func resume() { DispatchQueue.main.async { self.playNext() } }
    fileprivate func install(_ window: UIWindow) {
        guard appWindow !== window else { return }
        if let touchObserver { appWindow?.removeGestureRecognizer(touchObserver) }
        appWindow = window
        let observer = NativeXPTouchObserver { [weak self] point in
            self?.lastTouch = (point, ProcessInfo.processInfo.systemUptime)
        }
        window.addGestureRecognizer(observer); touchObserver = observer
        overlayWindow?.isHidden = true; overlayWindow = nil
    }
    func captureAction(key: String, point: CGPoint? = nil) {
        let origin = point ?? lastTouch.flatMap { ProcessInfo.processInfo.systemUptime - $0.time < 1.5 ? $0.point : nil }
        guard let origin else { return }
        if actionOrigins.count > 100 { actionOrigins.removeAll() }
        actionOrigins[key] = origin
    }
    func copyActionOrigin(from: String, to: String) { actionOrigins[to] = actionOrigins[from] }
    private func captureRequest(_ id: UUID, key: String?) {
        if let key, let point = actionOrigins[key] { requestOrigins[id] = point; return }
        guard let lastTouch, ProcessInfo.processInfo.systemUptime - lastTouch.time < 1.5 else { return }
        if requestOrigins.count > 100 { requestOrigins.removeAll() }
        requestOrigins[id] = lastTouch.point
    }
    fileprivate func registerNutritionProbe(_ view: UIView, id: UUID, index: Int) {
        nutritionProbes[id] = (index, WeakXPView(view))
    }
    fileprivate func removeNutritionProbe(_ id: UUID) { nutritionProbes[id] = nil }
    private func visibleNutritionTargets(from origin: CGPoint, in window: UIWindow) -> [CGRect] {
        let visible = nutritionProbes.values.compactMap { probe -> (Int, CGRect)? in
            guard let frame = probe.1.view?.xpVisibleFrame(in: window) else { return nil }
            return (probe.0, frame)
        }
        let grouped = Dictionary(grouping: visible, by: \.0)
        return (0..<4).compactMap { index in
            grouped[index]?.min { lhs, rhs in
                hypot(lhs.1.midX - origin.x, lhs.1.midY - origin.y) < hypot(rhs.1.midX - origin.x, rhs.1.midY - origin.y)
            }?.1
        }
    }
    private func receive(_ notice: XPAwardNotice) {
        let capturedOrigin = requestOrigins.removeValue(forKey: notice.requestID)
        let origin = appWindow?.windowScene?.activationState == .foregroundActive ? capturedOrigin : nil
        pending.append((notice, origin)); playNext()
    }
    private func playNext() {
        guard flight == nil, !fetchingSummary, !pending.isEmpty, let appWindow, let scene = appWindow.windowScene, scene.activationState == .foregroundActive else { return }
        let (notice, origin) = pending.removeFirst()
        guard let summary = notice.summary else {
            let token = generation
            fetchingSummary = true
            Task {
                let summary = try? await api?.getProgressOverview().gamification
                guard generation == token else { return }
                fetchingSummary = false
                if let summary {
                    pending.insert((XPAwardNotice(xp: notice.xp, requestID: notice.requestID, summary: summary), origin), at: 0)
                }
                playNext()
            }
            return
        }
        if overlayWindow == nil {
            let window = NativeXPWindow(windowScene: scene)
            window.windowLevel = .alert + 1
            let host = UIHostingController(rootView: NativeXPOverlay(effects: self))
            host.view.backgroundColor = .clear; window.rootViewController = host
            overlayWindow = window
        }
        let bounds = appWindow.bounds, top = appWindow.safeAreaInsets.top
        let visibleBar = appWindow.rootViewController?.presentedViewController == nil ? activeBars.compactMap { bars[$0]?.view?.xpVisibleFrame(in: appWindow) }.first : nil
        let nutritionTargets = origin.map { visibleNutritionTargets(from: $0, in: appWindow) } ?? []
        let toastBar = CGRect(x: 32, y: top + 60, width: bounds.width - 64, height: 6)
        let reduced = UIAccessibility.isReduceMotionEnabled
        let next = NativeXPFlight(origin: origin ?? CGPoint(x: bounds.midX, y: bounds.height * 0.46),
                                  bar: visibleBar ?? toastBar, nutritionTargets: nutritionTargets, xp: notice.xp, total: summary.totalXp,
                                  floating: visibleBar == nil, automatic: origin == nil, reduced: reduced, safeTop: top)
        flight = next; overlayWindow?.isHidden = false
        let token = generation
        Task {
            try? await Task.sleep(nanoseconds: reduced ? 350_000_000 : 1_980_000_000)
            guard generation == token else { return }
            if !reduced { UINotificationFeedbackGenerator().notificationOccurred(.success) }
            UIAccessibility.post(notification: .announcement, argument: "+\(notice.xp) XP")
            NotificationCenter.default.post(name: Notification.Name("fitTrackerDataDidChange"), object: nil)
            try? await Task.sleep(nanoseconds: next.floating ? 1_800_000_000 : 450_000_000)
            guard generation == token else { return }
            flight = nil; overlayWindow?.isHidden = true; playNext()
        }
    }
}

private final class NativeXPWindow: UIWindow {
    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? { nil }
}
private final class NativeXPTouchObserver: UIGestureRecognizer {
    let observed: (CGPoint) -> Void
    init(observed: @escaping (CGPoint) -> Void) {
        self.observed = observed; super.init(target: nil, action: nil)
        cancelsTouchesInView = false; delaysTouchesBegan = false; delaysTouchesEnded = false
    }
    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent) {
        if let touch = touches.first { observed(touch.location(in: view)) }
        state = .failed
    }
    override func canPrevent(_ preventedGestureRecognizer: UIGestureRecognizer) -> Bool { false }
    override func canBePrevented(by preventingGestureRecognizer: UIGestureRecognizer) -> Bool { false }
}
fileprivate final class WeakXPView {
    weak var view: UIView?
    init(_ view: UIView) { self.view = view }
}
private extension UIView {
    func xpVisibleFrame(in host: UIWindow) -> CGRect? {
        guard window === host, !isHidden, alpha > 0.01, bounds.width > 0 else { return nil }
        let rect = convert(bounds, to: host)
        var visible = host.bounds.inset(by: host.safeAreaInsets)
        var ancestor: UIView? = self
        while let view = ancestor {
            guard !view.isHidden, view.alpha > 0.01 else { return nil }
            if view.clipsToBounds { visible = visible.intersection(view.convert(view.bounds, to: host)) }
            ancestor = view.superview
        }
        guard visible.contains(rect) else { return nil }
        return rect
    }
}

struct NativeXPWindowProbe: UIViewRepresentable {
    func makeUIView(context: Context) -> Probe { Probe() }
    func updateUIView(_ uiView: Probe, context: Context) { if let window = uiView.window { NativeXPEffects.shared.install(window) } }
    final class Probe: UIView {
        override func didMoveToWindow() { super.didMoveToWindow(); if let window { NativeXPEffects.shared.install(window) } }
    }
}
private struct NativeXPBarProbe: UIViewRepresentable {
    let id: UUID
    func makeUIView(context: Context) -> UIView {
        let view = UIView(); view.isUserInteractionEnabled = false
        NativeXPEffects.shared.bars[id] = WeakXPView(view)
        return view
    }
    func updateUIView(_ uiView: UIView, context: Context) { }
}

struct NativeXPNutritionProbe: UIViewRepresentable {
    let index: Int
    func makeUIView(context: Context) -> Probe {
        let view = Probe(); view.isUserInteractionEnabled = false
        NativeXPEffects.shared.registerNutritionProbe(view, id: view.id, index: index)
        return view
    }
    func updateUIView(_ uiView: Probe, context: Context) {
        NativeXPEffects.shared.registerNutritionProbe(uiView, id: uiView.id, index: index)
    }
    static func dismantleUIView(_ uiView: Probe, coordinator: ()) {
        NativeXPEffects.shared.removeNutritionProbe(uiView.id)
    }
    final class Probe: UIView {
        let id = UUID()
    }
}

struct NativeXPLevelLabel: View {
    let summary: GamificationSummary
    @ObservedObject private var effects = NativeXPEffects.shared
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 60, paused: effects.flight == nil)) { timeline in
            let values = effects.flight?.values(timeline.date) ?? NativeXPValues(total: summary.totalXp)
            Text(L("\(values.rank) · Nível \(values.level)"))
        }
    }
}

struct NativeXPProgressBar: View {
    let summary: GamificationSummary
    var showsNextLevel = false
    @State private var id = UUID()
    @ObservedObject private var effects = NativeXPEffects.shared
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 60, paused: effects.flight == nil)) { timeline in
            let values = effects.flight?.values(timeline.date) ?? NativeXPValues(total: summary.totalXp)
            VStack(spacing: 10) {
                GeometryReader { geometry in
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color.secondary.opacity(0.22))
                        Capsule().fill(LinearGradient(colors: [.fitBlue, Color(red: 0.46, green: 0.79, blue: 1)], startPoint: .leading, endPoint: .trailing))
                            .frame(width: geometry.size.width * values.fraction)
                    }
                }.frame(height: 5).background(NativeXPBarProbe(id: id))
                HStack {
                    Text("\(values.xp) / \(values.required) XP").monospacedDigit()
                    Spacer()
                    Text(showsNextLevel ? L("Nível \(values.level + 1)") : L("Ver progresso"))
                }.font(.caption).foregroundColor(.secondary)
            }
        }
        .onAppear { effects.activeBars.insert(id) }
        .onDisappear { effects.activeBars.remove(id) }
    }
}

private struct NativeXPOverlay: View {
    @ObservedObject var effects: NativeXPEffects
    var body: some View {
        if let flight = effects.flight {
            TimelineView(.animation(minimumInterval: 1.0 / 60)) { timeline in
                let time = flight.elapsed(timeline.date), values = flight.values(timeline.date)
                let entrance = flight.reduced ? min(1, time / 0.15) : min(1, time / 0.45)
                let exit = max(0, min(1, (time - (flight.reduced ? 1.7 : 3.25)) / 0.35))
                ZStack(alignment: .top) {
                    if flight.floating {
                        VStack(spacing: 10) {
                            HStack(spacing: 9) {
                                Image(systemName: "rosette.fill").foregroundColor(.fitBlue)
                                Text(L("\(values.rank) · Nível \(values.level)"))
                                Spacer()
                                Text("+\(flight.xp) XP").foregroundColor(Color(red: 0.61, green: 0.82, blue: 1))
                            }.font(.subheadline.weight(.semibold)).frame(height: 22)
                            GeometryReader { geometry in
                                ZStack(alignment: .leading) {
                                    Capsule().fill(Color.white.opacity(0.12))
                                    Capsule().fill(LinearGradient(colors: [.fitBlue, .cyan], startPoint: .leading, endPoint: .trailing))
                                        .frame(width: geometry.size.width * values.fraction)
                                }
                            }.frame(height: 6)
                            HStack {
                                Text("\(values.xp) / \(values.required) XP").monospacedDigit()
                                Spacer(); Text(L("Ver progresso"))
                            }.font(.caption).foregroundColor(.secondary).frame(height: 14)
                        }.padding(16)
                            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 23))
                            .overlay(RoundedRectangle(cornerRadius: 23).stroke(Color.fitBlue.opacity(0.3)))
                            .padding(.horizontal, 16).padding(.top, flight.safeTop + 12)
                            .offset(y: flight.reduced ? 0 : -140 * pow(1 - entrance, 3))
                            .opacity(entrance * (1 - exit))
                    }
                    if !flight.reduced {
                        NativeXPParticleCanvas(flight: flight, date: timeline.date)
                        Text("+\(flight.xp) XP").font(.title3.bold()).foregroundColor(Color(red: 0.77, green: 0.9, blue: 1))
                            .position(x: flight.origin.x, y: flight.origin.y - 28 - CGFloat(min(1, time / 1.3)) * 30)
                            .opacity(min(1, time / 0.15) * max(0, 1 - time / 1.3))
                    }
                }.frame(maxWidth: .infinity, maxHeight: .infinity).ignoresSafeArea()
            }.allowsHitTesting(false).accessibilityHidden(true)
        }
    }
}

private struct NativeXPParticleCanvas: View {
    let flight: NativeXPFlight
    let date: Date
    var body: some View {
        Canvas { context, _ in
            let time = flight.elapsed(date)
            let destination = CGPoint(x: flight.bar.minX + flight.bar.width * flight.values(date).fraction, y: flight.bar.midY)
            if flight.automatic, time < 0.6 {
                let t = time / 0.6, radius = 8 + t * 95
                context.stroke(Path(ellipseIn: CGRect(x: flight.origin.x-radius, y: flight.origin.y-radius, width: radius*2, height: radius*2)), with: .color(.fitBlue.opacity((1-t)*0.45)), lineWidth: 1.5)
            }
            for i in 0..<NativeXPFlight.count {
                guard let point = flight.point(i, time, destination: destination) else { continue }
                var trail = Path()
                for k in (0...7).reversed() {
                    if let previous = flight.point(i, time - Double(k)*0.012, destination: destination) {
                        if trail.isEmpty { trail.move(to: previous) } else { trail.addLine(to: previous) }
                    }
                }
                context.stroke(trail, with: .color(.fitBlue.opacity(0.25)), lineWidth: 1)
                var glow = context
                glow.addFilter(.shadow(color: .fitBlue.opacity(0.75), radius: 4))
                let radius = 1 + flight.seed(i, 29)*2.1
                glow.fill(Path(ellipseIn: CGRect(x: point.x-radius, y: point.y-radius, width: radius*2, height: radius*2)), with: .color(i % 3 == 0 ? Color(red: 0.65, green: 0.9, blue: 1) : Color(red: 0.35, green: 0.65, blue: 1)))
            }
            let absorbed = flight.progress(date)
            if absorbed > 0, time < 2.25 {
                let radius = 7 + sin(absorbed * .pi) * 8
                var glow = context
                glow.addFilter(.blur(radius: 5))
                glow.fill(Path(ellipseIn: CGRect(x: destination.x-radius, y: destination.y-radius, width: radius*2, height: radius*2)), with: .color(.cyan.opacity(0.45 * sin(absorbed * .pi))))
            }
        }
    }
}
