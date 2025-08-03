import Foundation

/// Represents the JSON structure returned by the Xtream Codes `player_api.php` endpoint.
/// Using Codable, Swift can automatically decode the JSON into this structure.
struct XCAPIResponse: Codable {
    let userInfo: UserInfo?
    let serverInfo: ServerInfo?

    enum CodingKeys: String, CodingKey {
        case userInfo = "user_info"
        case serverInfo = "server_info"
    }

    // MARK: - UserInfo
    struct UserInfo: Codable {
        let auth: Int? // Typically 1 for success, 0 for failure.
        let status: String?
        let message: String?
        let expDate: String? // Comes as a stringified UNIX timestamp.
        let isTrial: String? // Comes as a string "0" or "1".
        let activeCons: Int?
        let maxConnections: String? // Comes as a string, e.g., "2".

        enum CodingKeys: String, CodingKey {
            case auth, status, message
            case expDate = "exp_date"
            case isTrial = "is_trial"
            case activeCons = "active_cons"
            case maxConnections = "max_connections"
        }
    }

    // MARK: - ServerInfo
    struct ServerInfo: Codable {
        // Capturing a few key fields for potential future use or debugging.
        let url: String?
        let port: String?
        let httpsPort: String?
        let serverProtocol: String?
        let timezone: String?

        enum CodingKeys: String, CodingKey {
            case url, port, timezone
            case httpsPort = "https_port"
            case serverProtocol = "protocol"
        }
    }
}
