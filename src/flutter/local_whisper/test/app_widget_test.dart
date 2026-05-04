import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:local_whisper_flutter/src/app.dart';
import 'package:local_whisper_flutter/src/model_store.dart';
import 'package:local_whisper_flutter/src/models.dart';
import 'package:local_whisper_flutter/src/setup_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _speechChannel = MethodChannel('local_whisper/speech');
const _levelsChannel = EventChannel('local_whisper/levels');
const _setupChannel = MethodChannel('local_whisper/setup');

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  late String installedModelPath;
  late Map<String, Object?>? startPayload;
  var permissionsGranted = true;
  var openedSettings = false;
  var keyboardSeen = false;
  var stopTranscript = 'um hello comma this is local whisper period';
  var stopDuration = 2.2;

  setUp(() async {
    tempDir = await Directory.systemTemp.createTemp('local-whisper-widget-');
    installedModelPath = await _createInstalledWhisperKitModel(tempDir);
    startPayload = null;
    permissionsGranted = true;
    openedSettings = false;
    keyboardSeen = false;
    stopTranscript = 'um hello comma this is local whisper period';
    stopDuration = 2.2;

    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_speechChannel, (call) async {
          switch (call.method) {
            case 'status':
              final args = Map<Object?, Object?>.from(
                call.arguments as Map<Object?, Object?>? ?? const {},
              );
              return {
                'permissionsGranted': permissionsGranted,
                'onDeviceAvailable': true,
                'recognitionAvailable': true,
                'localeId': args['locale'] ?? 'en-US',
                'message': permissionsGranted
                    ? 'Local Whisper is ready.'
                    : 'Microphone permission is not granted yet.',
              };
            case 'requestPermissions':
              return permissionsGranted;
            case 'start':
              startPayload = Map<String, Object?>.from(
                call.arguments as Map<Object?, Object?>,
              );
              return null;
            case 'stop':
              return {
                'transcript': stopTranscript,
                'rawTranscript': stopTranscript,
                'duration': stopDuration,
                'localeId': startPayload?['locale'] ?? 'en-US',
                'onDevice': true,
              };
            case 'cancel':
              return null;
          }
          throw PlatformException(code: 'missing', message: call.method);
        });

    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_setupChannel, (call) async {
          switch (call.method) {
            case 'openKeyboardSettings':
              openedSettings = true;
              return true;
            case 'openAppSettings':
              openedSettings = true;
              return true;
            case 'keyboardStatus':
              return {
                'keyboardSeen': keyboardSeen,
                'message': keyboardSeen
                    ? 'Local Whisper Keyboard was opened and verified.'
                    : 'Keyboard has not been verified yet. Add it in Settings, switch to it in the practice field, then tap Verify on the keyboard.',
              };
            case 'markKeyboardSeen':
              keyboardSeen = true;
              return null;
          }
          throw PlatformException(code: 'missing', message: call.method);
        });

    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockStreamHandler(
          _levelsChannel,
          MockStreamHandler.inline(
            onListen: (_, events) {
              events.success(0.32);
            },
          ),
        );
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      ..setMockMethodCallHandler(_speechChannel, null)
      ..setMockMethodCallHandler(_setupChannel, null)
      ..setMockStreamHandler(_levelsChannel, null);
    if (await tempDir.exists()) {
      await tempDir.delete(recursive: true);
    }
  });

  testWidgets('all primary tabs render and expose their core controls', (
    tester,
  ) async {
    await _pumpApp(
      tester,
      installedModelPath: installedModelPath,
      onboardingComplete: true,
    );

    expect(find.text('Local Whisper'), findsOneWidget);
    expect(find.text('Start talking'), findsOneWidget);
    expect(find.text('Private by default'), findsOneWidget);

    await tester.tap(find.text('History'));
    await tester.pumpAndSettle();
    expect(find.text('History'), findsWidgets);
    expect(find.byType(TextField), findsOneWidget);
    expect(find.text('No recordings yet'), findsOneWidget);

    await tester.tap(find.text('Modes'));
    await tester.pumpAndSettle();
    expect(find.byTooltip('Add mode'), findsOneWidget);
    expect(find.text('Clean Dictation'), findsOneWidget);
    expect(find.text('Message'), findsOneWidget);
    expect(find.text('Notes'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Prompt'), 160);
    expect(find.text('Prompt'), findsOneWidget);

    await tester.tap(find.text('Models'));
    await tester.pumpAndSettle();
    expect(find.text('Installed'), findsOneWidget);
    expect(find.text('Storage'), findsOneWidget);
    expect(find.text('Recorder'), findsOneWidget);
    expect(find.text('Qwen3-ASR'), findsOneWidget);
    expect(find.bySemanticsLabel('Download Qwen3-ASR'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Parakeet-TDT v3'), 200);
    expect(find.text('Parakeet-TDT v3'), findsOneWidget);
    expect(find.bySemanticsLabel('Download Parakeet-TDT v3'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Kokoro-82M TTS'), 240);
    expect(find.text('Kokoro-82M TTS'), findsOneWidget);
    expect(find.bySemanticsLabel('Download Kokoro-82M TTS'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('WhisperKit Large v3'), 240);
    expect(find.text('WhisperKit Large v3'), findsOneWidget);
    expect(
      find.bySemanticsLabel('WhisperKit Large v3 selected'),
      findsOneWidget,
    );
    expect(find.bySemanticsLabel('Remove WhisperKit Large v3'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Local Cleanup Engine'), 240);
    expect(find.text('Local Cleanup Engine'), findsOneWidget);

    await tester.tap(find.text('Settings'));
    await tester.pumpAndSettle();
    expect(find.text('Setup guide'), findsOneWidget);
    expect(find.text('Privacy'), findsOneWidget);
    expect(find.byTooltip('Refresh status'), findsOneWidget);
    expect(find.text('Transcription language'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Recording limits'), 160);
    expect(find.text('Recording limits'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Auto-copy result'), -160);
    expect(find.text('Auto-copy result'), findsOneWidget);
    expect(find.text('Smart punctuation cleanup'), findsOneWidget);
    expect(find.text('Remove filler words'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Keyboard'), 180);
    expect(find.text('Keyboard haptics'), findsOneWidget);
    expect(find.text('Keyboard quick insert'), findsOneWidget);
  });

  testWidgets('first launch shows onboarding and persists completion', (
    tester,
  ) async {
    await _pumpApp(tester, installedModelPath: installedModelPath);

    expect(find.text('Set up Local Whisper'), findsOneWidget);
    expect(find.text('Private voice, ready everywhere.'), findsOneWidget);

    await tester.tap(find.text('Start setup'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Use without keyboard'));
    await tester.pumpAndSettle();
    expect(find.text('Start talking'), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
    await _pumpApp(
      tester,
      installedModelPath: installedModelPath,
      resetPreferences: false,
    );
    expect(find.text('Set up Local Whisper'), findsNothing);
    expect(find.text('Start talking'), findsOneWidget);
  });

  testWidgets('settings can replay setup and open keyboard settings', (
    tester,
  ) async {
    await _pumpApp(
      tester,
      installedModelPath: installedModelPath,
      onboardingComplete: true,
    );

    await tester.tap(find.text('Settings'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Run setup again'));
    await tester.pumpAndSettle();

    expect(find.text('Set up Local Whisper'), findsOneWidget);
    await tester.tap(find.text('Start setup'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Enable Local Whisper Keyboard'), findsOneWidget);

    await tester.tap(find.text('Open Settings'));
    await tester.pumpAndSettle();
    expect(openedSettings, isTrue);
    expect(
      find.textContaining('Keyboard has not been verified yet.'),
      findsAtLeastNWidgets(1),
    );
  });

  testWidgets('model choices open inline during setup', (tester) async {
    await _pumpApp(tester, installedModelPath: null);

    await tester.tap(find.text('Start setup'));
    await tester.pumpAndSettle();
    expect(find.text('Install a model pack'), findsOneWidget);

    await tester.tap(find.text('More choices'));
    await tester.pumpAndSettle();

    expect(find.text('Model packs'), findsOneWidget);
    expect(find.text('Qwen3-ASR'), findsOneWidget);
    expect(find.text('Parakeet-TDT v3'), findsOneWidget);
    expect(find.text('WhisperKit Large v3'), findsWidgets);
    expect(find.text('Set up Local Whisper'), findsOneWidget);
  });

  testWidgets('keyboard verification updates onboarding state', (tester) async {
    await _pumpApp(tester, installedModelPath: installedModelPath);

    await tester.tap(find.text('Start setup'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Waiting for keyboard'), findsOneWidget);

    await tester.enterText(find.byType(TextField), keyboardVerificationToken);
    await tester.pumpAndSettle();

    expect(find.text('Keyboard verified'), findsOneWidget);
    expect(
      find.text('Local Whisper Keyboard was opened and verified.'),
      findsOneWidget,
    );
  });

  testWidgets('recording uses the installed model folder and saves history', (
    tester,
  ) async {
    await _pumpApp(
      tester,
      installedModelPath: installedModelPath,
      onboardingComplete: true,
    );

    await tester.tap(find.widgetWithIcon(FilledButton, Icons.mic_rounded));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Listening'), findsOneWidget);
    expect(find.text('Cancel'), findsOneWidget);
    expect(startPayload?['model'], 'whisperkit_large_v3_turbo');
    expect(startPayload?['modelPath'], installedModelPath);
    expect(startPayload?['locale'], 'en-US');

    await tester.tap(find.widgetWithIcon(FilledButton, Icons.stop_rounded));
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 100));
    });
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('Ready'), findsWidgets);
    expect(find.text('Hello, this is local whisper.'), findsOneWidget);
    expect(find.byTooltip('Copy'), findsOneWidget);

    await tester.tap(find.text('History'));
    await tester.pumpAndSettle();
    expect(find.text('Clean Dictation'), findsWidgets);
    expect(find.text('Hello, this is local whisper.'), findsOneWidget);
    expect(find.byTooltip('Re-polish'), findsOneWidget);
  });

  testWidgets('short and empty recordings show actionable errors', (
    tester,
  ) async {
    await _pumpApp(
      tester,
      installedModelPath: installedModelPath,
      onboardingComplete: true,
    );

    stopDuration = 0.1;
    await tester.tap(find.widgetWithIcon(FilledButton, Icons.mic_rounded));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.widgetWithIcon(FilledButton, Icons.stop_rounded));
    await tester.pumpAndSettle();
    expect(find.text('Needs attention'), findsOneWidget);
    expect(find.textContaining('Recording was too short'), findsOneWidget);

    stopDuration = 2;
    stopTranscript = '   ';
    await tester.tap(find.widgetWithIcon(FilledButton, Icons.mic_rounded));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.widgetWithIcon(FilledButton, Icons.stop_rounded));
    await tester.pumpAndSettle();
    expect(find.text('No speech was detected.'), findsOneWidget);
  });

  testWidgets('custom modes can be selected and used', (tester) async {
    await _pumpApp(
      tester,
      installedModelPath: installedModelPath,
      onboardingComplete: true,
      modes: [
        ...DictationMode.defaults,
        const DictationMode(
          id: 'ship-note',
          name: 'Ship Note',
          instruction: 'Make it a crisp release note.',
        ),
      ],
    );

    await tester.tap(find.text('Modes'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Ship Note'), 200);
    await tester.drag(find.byType(ListView), const Offset(0, -160));
    await tester.pumpAndSettle();
    expect(find.text('Ship Note'), findsOneWidget);

    await tester.tap(
      find.ancestor(
        of: find.text('Ship Note'),
        matching: find.byType(ListTile),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Record'));
    await tester.pumpAndSettle();
    expect(find.textContaining('using Ship Note'), findsOneWidget);
  });

  testWidgets('missing model turns the record action into install guidance', (
    tester,
  ) async {
    await _pumpApp(tester, installedModelPath: null, onboardingComplete: true);

    expect(find.text('Model needed'), findsWidgets);
    expect(find.text('Install model'), findsOneWidget);
    expect(find.text('Install model first'), findsOneWidget);

    await tester.tap(
      find.widgetWithIcon(FilledButton, Icons.download_for_offline_rounded),
    );
    await tester.pumpAndSettle();
    expect(find.text('Models'), findsWidgets);
    await tester.scrollUntilVisible(find.text('WhisperKit Large v3'), 240);
    expect(find.text('WhisperKit Large v3'), findsWidgets);
    expect(startPayload, isNull);
  });
}

Future<void> _pumpApp(
  WidgetTester tester, {
  required String? installedModelPath,
  List<DictationMode>? modes,
  bool onboardingComplete = false,
  bool resetPreferences = true,
}) async {
  if (resetPreferences) {
    SharedPreferences.resetStatic();
    SharedPreferences.setMockInitialValues({
      if (onboardingComplete) 'onboarding.v1': true,
      if (modes != null)
        'modes.v1': jsonEncode(modes.map((mode) => mode.toJson()).toList()),
      if (installedModelPath != null)
        'models.v1': jsonEncode([
          for (final model in ModelStore.catalog)
            model.id == 'whisperkit_large_v3_turbo'
                ? model
                      .copyWith(
                        state: ModelInstallState.installed,
                        localPath: installedModelPath,
                        installedBytes: 11,
                        installedFiles: 1,
                        progress: 1,
                      )
                      .toJson()
                : model.toJson(),
        ]),
    });
  }
  await tester.pumpWidget(
    LocalWhisperApp(
      initialModes: modes,
      initialModels: [
        for (final model in ModelStore.catalog)
          model.id == 'whisperkit_large_v3_turbo' && installedModelPath != null
              ? model.copyWith(
                  state: ModelInstallState.installed,
                  localPath: installedModelPath,
                  installedBytes: 16,
                  installedFiles: 1,
                  progress: 1,
                )
              : model,
      ],
    ),
  );
  await tester.runAsync(() async {
    await Future<void>.delayed(const Duration(milliseconds: 500));
  });
  await tester.pumpAndSettle();
}

Future<String> _createInstalledWhisperKitModel(Directory tempDir) async {
  final modelDir = Directory('${tempDir.path}/whisperkit_large_v3_turbo');
  await modelDir.create(recursive: true);
  final file = File('${modelDir.path}/config.json');
  await file.writeAsString('{"model":"test"}');
  final configSize = await file.length();
  final manifest = File('${modelDir.path}/local-whisper-model.json');
  await manifest.writeAsString(
    jsonEncode({
      'id': 'whisperkit_large_v3_turbo',
      'name': 'WhisperKit Large v3',
      'repoId': 'argmaxinc/whisperkit-coreml',
      'revision': 'main',
      'runtime': 'whisperKit',
      'minimumIosMajor': 14,
      'files': [
        {
          'sourcePath': 'openai_whisper-large-v3-v20240930_547MB/config.json',
          'path': 'config.json',
          'size': configSize,
        },
      ],
    }),
  );
  return modelDir.path;
}
