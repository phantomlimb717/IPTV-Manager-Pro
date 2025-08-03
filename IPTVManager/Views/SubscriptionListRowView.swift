import SwiftUI
import SwiftData

struct SubscriptionListRowView: View {
    let entry: IPTVEntry
    @ObservedObject var viewModel: SubscriptionListViewModel

    var body: some View {
        HStack(spacing: 15) {
            // Show a spinner if this specific entry is loading, otherwise show the status indicator.
            if viewModel.loadingStates[entry.id] == true {
                ProgressView()
                    .frame(width: 10, height: 10)
            } else {
                StatusIndicator(status: entry.apiStatus)
            }

            VStack(alignment: .leading) {
                Text(entry.name)
                    .font(.headline)

                if let expiryDate = entry.expiryDate {
                    Text("Expires: \(expiryDate, formatter: Self.dateFormatter)")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                } else {
                    Text("Expiry: Not available")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
            }

            Spacer()

            if let status = entry.apiStatus, !status.isEmpty {
                Text(status)
                    .font(.caption.bold())
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(statusColor.opacity(0.2))
                    .foregroundColor(statusColor)
                    .cornerRadius(8)
                    .lineLimit(1)
            }
        }
        .padding(.vertical, 4)
    }

    private var statusColor: Color {
        guard let status = entry.apiStatus?.lowercased() else { return .gray }

        if status.contains("active") {
            return .green
        } else if status.contains("expired") {
            return .orange
        } else if status.contains("banned") || status.contains("disabled") || status.contains("fail") {
            return .red
        } else {
            return .gray
        }
    }

    private static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .none
        return formatter
    }()
}

/// A simple view that displays a colored circle representing a status.
private struct StatusIndicator: View {
    let status: String?

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 10, height: 10)
    }

    private var color: Color {
        guard let status = status?.lowercased() else { return .gray }

        if status.contains("active") {
            return .green
        } else if status.contains("expired") {
            return .orange
        } else if status.contains("banned") || status.contains("disabled") || status.contains("fail") {
            return .red
        } else {
            return .gray
        }
    }
}
