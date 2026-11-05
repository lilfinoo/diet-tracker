"""Render the actual UIKit share artwork locally, without accounts or a simulator."""

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[3]
    app = root / "native-ios/App"
    meal = (app / "NativeMealComposer.swift").read_text()
    meal = meal[meal.index("private func renderMealShare("):meal.index("// UIImage is captured")]
    meal = meal.replace("private func renderMealShare(", "func renderMealShare(", 1)
    workout = (app / "NativeWorkoutCompletionView.swift").read_text()
    start = workout.index("private struct WorkoutShareCard:")
    end = workout.index("@MainActor\nprivate func renderShareCard", start)
    workout = workout[start:end].replace("private struct WorkoutShareCard:", "struct WorkoutShareCard:", 1)
    models = (root / "native-ios/Sources/FitTrackerCore/WorkoutModels.swift").read_text()
    models = models[models.index("public struct WorkoutActivitySummary:"):]
    sdk = subprocess.check_output(["xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True).strip()
    with tempfile.TemporaryDirectory(prefix="fittracker-share-render-") as temporary:
        work = Path(temporary)
        (work / "Render.swift").write_text("import UIKit\n" + meal)
        (work / "Workout.swift").write_text("import UIKit\nimport SwiftUI\n" + models + workout)
        shutil.copy(Path(__file__).with_name("main.swift"), work / "main.swift")
        shutil.copy(app / "Assets.xcassets/FitTrackerFullLogo.imageset/FitTrackerFullLogo.png", work)
        executable = work / "render"
        subprocess.run([
            "xcrun", "swiftc", "-target", "arm64-apple-ios15.0-macabi", "-sdk", sdk,
            "-F", str(Path(sdk) / "System/iOSSupport/System/Library/Frameworks"),
            str(work / "Render.swift"), str(work / "Workout.swift"), str(work / "main.swift"),
            "-o", str(executable),
        ], check=True)
        subprocess.run([
            str(executable), str(output),
            str(root / "docs/share-card-preview/assets/meal.jpg"),
        ], check=True)


if __name__ == "__main__":
    main()
