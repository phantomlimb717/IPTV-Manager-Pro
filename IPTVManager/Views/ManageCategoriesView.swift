import SwiftUI
import SwiftData

struct ManageCategoriesView: View {
    @Environment(\.modelContext) private var modelContext
    @Environment(\.dismiss) private var dismiss

    @Query(sort: \Category.name) private var categories: [Category]

    // State to manage alerts for add/rename
    @State private var isShowingAlert = false
    @State private var alertTextField = ""
    @State private var categoryToEdit: Category?

    var body: some View {
        NavigationStack {
            List {
                ForEach(categories) { category in
                    Text(category.name)
                        .contextMenu {
                            if category.name != "Uncategorized" {
                                Button("Rename", systemImage: "pencil") {
                                    categoryToEdit = category
                                    alertTextField = category.name
                                    isShowingAlert = true
                                }
                            }
                        }
                }
                .onDelete(perform: deleteCategory)
            }
            .navigationTitle("Manage Categories")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add") {
                        categoryToEdit = nil
                        alertTextField = ""
                        isShowingAlert = true
                    }
                }
            }
            .alert(categoryToEdit == nil ? "Add Category" : "Rename Category", isPresented: $isShowingAlert) {
                TextField("Category Name", text: $alertTextField)
                Button("Save", action: saveCategory)
                Button("Cancel", role: .cancel) { }
            } message: {
                Text("Please enter a name for the category.")
            }
        }
    }

    private func saveCategory() {
        let newName = alertTextField.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !newName.isEmpty else { return }

        // Prevent duplicate names
        if categories.contains(where: { $0.name.lowercased() == newName.lowercased() }) {
            // In a real app, show another alert for the error.
            print("Error: Category name already exists.")
            return
        }

        if let category = categoryToEdit {
            // Rename existing category
            category.name = newName
        } else {
            // Add new category
            let newCategory = Category(name: newName)
            modelContext.insert(newCategory)
        }
    }

    private func deleteCategory(at offsets: IndexSet) {
        for index in offsets {
            let categoryToDelete = categories[index]

            // Prevent deleting the "Uncategorized" category
            guard categoryToDelete.name != "Uncategorized" else { continue }

            // Find or create the "Uncategorized" category
            let uncategorized = getOrCreateUncategorizedCategory()

            // Reassign entries
            let entriesToReassign = categoryToDelete.entries ?? []
            for entry in entriesToReassign {
                entry.category = uncategorized
            }

            // Delete the now-empty category
            modelContext.delete(categoryToDelete)
        }
    }

    private func getOrCreateUncategorizedCategory() -> Category {
        if let uncategorized = categories.first(where: { $0.name == "Uncategorized" }) {
            return uncategorized
        } else {
            let newUncategorized = Category(name: "Uncategorized")
            modelContext.insert(newUncategorized)
            return newUncategorized
        }
    }
}

#Preview {
    let config = ModelConfiguration(isStoredInMemoryOnly: true)
    let container = try! ModelContainer(for: Category.self, configurations: config)

    container.mainContext.insert(Category(name: "Uncategorized"))
    container.mainContext.insert(Category(name: "News"))
    container.mainContext.insert(Category(name: "Sports"))

    return ManageCategoriesView()
        .modelContainer(container)
}
