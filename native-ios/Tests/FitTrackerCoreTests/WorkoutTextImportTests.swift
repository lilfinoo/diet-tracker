import XCTest
@testable import FitTrackerCore

final class WorkoutTextImportTests: XCTestCase {
    func testMultiDayPrescriptionRangesLoadAndRestArePreserved() throws {
        let source = "Treino A - Peito\n1. Supino reto 3x8-12 | 20 kg | descanso 90s\nTreino B\nAgachamento 4 séries de 10; intervalo 2 min"
        let result = try WorkoutTextParser.parse(source)
        XCTAssertEqual(result.sourceText, source)
        XCTAssertEqual(result.days.map(\.title), ["Treino A - Peito", "Treino B"])
        let supino = try XCTUnwrap(result.days.first?.exercises.first)
        XCTAssertEqual(supino.name, "Supino reto")
        XCTAssertEqual(supino.sets, 3)
        XCTAssertEqual(supino.reps, "8-12")
        XCTAssertEqual(supino.weight, "20 kg")
        XCTAssertEqual(supino.restSeconds, 90)
        XCTAssertEqual(result.days[1].exercises[0].restSeconds, 120)
        XCTAssertTrue(result.warnings.isEmpty)
    }
    func testMissingPrescriptionIsNeverFilledWithDefaults() throws {
        let result = try WorkoutTextParser.parse("Treino A\n1. Supino\nAgachamento 3x10")
        let incomplete = result.days[0].exercises[0]
        XCTAssertEqual(incomplete.name, "Supino")
        XCTAssertNil(incomplete.sets)
        XCTAssertEqual(incomplete.reps, "")
        XCTAssertNil(incomplete.restSeconds)
        XCTAssertNil(result.days[0].exercises[1].restSeconds)
        XCTAssertEqual(result.warnings.count, 4)
    }
    func testUnparsedInstructionsAndAmbiguousComplementsStayVisible() throws {
        let source = "Orientações do professor\nTreino A\nSupino 3x10 drop set\nTreino B"
        let result = try WorkoutTextParser.parse(source)
        XCTAssertEqual(result.sourceText, source)
        XCTAssertEqual(result.days.count, 2)
        XCTAssertEqual(result.days[0].exercises.count, 1)
        XCTAssertTrue(result.warnings.contains(where: { $0.contains("Orientações do professor") }))
        XCTAssertTrue(result.warnings.contains(where: { $0.contains("drop set") }))
        XCTAssertTrue(result.warnings.contains(where: { $0.contains("Treino B") }))
    }
    func testTimedPrescriptionsAndWeekdaysDoNotBecomeExtraExercises() throws {
        let result = try WorkoutTextParser.parse("Segunda-feira\nPrancha 3 × 30 s | descanso 0 s\nQuarta\nRemada 4x12 reps rest 60s")
        XCTAssertEqual(result.days.count, 2)
        XCTAssertEqual(result.days[0].exercises[0].reps, "30 s")
        XCTAssertEqual(result.days[0].exercises[0].restSeconds, 0)
        XCTAssertEqual(result.days[1].exercises[0].name, "Remada")
        XCTAssertTrue(result.warnings.isEmpty)
    }
    func testOutOfRangeSeriesAndRestRequireCorrection() throws {
        let result = try WorkoutTextParser.parse("Supino 99x10 descanso 999 s")
        XCTAssertNil(result.days[0].exercises[0].sets)
        XCTAssertNil(result.days[0].exercises[0].restSeconds)
        XCTAssertEqual(result.warnings.count, 2)
    }
    func testEmptyUnrecognizedAndOversizedSourcesReturnActionableErrors() {
        XCTAssertThrowsError(try WorkoutTextParser.parse(" \n ")) { XCTAssertTrue($0 is WorkoutTextImportError) }
        XCTAssertThrowsError(try WorkoutTextParser.parse("Sem exercícios identificáveis"))
        XCTAssertThrowsError(try WorkoutTextParser.parse(String(repeating: "a", count: 40_001)))
    }
    func testTooManyDaysOrExercisesFailWithoutTruncation() {
        let days = (1...8).map { "Treino \($0)\nSupino 3x10" }.joined(separator: "\n")
        XCTAssertThrowsError(try WorkoutTextParser.parse(days))
        let exercises = Array(repeating: "Supino 3x10", count: 13).joined(separator: "\n")
        XCTAssertThrowsError(try WorkoutTextParser.parse(exercises))
    }
}
