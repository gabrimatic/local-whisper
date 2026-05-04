import AVFoundation
import CoreML
import Flutter
import UIKit
import WhisperKit

final class LocalSpeechBridge: NSObject, FlutterStreamHandler {
  static let shared = LocalSpeechBridge()

  private var eventSink: FlutterEventSink?
  private let audioEngine = AVAudioEngine()
  private var outputFile: AVAudioFile?
  private var outputURL: URL?
  private var startDate: Date?
  private var isRecording = false
  private var didRegister = false
  private var selectedModel = "whisperkit_large_v3_turbo"
  private var selectedModelPath: String?
  private var selectedLocale = "en-US"
  private var loadedModel: String?
  private var loadedModelPath: String?
  private var whisperKit: WhisperKit?

  func register(with messenger: FlutterBinaryMessenger) {
    guard !didRegister else { return }
    didRegister = true
    let method = FlutterMethodChannel(name: "local_whisper/speech", binaryMessenger: messenger)
    method.setMethodCallHandler { [weak self] call, result in
      guard let self else {
        return result(FlutterError(code: "released", message: "Speech bridge released", details: nil))
      }
      Task { @MainActor in
        self.handle(call: call, result: result)
      }
    }

    let levels = FlutterEventChannel(name: "local_whisper/levels", binaryMessenger: messenger)
    levels.setStreamHandler(self)
  }

  func onListen(withArguments arguments: Any?, eventSink events: @escaping FlutterEventSink) -> FlutterError? {
    eventSink = events
    return nil
  }

  func onCancel(withArguments arguments: Any?) -> FlutterError? {
    eventSink = nil
    return nil
  }

  @MainActor
  private func handle(call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "status":
      let args = call.arguments as? [String: Any]
      result(statusPayload(locale: args?["locale"] as? String ?? selectedLocale))
    case "requestPermissions":
      requestPermissions(result: result)
    case "start":
      let args = call.arguments as? [String: Any]
      let model = args?["model"] as? String ?? selectedModel
      let modelPath = args?["modelPath"] as? String
      let locale = args?["locale"] as? String ?? selectedLocale
      start(model: model, modelPath: modelPath, locale: locale, result: result)
    case "stop":
      stop(result: result)
    case "cancel":
      cancel()
      result(nil)
    case "debugTranscribeFile":
      let args = call.arguments as? [String: Any]
      let audioPath = args?["audioPath"] as? String ?? ""
      let model = args?["model"] as? String ?? selectedModel
      let modelPath = args?["modelPath"] as? String
      let locale = args?["locale"] as? String ?? selectedLocale
      debugTranscribeFile(audioPath: audioPath, model: model, modelPath: modelPath, locale: locale, result: result)
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private func statusPayload(locale: String) -> [String: Any] {
    let micGranted = microphoneGranted()
    return [
      "permissionsGranted": micGranted,
      "onDeviceAvailable": true,
      "recognitionAvailable": true,
      "localeId": locale,
      "message": micGranted
        ? "Local Whisper is set to \(selectedModel)."
        : "Microphone permission is not granted yet.",
    ]
  }

  private func microphoneGranted() -> Bool {
    if #available(iOS 17.0, *) {
      return AVAudioApplication.shared.recordPermission == .granted
    }
    return AVAudioSession.sharedInstance().recordPermission == .granted
  }

