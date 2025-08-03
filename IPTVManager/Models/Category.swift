import Foundation
import SwiftData

@Model
final class Category {
    @Attribute(.unique)
    var name: String

    #Predicate { $0.category?.name == self.name }
    var entries: [IPTVEntry]?

    init(name: String) {
        self.name = name
    }
}
