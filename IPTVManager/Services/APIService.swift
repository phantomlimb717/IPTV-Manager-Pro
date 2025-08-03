import Foundation
import os

// MARK: - Custom Errors
enum APIError: LocalizedError {
    case invalidRequest(reason: String)
    case serverError(statusCode: Int)
    case decodingError(Error)
    case invalidResponse(reason: String)
    case notImplemented
    case handshakeFailed(reason: String)

    var errorDescription: String? {
        switch self {
        case .invalidRequest(let reason):
            return "Invalid Request: \(reason)"
        case .serverError(let statusCode):
            return "Server Error: Received status code \(statusCode)."
        case .decodingError:
            return "Decoding Error: Failed to parse the server response."
        case .invalidResponse(let reason):
            return "Invalid Response: \(reason)"
        case .notImplemented:
            return "This feature is not yet implemented."
        case .handshakeFailed(let reason):
            return "Handshake Failed: \(reason)"
        }
    }
}

// MARK: - APIService Protocol
/// Defines a common interface for all API services.
protocol APIServiceProtocol {
    func checkStatus(for entry: IPTVEntry) async throws -> APIResult
}


// MARK: - Main APIService Class
/// The primary service class that orchestrates API calls. It determines the account type
/// and delegates the work to the appropriate specialized method.
final class APIService: APIServiceProtocol {

    private let logger = Logger(subsystem: "com.yourapp.IPTVManager", category: "APIService")
    private let session: URLSession

    init() {
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 15 // 15-second timeout
        self.session = URLSession(configuration: configuration)
    }

    /// Primary entry point for checking an entry's status.
    func checkStatus(for entry: IPTVEntry) async throws -> APIResult {
        logger.info("Checking status for entry: '\(entry.name, privacy: .public)' of type '\(entry.accountType.rawValue, privacy: .public)'")
        switch entry.accountType {
        case .xtreamCodes:
            return try await checkXCStatus(for: entry)
        case .stalker:
            return try await checkStalkerStatus(for: entry)
        }
    }

    // MARK: - Xtream Codes API Logic
    private func checkXCStatus(for entry: IPTVEntry) async throws -> APIResult {
        guard let serverURL = entry.serverBaseURL, !serverURL.isEmpty,
              let username = entry.username, !username.isEmpty,
              let password = entry.password else {
            throw APIError.invalidRequest(reason: "Server URL, username, or password missing for XC entry.")
        }

        var components = URLComponents(string: serverURL)
        components?.path = "/player_api.php"
        components?.queryItems = [
            URLQueryItem(name: "username", value: username),
            URLQueryItem(name: "password", value: password),
            URLQueryItem(name: "action", value: "get_user_info")
        ]

        guard let url = components?.url else {
            throw APIError.invalidRequest(reason: "Could not create a valid URL from the provided server details.")
        }

        logger.debug("Requesting XC URL: \(url.absoluteString)")

        // Concurrently fetch user info and stream counts
        async let (data, response) = session.data(for: URLRequest(url: url))
        async let streamCounts = fetchStreamCounts(for: entry, serverURL: serverURL, username: username, password: password)

        // Await the results
        let (awaitedData, awaitedResponse) = try await (data, response)

        guard let httpResponse = awaitedResponse as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            let statusCode = (awaitedResponse as? HTTPURLResponse)?.statusCode ?? -1
            logger.error("Received non-200 response: \(statusCode)")
            throw APIError.serverError(statusCode: statusCode)
        }

