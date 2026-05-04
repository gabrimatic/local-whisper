import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'history_store.dart';
import 'model_store.dart';
import 'models.dart';
import 'native_speech_service.dart';
import 'setup_service.dart';
import 'text_polisher.dart';

class AppPalette {
  static const background = Color(0xFF091013);
  static const nav = Color(0xFF10181E);
  static const surface = Color(0xFF121821);
  static const surfaceRaised = Color(0xFF17202A);
  static const accent = Color(0xFF75E3BE);
  static const accentSoft = Color(0xFF9DEBD2);
  static const sky = Color(0xFF8DDCFF);
  static const textSoft = Color(0xFFC8D0DA);
  static const warning = Color(0xFFFFC857);
  static const danger = Color(0xFFFF6B6B);
}

class LocalWhisperApp extends StatelessWidget {
  const LocalWhisperApp({super.key, this.initialModels, this.initialModes});

  final List<LocalModel>? initialModels;
  final List<DictationMode>? initialModes;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Local Whisper',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark(),
      home: AppController(
        initialModels: initialModels,
        initialModes: initialModes,
      ),
    );
  }
}

class AppController extends StatefulWidget {
  const AppController({super.key, this.initialModels, this.initialModes});

  final List<LocalModel>? initialModels;
  final List<DictationMode>? initialModes;

  @override
  State<AppController> createState() => _AppControllerState();
}

