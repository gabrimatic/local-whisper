import Foundation

// MARK: - App directory paths

// Fixed paths must match the Python layout in src/whisper_voice/backup.py.
// History and audio live under the user-configurable backup directory, so
// panels resolve them from the live config instead of hardcoding ~/.whisper.
enum AppDirectories {
    static let whisper: String = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper")
    /// The IPC socket and config never move with backup.directory.
    static let ipcSocket: String = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/ipc.sock")
    static let config: String = (NSHomeDirectory() as NSString).appendingPathComponent(".whisper/config.toml")

    static func backupRoot(_ config: AppConfig) -> String {
        let raw = config.backup.directory.isEmpty ? "~/.whisper" : config.backup.directory
        return (raw as NSString).expandingTildeInPath
    }

    static func historyDir(_ config: AppConfig) -> String {
        (backupRoot(config) as NSString).appendingPathComponent("history")
    }

    static func audioDir(_ config: AppConfig) -> String {
        (backupRoot(config) as NSString).appendingPathComponent("audio_history")
    }
}
