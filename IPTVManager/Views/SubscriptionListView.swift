import SwiftUI
import SwiftData

struct SubscriptionListView: View {
    @Environment(\.modelContext) private var modelContext

    @StateObject private var viewModel = SubscriptionListViewModel()

    // State for presentation
    @State private var isShowingEditSheet = false
    @State private var entryToEdit: IPTVEntry?
    @State private var isShowingCategorySheet = false
    @State private var isShowingImporter = false
    @State private var isShowingBulkEditSheet = false

    // State for multi-selection
    @State private var editMode: EditMode = .inactive
    @State private var selection = Set<IPTVEntry.ID>()

    // State for import results alert
    @State private var isShowingImportAlert = false
    @State private var importResult: ImportService.ImportResult?

    // State for duplicate deletion alert
    @State private var isShowingDuplicatesAlert = false
    @State private var duplicatesDeletedCount = 0

    // State for URL import
    @State private var isShowingURLImportAlert = false
    @State private var importURLString = ""
    @State private var urlImportResult: (success: Bool, message: String)?
    @State private var isShowingURLImportResultAlert = false

    // State for bulk export
    @State private var isShowingExporter = false
    @State private var documentToExport: TextFile?

    // State for filtering and searching
    @State private var selectedCategory: Category?
    @State private var searchText = ""
    @State private var excludeNAs = false
    @Query private var categories: [Category]

    // The main query for all entries
    @Query(sort: \IPTVEntry.name) private var entries: [IPTVEntry]

