import 'dart:convert';

enum RecorderPhase { idle, checking, recording, processing, result, error }

enum ModelKind { transcription, cleanup, tts }

enum ModelRuntime { mlx, coreMl, whisperKit, bundled }

enum ModelInstallState {
  bundled,
  installed,
  notInstalled,
  downloading,
  unavailable,
}

class LocalWhisperException implements Exception {
  const LocalWhisperException(this.message);
  final String message;

  @override
  String toString() => message;
}

class NativeSpeechStatus {
  const NativeSpeechStatus({
    required this.permissionsGranted,
    required this.onDeviceAvailable,
    required this.recognitionAvailable,
    required this.localeId,
    required this.message,
  });

  const NativeSpeechStatus.unknown()
    : permissionsGranted = false,
      onDeviceAvailable = false,
      recognitionAvailable = false,
      localeId = 'en-US',
      message = 'Checking Local Whisper model engine.';

  final bool permissionsGranted;
  final bool onDeviceAvailable;
  final bool recognitionAvailable;
  final String localeId;
  final String message;

  factory NativeSpeechStatus.fromJson(Map<Object?, Object?> json) {
    return NativeSpeechStatus(
      permissionsGranted: json['permissionsGranted'] == true,
      onDeviceAvailable: json['onDeviceAvailable'] == true,
      recognitionAvailable: json['recognitionAvailable'] == true,
      localeId: json['localeId'] as String? ?? 'en-US',
      message: json['message'] as String? ?? 'Unknown status',
    );
  }
}

class NativeSpeechResult {
  const NativeSpeechResult({
    required this.transcript,
    required this.rawTranscript,
    required this.duration,
    required this.localeId,
    required this.onDevice,
  });

  final String transcript;
  final String rawTranscript;
  final double duration;
  final String localeId;
  final bool onDevice;

  factory NativeSpeechResult.fromJson(Map<Object?, Object?> json) {
    final transcript = json['transcript'] as String? ?? '';
    return NativeSpeechResult(
      transcript: transcript,
      rawTranscript: json['rawTranscript'] as String? ?? transcript,
      duration: (json['duration'] as num?)?.toDouble() ?? 0,
      localeId: json['localeId'] as String? ?? 'en-US',
      onDevice: json['onDevice'] == true,
    );
  }

  NativeSpeechResult copyWith({
    String? transcript,
    String? rawTranscript,
    double? duration,
    String? localeId,
    bool? onDevice,
  }) {
    return NativeSpeechResult(
      transcript: transcript ?? this.transcript,
      rawTranscript: rawTranscript ?? this.rawTranscript,
      duration: duration ?? this.duration,
      localeId: localeId ?? this.localeId,
      onDevice: onDevice ?? this.onDevice,
    );
  }
}

class DictationMode {
  const DictationMode({
    required this.id,
    required this.name,
    required this.instruction,
    this.builtIn = false,
  });

  final String id;
  final String name;
  final String instruction;
  final bool builtIn;

  static const defaults = [
    DictationMode(
      id: 'clean',
      name: 'Clean Dictation',
      instruction:
          'Clean punctuation, remove filler, preserve the speaker voice.',
      builtIn: true,
    ),
    DictationMode(
      id: 'message',
      name: 'Message',
      instruction:
          'Make it concise, warm, and ready to send as a chat message.',
      builtIn: true,
    ),
    DictationMode(
      id: 'notes',
      name: 'Notes',
      instruction: 'Turn it into compact notes with readable sentence breaks.',
      builtIn: true,
    ),
    DictationMode(
      id: 'prompt',
      name: 'Prompt',
      instruction: 'Keep intent precise and format it as an instruction.',
      builtIn: true,
    ),
  ];

  factory DictationMode.fromJson(Map<String, Object?> json) {
    return DictationMode(
      id: json['id'] as String,
      name: json['name'] as String,
      instruction: json['instruction'] as String,
      builtIn: json['builtIn'] == true,
    );
  }

  Map<String, Object?> toJson() => {
    'id': id,
    'name': name,
    'instruction': instruction,
    'builtIn': builtIn,
  };
}

class AppSettings {
  const AppSettings({
    this.localeId = 'en-US',
    this.selectedModeId = 'clean',
    this.selectedModelId = 'whisperkit_large_v3_turbo',
    this.autoCopy = true,
    this.smartPunctuation = true,
    this.removeFillers = true,
    this.minRecordingSeconds = 0.5,
    this.maxRecordingSeconds = 300,
    this.keyboardHaptics = true,
    this.keyboardQuickInsert = true,
  });