class _AppControllerState extends State<AppController>
    with WidgetsBindingObserver {
  final _speech = NativeSpeechService();
  final _setup = NativeSetupService();
  final _historyStore = HistoryStore();
  late final _modelStore = ModelStore(_historyStore);
  final _polisher = TextPolisher();
  final _searchController = TextEditingController();

  AppSettings _settings = const AppSettings();
  List<TranscriptEntry> _history = [];
  List<DictationMode> _modes = DictationMode.defaults;
  List<LocalModel> _models = ModelStore.catalog;
  DictationMode _selectedMode = DictationMode.defaults.first;
  RecorderPhase _phase = RecorderPhase.idle;
  NativeSpeechStatus _nativeStatus = const NativeSpeechStatus.unknown();
  NativeSpeechResult? _lastResult;
  KeyboardSetupStatus _keyboardStatus = const KeyboardSetupStatus.unknown();
  String _partialText = '';
  String? _error;
  double _level = 0;
  int _tabIndex = 0;
  bool _bootstrapped = false;
  bool _showOnboarding = false;
  final Set<String> _downloadingModels = {};
  final Map<String, ModelDownloadCancelToken> _downloadCancelTokens = {};
  Timer? _maxDurationTimer;
  Timer? _recordingTicker;
  StreamSubscription<double>? _levelSubscription;
  DateTime? _recordingStartedAt;
  Duration _recordingElapsed = Duration.zero;

  bool get _isBusy =>
      _phase == RecorderPhase.recording || _phase == RecorderPhase.processing;

  LocalModel get _selectedModel => _models.firstWhere(
    (model) => model.id == _settings.selectedModelId,
    orElse: () => _models.firstWhere(
      (model) => model.kind == ModelKind.transcription,
      orElse: () => ModelStore.catalog.first,
    ),
  );

  List<TranscriptEntry> get _filteredHistory {
    final query = _searchController.text.trim().toLowerCase();
    if (query.isEmpty) return _history;
    return _history
        .where(
          (entry) =>
              entry.rawText.toLowerCase().contains(query) ||
              entry.finalText.toLowerCase().contains(query) ||
              entry.modeName.toLowerCase().contains(query),
        )
        .toList(growable: false);
  }

  int get _iosMajorVersion {
    if (!Platform.isIOS) return 99;
    final match = RegExp(
      r'(?:Version |OS )(\d+)',
    ).firstMatch(Platform.operatingSystemVersion);
    return int.tryParse(match?.group(1) ?? '') ?? 14;
  }

  bool _hasNativeRuntime(LocalModel model) {
    return model.runtime == ModelRuntime.whisperKit ||
        model.runtime == ModelRuntime.bundled;
  }

  bool _canRecordWithModel(LocalModel model) {
    return model.kind == ModelKind.transcription &&
        model.state == ModelInstallState.installed &&
        model.supportsIosMajor(_iosMajorVersion) &&
        model.runtime == ModelRuntime.whisperKit &&
        (model.localPath?.isNotEmpty ?? false);
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _levelSubscription = _speech.levelStream.listen((level) {
      if (mounted) {
        setState(() => _level = level);
      }
    });
    _bootstrap();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _maxDurationTimer?.cancel();
    _recordingTicker?.cancel();
    _levelSubscription?.cancel();
    _searchController.dispose();
    _speech.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached) {
      if (_phase == RecorderPhase.recording) {
        _cancelRecording(
          message:
              'Recording stopped because Local Whisper left the foreground.',
        );
      }
    }
  }

  Future<void> _bootstrap() async {
    if (!kReleaseMode && Platform.environment['LOCAL_WHISPER_QA_SEED'] == '1') {
      await _seedInteractionData();
    }
    final modelsFuture = widget.initialModels == null
        ? _modelStore.loadModels()
        : Future<List<LocalModel>>.value(widget.initialModels);
    final modesFuture = widget.initialModes == null
        ? _historyStore.loadModes()
        : Future<List<DictationMode>>.value(widget.initialModes);
    final (settings, history, modes, models) = await (
      _historyStore.loadSettings(),
      _historyStore.loadHistory(),
      modesFuture,
      modelsFuture,
    ).wait;
    final onboardingComplete = await _historyStore.loadOnboardingComplete();
    NativeSpeechStatus nativeStatus;
    KeyboardSetupStatus keyboardStatus;
    try {
      nativeStatus = await _speech.status(locale: settings.localeId);
    } catch (error) {
      nativeStatus = NativeSpeechStatus(
        permissionsGranted: false,
        onDeviceAvailable: false,
        recognitionAvailable: false,
        localeId: settings.localeId,
        message: _friendlyError(error),
      );
    }
    try {
      keyboardStatus = await _setup.keyboardStatus();
    } catch (_) {
      keyboardStatus = const KeyboardSetupStatus.unknown();
    }
    if (!mounted) return;
    setState(() {
      _settings = settings;
      _history = history;
      _modes = modes.isEmpty ? DictationMode.defaults : modes;
      _models = models;
      _selectedMode = _modes.firstWhere(
        (mode) => mode.id == settings.selectedModeId,
        orElse: () => _modes.first,
      );
      _nativeStatus = nativeStatus;
      _keyboardStatus = keyboardStatus;
      _bootstrapped = true;
      _showOnboarding = !onboardingComplete;
    });
    await _syncKeyboardSettings(settings);
  }

  Future<void> _seedInteractionData() async {
    await _historyStore.saveHistory([
      TranscriptEntry.create(
        rawText: 'um local whisper comma test retry period',
        finalText: 'Local whisper, test retry.',
        modeName: 'Clean Dictation',
        localeId: 'en-US',
        duration: 2.4,
      ),
    ]);
    await _historyStore.saveModes([
      ...DictationMode.defaults,
      const DictationMode(
        id: 'qa-custom',
        name: 'QA Custom',
        instruction: 'Format this as a QA test note.',
      ),
    ]);
  }

  Future<void> _startRecording() async {
    if (_isBusy) return;
    setState(() {
      _phase = RecorderPhase.checking;
      _error = null;
      _lastResult = null;
      _partialText = '';
      _level = 0;
      _recordingElapsed = Duration.zero;
    });

    try {
      var status = await _speech.status(locale: _settings.localeId);
      if (!mounted) return;
      setState(() => _nativeStatus = status);

      final selectedModel = _selectedModel;
      if (selectedModel.kind != ModelKind.transcription) {
        throw const LocalWhisperException(
          'Choose a transcription model before recording.',
        );
      }
      if (selectedModel.state == ModelInstallState.notInstalled ||
          selectedModel.state == ModelInstallState.unavailable) {
        throw LocalWhisperException(
          'Download ${selectedModel.name} before recording.',
        );
      }
      if (!selectedModel.supportsIosMajor(_iosMajorVersion)) {
        throw LocalWhisperException(
          '${selectedModel.name} requires iOS ${selectedModel.minimumIosMajor}+.',
        );
      }
      if (!_hasNativeRuntime(selectedModel)) {
        throw LocalWhisperException(
          '${selectedModel.name} is installed as the Local Whisper model family, but its native iOS runtime is not wired yet.',
        );
      }
      if (selectedModel.runtime == ModelRuntime.whisperKit &&
          (selectedModel.localPath?.isEmpty ?? true)) {
        throw LocalWhisperException(
          '${selectedModel.name} needs a verified local model folder before recording.',
        );
      }
      if (!status.permissionsGranted) {
        final granted = await _speech.requestPermissions();
        if (!granted) {
          throw const LocalWhisperException(
            'Microphone permission is required for local recording.',
          );
        }
        status = await _speech.status(locale: _settings.localeId);
        if (!mounted) return;
        setState(() => _nativeStatus = status);
      }

      await _speech.start(
        locale: _settings.localeId,
        model: selectedModel.id,
        modelPath: selectedModel.localPath,
      );
      _maxDurationTimer?.cancel();
      if (_settings.maxRecordingSeconds > 0) {
        _maxDurationTimer = Timer(
          Duration(seconds: _settings.maxRecordingSeconds),
          () => _stopRecording(autoStopped: true),
        );
      }
      if (!mounted) return;
      setState(() {
        _phase = RecorderPhase.recording;
        _recordingStartedAt = DateTime.now();
        _recordingElapsed = Duration.zero;
      });
      _startRecordingTicker();
    } on Object catch (error) {
      _showError(_friendlyError(error));
    }
  }

  void _startRecordingTicker() {
    _recordingTicker?.cancel();
    _recordingTicker = Timer.periodic(const Duration(milliseconds: 250), (_) {
      final startedAt = _recordingStartedAt;
      if (!mounted || startedAt == null || _phase != RecorderPhase.recording) {
        return;
      }
      setState(() => _recordingElapsed = DateTime.now().difference(startedAt));
    });
  }

  Future<void> _stopRecording({bool autoStopped = false}) async {
    if (_phase != RecorderPhase.recording) return;
    _maxDurationTimer?.cancel();
    _recordingTicker?.cancel();
    setState(() => _phase = RecorderPhase.processing);

    try {
      final result = await _speech.stop();
      if (!mounted) return;

      final raw = result.transcript.trim();
      if (result.duration < _settings.minRecordingSeconds) {
        throw LocalWhisperException(
          'Recording was too short. Speak for at least ${_settings.minRecordingSeconds.toStringAsFixed(1)} seconds.',
        );
      }
      if (raw.isEmpty) {
        throw const LocalWhisperException('No speech was detected.');
      }

      final polished = _polisher.polish(
        raw,
        mode: _selectedMode,
        removeFillers: _settings.removeFillers,
        smartPunctuation: _settings.smartPunctuation,
      );
      final entry = TranscriptEntry.create(
        rawText: raw,
        finalText: polished,
        modeName: _selectedMode.name,
        localeId: _settings.localeId,
        duration: result.duration,
      );
      final history = [entry, ..._history].take(200).toList(growable: false);
      await _historyStore.saveHistory(history);
      if (_settings.autoCopy) {
        await Clipboard.setData(ClipboardData(text: polished));
      }

      if (!mounted) return;
      setState(() {
        _phase = RecorderPhase.result;
        _history = history;
        _lastResult = result.copyWith(transcript: polished, rawTranscript: raw);
        _partialText = '';
        _tabIndex = 0;
      });
      if (autoStopped) {
        _toast('Max duration reached. Text is ready.');
      }
    } on Object catch (error) {
      _showError(_friendlyError(error));
    }
  }

  Future<void> _cancelRecording({String? message}) async {
    _maxDurationTimer?.cancel();
    _recordingTicker?.cancel();
    await _speech.cancel();
    if (!mounted) return;
    setState(() {
      _phase = RecorderPhase.idle;
      _partialText = '';
      _level = 0;
      _recordingStartedAt = null;
      _recordingElapsed = Duration.zero;
      _error = message;
    });
  }

  Future<void> _retryPolish(TranscriptEntry entry) async {
    final polished = _polisher.polish(
      entry.rawText,
      mode: _selectedMode,
      removeFillers: _settings.removeFillers,
      smartPunctuation: _settings.smartPunctuation,
    );
    await Clipboard.setData(ClipboardData(text: polished));
    _toast('Re-polished and copied');
  }

  Future<void> _saveSettings(AppSettings settings) async {
    await _historyStore.saveSettings(settings);
    await _syncKeyboardSettings(settings);
    final status = await _speech.status(locale: settings.localeId);
    if (!mounted) return;
    setState(() {
      _settings = settings;
      _nativeStatus = status;
      _selectedMode = _modes.firstWhere(
        (mode) => mode.id == settings.selectedModeId,
        orElse: () => _modes.first,
      );
    });
  }

  Future<void> _syncKeyboardSettings(AppSettings settings) async {
    try {
      await _setup.syncKeyboardSettings(
        haptics: settings.keyboardHaptics,
        quickInsert: settings.keyboardQuickInsert,
      );
    } catch (_) {
      // The keyboard keeps safe defaults if the app group bridge is unavailable.
    }
  }

  Future<void> _completeOnboarding() async {
    await _historyStore.saveOnboardingComplete(true);
    if (!mounted) return;
    setState(() => _showOnboarding = false);
  }

  Future<void> _replayOnboarding() async {
    final keyboardStatus = await _refreshKeyboardStatus();
    if (!mounted) return;
    setState(() {
      _keyboardStatus = keyboardStatus;
      _showOnboarding = true;
    });
  }

  Future<KeyboardSetupStatus> _refreshKeyboardStatus() async {
    try {
      return await _setup.keyboardStatus();
    } catch (_) {
      return const KeyboardSetupStatus.unknown();
    }
  }

  Future<void> _checkKeyboardStatus() async {
    final status = await _refreshKeyboardStatus();
    if (!mounted) return;
    setState(() => _keyboardStatus = status);
  }

  Future<void> _markKeyboardSeenFromPractice() async {
    try {
      await _setup.markKeyboardSeen();
    } catch (_) {}
    if (!mounted) return;
    setState(() => _keyboardStatus = const KeyboardSetupStatus.verified());
  }

  Future<void> _openKeyboardSettings() async {
    try {
      final opened = await _setup.openKeyboardSettings();
      if (!opened) {
        _toast('Open Settings, then add Local Whisper Keyboard.');
      }
    } on Object catch (error) {
      _toast(_friendlyError(error));
    }
    await _checkKeyboardStatus();
  }

  Future<void> _openAppSettings() async {
    try {
      final opened = await _setup.openAppSettings();
      if (!opened) {
        _toast('Open iOS Settings for Local Whisper.');
      }
    } on Object catch (error) {
      _toast(_friendlyError(error));
    }
  }

  Future<void> _requestMicrophoneFromOnboarding() async {
    try {
      final granted = await _speech.requestPermissions();
      final status = await _speech.status(locale: _settings.localeId);
      if (!mounted) return;
      setState(() => _nativeStatus = status);
      _toast(
        granted ? 'Microphone ready' : 'Microphone permission was not granted.',
      );
    } on Object catch (error) {
      _toast(_friendlyError(error));
    }
  }

  Future<void> _saveModes(List<DictationMode> modes) async {
    await _historyStore.saveModes(modes);
    if (!mounted) return;
    setState(() {
      _modes = modes;
      if (!modes.any((mode) => mode.id == _selectedMode.id)) {
        _selectedMode = modes.first;
        _settings = _settings.copyWith(selectedModeId: _selectedMode.id);
        _historyStore.saveSettings(_settings);
      }
    });
  }

  Future<void> _downloadModel(LocalModel model) async {
    if (!model.canDownload || _downloadingModels.contains(model.id)) return;
    final cancelToken = ModelDownloadCancelToken();
    setState(() {
      _downloadingModels.add(model.id);
      _downloadCancelTokens[model.id] = cancelToken;
    });
    try {
      final models = await _modelStore.downloadModel(
        model,
        cancelToken: cancelToken,
        onProgress: (progressModel) {
          if (!mounted) return;
          setState(() {
            _models = _models
                .map(
                  (item) => item.id == progressModel.id ? progressModel : item,
                )
                .toList(growable: false);
          });
        },
      );
      if (!mounted) return;
      setState(() {
        _models = models;
        if (model.runtime == ModelRuntime.whisperKit &&
            model.kind == ModelKind.transcription) {
          _settings = _settings.copyWith(selectedModelId: model.id);
          _historyStore.saveSettings(_settings);
        }
      });
      _toast('${model.name} installed');
    } on ModelDownloadCanceledException {
      final models = await _modelStore.loadModels();
      if (!mounted) return;
      setState(() => _models = models);
      _toast('${model.name} download canceled');
    } on Object catch (error) {
      _showError(_friendlyError(error));
    } finally {
      if (mounted) {
        setState(() {
          _downloadingModels.remove(model.id);
          _downloadCancelTokens.remove(model.id);
        });
      }
    }
  }

  void _cancelModelDownload(LocalModel model) {
    _downloadCancelTokens[model.id]?.cancel();
  }

  Future<void> _removeModel(LocalModel model) async {
    final models = await _modelStore.removeModel(model);
    if (!mounted) return;
    setState(() {
      _models = models;
      if (_settings.selectedModelId == model.id) {
        final fallback = models.firstWhere(
          _canRecordWithModel,
          orElse: () => models.firstWhere(
            (item) =>
                item.kind == ModelKind.transcription &&
                item.runtime == ModelRuntime.whisperKit,
            orElse: () => models.firstWhere(
              (item) => item.kind == ModelKind.transcription,
            ),
          ),
        );
        _settings = _settings.copyWith(selectedModelId: fallback.id);
        _historyStore.saveSettings(_settings);
      }
    });
    _toast('${model.name} removed');
  }

  void _showError(String message) {
    if (!mounted) return;
    _recordingTicker?.cancel();
    setState(() {
      _phase = RecorderPhase.error;
      _error = message;
      _level = 0;
      _recordingStartedAt = null;
      _recordingElapsed = Duration.zero;
    });
  }

  String _friendlyError(Object error) {
    if (error is LocalWhisperException) return error.message;
    if (error is PlatformException) {
      return error.message ?? error.code;
    }
    return error.toString();
  }

  void _toast(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), behavior: SnackBarBehavior.floating),
    );
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      RecordPage(
        phase: _phase,
        level: _level,
        elapsed: _recordingElapsed,
        recordReady: _canRecordWithModel(_selectedModel),
        partialText: _partialText,
        result: _lastResult,
        error: _error,
        status: _nativeStatus,
        selectedMode: _selectedMode,
        selectedModel: _selectedModel,
        settings: _settings,
        onStart: _startRecording,
        onOpenModels: () => setState(() => _tabIndex = 3),
        onStop: _stopRecording,
        onCancel: () => _cancelRecording(),
        onCopy: (text) async {
          await Clipboard.setData(ClipboardData(text: text));
          _toast('Copied');
        },
      ),
      HistoryPage(
        searchController: _searchController,
        entries: _filteredHistory,
        onChangedSearch: () => setState(() {}),
        onCopy: (text) async {
          await Clipboard.setData(ClipboardData(text: text));
          _toast('Copied');
        },
        onRetry: _retryPolish,
      ),
      ModesPage(
        modes: _modes,
        selectedMode: _selectedMode,
        onSelect: (mode) =>
            _saveSettings(_settings.copyWith(selectedModeId: mode.id)),
        onSaveModes: _saveModes,
      ),
      ModelsPage(
        models: _models,
        downloadingModelIds: _downloadingModels,
        selectedModelId: _settings.selectedModelId,
        onDownload: _downloadModel,
        onCancelDownload: _cancelModelDownload,
        onRemove: _removeModel,
        onSelect: (model) =>
            _saveSettings(_settings.copyWith(selectedModelId: model.id)),
      ),
      SettingsPage(
        settings: _settings,
        status: _nativeStatus,
        keyboardStatus: _keyboardStatus,
        onChanged: _saveSettings,
        onRefreshStatus: () async {
          final status = await _speech.status(locale: _settings.localeId);
          if (mounted) setState(() => _nativeStatus = status);
        },
        onRunSetup: _replayOnboarding,
      ),
    ];

    final shell = Scaffold(
      body: SafeArea(
        child: IndexedStack(index: _tabIndex, children: pages),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tabIndex,
        onDestinationSelected: (index) => setState(() => _tabIndex = index),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.mic_rounded), label: 'Record'),
          NavigationDestination(
            icon: Icon(Icons.history_rounded),
            label: 'History',
          ),
          NavigationDestination(
            icon: Icon(Icons.auto_awesome_rounded),
            label: 'Modes',
          ),
          NavigationDestination(
            icon: Icon(Icons.memory_rounded),
            label: 'Models',
          ),
          NavigationDestination(
            icon: Icon(Icons.tune_rounded),
            label: 'Settings',
          ),
        ],
      ),
    );

    if (!_bootstrapped) {
      return const _LaunchHold();
    }
    if (_showOnboarding) {
      return OnboardingFlow(
        settings: _settings,
        status: _nativeStatus,
        keyboardStatus: _keyboardStatus,
        models: _models,
        selectedModel: _selectedModel,
        onOpenKeyboardSettings: _openKeyboardSettings,
        onRefreshKeyboardStatus: _checkKeyboardStatus,
        onRequestMicrophone: _requestMicrophoneFromOnboarding,
        onOpenAppSettings: _openAppSettings,
        onDownloadModel: _downloadModel,
        onKeyboardPracticeVerified: _markKeyboardSeenFromPractice,
        onFinish: _completeOnboarding,
      );
    }
    return shell;
  }
}

