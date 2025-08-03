// swift-tools-version: 5.9
import PackageDescription

// This manifest formally defines the project as a Swift Package.
// It specifies the project's name, target platforms, products, and dependencies.
let package = Package(
    name: "IPTVManager",
    platforms: [
        // This is the crucial line that tells Xcode our code requires iOS 17 or newer.
        .iOS(.v17)
    ],
    products: [
        // Defines the output of the package as an executable application.
        .executable(
            name: "IPTVManagerApp",
            targets: ["IPTVManagerApp"])
    ],
    targets: [
        // Defines the source code that builds the product.
        // The `path` tells the package manager to look inside the `IPTVManager`
        // folder for all the .swift files.
        .executableTarget(
            name: "IPTVManagerApp",
            path: "IPTVManager"
        )
    ]
)
