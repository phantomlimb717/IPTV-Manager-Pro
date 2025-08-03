import Foundation

/// A standardized structure to hold the result of an API status check.
/// This normalizes the data received from different API types (XC, Stalker)
/// into a single format that the app can easily use.
struct APIResult {
    // Core status
    let apiStatus: String
    let apiMessage: String

    // Account details
    let expiryDate: Date?
    let isTrial: Bool?

    // Connection details
    let activeConnections: Int?
    let maxConnections: Int?

    // Content counts
    let liveStreamsCount: Int?
    let moviesCount: Int?
    let seriesCount: Int?

    // Raw data for debugging/inspection
    let rawUserInfoJSON: String?
    let rawServerInfoJSON: String?
}
