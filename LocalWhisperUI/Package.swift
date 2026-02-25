// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "LocalWhisperUI",
    platforms: [
        .macOS(.v26)
    ],
    targets: [
        .executableTarget(
            name: "LocalWhisperUI",
            path: "Sources/LocalWhisperUI"
        )
    ]
)
