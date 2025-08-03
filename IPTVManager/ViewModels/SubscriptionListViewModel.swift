import SwiftUI
import SwiftData

/// The ViewModel responsible for handling the business logic of the SubscriptionListView.
/// It connects the UI to the APIService and manages the state for API operations.
@MainActor
class SubscriptionListViewModel: ObservableObject {

    /// Tracks the loading state for each individual entry by its UUID.
    /// This allows the UI to show a loading indicator only for the row being checked.
    @Published var loadingStates: [UUID: Bool] = [:]

    private let apiService: APIServiceProtocol

    init(apiService: APIServiceProtocol = APIService()) {
        self.apiService = apiService
    }

    /// Checks the status for a single IPTV entry.
    /// - Parameters:
    ///   - entry: The `IPTVEntry` to check.
    ///   - context: The SwiftData `ModelContext` used for updating the entry.
    func checkStatus(for entry: IPTVEntry, in context: ModelContext) async {
        loadingStates[entry.id] = true

        defer {
            // Ensure the loading state is always reset, even if an error occurs.
            loadingStates[entry.id] = false
        }

        do {
            let result = try await apiService.checkStatus(for: entry)

            // Update the entry with the new data from the API result.
            // Because 'entry' is a SwiftData model, these changes are
            // automatically tracked by the context.
            entry.apiStatus = result.apiStatus
            entry.apiMessage = result.apiMessage
            entry.expiryDate = result.expiryDate
            entry.isTrial = result.isTrial
            entry.activeConnections = result.activeConnections
            entry.maxConnections = result.maxConnections
            entry.liveStreamsCount = result.liveStreamsCount
            entry.moviesCount = result.moviesCount
            entry.seriesCount = result.seriesCount
            entry.rawUserInfoJSON = result.rawUserInfoJSON
            entry.rawServerInfoJSON = result.rawServerInfoJSON
            entry.lastCheckedAt = .now

        } catch {
            // If an error occurs, update the entry's status to reflect the error.
            entry.apiStatus = "Error"
            if let apiError = error as? APIError {
                entry.apiMessage = apiError.errorDescription
            } else {
                entry.apiMessage = error.localizedDescription
            }
            entry.lastCheckedAt = .now
        }
    }

    /// Checks the status for an array of IPTV entries sequentially.
    func checkAll(entries: [IPTVEntry], in context: ModelContext) async {
        for entry in entries {
            // Don't check multiple at once to avoid overwhelming servers.
            await checkStatus(for: entry, in: context)
        }
    }

    /// Finds and deletes duplicate entries from the database.
    /// A duplicate is defined by having the same credentials (server/user/pass for XC, portal/mac for Stalker).
    /// The function keeps the entry that was most recently checked.
    /// - Returns: The number of entries that were deleted.
    func deleteDuplicates(entries: [IPTVEntry], context: ModelContext) -> Int {
        var xtreamMap: [XtreamKey: IPTVEntry] = [:]
        var stalkerMap: [StalkerKey: IPTVEntry] = [:]
        var duplicatesToDelete = Set<IPTVEntry>()

        for entry in entries {
            switch entry.accountType {
            case .xtreamCodes:
                guard let serverURL = entry.serverBaseURL, let username = entry.username, let password = entry.password else { continue }
                let key = XtreamKey(serverURL: serverURL, username: username, password: password)

                if let existingEntry = xtreamMap[key] {
                    // A duplicate is found. Decide which one to keep.
                    // Keep the one that was checked more recently.
                    if let existingDate = existingEntry.lastCheckedAt, let currentDate = entry.lastCheckedAt {
                        if currentDate > existingDate {
                            // The current entry is newer, so the existing one is the duplicate.
                            duplicatesToDelete.insert(existingEntry)
                            xtreamMap[key] = entry // The current entry is now the one to compare against.
                        } else {
                            // The existing entry is newer or same, so the current one is the duplicate.
                            duplicatesToDelete.insert(entry)
                        }
                    } else if entry.lastCheckedAt != nil {
                        // Only the current entry has been checked, so keep it.
                        duplicatesToDelete.insert(existingEntry)
                        xtreamMap[key] = entry
                    } else {
                        // The existing entry has been checked (or neither has), so keep it.
                        duplicatesToDelete.insert(entry)
                    }
                } else {
                    // This is the first time we see this key.
                    xtreamMap[key] = entry
                }

            case .stalker:
                guard let portalURL = entry.portalURL, let macAddress = entry.macAddress else { continue }
                let key = StalkerKey(portalURL: portalURL, macAddress: macAddress)

                if let existingEntry = stalkerMap[key] {
                    if let existingDate = existingEntry.lastCheckedAt, let currentDate = entry.lastCheckedAt {
                        if currentDate > existingDate {
                            duplicatesToDelete.insert(existingEntry)
                            stalkerMap[key] = entry
                        } else {
                            duplicatesToDelete.insert(entry)
                        }
                    } else if entry.lastCheckedAt != nil {
                        duplicatesToDelete.insert(existingEntry)
                        stalkerMap[key] = entry
                    } else {
                        duplicatesToDelete.insert(entry)
                    }
                } else {
                    stalkerMap[key] = entry
                }
            }
        }

        if !duplicatesToDelete.isEmpty {
            for duplicate in duplicatesToDelete {
                context.delete(duplicate)
            }
        }

        return duplicatesToDelete.count
    }
}

// MARK: - Private Key Structs for Hashing
private struct XtreamKey: Hashable {
    let serverURL: String
    let username: String
    let password: String
}

private struct StalkerKey: Hashable {
    let portalURL: String
    let macAddress: String
}
