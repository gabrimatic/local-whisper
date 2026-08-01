import Flutter
import UIKit

final class LocalSetupBridge: NSObject {
  static let shared = LocalSetupBridge()

  private let appGroup = "group.info.gabrimatic.localWhisperFlutter"
  private var didRegister = false

  func register(with messenger: FlutterBinaryMessenger) {
    guard !didRegister else { return }
    didRegister = true
    let method = FlutterMethodChannel(name: "local_whisper/setup", binaryMessenger: messenger)
    method.setMethodCallHandler { [weak self] call, result in
      guard let self else {
        return result(FlutterError(code: "released", message: "Setup bridge released", details: nil))
      }
      switch call.method {
      case "openKeyboardSettings", "openAppSettings":
        guard let url = URL(string: UIApplication.openSettingsURLString) else {
          return result(false)
        }
        UIApplication.shared.open(url) { opened in
          result(opened)
        }
      case "keyboardStatus":
        result(self.keyboardStatusPayload())
      case "markKeyboardSeen":
        self.markKeyboardOpened()
        result(nil)
      case "syncKeyboardSettings":
        let args = call.arguments as? [String: Any]
        self.syncKeyboardSettings(
          haptics: args?["haptics"] as? Bool ?? true,
          quickInsert: args?["quickInsert"] as? Bool ?? true
        )
        result(nil)
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  private func syncKeyboardSettings(haptics: Bool, quickInsert: Bool) {
    guard let defaults = UserDefaults(suiteName: appGroup) else { return }
    defaults.set(haptics, forKey: "keyboard.haptics")
    defaults.set(quickInsert, forKey: "keyboard.quickInsert")
    defaults.synchronize()
  }

  private func markKeyboardOpened() {
    guard let defaults = UserDefaults(suiteName: appGroup) else { return }
    defaults.set(Date().timeIntervalSince1970, forKey: "keyboard.lastOpenedAt")
    defaults.synchronize()
  }

  private func keyboardStatusPayload() -> [String: Any] {
    guard let defaults = UserDefaults(suiteName: appGroup) else {
      return [
        "keyboardSeen": false,
        "message": "Keyboard status is unavailable because the app group could not be opened.",
      ]
    }
    let lastOpened = defaults.double(forKey: "keyboard.lastOpenedAt")
    let seen = lastOpened > 0
    return [
      "keyboardSeen": seen,
      "message": seen
        ? "Local Whisper Keyboard was opened and verified."
        : "Keyboard has not been verified yet. Add it in Settings, switch to it in the practice field, then tap Verify on the keyboard.",
    ]
  }
}
