import Foundation

public struct WorkoutTextImport: Sendable, Identifiable {
    public let id = UUID()
    public let sourceText: String
    public let days: [ImportedWorkoutDay]
    public let warnings: [String]
}

public struct ImportedWorkoutDay: Sendable {
    public var title: String
    public var exercises: [ImportedWorkoutExercise]
}

public struct ImportedWorkoutExercise: Sendable {
    public let name: String
    public let sets: Int?
    public let reps: String
    public let weight: String
    public let restSeconds: Int?
}

public enum WorkoutTextImportError: Error, LocalizedError {
    case empty, tooLarge, noExercises, tooManyDays, tooManyExercises
    public var errorDescription: String? {
        switch self {
        case .empty: return "Cole seu treino ou escolha uma imagem com texto."
        case .tooLarge: return "Importe até 40.000 caracteres por vez. Divida o treino em partes menores."
        case .noExercises: return "Não identificamos exercícios. Confira o texto e use, por exemplo, Supino 3x10. Nenhum plano foi salvo."
        case .tooManyDays: return "Um plano aceita até 7 treinos. Divida o texto em mais de um plano."
        case .tooManyExercises: return "Cada treino aceita até 12 exercícios. Divida os dias antes de importar."
        }
    }
}

/// A conservative parser: unknown text remains visible for review, never becomes a guessed prescription.
public enum WorkoutTextParser {
    public static func parse(_ source: String) throws -> WorkoutTextImport {
        guard source.count <= 40_000 else { throw WorkoutTextImportError.tooLarge }
        guard !source.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw WorkoutTextImportError.empty }
        var days: [ImportedWorkoutDay] = []
        var warnings: [String] = []
        for (offset, raw) in source.components(separatedBy: .newlines).enumerated() {
            let line = raw.trimmingCharacters(in: .whitespaces)
            guard !line.isEmpty else { continue }
            if matches(#"^(?:(?:treino|workout|dia|day)\s+[a-z0-9]+(?:\s*[-–—:]\s*.+)?|(?:segunda|terça|quarta|quinta|sexta)(?:-feira)?|sábado|domingo)\s*:?$"#, line) {
                days.append(ImportedWorkoutDay(title: line, exercises: []))
                continue
            }
            let cleaned = line.replacingOccurrences(of: #"^\s*(?:[-•●]\s*|\d+[.)]\s*)"#, with: "", options: .regularExpression)
            guard let exercise = exercise(cleaned, numbered: matches(#"^\d+[.)]\s*\p{L}"#, line)) else {
                warnings.append("Linha \(offset + 1) não interpretada: \(line)")
                continue
            }
            if days.isEmpty { days.append(ImportedWorkoutDay(title: "Treino A", exercises: [])) }
            days[days.count - 1].exercises.append(exercise.value)
            for issue in exercise.issues { warnings.append("Linha \(offset + 1): \(issue)") }
        }
        guard days.contains(where: { !$0.exercises.isEmpty }) else { throw WorkoutTextImportError.noExercises }
        guard days.count <= 7 else { throw WorkoutTextImportError.tooManyDays }
        guard days.allSatisfy({ $0.exercises.count <= 12 }) else { throw WorkoutTextImportError.tooManyExercises }
        for day in days where day.exercises.isEmpty { warnings.append("\(day.title): nenhum exercício identificado. Complete ou remova esse dia.") }
        return WorkoutTextImport(sourceText: source, days: days, warnings: warnings)
    }

    private static func exercise(_ line: String, numbered: Bool) -> (value: ImportedWorkoutExercise, issues: [String])? {
        // Accept 3x10, 3 × 8-12, 3 séries de 10, and preserve explicit repetition ranges.
        let pattern = #"^(.*?)\s*[:;|–—-]?\s*(\d{1,3})\s*(?:[x×]|s[eé]ries?\s*(?:de|[x×])?)\s*(\d{1,3}(?:\s*[-–]\s*\d{1,3})?(?:\s*(?:reps?|repetiç(?:ões|ão)|segundos?|s|min))?)(.*)$"#
        let groups = captures(pattern, line)
        var issues: [String] = []
        guard groups != nil || numbered else { return nil }
        let name = (groups?[0] ?? line).trimmingCharacters(in: CharacterSet(charactersIn: " \t:;|–—-"))
        guard name.rangeOfCharacter(from: .letters) != nil else { return nil }
        let rawSets = groups.flatMap { Int($0[1]) }
        let sets = rawSets.flatMap { (1...10).contains($0) ? $0 : nil }
        let reps = groups?[2].trimmingCharacters(in: .whitespaces) ?? ""
        var tail = groups?[3] ?? ""
        var rest: Int?
        var weight = ""
        if let match = captures(#"(?:descanso|intervalo|rest)\s*:?\s*(\d{1,3})\s*(s(?:eg(?:undos?)?)?|min(?:utos?)?)\b"#, tail), let amount = Int(match[0]) {
            let seconds = match[1].lowercased().hasPrefix("min") ? amount * 60 : amount
            if (0...600).contains(seconds) { rest = seconds }
            tail = tail.replacingOccurrences(of: #"(?:descanso|intervalo|rest)\s*:?\s*\d{1,3}\s*(?:s(?:eg(?:undos?)?)?|min(?:utos?)?)\b"#, with: "", options: [.regularExpression, .caseInsensitive])
        }
        if let match = captures(#"(?:carga\s*:?\s*)?(\d+(?:[.,]\d+)?\s*(?:kg|lbs?))\b"#, tail) {
            weight = match[0]
            tail = tail.replacingOccurrences(of: #"(?:carga\s*:?\s*)?\d+(?:[.,]\d+)?\s*(?:kg|lbs?)\b"#, with: "", options: [.regularExpression, .caseInsensitive])
        }
        if sets == nil { issues.append("\(name): informe de 1 a 10 séries; não atribuímos um valor.") }
        if reps.isEmpty { issues.append("\(name): informe as repetições.") }
        if rest == nil { issues.append("\(name): descanso não informado ou fora de 0 a 600 s; confirme na revisão.") }
        if !tail.trimmingCharacters(in: CharacterSet(charactersIn: " \t;|,·–—-")).isEmpty {
            issues.append("\(name): confira o complemento não interpretado: \(tail.trimmingCharacters(in: .whitespaces))")
        }
        return (ImportedWorkoutExercise(name: name, sets: sets, reps: reps, weight: weight, restSeconds: rest), issues)
    }
    private static func matches(_ pattern: String, _ text: String) -> Bool { captures(pattern, text) != nil }
    private static func captures(_ pattern: String, _ text: String) -> [String]? {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) else { return nil }
        return (1..<match.numberOfRanges).map { index in
            Range(match.range(at: index), in: text).map { String(text[$0]) } ?? ""
        }
    }
}