class OnboardingFlow extends StatefulWidget {
  const OnboardingFlow({
    required this.settings,
    required this.status,
    required this.keyboardStatus,
    required this.models,
    required this.selectedModel,
    required this.onOpenKeyboardSettings,
    required this.onRefreshKeyboardStatus,
    required this.onRequestMicrophone,
    required this.onOpenAppSettings,
    required this.onDownloadModel,
    required this.onKeyboardPracticeVerified,
    required this.onFinish,
    super.key,
  });

  final AppSettings settings;
  final NativeSpeechStatus status;
  final KeyboardSetupStatus keyboardStatus;
  final List<LocalModel> models;
  final LocalModel selectedModel;
  final VoidCallback onOpenKeyboardSettings;
  final VoidCallback onRefreshKeyboardStatus;
  final VoidCallback onRequestMicrophone;
  final VoidCallback onOpenAppSettings;
  final ValueChanged<LocalModel> onDownloadModel;
  final VoidCallback onKeyboardPracticeVerified;
  final VoidCallback onFinish;

  @override
  State<OnboardingFlow> createState() => _OnboardingFlowState();
}

class _OnboardingFlowState extends State<OnboardingFlow> {
  final _controller = PageController();
  final _practiceController = TextEditingController();
  bool _handlingPracticeVerification = false;
  int _index = 0;

  bool get _modelReady =>
      widget.selectedModel.state == ModelInstallState.installed ||
      widget.selectedModel.state == ModelInstallState.bundled;

  bool get _modelDownloading =>
      widget.selectedModel.state == ModelInstallState.downloading;

  @override
  void initState() {
    super.initState();
    _practiceController.addListener(_handlePracticeTextChanged);
  }

  @override
  void dispose() {
    _practiceController.removeListener(_handlePracticeTextChanged);
    _practiceController.dispose();
    _controller.dispose();
    super.dispose();
  }

  void _handlePracticeTextChanged() {
    if (_handlingPracticeVerification ||
        !_practiceController.text.contains(keyboardVerificationToken)) {
      return;
    }
    _handlingPracticeVerification = true;
    final cleaned = _practiceController.text
        .replaceAll(keyboardVerificationToken, '')
        .trimLeft();
    _practiceController.value = TextEditingValue(
      text: cleaned,
      selection: TextSelection.collapsed(offset: cleaned.length),
    );
    widget.onKeyboardPracticeVerified();
    _handlingPracticeVerification = false;
  }

  void _goTo(int index) {
    _controller.animateToPage(
      index,
      duration: const Duration(milliseconds: 320),
      curve: Curves.easeOutCubic,
    );
  }

