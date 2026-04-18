import Foundation

// MARK: - App directory paths

// Paths must match the Python layout in src/whisper_voice/backup.py.
enum AppDirectories {
    static let whisper: String = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper")
    static let ipcSocket: String = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/ipc.sock")
    static let text: String = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/history")
    static let audio: String = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/audio_history")
    static let config: String = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/config.toml")
}
