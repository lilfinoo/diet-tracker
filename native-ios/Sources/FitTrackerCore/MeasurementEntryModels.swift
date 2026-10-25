import Foundation

public struct NewMeasurementEntry: Encodable, Sendable {
    public let date: String
    public let weight: Double?
    public let height: Double?
    public let bodyFat: Double?
    public let muscleMass: Double?
    public let waist: Double?
    public let chest: Double?
    public let arm: Double?
    public let thigh: Double?
    public let notes: String?

    public init(date: String, weight: Double? = nil, height: Double? = nil,
                bodyFat: Double? = nil, muscleMass: Double? = nil,
                waist: Double? = nil, chest: Double? = nil, arm: Double? = nil, thigh: Double? = nil, notes: String? = nil) {
        self.date = date
        self.weight = weight
        // The backend accepts meters up to 3 and stores height in centimeters.
        self.height = height.map { value in
            let centimeters = value > 0 && value <= 3 ? value * 100 : value
            return (centimeters * 1_000_000).rounded() / 1_000_000
        }
        self.bodyFat = bodyFat
        self.muscleMass = muscleMass
        self.waist = waist
        self.chest = chest
        self.arm = arm
        self.thigh = thigh
        self.notes = notes
    }

    func validate() throws {
        for (value, maximum) in [(weight, 500.0), (height, 300.0), (bodyFat, 100.0),
                                 (muscleMass, 500.0), (waist, 500.0), (chest, 500.0),
                                 (arm, 500.0), (thigh, 500.0)] {
            if let value, !value.isFinite || value <= 0 || value > maximum {
                throw APIError.http(status: 400, message: "Medida fora do intervalo permitido. Deixe em branco os valores desconhecidos.")
            }
        }
    }
}

public struct MeasurementEntry: Decodable, Identifiable, Sendable {
    public let id: Int
    public let date: String
    public let weight: Double?
    public let height: Double?
    public let bodyFat: Double?
    public let muscleMass: Double?
    public let waist: Double?
    public let chest: Double?
    public let arm: Double?
    public let thigh: Double?
    public let notes: String?

    public var entry: NewMeasurementEntry {
        NewMeasurementEntry(date: date, weight: weight, height: height, bodyFat: bodyFat,
            muscleMass: muscleMass, waist: waist, chest: chest, arm: arm, thigh: thigh, notes: notes)
    }
}