        do {
            let apiResponse = try JSONDecoder().decode(XCAPIResponse.self, from: awaitedData)
            let counts = await streamCounts // Await the counts result
            return try mapXCResponseToAPIResult(response: apiResponse, streamCounts: counts, rawData: awaitedData)
        } catch {
            logger.error("XC JSON Decoding Error: \(error.localizedDescription)")
            if let responseString = String(data: awaitedData, encoding: .utf8) {
                 logger.error("Raw XC response: \(responseString)")
            }
            throw APIError.decodingError(error)
        }
    }

    /// Fetches the counts for live streams, movies, and series concurrently.
    private func fetchStreamCounts(for entry: IPTVEntry, serverURL: String, username: String, password: String) async -> (live: Int?, movies: Int?, series: Int?) {
        // A struct to decode the array of items. We only need the count, not the content.
        struct StreamItem: Codable {}

        async let liveCount = fetchCount(action: "get_live_streams", serverURL: serverURL, username: username, password: password)
        async let moviesCount = fetchCount(action: "get_vod_streams", serverURL: serverURL, username: username, password: password)
        async let seriesCount = fetchCount(action: "get_series", serverURL: serverURL, username: username, password: password)

        let counts = await (live: liveCount, movies: moviesCount, series: seriesCount)
        logger.info("Fetched stream counts for '\(entry.name, privacy: .public)': Live=\(counts.live ?? -1), Movies=\(counts.movies ?? -1), Series=\(counts.series ?? -1)")
        return counts
    }

    /// Generic helper to fetch an array from the API and return its count.
    private func fetchCount(action: String, serverURL: String, username: String, password: String) async -> Int? {
        struct StreamItem: Codable {}

        var components = URLComponents(string: serverURL)
        components?.path = "/player_api.php"
        components?.queryItems = [
            URLQueryItem(name: "username", value: username),
            URLQueryItem(name: "password", value: password),
            URLQueryItem(name: "action", value: action)
        ]

        guard let url = components?.url else {
            logger.error("Could not create URL for action '\(action)'")
            return nil
        }

        do {
            let (data, response) = try await session.data(for: URLRequest(url: url))
            guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
                logger.warning("Failed to fetch count for action '\(action)': HTTP \((response as? HTTPURLResponse)?.statusCode ?? -1)")
                return nil
            }
            let decodedArray = try JSONDecoder().decode([StreamItem].self, from: data)
            return decodedArray.count
        } catch {
            logger.error("Failed to fetch or decode count for action '\(action)': \(error.localizedDescription)")
            return nil
        }
    }

    private func mapXCResponseToAPIResult(response: XCAPIResponse,
                                          streamCounts: (live: Int?, movies: Int?, series: Int?),
                                          rawData: Data) throws -> APIResult {
        guard let userInfo = response.userInfo else {
            throw APIError.invalidResponse(reason: "Response did not contain a 'user_info' object.")
        }

        // Handle authentication failure
        if userInfo.auth != 1 {
            let message = userInfo.message ?? "Authentication failed. Check credentials."
            return APIResult(apiStatus: "Auth Failed", apiMessage: message, expiryDate: nil, isTrial: nil, activeConnections: nil, maxConnections: nil, liveStreamsCount: nil, moviesCount: nil, seriesCount: nil, rawUserInfoJSON: nil, rawServerInfoJSON: nil)
        }

        // Convert string-based date and numbers to their proper types
        var expiryDate: Date? = nil
        if let expDateString = userInfo.expDate, let timestamp = TimeInterval(expDateString) {
            expiryDate = Date(timeIntervalSince1970: timestamp)
        }

        let isTrial = userInfo.isTrial.flatMap { $0 == "1" }
        let maxConnections = userInfo.maxConnections.flatMap { Int($0) }

        // Serialize user_info and server_info for storage
        let encoder = JSONEncoder()
        encoder.outputFormatting = .prettyPrinted
        let userInfoJSON = try? String(data: encoder.encode(userInfo), encoding: .utf8)
        let serverInfoJSON = try? String(data: encoder.encode(response.serverInfo), encoding: .utf8)

        return APIResult(
            apiStatus: userInfo.status ?? "Active",
            apiMessage: userInfo.message ?? "Status successfully retrieved.",
            expiryDate: expiryDate,
            isTrial: isTrial,
            activeConnections: userInfo.activeCons,
            maxConnections: maxConnections,
            liveStreamsCount: streamCounts.live,
            moviesCount: streamCounts.movies,
            seriesCount: streamCounts.series,
            rawUserInfoJSON: userInfoJSON,
            rawServerInfoJSON: serverInfoJSON
        )
    }

    // MARK: - Stalker Portal API Logic

    private func checkStalkerStatus(for entry: IPTVEntry) async throws -> APIResult {
        guard let portalURL = entry.portalURL?.rstrip("/"), !portalURL.isEmpty,
              let macAddress = entry.macAddress, !macAddress.isEmpty else {
            throw APIError.invalidRequest(reason: "Portal URL or MAC Address missing for Stalker entry.")
        }

        // 1. Perform handshake to get token
        let token = try await _getStalkerToken(portalURL: portalURL, macAddress: macAddress)

        // 2. Use token to get account info
        let accountInfoURLString = "\(portalURL)/portal.php?type=account_info&action=get_main_info&JsHttpRequest=1-xml"
        guard let accountInfoURL = URL(string: accountInfoURLString) else {
            throw APIError.invalidRequest(reason: "Could not create Stalker account info URL.")
        }

        var request = URLRequest(url: accountInfoURL)
        request.httpMethod = "GET"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("XMLHttpRequest", forHTTPHeaderField: "X-Requested-With")

        logger.debug("Requesting Stalker Account Info URL: \(accountInfoURL.absoluteString)")

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? -1
            logger.error("Stalker account info received non-200 response: \(statusCode)")
            throw APIError.serverError(statusCode: statusCode)
        }

        // 3. Decode and map the response
        do {
            let apiResponse = try JSONDecoder().decode(StalkerAccountInfoResponse.self, from: data)
            return try _mapStalkerResponseToAPIResult(response: apiResponse, rawData: data)
        } catch {
            logger.error("Stalker JSON Decoding Error: \(error.localizedDescription)")
            if let responseString = String(data: data, encoding: .utf8) {
                 logger.error("Raw Stalker response: \(responseString)")
            }
            throw APIError.decodingError(error)
        }
    }

    private func _getStalkerToken(portalURL: String, macAddress: String) async throws -> String {
        let handshakeURLString = "\(portalURL)/portal.php?action=handshake&type=stb&token=&JsHttpRequest=1-xml"
        guard let handshakeURL = URL(string: handshakeURLString) else {
            throw APIError.invalidRequest(reason: "Could not create Stalker handshake URL.")
        }

        var request = URLRequest(url: handshakeURL)
        request.httpMethod = "GET"
        // Stalker portals are picky about headers.
        request.setValue("MAC \(macAddress)", forHTTPHeaderField: "Authorization")
        request.setValue("XMLHttpRequest", forHTTPHeaderField: "X-Requested-With")
        request.setValue("\(portalURL)/c/", forHTTPHeaderField: "Referer")

        logger.debug("Requesting Stalker Handshake URL: \(handshakeURL.absoluteString)")

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            let statusCode = (response as? HTTPURLResponse)?.statusCode ?? -1
            logger.error("Stalker handshake received non-200 response: \(statusCode)")
            throw APIError.handshakeFailed(reason: "Server returned status \(statusCode)")
        }

        do {
            let handshakeResponse = try JSONDecoder().decode(StalkerHandshakeResponse.self, from: data)
            let token = handshakeResponse.js.token
            logger.info("Stalker handshake successful. Token received.")
            return token
        } catch {
            logger.error("Stalker Handshake Decoding Error: \(error.localizedDescription)")
            if let responseString = String(data: data, encoding: .utf8) {
                 logger.error("Raw Stalker handshake response: \(responseString)")
            }
            throw APIError.handshakeFailed(reason: "Could not decode token from response.")
        }
    }

    private func _mapStalkerResponseToAPIResult(response: StalkerAccountInfoResponse, rawData: Data) throws -> APIResult {
        let js = response.js

        var apiStatus = "Unknown"
        if let status = js.status {
            switch status {
            case "1": apiStatus = "Active"
            case "2", "0": apiStatus = "Inactive/Disabled"
            default: apiStatus = "Status: \(status)"
            }
        }

        // Complex date parsing logic
        var expiryDate: Date?
        let flexibleDate = js.expDate ?? js.expireDate ?? js.phone

        if let dateValue = flexibleDate {
            switch dateValue {
            case .timestamp(let date):
                expiryDate = date
            case .string(let dateString):
                expiryDate = parseStalkerDateString(dateString)
            }
        }

        if let finalExpiry = expiryDate, finalExpiry < Date() {
            apiStatus = "Expired"
        }

        let encoder = JSONEncoder()
        encoder.outputFormatting = .prettyPrinted
        let userInfoJSON = try? String(data: encoder.encode(js), encoding: .utf8)

        return APIResult(
            apiStatus: apiStatus,
            apiMessage: "Status successfully retrieved.",
            expiryDate: expiryDate,
            isTrial: nil, // Stalker API doesn't typically provide this
            activeConnections: nil,
            maxConnections: nil,
            liveStreamsCount: nil,
            moviesCount: nil,
            seriesCount: nil,
            rawUserInfoJSON: userInfoJSON,
            rawServerInfoJSON: nil
        )
    }

    private func parseStalkerDateString(_ dateString: String) -> Date? {
        let formatters = [
            "MMMM d, yyyy, h:mm a", // "August 17, 2025, 12:00 am"
            "yyyy-MM-dd HH:mm:ss",  // "2025-08-17 00:00:00"
            "dd.MM.yyyy"            // "17.08.2025"
        ].map { format -> DateFormatter in
            let formatter = DateFormatter()
            formatter.dateFormat = format
            formatter.locale = Locale(identifier: "en_US_POSIX")
            return formatter
        }

        for formatter in formatters {
            if let date = formatter.date(from: dateString) {
                return date
            }
        }

        logger.warning("Could not parse Stalker date string: \(dateString)")
        return nil
    }
}

private extension String {
    func rstrip(_ characters: String) -> String {
        var s = self
        while s.hasSuffix(characters) {
            s = String(s.dropLast(characters.count))
        }
        return s
    }
}