  void _showModelChoices() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      backgroundColor: AppPalette.surface,
      builder: (context) => _SetupModelChoicesSheet(
        models: widget.models,
        selectedModelId: widget.selectedModel.id,
        onDownloadModel: widget.onDownloadModel,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final steps = [
      _SetupPageData(
        label: 'Welcome',
        icon: Icons.graphic_eq_rounded,
        title: 'Private voice, ready everywhere.',
        body:
            'Local Whisper records on this iPhone, formats your words locally, and keeps finished text ready to paste.',
        action: _SetupActions(
          primaryLabel: 'Start setup',
          primaryIcon: Icons.arrow_forward_rounded,
          onPrimary: () => _goTo(1),
        ),
      ),
      _SetupPageData(
        label: 'Model',
        icon: _modelReady
            ? Icons.check_circle_rounded
            : _modelDownloading
            ? Icons.downloading_rounded
            : Icons.download_for_offline_rounded,
        title: _modelReady ? 'Model pack ready' : 'Install a model pack',
        body: _modelReady
            ? '${widget.selectedModel.name} is ready for offline transcription.'
            : 'Use the recommended WhisperKit pack for the first offline transcription path. You can add more model families later.',
        action: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (!_modelReady) ...[
              _SetupModelChoice(
                model: widget.selectedModel,
                downloading: _modelDownloading,
                onDownload: () => widget.onDownloadModel(widget.selectedModel),
                onOpenModels: _showModelChoices,
              ),
              const SizedBox(height: 16),
            ],
            _SetupActions(
              primaryLabel: 'Continue',
              primaryIcon: Icons.arrow_forward_rounded,
              onPrimary: () => _goTo(2),
              onBack: () => _goTo(0),
            ),
          ],
        ),
      ),
      _SetupPageData(
        label: 'Microphone',
        icon: widget.status.permissionsGranted
            ? Icons.mic_rounded
            : Icons.mic_off_rounded,
        title: widget.status.permissionsGranted
            ? 'Microphone ready'
            : 'Allow microphone access',
        body: widget.status.permissionsGranted
            ? widget.status.message
            : 'Local recording needs microphone permission. Audio stays on-device and is not sent to Apple Speech or cloud services.',
        action: _SetupActions(
          primaryLabel: widget.status.permissionsGranted ? 'Continue' : 'Allow',
          primaryIcon: widget.status.permissionsGranted
              ? Icons.arrow_forward_rounded
              : Icons.mic_rounded,
          onPrimary: widget.status.permissionsGranted
              ? () => _goTo(3)
              : widget.onRequestMicrophone,
          onBack: () => _goTo(1),
          secondaryLabel: widget.status.permissionsGranted
              ? null
              : 'Open Settings',
          secondaryIcon: Icons.settings_rounded,
          onSecondary: widget.status.permissionsGranted
              ? null
              : widget.onOpenAppSettings,
        ),
      ),
      _SetupPageData(
        label: 'Keyboard',
        icon: Icons.keyboard_rounded,
        title: 'Enable Local Whisper Keyboard',
        body:
            'Open Settings, add Local Whisper Keyboard, then return here. In the practice field, switch to Local Whisper Keyboard and tap Verify on the keyboard.\n\n${widget.keyboardStatus.message}',
        action: _SetupActions(
          primaryLabel: 'Open Settings',
          primaryIcon: Icons.settings_rounded,
          onPrimary: widget.onOpenKeyboardSettings,
          onBack: () => _goTo(2),
          secondaryLabel: 'Check',
          secondaryIcon: Icons.fact_check_rounded,
          onSecondary: widget.onRefreshKeyboardStatus,
          tertiaryLabel: 'Continue',
          tertiaryIcon: Icons.arrow_forward_rounded,
          onTertiary: () => _goTo(4),
        ),
      ),
      _SetupPageData(
        label: 'Practice',
        icon: Icons.edit_note_rounded,
        title: widget.keyboardStatus.keyboardSeen
            ? 'Keyboard verified'
            : 'Waiting for keyboard',
        body: widget.keyboardStatus.message,
        action: _SetupActions(
          primaryLabel: widget.keyboardStatus.keyboardSeen
              ? 'Finish setup'
              : 'Use without keyboard',
          primaryIcon: widget.keyboardStatus.keyboardSeen
              ? Icons.check_rounded
              : Icons.keyboard_hide_rounded,
          onPrimary: widget.onFinish,
          onBack: () => _goTo(3),
          secondaryLabel: 'Check',
          secondaryIcon: Icons.fact_check_rounded,
          onSecondary: widget.onRefreshKeyboardStatus,
        ),
      ),
    ];

    return Scaffold(
      backgroundColor: AppPalette.background,
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(18, 14, 18, 18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Set up Local Whisper', style: theme.textTheme.displaySmall),
              const SizedBox(height: 8),
              Text(
                'Step ${_index + 1} of ${steps.length}: ${steps[_index].label}',
                style: theme.textTheme.bodyLarge,
              ),
              const SizedBox(height: 12),
              LinearProgressIndicator(
                value: (_index + 1) / steps.length,
                minHeight: 8,
                borderRadius: BorderRadius.circular(99),
              ),
              const SizedBox(height: 16),
              Expanded(
                child: PageView.builder(
                  controller: _controller,
                  physics: const NeverScrollableScrollPhysics(),
                  onPageChanged: (value) => setState(() => _index = value),
                  itemCount: steps.length,
                  itemBuilder: (context, index) => _SetupPage(
                    data: steps[index],
                    keyboardStatus: widget.keyboardStatus,
                    practiceController: _practiceController,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SetupPageData {
  const _SetupPageData({
    required this.label,
    required this.icon,
    required this.title,
    required this.body,
    required this.action,
  });

  final String label;
  final IconData icon;
  final String title;
  final String body;
  final Widget action;
}

class _SetupActions extends StatelessWidget {
  const _SetupActions({
    required this.primaryLabel,
    required this.primaryIcon,
    required this.onPrimary,
    this.onBack,
    this.secondaryLabel,
    this.secondaryIcon,
    this.onSecondary,
    this.tertiaryLabel,
    this.tertiaryIcon,
    this.onTertiary,
  });

  final String primaryLabel;
  final IconData primaryIcon;
  final VoidCallback onPrimary;
  final VoidCallback? onBack;
  final String? secondaryLabel;
  final IconData? secondaryIcon;
  final VoidCallback? onSecondary;
  final String? tertiaryLabel;
  final IconData? tertiaryIcon;
  final VoidCallback? onTertiary;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 10,
      runSpacing: 10,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        if (onBack != null)
          TextButton.icon(
            onPressed: onBack,
            icon: const Icon(Icons.arrow_back_rounded),
            label: const Text('Back'),
          ),
        FilledButton.icon(
          onPressed: onPrimary,
          icon: Icon(primaryIcon),
          label: Text(primaryLabel),
        ),
        if (secondaryLabel != null &&
            secondaryIcon != null &&
            onSecondary != null)
          OutlinedButton.icon(
            onPressed: onSecondary,
            icon: Icon(secondaryIcon),
            label: Text(secondaryLabel!),
          ),
        if (tertiaryLabel != null && tertiaryIcon != null && onTertiary != null)
          TextButton.icon(
            onPressed: onTertiary,
            icon: Icon(tertiaryIcon),
            label: Text(tertiaryLabel!),
          ),
      ],
    );
  }
}

class _SetupModelChoice extends StatelessWidget {
  const _SetupModelChoice({
    required this.model,
    required this.downloading,
    required this.onDownload,
    required this.onOpenModels,
  });

  final LocalModel model;
  final bool downloading;
  final VoidCallback onDownload;
  final VoidCallback onOpenModels;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.09)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.offline_bolt_rounded, color: AppPalette.accent),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  model.name,
                  style: Theme.of(context).textTheme.titleMedium,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _MetaChip(text: model.sizeLabel),
              const _MetaChip(text: 'Recommended'),
              const _MetaChip(text: 'Offline'),
            ],
          ),
          const SizedBox(height: 10),
          Text(model.description),
          if (downloading) ...[
            const SizedBox(height: 12),
            LinearProgressIndicator(
              value: model.progress == 0 ? null : model.progress,
              semanticsLabel: '${model.name} download progress',
            ),
          ],
          const SizedBox(height: 12),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              FilledButton.icon(
                onPressed: downloading ? null : onDownload,
                icon: Icon(
                  downloading
                      ? Icons.downloading_rounded
                      : Icons.download_rounded,
                ),
                label: Text(downloading ? 'Installing' : 'Install'),
              ),
              TextButton.icon(
                onPressed: onOpenModels,
                icon: const Icon(Icons.tune_rounded),
                label: const Text('More choices'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SetupModelChoicesSheet extends StatelessWidget {
  const _SetupModelChoicesSheet({
    required this.models,
    required this.selectedModelId,
    required this.onDownloadModel,
  });

  final List<LocalModel> models;
  final String selectedModelId;
  final ValueChanged<LocalModel> onDownloadModel;

  @override
  Widget build(BuildContext context) {
    final modelPacks = models
        .where((model) => model.kind != ModelKind.cleanup)
        .toList(growable: false);
    final sheetHeight = MediaQuery.sizeOf(context).height * 0.72;
    return SafeArea(
      child: SizedBox(
        height: sheetHeight,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(18, 0, 18, 0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Model packs',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'Start with WhisperKit for the iPhone recorder. The other packs can be installed for upcoming local engines.',
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            Expanded(
              child: ListView.separated(
                padding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
                itemCount: modelPacks.length,
                separatorBuilder: (_, _) => Divider(
                  height: 1,
                  color: Colors.white.withValues(alpha: 0.08),
                ),
                itemBuilder: (context, index) {
                  final model = modelPacks[index];
                  final isSelected = model.id == selectedModelId;
                  final isReady =
                      model.state == ModelInstallState.installed ||
                      model.state == ModelInstallState.bundled;
                  final isDownloading =
                      model.state == ModelInstallState.downloading;
                  final canInstall =
                      model.state == ModelInstallState.notInstalled ||
                      model.state == ModelInstallState.unavailable;
                  return ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(
                      isReady
                          ? Icons.check_circle_rounded
                          : isDownloading
                          ? Icons.downloading_rounded
                          : Icons.download_for_offline_rounded,
                      color: isReady ? AppPalette.accent : AppPalette.sky,
                    ),
                    title: Text(model.name),
                    subtitle: Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Wrap(
                        spacing: 8,
                        runSpacing: 6,
                        children: [
                          _MetaChip(text: model.sizeLabel),
                          _MetaChip(text: _runtimeLabel(model.runtime)),
                          if (isSelected) const _MetaChip(text: 'Selected'),
                        ],
                      ),
                    ),
                    trailing: canInstall
                        ? TextButton(
                            onPressed: isDownloading
                                ? null
                                : () {
                                    Navigator.of(context).pop();
                                    onDownloadModel(model);
                                  },
                            child: Text(
                              isDownloading ? 'Installing' : 'Install',
                            ),
                          )
                        : null,
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  static String _runtimeLabel(ModelRuntime runtime) {
    return switch (runtime) {
      ModelRuntime.mlx => 'MLX',
      ModelRuntime.coreMl => 'Core ML',
      ModelRuntime.whisperKit => 'WhisperKit',
      ModelRuntime.bundled => 'Bundled',
    };
  }
}

class _SetupPage extends StatelessWidget {
  const _SetupPage({
    required this.data,
    required this.keyboardStatus,
    required this.practiceController,
  });

  final _SetupPageData data;
  final KeyboardSetupStatus keyboardStatus;
  final TextEditingController practiceController;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 220),
      child: ListView(
        padding: EdgeInsets.zero,
        key: ValueKey(data.label),
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        children: [
          _Panel(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(data.title, style: theme.textTheme.headlineSmall),
                const SizedBox(height: 10),
                Text(data.body, style: theme.textTheme.bodyLarge),
                const SizedBox(height: 18),
                data.action,
                const SizedBox(height: 20),
                _MiniPhoneFrame(
                  icon: data.icon,
                  title: data.label,
                  verified: keyboardStatus.keyboardSeen,
                ),
              ],
            ),
          ),
          if (data.label == 'Keyboard') ...[
            const SizedBox(height: 14),
            _InlineNotice(text: keyboardStatus.message),
            const SizedBox(height: 14),
            const _KeyboardHelpPanel(),
          ],
          if (data.label == 'Practice') ...[
            const SizedBox(height: 14),
            TextField(
              controller: practiceController,
              minLines: 3,
              maxLines: 5,
              scrollPadding: EdgeInsets.only(
                bottom: MediaQuery.viewInsetsOf(context).bottom + 180,
              ),
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.keyboard_rounded),
                labelText: 'Practice field',
                hintText: 'Switch to Local Whisper Keyboard and tap Verify',
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _MiniPhoneFrame extends StatelessWidget {
  const _MiniPhoneFrame({
    required this.icon,
    required this.title,
    required this.verified,
  });

  final IconData icon;
  final String title;
  final bool verified;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 154,
      width: double.infinity,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF172C35), Color(0xFF2A2540), Color(0xFF16372D)],
        ),
      ),
      child: Stack(
        children: [
          Positioned(
            left: 24,
            top: 26,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 260),
              width: verified ? 92 : 78,
              height: verified ? 92 : 78,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppPalette.accent.withValues(alpha: 0.14),
                boxShadow: [
                  BoxShadow(
                    color: AppPalette.accent.withValues(alpha: 0.28),
                    blurRadius: 38,
                    spreadRadius: 4,
                  ),
                ],
              ),
              child: Icon(icon, color: AppPalette.accent, size: 38),
            ),
          ),
          Positioned(right: 18, top: 20, child: _MetaChip(text: title)),
          Positioned(
            left: 22,
            right: 22,
            bottom: 22,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 160,
                  height: 12,
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.84),
                    borderRadius: BorderRadius.circular(99),
                  ),
                ),
                const SizedBox(height: 10),
                Container(
                  width: 230,
                  height: 12,
                  decoration: BoxDecoration(
                    color: AppPalette.sky.withValues(alpha: 0.55),
                    borderRadius: BorderRadius.circular(99),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _KeyboardHelpPanel extends StatelessWidget {
  const _KeyboardHelpPanel();

  @override
  Widget build(BuildContext context) {
    return const _MessagePanel(
      icon: Icons.route_rounded,
      title: 'Keyboard setup path',
      body:
          'Settings opens outside the app. Add Local Whisper Keyboard, return here, switch keyboards in the practice field, then tap Verify on the keyboard. Some apps block third-party keyboards in secure fields.',
      color: AppPalette.sky,
    );
  }
}

class _LaunchHold extends StatelessWidget {
  const _LaunchHold();

  @override
  Widget build(BuildContext context) {
    return const Material(
      color: AppPalette.background,
      child: SafeArea(
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.graphic_eq_rounded,
                color: AppPalette.accent,
                size: 54,
              ),
              SizedBox(height: 18),
              Text(
                'Local Whisper',
                style: TextStyle(fontSize: 30, fontWeight: FontWeight.w800),
              ),
              SizedBox(height: 8),
              Text(
                'Preparing setup',
                style: TextStyle(color: AppPalette.textSoft, fontSize: 16),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class RecordPage extends StatelessWidget {
  const RecordPage({
    required this.phase,
    required this.level,
    required this.elapsed,
    required this.recordReady,
    required this.partialText,
    required this.result,
    required this.error,
    required this.status,
    required this.selectedMode,
    required this.selectedModel,
    required this.settings,
    required this.onStart,
    required this.onOpenModels,
    required this.onStop,
    required this.onCancel,
    required this.onCopy,
    super.key,
  });

  final RecorderPhase phase;
  final double level;
  final Duration elapsed;
  final bool recordReady;
  final String partialText;
  final NativeSpeechResult? result;
  final String? error;
  final NativeSpeechStatus status;
  final DictationMode selectedMode;
  final LocalModel selectedModel;
  final AppSettings settings;
  final VoidCallback onStart;
  final VoidCallback onOpenModels;
  final Future<void> Function({bool autoStopped}) onStop;
  final VoidCallback onCancel;
  final ValueChanged<String> onCopy;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final recording = phase == RecorderPhase.recording;
    final processing = phase == RecorderPhase.processing;
    final modelBlocked = !recordReady && !recording && !processing;
    final title = switch (phase) {
      RecorderPhase.recording => 'Listening',
      RecorderPhase.processing => 'Polishing locally',
      RecorderPhase.result => 'Ready',
      RecorderPhase.error => 'Needs attention',
      RecorderPhase.checking => 'Checking offline engine',
      RecorderPhase.idle => modelBlocked ? 'Model needed' : 'Local Whisper',
    };
    final subtitle = modelBlocked
        ? 'Install ${selectedModel.name} before recording on this iPhone.'
        : '${selectedModel.name} in ${settings.localeId} using ${selectedMode.name}.';

    return CustomScrollView(
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      slivers: [
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(20, 18, 20, 12),
          sliver: SliverToBoxAdapter(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(title, style: theme.textTheme.displaySmall),
                          const SizedBox(height: 8),
                          Text(subtitle, style: theme.textTheme.bodyLarge),
                        ],
                      ),
                    ),
                    _StatusPill(status: status, recordReady: recordReady),
                  ],
                ),
                const SizedBox(height: 22),
                _RecorderSurface(
                  phase: phase,
                  level: level,
                  elapsed: elapsed,
                  recordReady: recordReady,
                  selectedModelName: selectedModel.name,
                  onTap: recording
                      ? () => onStop(autoStopped: false)
                      : processing
                      ? null
                      : recordReady
                      ? onStart
                      : onOpenModels,
                  onCancel: recording ? onCancel : null,
                ),
                const SizedBox(height: 18),
                AnimatedSwitcher(
                  duration: const Duration(milliseconds: 240),
                  child: error != null && phase == RecorderPhase.error
                      ? _MessagePanel(
                          key: const ValueKey('error'),
                          icon: Icons.error_outline_rounded,
                          title: 'Could not finish',
                          body: error!,
                          color: AppPalette.danger,
                        )
                      : result != null
                      ? _ResultPanel(
                          key: const ValueKey('result'),
                          result: result!,
                          onCopy: onCopy,
                        )
                      : modelBlocked
                      ? _MessagePanel(
                          key: const ValueKey('model-needed'),
                          icon: Icons.download_for_offline_rounded,
                          title: 'Install model first',
                          body:
                              'Recording starts after a verified local WhisperKit model pack is installed on this iPhone.',
                          color: AppPalette.warning,
                        )
                      : _MessagePanel(
                          key: const ValueKey('hint'),
                          icon: Icons.lock_rounded,
                          title: 'Private by default',
                          body:
                              'Audio stays on this iPhone. Recording requires a selected Local Whisper model pack.',
                          color: AppPalette.accentSoft,
                        ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _RecorderSurface extends StatelessWidget {
  const _RecorderSurface({
    required this.phase,
    required this.level,
    required this.elapsed,
    required this.recordReady,
    required this.selectedModelName,
    required this.onTap,
    this.onCancel,
  });

  final RecorderPhase phase;
  final double level;
  final Duration elapsed;
  final bool recordReady;
  final String selectedModelName;
  final VoidCallback? onTap;
  final VoidCallback? onCancel;

  @override
  Widget build(BuildContext context) {
    final recording = phase == RecorderPhase.recording;
    final processing = phase == RecorderPhase.processing;
    final idle = phase == RecorderPhase.idle || phase == RecorderPhase.error;
    final blocked = !recordReady && !recording && !processing;
    final baseSize = recording ? 132.0 + (level.clamp(0, 1) * 28) : 146.0;
    final primaryLabel = recording
        ? 'Stop recording'
        : processing
        ? 'Processing'
        : blocked
        ? 'Install model'
        : 'Start talking';
    final helper = recording
        ? 'Recording ${_formatElapsed(elapsed)}'
        : processing
        ? 'Transcribing and formatting offline'
        : blocked
        ? 'Install $selectedModelName first. Then tap here and speak.'
        : 'Tap the microphone and speak naturally.';
    final actionColor = recording
        ? AppPalette.danger
        : blocked
        ? AppPalette.warning
        : idle
        ? AppPalette.accent
        : AppPalette.sky;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 22, 20, 20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(32),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppPalette.surfaceRaised,
            Color(0xFF25283A),
            Color(0xFF14332B),
          ],
        ),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(
        children: [
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 220),
            child: Text(
              recording
                  ? 'Speak now'
                  : processing
                  ? 'Working locally'
                  : blocked
                  ? 'One thing first'
                  : 'Ready when you are',
              key: ValueKey(phase),
              style: Theme.of(context).textTheme.headlineSmall,
              textAlign: TextAlign.center,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            helper,
            style: Theme.of(context).textTheme.bodyLarge,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 18),
          Semantics(
            button: true,
            label: recording
                ? 'Stop recording'
                : processing
                ? 'Processing recording'
                : blocked
                ? 'Open model downloads'
                : 'Start recording',
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 160),
              width: baseSize,
              height: baseSize,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: actionColor.withValues(alpha: 0.35),
                    blurRadius: recording ? 48 : 28,
                    spreadRadius: recording ? 10 : 2,
                  ),
                ],
              ),
              child: Stack(
                alignment: Alignment.center,
                children: [
                  if (!recording && !processing)
                    _BreathingHalo(color: actionColor),
                  ExcludeSemantics(
                    child: FilledButton(
                      onPressed: onTap,
                      style: FilledButton.styleFrom(
                        shape: const CircleBorder(),
                      ),
                      child: processing
                          ? const SizedBox.square(
                              dimension: 38,
                              child: CircularProgressIndicator(strokeWidth: 4),
                            )
                          : Icon(
                              recording
                                  ? Icons.stop_rounded
                                  : blocked
                                  ? Icons.download_for_offline_rounded
                                  : Icons.mic_rounded,
                              size: 64,
                            ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),
          Text(primaryLabel, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 14),
          _LevelMeter(level: recording ? level : 0, active: recording),
          if (onCancel != null) ...[
            const SizedBox(height: 12),
            TextButton.icon(
              onPressed: onCancel,
              icon: const Icon(Icons.close_rounded),
              label: const Text('Cancel'),
            ),
          ],
        ],
      ),
    );
  }

  static String _formatElapsed(Duration duration) {
    final minutes = duration.inMinutes.remainder(60).toString().padLeft(2, '0');
    final seconds = duration.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }
}

class _BreathingHalo extends StatefulWidget {
  const _BreathingHalo({required this.color});

  final Color color;

  @override
  State<_BreathingHalo> createState() => _BreathingHaloState();
}

class _BreathingHaloState extends State<_BreathingHalo>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final value = Curves.easeInOut.transform(_controller.value);
        return Container(
          width: 108 + value * 18,
          height: 108 + value * 18,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
              color: widget.color.withValues(alpha: 0.16 + value * 0.14),
              width: 2,
            ),
          ),
        );
      },
    );
  }
}

class _LevelMeter extends StatelessWidget {
  const _LevelMeter({required this.level, required this.active});

  final double level;
  final bool active;

  @override
  Widget build(BuildContext context) {
    final normalized = level.clamp(0, 1);
    return Semantics(
      label: active ? 'Recording level' : 'Recording level idle',
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: List.generate(9, (index) {
          final threshold = (index + 1) / 9;
          final lit = active && normalized >= threshold * 0.72;
          final height = 8.0 + (index.isEven ? 10.0 : 18.0);
          return AnimatedContainer(
            duration: const Duration(milliseconds: 130),
            margin: const EdgeInsets.symmetric(horizontal: 3),
            width: 8,
            height: lit ? height + normalized * 12 : 8,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(99),
              color: lit
                  ? AppPalette.accent
                  : Colors.white.withValues(alpha: active ? 0.18 : 0.1),
            ),
          );
        }),
      ),
    );
  }
}

