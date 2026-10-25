import XCTest
@testable import FitTrackerCore

final class RequestFailureTests: XCTestCase {
    func testConnectionLossHasActionableGuidanceWithoutSystemDetails() {
        for code: URLError.Code in [.notConnectedToInternet, .networkConnectionLost, .dataNotAllowed] {
            let message = RequestFailure.message(URLError(code), fallback: "Tente depois.")
            XCTAssertTrue(message.contains("internet"))
            XCTAssertTrue(message.contains("tente novamente"))
            XCTAssertFalse(message.contains("NSURLError"))
        }
    }

    func testTimeoutAndUnavailableHostAreDifferentFromNoConnection() {
        XCTAssertTrue(RequestFailure.message(URLError(.timedOut), fallback: "Falha").contains("demorando"))
        XCTAssertTrue(RequestFailure.message(URLError(.cannotConnectToHost), fallback: "Falha").contains("conectar"))
    }

    func testServerAndUnexpectedFailuresDoNotExposeInternalMessages() {
        let fallback = "Seu progresso não carregou. Tente de novo."
        for failure: Error in [APIError.http(status: 503, message: "SQL stack trace"), APIError.invalidResponse,
                               NSError(domain: "InternalImplementation", code: 42)] {
            XCTAssertEqual(RequestFailure.message(failure, fallback: fallback), fallback)
        }
    }

    func testAuthenticationAndRateLimitsOfferAppropriateNextStep() {
        XCTAssertTrue(RequestFailure.message(APIError.http(status: 401, message: "internal"), fallback: "Falha").contains("Entre novamente"))
        XCTAssertTrue(RequestFailure.message(APIError.csrfMismatch, fallback: "Falha").contains("confirmar seu acesso"))
        XCTAssertTrue(RequestFailure.message(APIError.http(status: 429, message: "limit"), fallback: "Falha").contains("Aguarde"))
    }

    func testValidationAndConsentGuidanceArePreserved() {
        let validation = "Informe as repetições desta série."
        XCTAssertEqual(RequestFailure.message(APIError.http(status: 422, message: validation), fallback: "Falha"), validation)
        let consent = "Revise suas preferências de IA."
        XCTAssertEqual(RequestFailure.message(APIError.http(status: 403, message: consent), fallback: "Falha"), consent)
    }
}
