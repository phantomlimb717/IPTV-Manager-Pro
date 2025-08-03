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

    // State for import results alert
    @State private var isShowingImportAlert = false
    @State private var importResult: ImportService.ImportResult?

    // State for filtering and searching
    @State private var selectedCategory: Category?
    @State private var searchText = ""
    @Query private var categories: [Category]

    // The main query for all entries
    @Query(sort: \IPTVEntry.name) private var entries: [IPTVEntry]

    var body: some View {
        NavigationStack {
            List {
                ForEach(filteredEntries) { entry in
                    Button(action: {
                        self.entryToEdit = entry
                        self.isShowingEditSheet = true
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
                    Button(action: {
                        self.entryToEdit = nil
                        self.isShowingEditSheet = true
                    }) { Image(systemName: "plus") }
                }
                ToolbarItem(placement: .navigationBarLeading) {
                    Menu {
                        Picker("Filter by Category", selection: $selectedCategory) {
                            Text("All Categories").tag(nil as Category?)
                            ForEach(categories) { category in
                                Text(category.name).tag(category as Category?)
                            }
                        }
                        .pickerStyle(.inline)

                        Divider()

                        Button("Manage Categories") { isShowingCategorySheet = true }

                        Button("Import from File...") { isShowingImporter = true }

                    } label: {
                        Image(systemName: "folder")
                    }
                }
                ToolbarItemGroup(placement: .bottomBar) {
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
            .sheet(isPresented: $isShowingEditSheet) { EditSubscriptionView(entryToEdit: entryToEdit) }
            .sheet(isPresented: $isShowingCategorySheet) { ManageCategoriesView() }
            .fileImporter(isPresented: $isShowingImporter, allowedContentTypes: [.plainText]) { result in
                switch result {
                case .success(let url):
                    handleImport(from: url)
                case .failure(let error):
                    print("Error importing file: \(error.localizedDescription)")
                }
            }
            .alert("Import Complete", isPresented: $isShowingImportAlert, presenting: importResult) { result in
                Button("OK") {}
            } message: { result in
                Text("Successfully imported \(result.importedCount) entries.\nFailed to import \(result.failedCount) entries.")
            }
            .overlay {
                if filteredEntries.isEmpty && !entries.isEmpty {
                    ContentUnavailableView.search
                } else if entries.isEmpty {
                    ContentUnavailableView("No Subscriptions", systemImage: "list.bullet.rectangle.portrait", description: Text("Tap the + button to add your first subscription."))
                }
            }
        }
    }

    private var filteredEntries: [IPTVEntry] {
        var filtered = entries
        if let category = selectedCategory {
            filtered = filtered.filter { $0.category == category }
        }
        if !searchText.isEmpty {
            filtered = filtered.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
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