class _ResultPanel extends StatelessWidget {
  const _ResultPanel({required this.result, required this.onCopy, super.key});

  final NativeSpeechResult result;
  final ValueChanged<String> onCopy;

  @override
  Widget build(BuildContext context) {
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.check_circle_rounded, color: AppPalette.accent),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Copied-ready text',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              IconButton(
                tooltip: 'Copy',
                onPressed: () => onCopy(result.transcript),
                icon: const Icon(Icons.copy_rounded),
              ),
            ],
          ),
          const SizedBox(height: 12),
          SelectableText(result.transcript),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            children: [
              Chip(label: Text('${result.duration.toStringAsFixed(1)}s')),
              Chip(label: Text(result.localeId)),
              if (!result.onDevice) const Chip(label: Text('Not offline')),
            ],
          ),
        ],
      ),
    );
  }
}

class _MessagePanel extends StatelessWidget {
  const _MessagePanel({
    required this.icon,
    required this.title,
    required this.body,
    required this.color,
    super.key,
  });

  final IconData icon;
  final String title;
  final String body;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return _Panel(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 6),
                Text(body),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.status, required this.recordReady});

  final NativeSpeechStatus status;
  final bool recordReady;

  @override
  Widget build(BuildContext context) {
    final ok = status.onDeviceAvailable && status.permissionsGranted;
    final ready = ok && recordReady;
    final color = ready
        ? AppPalette.accent
        : recordReady
        ? AppPalette.sky
        : AppPalette.warning;
    return Tooltip(
      message: recordReady
          ? status.message
          : 'Install the selected model before recording.',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(99),
          color: color.withValues(alpha: 0.14),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              ready
                  ? Icons.offline_bolt_rounded
                  : recordReady
                  ? Icons.mic_external_on_rounded
                  : Icons.download_for_offline_rounded,
              size: 18,
              color: color,
            ),
            const SizedBox(width: 6),
            Text(
              ready
                  ? 'Ready'
                  : recordReady
                  ? 'Check mic'
                  : 'Model needed',
            ),
          ],
        ),
      ),
    );
  }
}

