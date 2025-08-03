import SwiftUI
import SwiftData

struct EditSubscriptionView: View {
    @Environment(\.modelContext) private var modelContext
    @Environment(\.dismiss) private var dismiss

    // The entry to edit, or nil if we are adding a new one.
    var entryToEdit: IPTVEntry?

    // Form state variables
    @State private var name: String = ""
    @State private var accountType: AccountType = .xtreamCodes
    @State private var category: Category?

    // XC fields
    @State private var serverURL: String = ""
    @State private var username: String = ""
    @State private var password: String = ""

    // Stalker fields
    @State private var portalURL: String = ""
    @State private var macAddress: String = ""

    // Category data
    @Query(sort: \Category.name) private var categories: [Category]

    var body: some View {
        NavigationStack {
            Form {
                Section("General") {
                    TextField("Name", text: $name)
                    Picker("Category", selection: $category) {
                        Text("Uncategorized").tag(nil as Category?)
                        ForEach(categories) { cat in
                            Text(cat.name).tag(cat as Category?)
                        }
                    }
                }

                Section("Account Details") {
                    Picker("Account Type", selection: $accountType) {
                        ForEach(AccountType.allCases, id: \.self) { type in
                            Text(type.rawValue).tag(type)
                        }
                    }
                    .pickerStyle(.segmented)

                    if accountType == .xtreamCodes {
                        TextField("Server URL (e.g., http://domain:port)", text: $serverURL)
                            .keyboardType(.URL)
                            .autocapitalization(.none)
                        TextField("Username", text: $username)
                            .autocapitalization(.none)
                        SecureField("Password", text: $password)
                    } else { // Stalker Portal
                        TextField("Portal URL (e.g., http://domain:port/c/)", text: $portalURL)
                            .keyboardType(.URL)
                            .autocapitalization(.none)
                        TextField("MAC Address (XX:XX:XX:XX:XX:XX)", text: $macAddress)
                            .autocapitalization(.allCharacters)
                    }
                }
            }
            .navigationTitle(isEditing ? "Edit Subscription" : "Add Subscription")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save", action: save)
                }
            }
            .onAppear(perform: loadInitialData)
        }
    }

    private var isEditing: Bool {
        entryToEdit != nil
    }

    private func loadInitialData() {
        guard let entry = entryToEdit else { return }

        name = entry.name
        accountType = entry.accountType
        category = entry.category

        serverURL = entry.serverBaseURL ?? ""
        username = entry.username ?? ""
        password = entry.password ?? ""

        portalURL = entry.portalURL ?? ""
        macAddress = entry.macAddress ?? ""
    }

    private func save() {
        // TODO: Add more robust validation
        guard !name.isEmpty else {
            // In a real app, show an alert to the user.
            print("Validation failed: Name is empty.")
            return
        }

        if isEditing {
            // Update existing entry
            guard let entry = entryToEdit else { return }
            entry.name = name
            entry.accountType = accountType
            entry.category = category

            if accountType == .xtreamCodes {
                entry.serverBaseURL = serverURL
                entry.username = username
                entry.password = password
                entry.portalURL = nil
                entry.macAddress = nil
            } else {
                entry.portalURL = portalURL
                entry.macAddress = macAddress
                entry.serverBaseURL = nil
                entry.username = nil
                entry.password = nil
            }
        } else {
            // Create new entry
            let newEntry = IPTVEntry(
                name: name,
                accountType: accountType,
                category: category,
                serverBaseURL: accountType == .xtreamCodes ? serverURL : nil,
                username: accountType == .xtreamCodes ? username : nil,
                password: accountType == .xtreamCodes ? password : nil,
                macAddress: accountType == .stalker ? macAddress : nil,
                portalURL: accountType == .stalker ? portalURL : nil
            )
            modelContext.insert(newEntry)
        }

        // The modelContext will be saved automatically by SwiftData.
        // We just need to dismiss the view.
        dismiss()
    }
}

// Add allCases to AccountType for the Picker
extension AccountType: CaseIterable {}

#Preview {
    let config = ModelConfiguration(isStoredInMemoryOnly: true)
    let container = try! ModelContainer(for: IPTVEntry.self, Category.self, configurations: config)

    return EditSubscriptionView()
        .modelContainer(container)
}