  final String localeId;
  final String selectedModeId;
  final String selectedModelId;
  final bool autoCopy;
  final bool smartPunctuation;
  final bool removeFillers;
  final double minRecordingSeconds;
  final int maxRecordingSeconds;
  final bool keyboardHaptics;
  final bool keyboardQuickInsert;

  factory AppSettings.fromJson(Map<String, Object?> json) => AppSettings(
    localeId: json['localeId'] as String? ?? 'en-US',
    selectedModeId: json['selectedModeId'] as String? ?? 'clean',
    selectedModelId:
        json['selectedModelId'] as String? ?? 'whisperkit_large_v3_turbo',
    autoCopy: json['autoCopy'] as bool? ?? true,
    smartPunctuation: json['smartPunctuation'] as bool? ?? true,
    removeFillers: json['removeFillers'] as bool? ?? true,
    minRecordingSeconds:
        (json['minRecordingSeconds'] as num?)?.toDouble() ?? 0.5,
    maxRecordingSeconds: (json['maxRecordingSeconds'] as num?)?.toInt() ?? 300,
    keyboardHaptics: json['keyboardHaptics'] as bool? ?? true,
    keyboardQuickInsert: json['keyboardQuickInsert'] as bool? ?? true,
  );

  AppSettings copyWith({
    String? localeId,
    String? selectedModeId,
    String? selectedModelId,
    bool? autoCopy,
    bool? smartPunctuation,
    bool? removeFillers,
    double? minRecordingSeconds,
    int? maxRecordingSeconds,
    bool? keyboardHaptics,
    bool? keyboardQuickInsert,
  }) {
    return AppSettings(
      localeId: localeId ?? this.localeId,
      selectedModeId: selectedModeId ?? this.selectedModeId,
      selectedModelId: selectedModelId ?? this.selectedModelId,
      autoCopy: autoCopy ?? this.autoCopy,
      smartPunctuation: smartPunctuation ?? this.smartPunctuation,
      removeFillers: removeFillers ?? this.removeFillers,
      minRecordingSeconds: minRecordingSeconds ?? this.minRecordingSeconds,
      maxRecordingSeconds: maxRecordingSeconds ?? this.maxRecordingSeconds,
      keyboardHaptics: keyboardHaptics ?? this.keyboardHaptics,
      keyboardQuickInsert: keyboardQuickInsert ?? this.keyboardQuickInsert,
    );
  }

  Map<String, Object?> toJson() => {
    'localeId': localeId,
    'selectedModeId': selectedModeId,
    'selectedModelId': selectedModelId,
    'autoCopy': autoCopy,
    'smartPunctuation': smartPunctuation,
    'removeFillers': removeFillers,
    'minRecordingSeconds': minRecordingSeconds,
    'maxRecordingSeconds': maxRecordingSeconds,
    'keyboardHaptics': keyboardHaptics,
    'keyboardQuickInsert': keyboardQuickInsert,
  };
}

class LocalModel {
  const LocalModel({
    required this.id,
    required this.name,
    required this.kind,
    required this.description,
    required this.sizeLabel,
    required this.state,
    required this.runtime,
    required this.minimumIosMajor,
    this.downloadUrl,
    this.repoId,
    this.revision = 'main',
    this.snapshotPath,
    this.installNote = '',
    this.localPath,
    this.installedBytes = 0,
    this.installedFiles = 0,
    this.progress = 0,
  });

  final String id;
  final String name;
  final ModelKind kind;
  final String description;
  final String sizeLabel;
  final ModelInstallState state;
  final ModelRuntime runtime;
  final int minimumIosMajor;
  final String? downloadUrl;
  final String? repoId;
  final String revision;
  final String? snapshotPath;
  final String installNote;
  final String? localPath;
  final int installedBytes;
  final int installedFiles;
  final double progress;

  bool get canDownload =>
      (downloadUrl != null || repoId != null) &&
      state == ModelInstallState.notInstalled;

  bool get canRemove => state == ModelInstallState.installed;

  bool get isRuntimeBundled => runtime == ModelRuntime.bundled;

  bool supportsIosMajor(int major) => major >= minimumIosMajor;

