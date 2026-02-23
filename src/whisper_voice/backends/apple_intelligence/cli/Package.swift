// swift-tools-version: 6.2
// SPDX-License-Identifier: MIT
// Copyright (c) 2025-2026 Soroush Yousefpour

import PackageDescription

let package = Package(
    name: "apple-ai-cli",
    platforms: [
        .macOS(.v26)
    ],
    targets: [
        .executableTarget(
            name: "apple-ai-cli",
            path: "Sources/apple-ai-cli"
        )
    ]
)