class HistoryPage extends StatelessWidget {
  const HistoryPage({
    required this.searchController,
    required this.entries,
    required this.onChangedSearch,
    required this.onCopy,
    required this.onRetry,
    super.key,
  });

  final TextEditingController searchController;
  final List<TranscriptEntry> entries;
  final VoidCallback onChangedSearch;
  final ValueChanged<String> onCopy;
  final ValueChanged<TranscriptEntry> onRetry;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: EdgeInsets.fromLTRB(
        20,
        20,
        20,
        20 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      children: [
        Text('History', style: Theme.of(context).textTheme.displaySmall),
        const SizedBox(height: 14),
        TextField(
          controller: searchController,
          onChanged: (_) => onChangedSearch(),
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.search_rounded),
            hintText: 'Search transcripts, modes, or raw text',
          ),
        ),
        const SizedBox(height: 16),
        if (entries.isEmpty)
          const _MessagePanel(
            icon: Icons.history_rounded,
            title: 'No recordings yet',
            body: 'Finished dictations appear here and stay on this device.',
            color: AppPalette.sky,
          )
        else
          for (final entry in entries) ...[
            _HistoryCard(entry: entry, onCopy: onCopy, onRetry: onRetry),
            const SizedBox(height: 12),
          ],
      ],
    );
  }
}

class _HistoryCard extends StatelessWidget {
  const _HistoryCard({
    required this.entry,
    required this.onCopy,
    required this.onRetry,
  });

  final TranscriptEntry entry;
  final ValueChanged<String> onCopy;
  final ValueChanged<TranscriptEntry> onRetry;

  @override
  Widget build(BuildContext context) {
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  entry.modeName,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              Text(entry.prettyDate),
            ],
          ),
          const SizedBox(height: 10),
          Text(entry.finalText, maxLines: 4, overflow: TextOverflow.ellipsis),
          const SizedBox(height: 12),
          Row(
            children: [
              Text('${entry.duration.toStringAsFixed(1)}s'),
              const Spacer(),
              IconButton(
                tooltip: 'Re-polish',
                onPressed: () => onRetry(entry),
                icon: const Icon(Icons.auto_fix_high_rounded),
              ),
              IconButton(
                tooltip: 'Copy',
                onPressed: () => onCopy(entry.finalText),
                icon: const Icon(Icons.copy_rounded),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class ModesPage extends StatefulWidget {
  const ModesPage({
    required this.modes,
    required this.selectedMode,
    required this.onSelect,
    required this.onSaveModes,
    super.key,
  });

  final List<DictationMode> modes;
  final DictationMode selectedMode;
  final ValueChanged<DictationMode> onSelect;
  final ValueChanged<List<DictationMode>> onSaveModes;

  @override
  State<ModesPage> createState() => _ModesPageState();
}

class _ModesPageState extends State<ModesPage> {
  Future<void> _editMode([DictationMode? existing]) async {
    final name = TextEditingController(text: existing?.name ?? '');
    final instruction = TextEditingController(
      text: existing?.instruction ?? '',
    );
    final result = await showModalBottomSheet<DictationMode>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SingleChildScrollView(
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        padding: EdgeInsets.fromLTRB(
          20,
          20,
          20,
          20 + MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              existing == null ? 'New mode' : 'Edit mode',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 14),
            TextField(
              controller: name,
              decoration: const InputDecoration(labelText: 'Name'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: instruction,
              minLines: 3,
              maxLines: 6,
              decoration: const InputDecoration(
                labelText: 'Offline formatting instruction',
              ),
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: () {
                final trimmedName = name.text.trim();
                final trimmedInstruction = instruction.text.trim();
                if (trimmedName.isEmpty || trimmedInstruction.isEmpty) return;
                Navigator.pop(
                  context,
                  DictationMode(
                    id:
                        existing?.id ??
                        DateTime.now().microsecondsSinceEpoch.toString(),
                    name: trimmedName,
                    instruction: trimmedInstruction,
                    builtIn: false,
                  ),
                );
              },
              icon: const Icon(Icons.save_rounded),
              label: const Text('Save'),
            ),
          ],
        ),
      ),
    );
    if (result == null) return;
    final modes = [...widget.modes];
    final index = modes.indexWhere((mode) => mode.id == result.id);
    if (index == -1) {
      modes.add(result);
    } else {
      modes[index] = result;
    }
    widget.onSaveModes(modes);
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: EdgeInsets.fromLTRB(
        20,
        20,
        20,
        20 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                'Modes',
                style: Theme.of(context).textTheme.displaySmall,
              ),
            ),
            IconButton.filled(
              tooltip: 'Add mode',
              onPressed: () => _editMode(),
              icon: const Icon(Icons.add_rounded),
            ),
          ],
        ),
        const SizedBox(height: 14),
        _Panel(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.tune_rounded, color: AppPalette.accent),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Modes are local formatting presets applied after transcription. They do not download or switch AI models.',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        for (final mode in widget.modes) ...[
          _Panel(
            child: ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(mode.name),
              subtitle: Text(mode.instruction),
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (!mode.builtIn)
                    IconButton(
                      tooltip: 'Edit ${mode.name}',
                      onPressed: () => _editMode(mode),
                      icon: const Icon(Icons.edit_rounded),
                    ),
                  IconButton(
                    tooltip: mode.id == widget.selectedMode.id
                        ? '${mode.name} selected'
                        : 'Select ${mode.name}',
                    onPressed: () => widget.onSelect(mode),
                    icon: Icon(
                      mode.id == widget.selectedMode.id
                          ? Icons.radio_button_checked_rounded
                          : Icons.radio_button_off_rounded,
                    ),
                  ),
                ],
              ),
              onTap: () => widget.onSelect(mode),
            ),
          ),
          const SizedBox(height: 12),
        ],
      ],
    );
  }
}

class ModelsPage extends StatelessWidget {
  const ModelsPage({
    required this.models,
    required this.downloadingModelIds,
    required this.selectedModelId,
    required this.onDownload,
    required this.onCancelDownload,
    required this.onRemove,
    required this.onSelect,
    super.key,
  });

  final List<LocalModel> models;
  final Set<String> downloadingModelIds;
  final String selectedModelId;
  final ValueChanged<LocalModel> onDownload;
  final ValueChanged<LocalModel> onCancelDownload;
  final ValueChanged<LocalModel> onRemove;
  final ValueChanged<LocalModel> onSelect;

