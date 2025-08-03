import SwiftUI
import UniformTypeIdentifiers

/// A simple document type that represents a plain text file.
/// This is used with the `.fileExporter` view modifier to allow users
/// to save text content to a file on their device.
struct TextFile: FileDocument {
    // Tells the system that this document represents plain text.
    static var readableContentTypes: [UTType] { [.plainText] }

    var text: String

    /// Initializes a new document with the provided text content.
    init(initialText: String = "") {
        self.text = initialText
    }

    /// Initializes a new document by reading data from a file.
    init(configuration: ReadConfiguration) throws {
        guard let data = configuration.file.regularFileContents,
              let string = String(data: data, encoding: .utf8)
        else {
            throw CocoaError(.fileReadCorruptFile)
        }
        text = string
    }

    /// Generates the data to be written to the file.
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        return FileWrapper(regularFileWithContents: text.data(using: .utf8)!)
    }
}
