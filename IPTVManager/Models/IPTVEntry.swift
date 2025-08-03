import Foundation
import SwiftData

@Model
final class IPTVEntry {
    @Attribute(.unique)
    var id: UUID
    var name: String
    var createdAt: Date

    // Account Type
    var accountType: AccountType = .xtreamCodes

    // Xtream Codes Credentials
    var serverBaseURL: String?
    var username: String?
    var password: String?

    // Stalker Portal Credentials
    var macAddress: String?
    var portalURL: String?

    // Status Information
    var lastCheckedAt: Date?
    var apiStatus: String?
    var apiMessage: String?
    var expiryDate: Date?
    var isTrial: Bool?
    var activeConnections: Int?
    var maxConnections: Int?

    // Content Counts
    var liveStreamsCount: Int?
    var moviesCount: Int?
    var seriesCount: Int?

    // Raw API Responses (for debugging)
    @Attribute(originalName: "rawUserInfo")
    var rawUserInfoJSON: String?
    @Attribute(originalName: "rawServerInfo")
    var rawServerInfoJSON: String?

    // Relationship
    var category: Category?

    init(name: String,
         accountType: AccountType,
         category: Category? = nil,
         serverBaseURL: String? = nil,
         username: String? = nil,
         password: String? = nil,
         macAddress: String? = nil,
         portalURL: String? = nil) {
        self.id = UUID()
        self.name = name
        self.createdAt = .now
        self.accountType = accountType
        self.category = category
        self.serverBaseURL = serverBaseURL
        self.username = username
        self.password = password
        self.macAddress = macAddress
        self.portalURL = portalURL
    }

    /// A computed property that generates the exportable string for the entry.
    var exportString: String {
        switch accountType {
        case .xtreamCodes:
            guard let serverURL = serverBaseURL, !serverURL.isEmpty,
                  let username = username, !username.isEmpty,
                  let password = password else {
                return "Incomplete Xtream Codes Entry"
            }
            return "\(serverURL)/get.php?username=\(username)&password=\(password)&type=m3u_plus&output=ts"
        case .stalker:
            guard let portalURL = portalURL, !portalURL.isEmpty,
                  let macAddress = macAddress, !macAddress.isEmpty else {
                return "Incomplete Stalker Portal Entry"
            }
            return "stalker_portal:\(portalURL),mac:\(macAddress)"
        }
    }
}

enum AccountType: String, Codable {
    case xtreamCodes = "Xtream Codes"
    case stalker = "Stalker Portal"
}