  @override
  Widget build(BuildContext context) {
    final aiModels = models
        .where((model) => model.kind != ModelKind.cleanup)
        .toList(growable: false);
    final bundled = models
        .where((model) => model.kind == ModelKind.cleanup)
        .toList(growable: false);
    final installedModels = models
        .where(
          (model) =>
              model.state == ModelInstallState.installed ||
              model.state == ModelInstallState.bundled,
        )
        .length;
    final storageBytes = models.fold<int>(
      0,
      (total, model) => total + model.installedBytes,
    );
    final recordReady = models.any(
      (model) =>
          model.id == selectedModelId &&
          model.state == ModelInstallState.installed &&
          model.kind == ModelKind.transcription &&
          model.runtime == ModelRuntime.whisperKit &&
          model.supportsIosMajor(_currentIosMajor()),
    );

    return ListView(
      padding: EdgeInsets.fromLTRB(
        20,
        20,
        20,
        20 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      children: [
        Text('Models', style: Theme.of(context).textTheme.displaySmall),
        const SizedBox(height: 8),
        Text(
          'Manage offline engines and model packs. Installed packs live on this device and can be removed anytime.',
          style: Theme.of(context).textTheme.bodyLarge,
        ),
        const SizedBox(height: 16),
        _Panel(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.memory_rounded, color: AppPalette.accent),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Choose the offline AI model pack used for recording. The cleanup engine is bundled rule-based post-processing, not a downloaded AI model.',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        _ModelsSummary(
          installedModels: installedModels,
          storageBytes: storageBytes,
          recordReady: recordReady,
        ),
        const SizedBox(height: 18),
        Text('AI model packs', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        for (final model in aiModels) ...[
          _ModelCard(
            model: model,
            iosMajorVersion: _currentIosMajor(),
            isSelected: selectedModelId == model.id,
            isDownloading: downloadingModelIds.contains(model.id),
            onDownload: onDownload,
            onCancelDownload: onCancelDownload,
            onRemove: onRemove,
            onSelect: onSelect,
          ),
          const SizedBox(height: 12),
        ],
        const SizedBox(height: 8),
        Text('Bundled engines', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        for (final model in bundled) ...[
          _ModelCard(
            model: model,
            iosMajorVersion: _currentIosMajor(),
            isSelected: selectedModelId == model.id,
            isDownloading: downloadingModelIds.contains(model.id),
            onDownload: onDownload,
            onCancelDownload: onCancelDownload,
            onRemove: onRemove,
            onSelect: onSelect,
          ),
          const SizedBox(height: 12),
        ],
      ],
    );
  }
}

int _currentIosMajor() {
  if (!Platform.isIOS) return 99;
  final match = RegExp(
    r'(?:Version |OS )(\d+)',
  ).firstMatch(Platform.operatingSystemVersion);
  return int.tryParse(match?.group(1) ?? '') ?? 14;
}

class _ModelsSummary extends StatelessWidget {
  const _ModelsSummary({
    required this.installedModels,
    required this.storageBytes,
    required this.recordReady,
  });

  final int installedModels;
  final int storageBytes;
  final bool recordReady;

  @override
  Widget build(BuildContext context) {
    return _Panel(
      child: Row(
        children: [
          _SummaryMetric(
            icon: Icons.inventory_2_rounded,
            label: 'Installed',
            value: '$installedModels',
          ),
          const SizedBox(width: 12),
          _SummaryMetric(
            icon: Icons.sd_storage_rounded,
            label: 'Storage',
            value: storageBytes == 0 ? '0 MB' : _formatBytes(storageBytes),
          ),
          const SizedBox(width: 12),
          _SummaryMetric(
            icon: recordReady
                ? Icons.mic_external_on_rounded
                : Icons.download_for_offline_rounded,
            label: 'Recorder',
            value: recordReady ? 'Ready' : 'Needs pack',
          ),
        ],
      ),
    );
  }
}

class _SummaryMetric extends StatelessWidget {
  const _SummaryMetric({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Semantics(
        label: '$label $value',
        child: ExcludeSemantics(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: AppPalette.accent, size: 20),
              const SizedBox(height: 8),
              Text(value, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 2),
              Text(label, style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
      ),
    );
  }
}

class _ModelCard extends StatelessWidget {
  const _ModelCard({
    required this.model,
    required this.iosMajorVersion,
    required this.isSelected,
    required this.isDownloading,
    required this.onDownload,
    required this.onCancelDownload,
    required this.onRemove,
    required this.onSelect,
  });

  final LocalModel model;
  final int iosMajorVersion;
  final bool isSelected;
  final bool isDownloading;
  final ValueChanged<LocalModel> onDownload;
  final ValueChanged<LocalModel> onCancelDownload;
  final ValueChanged<LocalModel> onRemove;
  final ValueChanged<LocalModel> onSelect;

  @override
  Widget build(BuildContext context) {
    final stateLabel = switch (model.state) {
      ModelInstallState.bundled => 'Bundled',
      ModelInstallState.installed => 'Installed',
      ModelInstallState.notInstalled => 'Not installed',
      ModelInstallState.downloading => 'Downloading',
      ModelInstallState.unavailable => 'Unavailable',
    };
    final effectiveLabel =
        isSelected && model.state != ModelInstallState.notInstalled
        ? 'Selected'
        : stateLabel;
    final canSelect =
        model.kind == ModelKind.transcription &&
        model.state != ModelInstallState.notInstalled &&
        model.state != ModelInstallState.unavailable &&
        model.supportsIosMajor(iosMajorVersion) &&
        model.runtime == ModelRuntime.whisperKit &&
        !isDownloading;
    final runtimeLabel = switch (model.runtime) {
      ModelRuntime.mlx => 'MLX',
      ModelRuntime.coreMl => 'Core ML',
      ModelRuntime.whisperKit => 'WhisperKit',
      ModelRuntime.bundled => 'Bundled',
    };
    final unavailableReason = !model.supportsIosMajor(iosMajorVersion)
        ? 'Requires iOS ${model.minimumIosMajor}+.'
        : model.kind == ModelKind.transcription &&
              model.state == ModelInstallState.installed &&
              model.runtime != ModelRuntime.whisperKit
        ? 'Installed pack. Native iOS runtime adapter still required.'
        : null;
    final actions = _modelActionButtons(
      model: model,
      isSelected: isSelected,
      isDownloading: isDownloading,
      canSelect: canSelect,
      onDownload: onDownload,
      onCancelDownload: onCancelDownload,
      onRemove: onRemove,
      onSelect: onSelect,
    );

    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(switch (model.kind) {
                ModelKind.transcription => Icons.graphic_eq_rounded,
                ModelKind.tts => Icons.spatial_audio_off_rounded,
                ModelKind.cleanup => Icons.offline_bolt_rounded,
              }),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  model.name,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              Chip(label: Text(effectiveLabel)),
            ],
          ),
          const SizedBox(height: 10),
          Text(model.description),
          if (model.installNote.isNotEmpty && unavailableReason == null) ...[
            const SizedBox(height: 8),
            Text(
              model.installNote,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
          if (unavailableReason != null) ...[
            const SizedBox(height: 8),
            _InlineNotice(text: unavailableReason),
          ],
          const SizedBox(height: 12),
          if (isDownloading ||
              model.state == ModelInstallState.downloading) ...[
            LinearProgressIndicator(
              value: model.progress == 0 ? null : model.progress,
              semanticsLabel: '${model.name} download progress',
            ),
            const SizedBox(height: 10),
          ],
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _MetaChip(text: model.sizeLabel),
              _MetaChip(text: runtimeLabel),
              _MetaChip(text: 'iOS ${model.minimumIosMajor}+'),
              if (model.installedFiles > 0)
                _MetaChip(text: '${model.installedFiles} files'),
              if (model.installedBytes > 0)
                _MetaChip(text: _formatBytes(model.installedBytes)),
            ],
          ),
          const SizedBox(height: 14),
          Align(
            alignment: Alignment.centerRight,
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              alignment: WrapAlignment.end,
              children: actions,
            ),
          ),
        ],
      ),
    );
  }
}

class _MetaChip extends StatelessWidget {
  const _MetaChip({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Chip(
      visualDensity: VisualDensity.compact,
      label: Text(text),
      side: BorderSide(color: Colors.white.withValues(alpha: 0.08)),
      backgroundColor: Colors.white.withValues(alpha: 0.04),
    );
  }
}

List<Widget> _modelActionButtons({
  required LocalModel model,
  required bool isSelected,
  required bool isDownloading,
  required bool canSelect,
  required ValueChanged<LocalModel> onDownload,
  required ValueChanged<LocalModel> onCancelDownload,
  required ValueChanged<LocalModel> onRemove,
  required ValueChanged<LocalModel> onSelect,
}) {
  if (isDownloading || model.state == ModelInstallState.downloading) {
    return [
      _ActionSemantics(
        label: 'Cancel ${model.name} download',
        child: OutlinedButton.icon(
          onPressed: () => onCancelDownload(model),
          icon: const Icon(Icons.close_rounded),
          label: const Text('Cancel'),
        ),
      ),
    ];
  }

  if (model.canDownload) {
    return [
      _ActionSemantics(
        label: 'Download ${model.name}',
        child: FilledButton.icon(
          onPressed: () => onDownload(model),
          icon: const Icon(Icons.download_rounded),
          label: const Text('Download'),
        ),
      ),
    ];
  }

  final actions = <Widget>[];
  if (canSelect) {
    actions.add(
      _ActionSemantics(
        label: isSelected ? '${model.name} selected' : 'Use ${model.name}',
        child: FilledButton.icon(
          onPressed: isSelected ? null : () => onSelect(model),
          icon: const Icon(Icons.check_circle_rounded),
          label: Text(isSelected ? 'Selected' : 'Use'),
        ),
      ),
    );
  }
  if (model.canRemove) {
    actions.add(
      _ActionSemantics(
        label: 'Remove ${model.name}',
        child: OutlinedButton.icon(
          onPressed: () => onRemove(model),
          icon: const Icon(Icons.delete_outline_rounded),
          label: const Text('Remove'),
        ),
      ),
    );
  }
  if (actions.isEmpty) {
    actions.add(const Text('Always available'));
  }
  return actions;
}

class _ActionSemantics extends StatelessWidget {
  const _ActionSemantics({required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      container: true,
      button: true,
      label: label,
      child: Tooltip(
        message: label,
        excludeFromSemantics: true,
        child: ExcludeSemantics(child: child),
      ),
    );
  }
}

class SettingsPage extends StatelessWidget {
  const SettingsPage({
    required this.settings,
    required this.status,
    required this.keyboardStatus,
    required this.onChanged,
    required this.onRefreshStatus,
    required this.onRunSetup,
    super.key,
  });

