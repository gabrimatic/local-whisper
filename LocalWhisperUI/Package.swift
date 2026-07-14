// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "LocalWhisperUI",
    platforms: [
        .macOS(.v26)
    ],
    products: [
        .executable(name: "LocalWhisperUI", targets: ["LocalWhisperUI"]),
        .library(name: "AppleSpeechCore", targets: ["AppleSpeechCore"]),
        .executable(name: "LocalWhisperSpeech", targets: ["LocalWhisperSpeech"]),
    ],
    targets: [
        .executableTarget(
            name: "LocalWhisperUI",
            path: "Sources/LocalWhisperUI"
        ),
        .target(
            name: "AppleSpeechCore",
            path: "Sources/AppleSpeechCore"
        ),
        .executableTarget(
            name: "LocalWhisperSpeech",
            dependencies: ["AppleSpeechCore"],
            path: "Sources/LocalWhisperSpeech"
        ),
        .testTarget(
            name: "AppleSpeechCoreTests",
            dependencies: ["AppleSpeechCore"],
            path: "Tests/AppleSpeechCoreTests"
        ),
    ]
)
