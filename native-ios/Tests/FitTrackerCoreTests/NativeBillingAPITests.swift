import XCTest
@testable import FitTrackerCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class NativeBillingAPITests: XCTestCase {
    func testDefaultPlatformDecodesExistingIOSContract() async throws {
        let api = makeAPI(platform: "ios", response: """
        {"configured":true,"public_api_key":"appl_public","entitlement_id":"fittracker_ai_pro"}
        """)
        let result = try await api.nativeBillingConfiguration()
        XCTAssertTrue(result.configured)
        XCTAssertEqual(result.publicApiKey, "appl_public")
        XCTAssertNil(result.productIdentifiers)
    }

    func testAndroidRequestsItsOwnKeyAndServerProductIdentifiers() async throws {
        let api = makeAPI(platform: "android", response: """
        {"configured":true,"public_api_key":"goog_public","entitlement_id":"fittracker_ai_pro","product_identifiers":["fit_monthly","fit_annual"]}
        """)
        let result = try await api.nativeBillingConfiguration(platform: "android")
        XCTAssertEqual(result.publicApiKey, "goog_public")
        XCTAssertEqual(result.productIdentifiers, ["fit_monthly", "fit_annual"])
    }

    private func makeAPI(platform: String, response: String) -> FitTrackerAPI {
        BillingProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.path, "/api/billing/revenuecat/config")
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems
            XCTAssertEqual(query?.first(where: { $0.name == "platform" })?.value, platform)
            return Data(response.utf8)
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [BillingProtocol.self]
        return FitTrackerAPI(baseURL: URL(string: "https://billing.invalid/api")!, session: URLSession(configuration: configuration))
    }
}

private final class BillingProtocol: URLProtocol {
    static var handler: ((URLRequest) -> Data)?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let handler = Self.handler else { return }
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: handler(request))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() { }
}