  final AppSettings settings;
  final NativeSpeechStatus status;
  final KeyboardSetupStatus keyboardStatus;
  final ValueChanged<AppSettings> onChanged;
  final VoidCallback onRefreshStatus;
  final VoidCallback onRunSetup;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: EdgeInsets.fromLTRB(
        20,
        20,
        20,
        20 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                'Settings',
                style: Theme.of(context).textTheme.displaySmall,
              ),
            ),
            IconButton(
              tooltip: 'Refresh status',
              onPressed: onRefreshStatus,
              icon: const Icon(Icons.refresh_rounded),
            ),
          ],
        ),
        const SizedBox(height: 14),
        _Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Setup guide',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              Text(
                'Replay the first-run guide for model, microphone, and keyboard setup.',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 14),
              FilledButton.icon(
                onPressed: onRunSetup,
                icon: const Icon(Icons.play_circle_rounded),
                label: const Text('Run setup again'),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        _Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Privacy', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 10),
              _PresetSelector(settings: settings, onChanged: onChanged),
              const Divider(height: 28),
              DropdownButtonFormField<String>(
                initialValue: settings.localeId,
                decoration: const InputDecoration(
                  labelText: 'Transcription language',
                ),
                items: const [
                  DropdownMenuItem(value: 'en-US', child: Text('English US')),
                  DropdownMenuItem(value: 'en-GB', child: Text('English UK')),
                  DropdownMenuItem(value: 'de-DE', child: Text('German')),
                  DropdownMenuItem(value: 'fa-IR', child: Text('Persian')),
                  DropdownMenuItem(value: 'fr-FR', child: Text('French')),
                  DropdownMenuItem(value: 'es-ES', child: Text('Spanish')),
                ],
                onChanged: (value) {
                  if (value != null) {
                    onChanged(settings.copyWith(localeId: value));
                  }
                },
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        _Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Output', style: Theme.of(context).textTheme.titleLarge),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                secondary: const Icon(Icons.copy_rounded),
                title: const Text('Auto-copy result'),
                subtitle: const Text('Copy finished text after every run.'),
                value: settings.autoCopy,
                onChanged: (value) =>
                    onChanged(settings.copyWith(autoCopy: value)),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                secondary: const Icon(Icons.auto_fix_high_rounded),
                title: const Text('Smart punctuation cleanup'),
                subtitle: const Text('Turn spoken punctuation into symbols.'),
                value: settings.smartPunctuation,
                onChanged: (value) =>
                    onChanged(settings.copyWith(smartPunctuation: value)),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                secondary: const Icon(Icons.cleaning_services_rounded),
                title: const Text('Remove filler words'),
                subtitle: const Text('Drop ums and uhs during local cleanup.'),
                value: settings.removeFillers,
                onChanged: (value) =>
                    onChanged(settings.copyWith(removeFillers: value)),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        _Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Keyboard', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              _InlineNotice(text: keyboardStatus.message),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                secondary: const Icon(Icons.vibration_rounded),
                title: const Text('Keyboard haptics'),
                subtitle: const Text('Used by the Local Whisper keyboard.'),
                value: settings.keyboardHaptics,
                onChanged: (value) =>
                    onChanged(settings.copyWith(keyboardHaptics: value)),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                secondary: const Icon(Icons.bolt_rounded),
                title: const Text('Keyboard quick insert'),
                subtitle: const Text('Show punctuation and mode shortcuts.'),
                value: settings.keyboardQuickInsert,
                onChanged: (value) =>
                    onChanged(settings.copyWith(keyboardQuickInsert: value)),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        _Panel(
          child: ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            leading: const Icon(Icons.timer_rounded),
            title: Text(
              'Recording limits',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            subtitle: const Text('Tune short clip rejection and auto-stop.'),
            children: [
              const SizedBox(height: 8),
              _NumberSetting(
                label: 'Min seconds',
                value: settings.minRecordingSeconds,
                onChanged: (value) =>
                    onChanged(settings.copyWith(minRecordingSeconds: value)),
              ),
              _NumberSetting(
                label: 'Max seconds',
                value: settings.maxRecordingSeconds.toDouble(),
                onChanged: (value) => onChanged(
                  settings.copyWith(maxRecordingSeconds: value.round()),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        _MessagePanel(
          icon: status.onDeviceAvailable
              ? Icons.offline_bolt_rounded
              : Icons.warning_amber_rounded,
          title: status.onDeviceAvailable
              ? 'Offline engine available'
              : 'Offline engine unavailable',
          body: status.message,
          color: status.onDeviceAvailable
              ? AppPalette.accent
              : AppPalette.warning,
        ),
      ],
    );
  }
}

class _PresetSelector extends StatelessWidget {
  const _PresetSelector({required this.settings, required this.onChanged});

  final AppSettings settings;
  final ValueChanged<AppSettings> onChanged;

  @override
  Widget build(BuildContext context) {
    final compact = !settings.autoCopy && !settings.removeFillers;
    final balanced =
        settings.autoCopy &&
        settings.smartPunctuation &&
        settings.removeFillers;
    final active = compact
        ? 'Manual'
        : balanced
        ? 'Balanced'
        : 'Custom';

    return SegmentedButton<String>(
      segments: const [
        ButtonSegment(
          value: 'Balanced',
          icon: Icon(Icons.auto_awesome_rounded),
          label: Text('Auto'),
        ),
        ButtonSegment(
          value: 'Manual',
          icon: Icon(Icons.back_hand_rounded),
          label: Text('Manual'),
        ),
        ButtonSegment(
          value: 'Custom',
          icon: Icon(Icons.tune_rounded),
          label: Text('Custom'),
        ),
      ],
      selected: {active},
      onSelectionChanged: (selection) {
        final value = selection.single;
        if (value == 'Balanced') {
          onChanged(
            settings.copyWith(
              autoCopy: true,
              smartPunctuation: true,
              removeFillers: true,
            ),
          );
        } else if (value == 'Manual') {
          onChanged(
            settings.copyWith(
              autoCopy: false,
              smartPunctuation: true,
              removeFillers: false,
            ),
          );
        }
      },
    );
  }
}

class _NumberSetting extends StatelessWidget {
  const _NumberSetting({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final double value;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    final displayValue = label.startsWith('Max')
        ? _formatDurationSeconds(value.round())
        : '${value.toStringAsFixed(1)}s';
    return Row(
      children: [
        SizedBox(width: 112, child: Text(label)),
        Expanded(
          child: Semantics(
            label: label,
            value: displayValue,
            child: Slider(
              min: label.startsWith('Min') ? 0.3 : 10,
              max: label.startsWith('Min') ? 5 : 1200,
              divisions: label.startsWith('Min') ? 47 : 119,
              value: value,
              onChanged: onChanged,
            ),
          ),
        ),
        SizedBox(
          width: 72,
          child: Text(displayValue, textAlign: TextAlign.end),
        ),
      ],
    );
  }
}

String _formatDurationSeconds(int seconds) {
  if (seconds < 60) return '${seconds}s';
  final minutes = seconds ~/ 60;
  final remainder = seconds % 60;
  if (remainder == 0) return '${minutes}m';
  return '${minutes}m ${remainder}s';
}

class _InlineNotice extends StatelessWidget {
  const _InlineNotice({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF211A12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: const Color(0xFFE0A445).withValues(alpha: 0.35),
        ),
      ),
      child: Text(text, style: Theme.of(context).textTheme.bodySmall),
    );
  }
}

String _formatBytes(int bytes) {
  const units = ['B', 'KB', 'MB', 'GB'];
  var size = bytes.toDouble();
  var unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  final decimals = unit == 0 || size >= 10 ? 0 : 1;
  return '${size.toStringAsFixed(decimals)} ${units[unit]}';
}

class _Panel extends StatelessWidget {
  const _Panel({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppPalette.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: child,
    );
  }
}

class AppTheme {
  static ThemeData dark() {
    final scheme = ColorScheme.fromSeed(
      seedColor: AppPalette.accent,
      brightness: Brightness.dark,
      surface: AppPalette.background,
    );
    return ThemeData(
      colorScheme: scheme,
      useMaterial3: true,
      scaffoldBackgroundColor: AppPalette.background,
      navigationBarTheme: const NavigationBarThemeData(
        backgroundColor: AppPalette.nav,
        indicatorColor: Color(0xFF254237),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppPalette.surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.08)),
        ),
      ),
      textTheme: const TextTheme(
        displaySmall: TextStyle(fontSize: 34, fontWeight: FontWeight.w800),
        headlineSmall: TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
        titleLarge: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
        titleMedium: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
        bodyLarge: TextStyle(fontSize: 16, color: AppPalette.textSoft),
      ),
    );
  }
}
