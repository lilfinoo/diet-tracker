import UIKit
import Foundation
let output = URL(fileURLWithPath: CommandLine.arguments[1])
precondition(UIImage(named: "FitTrackerFullLogo") != nil, "Official logo must load")
func background(_ color: UIColor) -> UIImage {
    let f = UIGraphicsImageRendererFormat(); f.scale = 1
    return UIGraphicsImageRenderer(size: CGSize(width: 1080, height: 1920), format: f).image { c in
        color.setFill(); c.fill(CGRect(x: 0, y: 0, width: 1080, height: 1920))
    }
}
func check(_ image: UIImage, _ name: String) throws {
    precondition(image.size == CGSize(width: 1080, height: 1920) && image.scale == 1)
    let png = image.pngData()!
    precondition(UIImage(data: png)!.size == image.size)
    try png.write(to: output.appendingPathComponent(name + ".png"))
    print("PASS \(name): 1080 × 1920, PNG round-trip")
}
let white = background(.white), black = background(.black)
try check(renderMealShare(photo: white, mealType: "Almoço", calories: 220, macros: [8,40,2]), "native-meal-white")
try check(renderMealShare(photo: black, mealType: "Café da manhã", calories: 220, macros: [8,40,2]), "native-meal-black")
try check(renderMealShare(photo: white, mealType: "Outros", calories: 0, macros: [nil,nil,nil]), "native-meal-missing")
try check(renderMealShare(photo: white, mealType: "Jantar", calories: 12345.6, macros: [1234.5,0,nil]), "native-meal-large")
let photo = UIImage(contentsOfFile: CommandLine.arguments[2])!
try check(renderMealShare(photo: photo, mealType: "Almoço", calories: 220, macros: [8,40,2]), "native-meal-photo")
let sets = (1...3).map { WorkoutPerformedSet(setOrder: $0, repetitions: 12, loadKg: 40, isWarmup: false) }
let exercise = WorkoutPerformedExercise(exerciseId: 1, name: "Supino reto com barra", sets: sets)
let summary = WorkoutActivitySummary(id: 1, workoutName: "Peito e tríceps", planName: "Plano", durationSeconds: 2880, exercisesPerformed: 6, totalExercises: 6, setsPerformed: 18, volumeTotalKg: 1440, exercises: [exercise])
for (name, photo) in [("white", white as UIImage?), ("black", black as UIImage?), ("no-photo", nil)] {
    try check(WorkoutShareCard(summary: summary, exercise: exercise, duration: "48 min", photo: photo).artwork(), "native-workout-" + name)
}
let varied = WorkoutPerformedExercise(exerciseId: 2, name: "Desenvolvimento com halteres sentado e pegada neutra", sets: [sets[0], WorkoutPerformedSet(setOrder: 2, repetitions: 10, loadKg: 42, isWarmup: false)])
try check(WorkoutShareCard(summary: summary, exercise: varied, duration: "1h 48min", photo: white).artwork(), "native-workout-varied")
let planned = WorkoutPerformedExercise(exerciseId: 3, name: "Flexão", sets: [], plannedPrescription: WorkoutPlannedPrescription(sets: 3, reps: "8–12"))
try check(WorkoutShareCard(summary: summary, exercise: planned, duration: "48 min", photo: black).artwork(), "native-workout-planned")
