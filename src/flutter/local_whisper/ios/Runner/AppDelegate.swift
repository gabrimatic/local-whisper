import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  // Bridges are registered from SceneDelegate.scene(_:willConnectTo:), where
  // window?.rootViewController is guaranteed to already be the FlutterViewController.
  // This app declares UIApplicationSceneManifest, so window is scene-owned and is
  // NOT reliably available here in didFinishLaunchingWithOptions: a prior polling-retry
  // registration attempt in this method never resolved and left local_whisper/setup
  // (openKeyboardSettings, openAppSettings, keyboardStatus, markKeyboardSeen,
  // syncKeyboardSettings) permanently unregistered, surfacing as MissingPluginException.

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
  }
}
