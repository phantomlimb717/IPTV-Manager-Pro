import Foundation

// MARK: - Stalker Handshake Response
/// Represents the JSON structure for the initial Stalker Portal handshake request.
/// Its sole purpose is to extract the temporary authorization token.
struct StalkerHandshakeResponse: Codable {
    let js: HandshakeJS

    struct HandshakeJS: Codable {
        let token: String
    }
}

// MARK: - Stalker Account Info Response
/// Represents the JSON structure for the main account info request.
struct StalkerAccountInfoResponse: Codable {
    let js: AccountInfoJS

    struct AccountInfoJS: Codable {
        let status: String? // e.g., "1" for active, "2" for off
        let expDate: StalkerFlexibleDate?
        let expireDate: StalkerFlexibleDate? // Some portals use this key instead
        let phone: StalkerFlexibleDate? // Some portals unconventionally put the expiry here

        // Other potential fields can be added here if needed.

        enum CodingKeys: String, CodingKey {
            case status
            case expDate = "exp_date"
            case expireDate = "expire_date"
            case phone
        }
    }
}

// MARK: - Flexible Date Type
/// A custom Codable type to handle dates that can be a String or a numeric Timestamp.
/// Stalker Portal APIs are notoriously inconsistent with their date formats.
enum StalkerFlexibleDate: Codable {
    case timestamp(Date)
    case string(String)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        // Try to decode as a numeric timestamp first.
        if let intValue = try? container.decode(Int.self) {
            self = .timestamp(Date(timeIntervalSince1970: TimeInterval(intValue)))
            return
        }
        if let doubleValue = try? container.decode(Double.self) {
            self = .timestamp(Date(timeIntervalSince1970: doubleValue))
            return
        }
        // If numeric decoding fails, decode as a string.
        if let stringValue = try? container.decode(String.self) {
            // Further parsing of the string value (e.g., "YYYY-MM-DD")
            // will be handled in the service layer.
            self = .string(stringValue)
            return
        }
        throw DecodingError.typeMismatch(StalkerFlexibleDate.self, DecodingError.Context(codingPath: decoder.codingPath, debugDescription: "Expected a String, Int, or Double for the date field."))
    }

    func encode(to encoder: Encoder) throws {
        // Encoding is not needed as we only decode this response.
        var container = encoder.singleValueContainer()
        switch self {
        case .timestamp(let date):
            try container.encode(date.timeIntervalSince1970)
        case .string(let string):
            try container.encode(string)
        }
    }
}
