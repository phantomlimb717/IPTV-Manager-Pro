import SwiftUI
import SwiftData

struct BulkEditCategoryView: View {
    @Environment(\.modelContext) private var modelContext
    @Environment(\.dismiss) private var dismiss

    // The IDs of the entries to be updated.
    let selectedIDs: Set<UUID>

    // Query for all entries to find the ones to update.
    @Query private var allEntries: [IPTVEntry]

    // Query for categories to populate the picker.
    @Query(sort: \Category.name) private var categories: [Category]

    // State for the selected category in the picker.
    @State private var newCategory: Category?

    var body: some View {
        NavigationStack {
            Form {
                Section(header: Text("Assign to Category")) {
                    Picker("Select New Category", selection: $newCategory) {
                        Text("Uncategorized").tag(nil as Category?)
                        ForEach(categories) { category in
                            Text(category.name).tag(category as Category?)
                        }
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()
                }
            }
            .navigationTitle("Change Category")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save", action: updateCategories)
                }
            }
        }
    }

    private func updateCategories() {
        // Filter the entries that are part of the selection.
        let entriesToUpdate = allEntries.filter { selectedIDs.contains($0.id) }

        guard !entriesToUpdate.isEmpty else {
            // This shouldn't happen if the button is enabled correctly, but as a safeguard.
            dismiss()
            return
        }

        for entry in entriesToUpdate {
            entry.category = newCategory
        }

        // SwiftData will automatically save the context.
        dismiss()
    }
}
