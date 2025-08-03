import SwiftUI
import SwiftData

final class ImportService {

    enum ImportError: LocalizedError {
        case couldNotAccessFile
        case failedToReadFile(Error)

        var errorDescription: String? {
            switch self {
            case .couldNotAccessFile:
                return "Could not access the selected file. Please check permissions."
            case .failedToReadFile(let error):
                return "Failed to read the file content. Error: \(error.localizedDescription)"
            }
        }
    }

    struct ImportResult {
        let importedCount: Int
        let failedCount: Int
    }

    /// Imports a single entry from a full M3U `get.php` URL.
    /// - Returns: `true` if the import was successful, otherwise `false`.
    func importEntry(from urlString: String, context: ModelContext) -> Bool {
        // A single URL import is assumed to be for an Xtream Codes entry.
        guard urlString.lowercased().contains("get.php?") else {
            return false
        }
        return parseAndAddXCEntry(from: urlString, context: context)
    }

    func importEntries(from fileURL: URL, context: ModelContext) throws -> ImportResult {
        guard fileURL.startAccessingSecurityScopedResource() else {
            throw ImportError.couldNotAccessFile
        }
        defer { fileURL.stopAccessingSecurityScopedResource() }

        let fileContent: String
        do {
            fileContent = try String(contentsOf: fileURL, encoding: .utf8)
        } catch {
            throw ImportError.failedToReadFile(error)
        }

        let lines = fileContent.components(separatedBy: .newlines)

        var importedCount = 0
        var failedCount = 0
        var currentStalkerPortalURL: String?

        for (index, line) in lines.enumerated() {
            let trimmedLine = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmedLine.isEmpty || trimmedLine.starts(with: "#") {
                continue
            }

            // This logic directly mirrors the Python script's import functionality.
            if trimmedLine.contains("get.php?") {
                // Case 1: Full Xtream Codes URL
                if parseAndAddXCEntry(from: trimmedLine, context: context) {
                    importedCount += 1
                } else {
                    failedCount += 1
                }
                currentStalkerPortalURL = nil
            } else if trimmedLine.starts(with: "stalker_portal:") {
                // Case 2: Full Stalker Portal string
                if parseAndAddStalkerString(from: trimmedLine, context: context) {
                    importedCount += 1
                } else {
                    failedCount += 1
                }
                currentStalkerPortalURL = nil
            } else if trimmedLine.starts(with: "http://") || trimmedLine.starts(with: "https://") {
                // Case 3: A line that is just a URL (could be a Stalker Portal)
                currentStalkerPortalURL = trimmedLine
            } else if isPotentialMAC(trimmedLine) {
                // Case 4: A potential MAC address
                if let portalURL = currentStalkerPortalURL {
                    if addStalkerEntry(portalURL: portalURL, macAddress: trimmedLine, context: context) {
                        importedCount += 1
                    } else {
                        failedCount += 1
                    }
                } else {
                    // MAC address found without a preceding portal URL
                    failedCount += 1
                }
            } else {
                // Unrecognized line format
                failedCount += 1
            }
        }

        return ImportResult(importedCount: importedCount, failedCount: failedCount)
    }

    private func parseAndAddXCEntry(from urlString: String, context: ModelContext) -> Bool {
        guard let components = URLComponents(string: urlString),
              let queryItems = components.queryItems,
              let username = queryItems.first(where: { $0.name == "username" })?.value,
              let password = queryItems.first(where: { $0.name == "password" })?.value,
              let host = components.host else {
            return false
        }

        let scheme = components.scheme ?? "http"
        let port = components.port.map { ":\($0)" } ?? ""
        let serverURL = "\(scheme)://\(host)\(port)"
        let name = "Imported - \(host)"

        let newEntry = IPTVEntry(name: name, accountType: .xtreamCodes, serverBaseURL: serverURL, username: username, password: password)
        context.insert(newEntry)
        return true
    }

    private func parseAndAddStalkerString(from line: String, context: ModelContext) -> Bool {
        let parts = line.replacingOccurrences(of: "stalker_portal:", with: "").components(separatedBy: ",mac:")
        guard parts.count == 2 else { return false }

        return addStalkerEntry(portalURL: parts[0], macAddress: parts[1], context: context)
    }

    private func addStalkerEntry(portalURL: String, macAddress: String, context: ModelContext) -> Bool {
        guard let host = URL(string: portalURL)?.host else { return false }
        let name = "Imported - \(host)"

        let newEntry = IPTVEntry(name: name, accountType: .stalker, macAddress: macAddress, portalURL: portalURL)
        context.insert(newEntry)
        return true
    }

    private func isPotentialMAC(_ text: String) -> Bool {
        let pattern = #"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"#
        return text.range(of: pattern, options: .regularExpression) != nil
    }
}