  private func requestPermissions(result: @escaping FlutterResult) {
    let completion: (Bool) -> Void = { granted in
      DispatchQueue.main.async { result(granted) }
    }
    if #available(iOS 17.0, *) {
      AVAudioApplication.requestRecordPermission(completionHandler: completion)
    } else {
      AVAudioSession.sharedInstance().requestRecordPermission(completion)
    }
  }

  @MainActor
  private func start(model: String, modelPath: String?, locale: String, result: @escaping FlutterResult) {
    guard !isRecording else {
      result(FlutterError(code: "busy", message: "A recording is already active.", details: nil))
      return
    }
    guard microphoneGranted() else {
      result(FlutterError(code: "permissionDenied", message: "Microphone permission is not granted.", details: nil))
      return
    }

    cancel()
    selectedModel = model
    selectedModelPath = modelPath
    selectedLocale = locale
    startDate = Date()

    do {
      let session = AVAudioSession.sharedInstance()
      try session.setCategory(.record, mode: .measurement, options: [.duckOthers])
      try session.setActive(true, options: .notifyOthersOnDeactivation)

      let input = audioEngine.inputNode
      let format = input.outputFormat(forBus: 0)
      let url = FileManager.default.temporaryDirectory
        .appendingPathComponent("local-whisper-\(UUID().uuidString).wav")
      let file = try AVAudioFile(forWriting: url, settings: format.settings)

      input.removeTap(onBus: 0)
      input.installTap(onBus: 0, bufferSize: 2048, format: format) { [weak self] buffer, _ in
        do {
          try file.write(from: buffer)
        } catch {
          // Stop will surface empty/failed audio; keep the tap realtime-safe.
        }
        self?.emitLevel(buffer: buffer)
      }

      outputFile = file
      outputURL = url
      audioEngine.prepare()
      try audioEngine.start()
      isRecording = true
      result(nil)
    } catch {
      cancel()
      result(FlutterError(code: "audioStartFailed", message: error.localizedDescription, details: nil))
    }
  }

  @MainActor
  private func stop(result: @escaping FlutterResult) {
    guard isRecording else {
      result(FlutterError(code: "notRecording", message: "No active recording.", details: nil))
      return
    }

    let duration = Date().timeIntervalSince(startDate ?? Date())
    audioEngine.inputNode.removeTap(onBus: 0)
    audioEngine.stop()
    isRecording = false
    outputFile = nil
    try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    eventSink?(0.0)

    guard let audioURL = outputURL else {
      result(FlutterError(code: "audioMissing", message: "Recording file was not created.", details: nil))
      return
    }

    let model = selectedModel
    let modelPath = selectedModelPath
    let locale = selectedLocale
    Task {
      do {
        let text = try await transcribe(audioURL: audioURL, model: model, modelPath: modelPath)
        try? FileManager.default.removeItem(at: audioURL)
        await MainActor.run {
          result([
            "transcript": text,
            "rawTranscript": text,
            "duration": duration,
            "localeId": locale,
            "onDevice": true,
          ])
        }
      } catch {
        try? FileManager.default.removeItem(at: audioURL)
        await MainActor.run {
          result(FlutterError(code: "transcriptionFailed", message: error.localizedDescription, details: nil))
        }
      }
    }
  }

  @MainActor
  private func cancel() {
    if audioEngine.isRunning {
      audioEngine.inputNode.removeTap(onBus: 0)
      audioEngine.stop()
    }
    outputFile = nil
    if let outputURL {
      try? FileManager.default.removeItem(at: outputURL)
    }
    outputURL = nil
    isRecording = false
    startDate = nil
    try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    eventSink?(0.0)
  }

  private func debugTranscribeFile(
    audioPath: String,
    model: String,
    modelPath: String?,
    locale: String,
    result: @escaping FlutterResult
  ) {
    guard FileManager.default.fileExists(atPath: audioPath) else {
      result(FlutterError(code: "audioMissing", message: "Debug audio file is missing: \(audioPath)", details: nil))
      return
    }
    Task {
      do {
        let text = try await transcribe(audioURL: URL(fileURLWithPath: audioPath), model: model, modelPath: modelPath)
        await MainActor.run {
          result([
            "transcript": text,
            "rawTranscript": text,
            "duration": 0,
            "localeId": locale,
            "onDevice": true,
          ])
        }
      } catch {
        await MainActor.run {
          result(FlutterError(code: "debugTranscriptionFailed", message: error.localizedDescription, details: nil))
        }
      }
    }
  }

  private func transcribe(audioURL: URL, model: String, modelPath: String?) async throws -> String {
    let whisperKitModel = try whisperKitModelName(for: model)
    guard let modelPath, !modelPath.isEmpty else {
      throw NSError(
        domain: "LocalWhisper",
        code: 4,
        userInfo: [NSLocalizedDescriptionKey: "\(whisperKitModel) is not installed locally yet."]
      )
    }
    guard FileManager.default.fileExists(atPath: modelPath) else {
      throw NSError(
        domain: "LocalWhisper",
        code: 5,
        userInfo: [NSLocalizedDescriptionKey: "Installed model folder is missing: \(modelPath)."]
      )
    }
    let preparedModelPath = try prepareCoreMLModelsIfNeeded(modelPath: modelPath, model: whisperKitModel)
    if whisperKit == nil || loadedModel != whisperKitModel || loadedModelPath != preparedModelPath {
      let config = WhisperKitConfig(model: whisperKitModel, modelFolder: preparedModelPath, download: false)
      whisperKit = try await WhisperKit(config)
      loadedModel = whisperKitModel
      loadedModelPath = preparedModelPath
    }
    guard let whisperKit else {
      throw NSError(domain: "LocalWhisper", code: 1, userInfo: [NSLocalizedDescriptionKey: "WhisperKit did not load."])
    }
    let results = try await whisperKit.transcribe(audioPath: audioURL.path)
    return results
      .map { $0.text }
      .joined(separator: " ")
      .trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private func prepareCoreMLModelsIfNeeded(modelPath: String, model: String) throws -> String {
    let fileManager = FileManager.default
    let source = URL(fileURLWithPath: modelPath, isDirectory: true)
    let support = try fileManager.url(
      for: .applicationSupportDirectory,
      in: .userDomainMask,
      appropriateFor: nil,
      create: true
    )
    let target = support
      .appendingPathComponent("LocalWhisperCompiled", isDirectory: true)
      .appendingPathComponent(model, isDirectory: true)

    let modelNames = ["MelSpectrogram", "AudioEncoder", "TextDecoder"]
    let needsPreparation = modelNames.contains { name in
      fileManager.fileExists(
        atPath: source
          .appendingPathComponent("\(name).mlmodelc", isDirectory: true)
          .appendingPathComponent("model.mlmodel")
          .path
      )
    }
    if !needsPreparation {
      return modelPath
    }
    if modelNames.allSatisfy({ name in
      fileManager.fileExists(
        atPath: target.appendingPathComponent("\(name).mlmodelc", isDirectory: true).path
      )
    }) {
      return target.path
    }

    if fileManager.fileExists(atPath: target.path) {
      try fileManager.removeItem(at: target)
    }
    try fileManager.createDirectory(at: target, withIntermediateDirectories: true)

    for fileName in ["config.json", "generation_config.json"] {
      let from = source.appendingPathComponent(fileName)
      if fileManager.fileExists(atPath: from.path) {
        try fileManager.copyItem(at: from, to: target.appendingPathComponent(fileName))
      }
    }

    for name in modelNames {
      let sourceModel = source.appendingPathComponent("\(name).mlmodelc", isDirectory: true)
      let modelDefinition = sourceModel.appendingPathComponent("model.mlmodel")
      let destination = target.appendingPathComponent("\(name).mlmodelc", isDirectory: true)

      if fileManager.fileExists(atPath: modelDefinition.path) {
        let compiled = try MLModel.compileModel(at: modelDefinition)
        try fileManager.copyItem(at: compiled, to: destination)
      } else if fileManager.fileExists(atPath: sourceModel.path) {
        try fileManager.copyItem(at: sourceModel, to: destination)
      }
    }

    return target.path
  }

  private func whisperKitModelName(for model: String) throws -> String {
    switch model {
    case "whisperkit_large_v3_turbo":
      return "large-v3-v20240930_547MB"
    case "qwen3_asr", "parakeet_tdt_v3":
      throw NSError(
        domain: "LocalWhisper",
        code: 2,
        userInfo: [
          NSLocalizedDescriptionKey:
            "\(model) is managed in Local Whisper models, but this iOS build only has the WhisperKit/Core ML transcription runtime wired."
        ]
      )
    default:
      throw NSError(
        domain: "LocalWhisper",
        code: 3,
        userInfo: [NSLocalizedDescriptionKey: "Unknown transcription model: \(model)."]
      )
    }
  }

  private func emitLevel(buffer: AVAudioPCMBuffer) {
    guard let channel = buffer.floatChannelData?[0] else { return }
    let count = Int(buffer.frameLength)
    guard count > 0 else { return }
    var sum: Float = 0
    for index in 0..<count {
      let sample = channel[index]
      sum += sample * sample
    }
    let rms = sqrt(sum / Float(count))
    let normalized = min(max(Double(rms) * 8.0, 0.0), 1.0)
    DispatchQueue.main.async { [weak self] in
      self?.eventSink?(normalized)
    }
  }
}
