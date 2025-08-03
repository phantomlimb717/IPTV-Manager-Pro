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
}
