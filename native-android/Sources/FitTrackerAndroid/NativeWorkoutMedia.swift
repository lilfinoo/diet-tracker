import SwiftUI
import Observation
#if os(Android)
import SkipFuse
#endif
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
#if !os(Android)
import UIKit
import ImageIO
#endif

@MainActor
final class NativeWorkoutMediaCache {
    static let shared = NativeWorkoutMediaCache()

    let media = NSCache<NSString, NSData>()
    var inFlight: [String: (id: UUID, task: Task<Data?, Never>)] = [:]

    init() {
        media.totalCostLimit = 120 * 1024 * 1024
    }

    func data(for catalogKey: String) async -> Data? {
        guard !catalogKey.isEmpty, !catalogKey.hasPrefix("custom:") else { return nil }
        let cacheKey = catalogKey as NSString
        if let data = media.object(forKey: cacheKey) { return data as Data }

        let request: (id: UUID, task: Task<Data?, Never>)
        if let existing = inFlight[catalogKey] {
            request = existing
        } else {
            request = (UUID(), Task { await Self.fetchData(catalogKey: catalogKey) })
            inFlight[catalogKey] = request
        }

        let data = await request.task.value
        if inFlight[catalogKey]?.id == request.id {
            inFlight[catalogKey] = nil
        }
        if let data {
            media.setObject(data as NSData, forKey: cacheKey, cost: data.count)
        }
        return data
    }

    func prefetch(keys: [String]) async {
        var seen = Set<String>()
        let keys = keys.filter { !$0.isEmpty && seen.insert($0).inserted }
        guard !keys.isEmpty else { return }
        var next = 0
        await withTaskGroup(of: Void.self) { group in
            for _ in 0..<min(2, keys.count) {
                let key = keys[next]
                next += 1
                group.addTask { _ = await self.data(for: key) }
            }
            while await group.next() != nil {
                guard !Task.isCancelled, next < keys.count else { continue }
                let key = keys[next]
                next += 1
                group.addTask { _ = await self.data(for: key) }
            }
        }
    }

    static func fetchData(catalogKey: String) async -> Data? {
        let base = NativeConfiguration.apiBaseURL
        let url = base.appendingPathComponent("public/exercise-media").appendingPathComponent(catalogKey)
        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200,
                  data.count <= 20_000_000 else { return nil }
            return data
        } catch {
            return nil
        }
    }

}

struct NativeExerciseAnimation: View {
    let catalogKey: String?
    var showsPlaybackControls = true
    @Environment(\.accessibilityReduceMotion) var reduceMotion
    @Environment(\.scenePhase) var scenePhase
    @State var data: Data?
    @State var failed = false
    @State var retry = 0
    @State var isPlaying = true
    @State var isVisible = false

