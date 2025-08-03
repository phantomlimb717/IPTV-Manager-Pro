import SwiftUI
import SwiftData

struct SubscriptionListRowView: View {
    let entry: IPTVEntry
    @ObservedObject var viewModel: SubscriptionListViewModel

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            // Loading indicator or status circle
            if viewModel.loadingStates[entry.id] == true {
                ProgressView()
                    .frame(width: 12, height: 12)
            } else {
                StatusIndicator(status: entry.apiStatus)
            }

            VStack(alignment: .leading, spacing: 6) {
                // Top Row: Name and Status Badge
                HStack {
                    Text(entry.name)
                        .font(.headline)
                        .lineLimit(1)
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

                // Middle Row: Expiry and Connection Info
                HStack(spacing: 12) {
                    if let expiryDate = entry.expiryDate {
                        Label {
                            Text(expiryDate, formatter: Self.dateFormatter)
                        } icon: {
                            Image(systemName: "calendar")
                        }
                    } else {
                        Label("N/A", systemImage: "calendar")
                    }

                    if let active = entry.activeConnections, let max = entry.maxConnections {
                        Label("\(active)/\(max)", systemImage: "network")
                    }
                }
                .font(.subheadline)
                .foregroundColor(.secondary)

                // Bottom Row: Content Counts
                if entry.liveStreamsCount != nil || entry.moviesCount != nil || entry.seriesCount != nil {
                    HStack(spacing: 12) {
                        if let live = entry.liveStreamsCount {
                            Label("\(live)", systemImage: "tv")
                        }
                        if let movies = entry.moviesCount {
                            Label("\(movies)", systemImage: "film")
                        }
                        if let series = entry.seriesCount {
                            Label("\(series)", systemImage: "play.tv")
                        }
                    }
                    .font(.caption)
                    .foregroundColor(.secondary)
                }
            }
        }
        .padding(.vertical, 6)
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