    var body: some View {
        NavigationStack {
            List(selection: $selection) {
                ForEach(filteredEntries) { entry in
                    Button(action: {
                        // Inactive mode: show edit sheet. Active mode: toggle selection.
                        if !editMode.isEditing {
                            self.entryToEdit = entry
                            self.isShowingEditSheet = true
                        }
                    }) {
                        SubscriptionListRowView(entry: entry, viewModel: viewModel)
                    }
                    .buttonStyle(PlainButtonStyle())
                    .foregroundColor(.primary)
                    .swipeActions(edge: .leading, allowsFullSwipe: true) {
                        Button {
                            Task {
                                await viewModel.checkStatus(for: entry, in: modelContext)
                            }
                        } label: {
                            Label("Check Status", systemImage: "arrow.clockwise.circle")
                        }
                        .tint(.accentColor)
                    }
                    .contextMenu {
                        ShareLink(item: entry.exportString) {
                            Label("Share Link", systemImage: "square.and.arrow.up")
                        }
                    }
                }
                .onDelete(perform: deleteEntries)
            }
            .navigationTitle("Subscriptions")
            .searchable(text: $searchText, prompt: "Search Subscriptions")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    // Standard "Add" button, hidden when editing
                    if !editMode.isEditing {
                        Button(action: {
                            self.entryToEdit = nil
                            self.isShowingEditSheet = true
                        }) { Image(systemName: "plus") }
                    }
                }
                ToolbarItem(placement: .navigationBarLeading) {
                    // Standard Edit/Done button
                    EditButton()
                }
                ToolbarItem(placement: .primaryAction) {
                    // Menu is only shown when not in edit mode
                    if !editMode.isEditing {
                        Menu {
                            Picker("Filter by Category", selection: $selectedCategory) {
                                Text("All Categories").tag(nil as Category?)
                                ForEach(categories) { category in
                                    Text(category.name).tag(category as Category?)
                                }
                            }
                            .pickerStyle(.inline)

                            Toggle(isOn: $excludeNAs) {
                                Text("Exclude N/A")
                            }

                            Divider()

                            Button("Manage Categories") { isShowingCategorySheet = true }

                            Button("Import from File...") { isShowingImporter = true }

                            Button("Import from URL...") { isShowingURLImportAlert = true }

                            Divider()

                            Button("Delete Duplicates", systemImage: "minus.square.on.square", action: findAndShowDuplicates)

                        } label: {
                            Image(systemName: "folder")
                        }
                    }
                }
                ToolbarItemGroup(placement: .bottomBar) {
                    if editMode.isEditing {
                        Button("Category...") { isShowingBulkEditSheet = true }
                            .disabled(selection.isEmpty)
                        Spacer()
                        Button("Export...") { exportSelected() }
                            .disabled(selection.isEmpty)
                        Spacer()
                        Text("\(selection.count) selected")
                            .font(.subheadline)
                        Spacer()
                        Button(role: .destructive, action: deleteSelected) { Image(systemName: "trash") }
                            .disabled(selection.isEmpty)
                    } else {
                        Spacer()
                        Button(action: {
                            Task {
                                await viewModel.checkAll(entries: filteredEntries, in: modelContext)
                            }
                        }) {
                            Label("Check All Visible", systemImage: "arrow.clockwise")
                        }
                        .disabled(viewModel.loadingStates.values.contains(true) || filteredEntries.isEmpty)
                        Spacer()
                    }
                }
            }
            .environment(\.editMode, $editMode)
            .sheet(isPresented: $isShowingEditSheet) { EditSubscriptionView(entryToEdit: entryToEdit) }
            .sheet(isPresented: $isShowingCategorySheet) { ManageCategoriesView() }
            .sheet(isPresented: $isShowingBulkEditSheet) {
                BulkEditCategoryView(selectedIDs: selection)
            }
            .fileImporter(isPresented: $isShowingImporter, allowedContentTypes: [.plainText]) { result in
                switch result {
                case .success(let url):
                    handleImport(from: url)
                case .failure(let error):
                    print("Error importing file: \(error.localizedDescription)")
                }
            }
            .fileExporter(isPresented: $isShowingExporter, document: documentToExport, contentType: .plainText, defaultFilename: "IPTVManager_Export.txt") { result in
                switch result {
                case .success(let url):
                    print("Exported successfully to \(url)")
                case .failure(let error):
                    print("Export failed: \(error.localizedDescription)")
                }
            }
            .alert("Import Complete", isPresented: $isShowingImportAlert, presenting: importResult) { result in
                Button("OK") {}
            } message: { result in
                Text("Successfully imported \(result.importedCount) entries.\nFailed to import \(result.failedCount) entries.")
            }
            .alert("Duplicates Deleted", isPresented: $isShowingDuplicatesAlert) {
                Button("OK") {}
            } message: {
                Text("Found and deleted \(duplicatesDeletedCount) duplicate entries.")
            }
            .alert("Import from URL", isPresented: $isShowingURLImportAlert) {
                TextField("M3U Get Link URL", text: $importURLString)
                    .keyboardType(.URL)
                    .autocapitalization(.none)
                Button("Import", action: handleURLImport)
                Button("Cancel", role: .cancel) {
                    importURLString = ""
                }
            } message: {
                Text("Please paste the full M3U Get Link URL.")
            }
            .alert(isPresented: $isShowingURLImportResultAlert, content: {
                let result = urlImportResult ?? (success: false, message: "")
                return Alert(
                    title: Text(result.success ? "Success" : "Error"),
                    message: Text(result.message),
                    dismissButton: .default(Text("OK"))
                )
            })
            .overlay {
                if filteredEntries.isEmpty && !entries.isEmpty {
                    ContentUnavailableView.search
                } else if entries.isEmpty {
                    ContentUnavailableView("No Subscriptions", systemImage: "list.bullet.rectangle.portrait", description: Text("Tap the + button to add your first subscription."))
                }
            }
        }
    }

    private func deleteSelected() {
        withAnimation {
            let entriesToDelete = entries.filter { selection.contains($0.id) }
            for entry in entriesToDelete {
                modelContext.delete(entry)
            }
            // Clear selection and exit edit mode after deletion
            selection.removeAll()
            editMode = .inactive
        }
    }

    private var filteredEntries: [IPTVEntry] {
        var filtered = entries

        // Apply category filter
        if let category = selectedCategory {
            filtered = filtered.filter { $0.category == category }
        }

        // Apply search text filter
        if !searchText.isEmpty {
            filtered = filtered.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
        }

        // Apply "Exclude N/A" filter
        if excludeNAs {
            filtered = filtered.filter { entry in
                guard let status = entry.apiStatus?.lowercased() else {
                    return false // Exclude entries that have never been checked
                }
                // Keep entries with a definitive status
                let definitiveStati = ["active", "expired", "banned", "disabled", "fail"]
                return definitiveStati.contains { status.contains($0) }
            }
        }

        return filtered
    }

    private func deleteEntries(offsets: IndexSet) {
        withAnimation {
            let entriesToDelete = offsets.map { filteredEntries[$0] }
            for entry in entriesToDelete {
                modelContext.delete(entry)
            }
        }
    }

    private func findAndShowDuplicates() {
        let count = viewModel.deleteDuplicates(entries: entries, context: modelContext)
        self.duplicatesDeletedCount = count
        self.isShowingDuplicatesAlert = true
    }

    private func exportSelected() {
        let selectedEntries = entries.filter { selection.contains($0.id) }
        guard !selectedEntries.isEmpty else { return }

        let exportContent = selectedEntries
            .map { $0.exportString }
            .joined(separator: "\n")

        self.documentToExport = TextFile(initialText: exportContent)
        self.isShowingExporter = true
    }

    private func handleImport(from url: URL) {
        let importService = ImportService()
        Task {
            do {
                let result = try importService.importEntries(from: url, context: modelContext)
                self.importResult = result
                self.isShowingImportAlert = true
            } catch {
                print("Import failed with error: \(error.localizedDescription)")
            }
        }
    }

    private func handleURLImport() {
        let importService = ImportService()
        let success = importService.importEntry(from: importURLString, context: modelContext)

        if success {
            self.urlImportResult = (true, "The subscription was imported successfully.")
        } else {
            self.urlImportResult = (false, "The provided URL was invalid or could not be processed.")
        }

        self.importURLString = ""
        self.isShowingURLImportResultAlert = true
    }
}

#Preview {
    let config = ModelConfiguration(isStoredInMemoryOnly: true)
    let container = try! ModelContainer(for: IPTVEntry.self, Category.self, configurations: config)

    let cat1 = Category(name: "News")
    container.mainContext.insert(cat1)

    let entry1 = IPTVEntry(name: "News Provider", accountType: .xtreamCodes, category: cat1)
    container.mainContext.insert(entry1)

    return SubscriptionListView()
        .modelContainer(container)
}