    var body: some View {
        Group {
            if let data {
                ZStack(alignment: .bottomTrailing) {
                    NativeAnimatedImage(data: data, animate: isVisible && isPlaying && scenePhase == .active)
                    if showsPlaybackControls { Button { isPlaying.toggle() } label: {
                        Image(systemName: isPlaying ? "pause.fill" : "play.fill")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundColor(.white)
                            .frame(width: 44, height: 44)
                            .background(Color(red: 0, green: 0.82, blue: 0.69), in: Circle())
                    }
                    .buttonStyle(.plain)
                    .padding(12)
                    .accessibilityLabel(isPlaying ? "Pausar demonstração" : "Reproduzir demonstração")
                    }
                }
            } else if catalogKey == nil || catalogKey?.hasPrefix("custom:") == true {
                Color.clear
            } else if failed {
                VStack(spacing: 14) {
                    Image(systemName: "dumbbell.fill").font(.system(size: 44))
                    Text("Demonstração indisponível").font(.subheadline)
                    if catalogKey != nil { Button("Tentar carregar novamente") { retry += 1 } }
                }.foregroundColor(.gray).frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ProgressView("Carregando demonstração…").tint(.gray).foregroundColor(.gray)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(Color.white)
        .onAppear { isVisible = true; isPlaying = !reduceMotion }
        .onDisappear { isVisible = false; isPlaying = false }
        .accessibilityLabel("Demonstração do exercício")
        .task(id: "\(catalogKey ?? ""): \(retry)") { await load() }
    }

    func load() async {
        data = nil
        failed = false
        guard let catalogKey else { failed = true; return }
        let result = await NativeWorkoutMediaCache.shared.data(for: catalogKey)
        guard !Task.isCancelled else { return }
        if let result { data = result } else { failed = true }
    }
}

#if os(Android)
struct NativeAnimatedImage: View {
    let data: Data
    let animate: Bool

    var body: some View {
        ComposeView { WorkoutGIFComposer(encoded: data.base64EncodedString(), animate: animate) }
    }
}
#else
struct NativeAnimatedImage: UIViewRepresentable {
    let data: Data
    let animate: Bool

    func makeUIView(context: Context) -> WorkoutGIFView {
        let view = WorkoutGIFView()
        view.imageView.contentMode = .scaleAspectFit
        view.imageView.setContentHuggingPriority(.defaultLow, for: .vertical)
        view.imageView.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        view.imageView.setContentCompressionResistancePriority(.defaultLow, for: .vertical)
        view.update(data: data, animate: animate)
        return view
    }

    func updateUIView(_ view: WorkoutGIFView, context: Context) {
        view.update(data: data, animate: animate)
    }

    static func dismantleUIView(_ view: WorkoutGIFView, coordinator: ()) {
        view.stopAnimation()
    }
}

final class WorkoutGIFView: UIView {
    let imageView = UIImageView()
    let frames = NSCache<NSNumber, UIImage>()
    let decodeQueue = DispatchQueue(label: "fittracker.workout.gif", qos: .userInitiated)
    var data: Data?
    var source: CGImageSource?
    var delays: [TimeInterval] = []
    var timer: Timer?
    var generation = 0
    var isAnimating = false
    var requestedAnimation = false
    var preparedFrame: (index: Int, image: CGImage)?
    var decodingIndex: Int?
    var requestedIndex: Int?

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .white
        imageView.backgroundColor = .white
        frames.totalCostLimit = 40 * 1024 * 1024
        addSubview(imageView)
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    override func layoutSubviews() {
        super.layoutSubviews()
        imageView.frame = bounds
    }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        if window == nil {
            stopAnimation()
        } else if requestedAnimation, !isAnimating, delays.count > 1 {
            isAnimating = true
            display(index: 0, animate: true)
        }
    }

    func update(data: Data, animate: Bool) {
        requestedAnimation = animate
        if self.data != data {
            self.data = data
            source = CGImageSourceCreateWithData(data as CFData, nil)
            generation += 1
            stop()
            frames.removeAllObjects()
            preparedFrame = nil
            decodingIndex = nil
            requestedIndex = nil
            let count = source.map { CGImageSourceGetCount($0) } ?? 0
            delays = (0..<count).map { index in
                let properties = source.flatMap { CGImageSourceCopyPropertiesAtIndex($0, index, nil) as? [CFString: Any] }
                let gif = properties?[kCGImagePropertyGIFDictionary] as? [CFString: Any]
                return max(0.02, (gif?[kCGImagePropertyGIFUnclampedDelayTime] as? Double)
                    ?? (gif?[kCGImagePropertyGIFDelayTime] as? Double) ?? 0.1)
            }
            isAnimating = animate && window != nil && delays.count > 1
            display(index: 0, animate: isAnimating)
        } else if !animate, isAnimating {
            stopAnimation()
            display(index: 0, animate: false)
        } else if animate, window != nil, !isAnimating, delays.count > 1 {
            isAnimating = true
            display(index: 0, animate: true)
        }
    }

    func display(index: Int, animate: Bool) {
        guard source != nil, !delays.isEmpty else { return }
        stop()
        requestedIndex = index
        if let frame = frames.object(forKey: NSNumber(value: index))?.cgImage {
            show(frame, at: index, animate: animate)
            return
        }
        if let preparedFrame, preparedFrame.index == index {
            self.preparedFrame = nil
            show(preparedFrame.image, at: index, animate: animate)
            return
        }
        guard decodingIndex != index else { return }
        decode(index)
    }

    func decode(_ index: Int) {
        guard let source else { return }
        decodingIndex = index
        let currentGeneration = generation
        decodeQueue.async { [weak self] in
            let options = [kCGImageSourceShouldCacheImmediately: true] as CFDictionary
            let frame = CGImageSourceCreateImageAtIndex(source, index, options)
            CGImageSourceRemoveCacheAtIndex(source, index)
            DispatchQueue.main.async {
                guard let self, self.generation == currentGeneration else { return }
                self.decodingIndex = nil
                guard let frame else { return }
                self.frames.setObject(UIImage(cgImage: frame), forKey: NSNumber(value: index),
                    cost: frame.width * frame.height * 4)
                if self.requestedIndex == index {
                    self.show(frame, at: index, animate: self.isAnimating)
                } else {
                    self.preparedFrame = (index, frame)
                }
            }
        }
    }

    func show(_ frame: CGImage, at index: Int, animate: Bool) {
        imageView.image = UIImage(cgImage: frame)
        guard animate, isAnimating, requestedAnimation, window != nil, delays.count > 1 else { return }
        let nextIndex = (index + 1) % delays.count
        if preparedFrame?.index != nextIndex, decodingIndex != nextIndex {
            decode(nextIndex)
        }
        let timer = Timer(timeInterval: delays[index], repeats: false) { [weak self] _ in
            self?.display(index: nextIndex, animate: true)
        }
        self.timer = timer
        RunLoop.main.add(timer, forMode: .common)
    }

    func stop() {
        timer?.invalidate()
        timer = nil
    }

    func stopAnimation() {
        stop()
        isAnimating = false
        generation += 1
        preparedFrame = nil
        decodingIndex = nil
        requestedIndex = nil
    }
}

#endif

#if SKIP
struct WorkoutGIFComposer: ContentComposer {
    let encoded: String
    let animate: Bool

    @Composable func Compose(context: ComposeContext) {
        NativeWorkoutPlatform.GIF(encoded: encoded, animate: animate, modifier: context.modifier)
    }
}


#endif
