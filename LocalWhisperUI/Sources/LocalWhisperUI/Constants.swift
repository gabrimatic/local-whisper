import Foundation

// MARK: - App directory paths

enum AppDirectories {
    static let whisper: String = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper")
    static let ipcSocket: String = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/ipc.sock")
    static let text: String = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/text")
    static let audio: String = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/audio")
    static let config: String = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/config.toml")
}