  LocalModel copyWith({
    ModelInstallState? state,
    String? localPath,
    int? installedBytes,
    int? installedFiles,
    double? progress,
  }) {
    return LocalModel(
      id: id,
      name: name,
      kind: kind,
      description: description,
      sizeLabel: sizeLabel,
      state: state ?? this.state,
      runtime: runtime,
      minimumIosMajor: minimumIosMajor,
      downloadUrl: downloadUrl,
      repoId: repoId,
      revision: revision,
      snapshotPath: snapshotPath,
      installNote: installNote,
      localPath: localPath ?? this.localPath,
      installedBytes: installedBytes ?? this.installedBytes,
      installedFiles: installedFiles ?? this.installedFiles,
      progress: progress ?? this.progress,
    );
  }

  factory LocalModel.fromJson(Map<String, Object?> json) {
    return LocalModel(
      id: json['id'] as String,
      name: json['name'] as String,
      kind: ModelKind.values.firstWhere(
        (kind) => kind.name == json['kind'],
        orElse: () => ModelKind.transcription,
      ),
      description: json['description'] as String? ?? '',
      sizeLabel: json['sizeLabel'] as String? ?? '',
      state: ModelInstallState.values.firstWhere(
        (state) => state.name == json['state'],
        orElse: () => ModelInstallState.notInstalled,
      ),
      runtime: ModelRuntime.values.firstWhere(
        (runtime) => runtime.name == json['runtime'],
        orElse: () => ModelRuntime.coreMl,
      ),
      minimumIosMajor: (json['minimumIosMajor'] as num?)?.toInt() ?? 14,
      downloadUrl: json['downloadUrl'] as String?,
      repoId: json['repoId'] as String?,
      revision: json['revision'] as String? ?? 'main',
      snapshotPath: json['snapshotPath'] as String?,
      installNote: json['installNote'] as String? ?? '',
      localPath: json['localPath'] as String?,
      installedBytes: (json['installedBytes'] as num?)?.toInt() ?? 0,
      installedFiles: (json['installedFiles'] as num?)?.toInt() ?? 0,
      progress: (json['progress'] as num?)?.toDouble() ?? 0,
    );
  }

  Map<String, Object?> toJson() => {
    'id': id,
    'name': name,
    'kind': kind.name,
    'description': description,
    'sizeLabel': sizeLabel,
    'state': state.name,
    'runtime': runtime.name,
    'minimumIosMajor': minimumIosMajor,
    'downloadUrl': downloadUrl,
    'repoId': repoId,
    'revision': revision,
    'snapshotPath': snapshotPath,
    'installNote': installNote,
    'localPath': localPath,
    'installedBytes': installedBytes,
    'installedFiles': installedFiles,
    'progress': progress,
  };
}

class TranscriptEntry {
  const TranscriptEntry({
    required this.id,
    required this.createdAt,
    required this.rawText,
    required this.finalText,
    required this.modeName,
    required this.localeId,
    required this.duration,
  });

  final String id;
  final DateTime createdAt;
  final String rawText;
  final String finalText;
  final String modeName;
  final String localeId;
  final double duration;

  String get prettyDate {
    final local = createdAt.toLocal();
    return '${local.month}/${local.day} ${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
  }

  static TranscriptEntry create({
    required String rawText,
    required String finalText,
    required String modeName,
    required String localeId,
    required double duration,
  }) {
    return TranscriptEntry(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      createdAt: DateTime.now(),
      rawText: rawText,
      finalText: finalText,
      modeName: modeName,
      localeId: localeId,
      duration: duration,
    );
  }

  factory TranscriptEntry.fromJson(Map<String, Object?> json) {
    return TranscriptEntry(
      id: json['id'] as String,
      createdAt: DateTime.parse(json['createdAt'] as String),
      rawText: json['rawText'] as String,
      finalText: json['finalText'] as String,
      modeName: json['modeName'] as String,
      localeId: json['localeId'] as String,
      duration: (json['duration'] as num).toDouble(),
    );
  }

  Map<String, Object?> toJson() => {
    'id': id,
    'createdAt': createdAt.toIso8601String(),
    'rawText': rawText,
    'finalText': finalText,
    'modeName': modeName,
    'localeId': localeId,
    'duration': duration,
  };
}

extension JsonListEncoding on List<Object?> {
  String encodeJson() => jsonEncode(this);
}
