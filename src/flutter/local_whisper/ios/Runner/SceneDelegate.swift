import Flutter
import UIKit

class SceneDelegate: FlutterSceneDelegate {
  override func scene(
    _ scene: UIScene,
    willConnectTo session: UISceneSession,
    options connectionOptions: UIScene.ConnectionOptions
  ) {
    super.scene(scene, willConnectTo: session, options: connectionOptions)
    if let controller = window?.rootViewController as? FlutterViewController {
      LocalSpeechBridge.shared.register(with: controller.binaryMessenger)
      // AppDelegate.window is nil under the UIScene lifecycle, so the setup
      // channel registration there never runs. Register it from the scene,
      // which owns the window that actually hosts the Flutter controller.
      (UIApplication.shared.delegate as? AppDelegate)?
        .registerSetupBridge(with: controller.binaryMessenger)
    }
  }
}
