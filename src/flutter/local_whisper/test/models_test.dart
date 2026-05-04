import 'package:flutter_test/flutter_test.dart';
import 'dart:convert';
import 'dart:io';
import 'package:local_whisper_flutter/src/history_store.dart';
import 'package:local_whisper_flutter/src/model_store.dart';
import 'package:local_whisper_flutter/src/models.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('settings round-trip preserves offline dictation controls', () {
    const settings = AppSettings(
      localeId: 'de-DE',
      selectedModeId: 'notes',
      selectedModelId: 'parakeet_tdt_v3',
      autoCopy: false,
      smartPunctuation: false,
      removeFillers: false,
      minRecordingSeconds: 1.2,
      maxRecordingSeconds: 42,
    );

    final roundTrip = AppSettings.fromJson(settings.toJson());

    expect(roundTrip.localeId, 'de-DE');
    expect(roundTrip.selectedModeId, 'notes');
    expect(roundTrip.selectedModelId, 'parakeet_tdt_v3');
    expect(roundTrip.autoCopy, isFalse);
    expect(roundTrip.smartPunctuation, isFalse);
    expect(roundTrip.removeFillers, isFalse);
    expect(roundTrip.minRecordingSeconds, 1.2);
    expect(roundTrip.maxRecordingSeconds, 42);
  });

  test(
    'native status parsing keeps the offline availability flag explicit',
    () {
      final status = NativeSpeechStatus.fromJson({
        'permissionsGranted': true,
        'onDeviceAvailable': false,
        'recognitionAvailable': true,
        'localeId': 'fa-IR',
        'message': 'Microphone permission is not granted yet.',
      });

      expect(status.permissionsGranted, isTrue);
      expect(status.onDeviceAvailable, isFalse);
      expect(status.recognitionAvailable, isTrue);
      expect(status.localeId, 'fa-IR');
    },
  );

  test('model metadata tracks install and removal capability', () {
    const model = LocalModel(
      id: 'whisperkit_large_v3_turbo',
      name: 'WhisperKit Large v3',
      kind: ModelKind.transcription,
      description: 'Offline model pack',
      sizeLabel: 'Download pack',
      state: ModelInstallState.notInstalled,
      runtime: ModelRuntime.whisperKit,
      minimumIosMajor: 14,
      downloadUrl: 'https://example.invalid/model.zip',
    );

    expect(model.canDownload, isTrue);
    expect(model.canRemove, isFalse);

    final installed = model.copyWith(
      state: ModelInstallState.installed,
      localPath: '/tmp/model.zip',
      installedBytes: 42,
    );

    expect(installed.canDownload, isFalse);
    expect(installed.canRemove, isTrue);
    expect(LocalModel.fromJson(installed.toJson()).installedBytes, 42);
    expect(installed.supportsIosMajor(14), isTrue);
  });

  test('model state keeps verified installed model packs', () async {
    final tempDir = await Directory.systemTemp.createTemp(
      'local-whisper-model-state-',
    );
    addTearDown(() async {
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
      SharedPreferences.resetStatic();
    });

    final modelDir = Directory('${tempDir.path}/whisperkit_large_v3_turbo');
    await modelDir.create(recursive: true);
    final config = File('${modelDir.path}/config.json');
    await config.writeAsString('{"model":"test"}');
    await File('${modelDir.path}/local-whisper-model.json').writeAsString(
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
            'size': await config.length(),
          },
        ],
      }),
    );

    SharedPreferences.resetStatic();
    SharedPreferences.setMockInitialValues({
      'models.v1': jsonEncode([
        for (final model in ModelStore.catalog)
          model.id == 'whisperkit_large_v3_turbo'
              ? model
                    .copyWith(
                      state: ModelInstallState.installed,
                      localPath: modelDir.path,
                      installedBytes: await config.length(),
                      installedFiles: 1,
                      progress: 1,
                    )
                    .toJson()
              : model.toJson(),
      ]),
    });

    final models = await ModelStore(
      HistoryStore(),
      modelDirectory: tempDir,
    ).loadModels();
    final whisperKit = models.firstWhere(
      (model) => model.id == 'whisperkit_large_v3_turbo',
    );

    expect(whisperKit.state, ModelInstallState.installed);
    expect(whisperKit.localPath, modelDir.path);
  });

  test(
    'model state rediscovers verified model folders when prefs are stale',
    () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'local-whisper-model-discovery-',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
        SharedPreferences.resetStatic();
      });

      final modelDir = Directory('${tempDir.path}/parakeet_tdt_v3');
      await modelDir.create(recursive: true);
      final modelFile = File('${modelDir.path}/model.safetensors');
      await modelFile.writeAsString('actual model bytes');
      await File('${modelDir.path}/local-whisper-model.json').writeAsString(
        jsonEncode({
          'id': 'parakeet_tdt_v3',
          'repoId': 'mlx-community/parakeet-tdt-0.6b-v3',
          'files': [
            {'path': 'model.safetensors', 'size': await modelFile.length()},
          ],
        }),
      );

      SharedPreferences.resetStatic();
      SharedPreferences.setMockInitialValues({
        'models.v1': jsonEncode([
          for (final model in ModelStore.catalog) model.toJson(),
        ]),
      });

      final models = await ModelStore(
        HistoryStore(),
        modelDirectory: tempDir,
      ).loadModels();
      final parakeet = models.firstWhere(
        (model) => model.id == 'parakeet_tdt_v3',
      );

      expect(parakeet.state, ModelInstallState.installed);
      expect(parakeet.localPath, modelDir.path);
      expect(parakeet.installedFiles, 1);
      expect(parakeet.installedBytes, greaterThan(0));
    },
  );

  test(
    'model state repairs installed prefs that point at an old container',
    () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'local-whisper-model-repair-',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
        SharedPreferences.resetStatic();
      });

      final modelDir = Directory('${tempDir.path}/whisperkit_large_v3_turbo');
      await modelDir.create(recursive: true);
      final modelFile = File('${modelDir.path}/config.json');
      await modelFile.writeAsString('{"model":"test"}');
      await File('${modelDir.path}/local-whisper-model.json').writeAsString(
        jsonEncode({
          'id': 'whisperkit_large_v3_turbo',
          'repoId': 'argmaxinc/whisperkit-coreml',
          'files': [
            {'path': 'config.json', 'size': await modelFile.length()},
          ],
        }),
      );

      SharedPreferences.resetStatic();
      SharedPreferences.setMockInitialValues({
        'models.v1': jsonEncode([
          for (final model in ModelStore.catalog)
            model.id == 'whisperkit_large_v3_turbo'
                ? model
                      .copyWith(
                        state: ModelInstallState.installed,
                        localPath:
                            '${tempDir.path}/old-gone-container/whisperkit_large_v3_turbo',
                        installedBytes: 999,
                        installedFiles: 9,
                        progress: 1,
                      )
                      .toJson()
                : model.toJson(),
        ]),
      });

      final models = await ModelStore(
        HistoryStore(),
        modelDirectory: tempDir,
      ).loadModels();
      final whisperKit = models.firstWhere(
        (model) => model.id == 'whisperkit_large_v3_turbo',
      );

      expect(whisperKit.state, ModelInstallState.installed);
      expect(whisperKit.localPath, modelDir.path);
      expect(whisperKit.installedFiles, 1);
      expect(whisperKit.installedBytes, greaterThan(await modelFile.length()));
    },
  );
}
