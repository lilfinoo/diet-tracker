import SwiftUI
#if os(Android)
import SkipFuse
#endif

struct NativeLaunchView: View {
    @Environment(\.accessibilityReduceMotion) var reduceMotion
    @State var animate = false
    @State var reflected = false

    var body: some View {
        GeometryReader { geometry in
            let logoWidth = min(320, geometry.size.width * 0.84)
            ZStack {
                RadialGradient(colors: [Color(red: 17/255, green: 35/255, blue: 60/255), Color.fitBackground],
                               center: UnitPoint(x: 0.5, y: 0.43), startRadius: 5, endRadius: geometry.size.height * 0.7)
                Circle()
                    .fill(RadialGradient(colors: [Color.fitBlue.opacity(0.08), .clear],
                                         center: .center, startRadius: 4, endRadius: 160))
                    .frame(width: 320, height: 260)
                    .position(x: geometry.size.width / 2, y: geometry.size.height * 0.43)
                VStack(spacing: 7) {
                    Image("FitTrackerFullLogo", bundle: .module)
                        .resizable().scaledToFit()
                        .overlay {
                            Image("FitTrackerFullLogo", bundle: .module)
                                .renderingMode(.template).resizable().scaledToFit()
                                .foregroundColor(.white.opacity(0.9))
                                .mask(alignment: .leading) {
                                    Rectangle().frame(width: logoWidth * 0.565).offset(x: logoWidth * 0.25)
                                }
                        }
                        .overlay {
                            if !reduceMotion {
                                LinearGradient(stops: [
                                    .init(color: .clear, location: 0.43),
                                    .init(color: .white.opacity(0.18), location: 0.47),
                                    .init(color: .white.opacity(0.95), location: 0.5),
                                    .init(color: .white.opacity(0.18), location: 0.53),
                                    .init(color: .clear, location: 0.57),
                                ], startPoint: .leading, endPoint: .trailing)
                                .frame(width: logoWidth * 3, height: logoWidth / 3)
                                .offset(x: reflected ? 0 : -logoWidth * 2)
                                .frame(width: logoWidth, height: logoWidth / 3, alignment: .leading)
                                .mask(Image("FitTrackerFullLogo", bundle: .module).resizable().scaledToFit())
                            }
                        }
                        .frame(width: logoWidth, height: logoWidth / 3)
                    Text("SEU TREINO. SUA EVOLUÇÃO.")
                        .font(.system(size: 10, weight: .semibold)).tracking(2.1)
                        .foregroundColor(Color(red: 137/255, green: 161/255, blue: 191/255))
                }
                .accessibilityHidden(true)
                .position(x: geometry.size.width / 2, y: geometry.size.height * 0.43)
                VStack(spacing: 14) {
                    Text("Preparando seu dia").font(.caption).foregroundColor(Color(red: 135/255, green: 161/255, blue: 194/255))
                    if !reduceMotion {
                        HStack(spacing: 5) {
                            ForEach(0..<3) { index in
                                Circle().fill(Color.fitBlue).frame(width: 4, height: 4)
                                    .opacity(animate ? 1 : 0.35)
                                    .animation(.easeInOut(duration: 0.65).repeatForever().delay(Double(index) * 0.15), value: animate)
                            }
                        }
                    }
                }
                .accessibilityHidden(true)
                .position(x: geometry.size.width / 2, y: geometry.size.height - 110)
            }
            .ignoresSafeArea()
            .accessibilityLabel("Fit Tracker. Preparando seu dia")
            .onAppear { if !reduceMotion { animate = true } }
            .task {
                guard !reduceMotion else { return }
                do { try await Task.sleep(nanoseconds: 300_000_000) } catch { return }
                withAnimation(.easeInOut(duration: 1.65)) { reflected = true }
            }
        }
        .background(Color.fitBackground.ignoresSafeArea())
    }
}
