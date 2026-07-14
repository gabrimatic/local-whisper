import 'package:flutter_test/flutter_test.dart';
import 'dart:convert';
import 'dart:io';
import 'package:local_whisper_flutter/src/history_store.dart';
import 'package:local_whisper_flutter/src/model_store.dart';
import 'package:local_whisper_flutter/src/models.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('Apple SpeechTranscriber is a native installable iOS model', () {
    final model = ModelStore.catalog.firstWhere(
      (item) => item.id == 'apple_speech',
    );

    expect(model.runtime, ModelRuntime.appleSpeech);
    expect(model.minimumIosMajor, 26);
    expect(model.canDownload, isTrue);
    expect(model.repoId, isNull);
    expect(model.downloadUrl, isNull);
  });

  test('history export renders portable markdown without network services', () {
    final entry = TranscriptEntry(
      id: 'entry-1',
      createdAt: DateTime.utc(2026, 5, 12, 8, 30),
      rawText: 'um hello comma local whisper period',
      finalText: 'Hello, local whisper.',
      modeName: 'Clean Dictation',
      localeId: 'en-US',
      duration: 2.4,
    );

    final markdown = HistoryStore.exportMarkdown([entry]);

    expect(markdown, startsWith('# Local Whisper History'));
    expect(markdown, contains('## 2026-05-12 08:30 UTC'));
    expect(markdown, contains('- Mode: Clean Dictation'));
    expect(markdown, contains('- Locale: en-US'));
    expect(markdown, contains('- Duration: 2.4s'));
    expect(markdown, contains('### Final'));
    expect(markdown, contains('Hello, local whisper.'));
    expect(markdown, contains('### Raw'));
    expect(markdown, contains('um hello comma local whisper period'));
  });

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
            'sourcePath': 'openai_whisper-large-v3-v20240930_626MB/config.json',
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

  test('model state rejects stale WhisperKit snapshot installs', () async {
    final tempDir = await Directory.systemTemp.createTemp(
      'local-whisper-model-stale-snapshot-',
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

    expect(whisperKit.state, ModelInstallState.notInstalled);
    expect(whisperKit.localPath, isEmpty);
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
            {
              'sourcePath':
                  'openai_whisper-large-v3-v20240930_626MB/config.json',
              'path': 'config.json',
              'size': await modelFile.length(),
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

  test(
    'snapshot downloads retry transient file failures and install verified packs',
    () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'local-whisper-model-retry-',
      );
      final payload = utf8.encode('{"model":"test"}');
      var fileRequests = 0;
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      server.listen((request) async {
        if (request.uri.path.contains('/tree/')) {
          request.response.headers.contentType = ContentType.json;
          request.response.write(
            jsonEncode([
              {
                'type': 'file',
                'path': 'openai_whisper-large-v3-v20240930_626MB/config.json',
                'size': payload.length,
              },
            ]),
          );
        } else if (request.uri.path.contains('/resolve/')) {
          fileRequests += 1;
          if (fileRequests == 1) {
            request.response.statusCode = HttpStatus.internalServerError;
            request.response.write('temporary failure');
          } else {
            request.response.add(payload);
          }
        } else {
          request.response.statusCode = HttpStatus.notFound;
        }
        await request.response.close();
      });
      addTearDown(() async {
        await server.close(force: true);
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
        SharedPreferences.resetStatic();
      });

      SharedPreferences.resetStatic();
      SharedPreferences.setMockInitialValues({
        'models.v1': jsonEncode([
          for (final model in ModelStore.catalog) model.toJson(),
        ]),
      });

      final store = ModelStore(
        HistoryStore(),
        modelDirectory: tempDir,
        huggingFaceBaseUri: Uri(
          scheme: 'http',
          host: server.address.host,
          port: server.port,
        ),
        downloadRetryDelay: Duration.zero,
      );
      final model = ModelStore.catalog.firstWhere(
        (item) => item.id == 'whisperkit_large_v3_turbo',
      );

      final models = await store.downloadModel(
        model,
        onProgress: (_) {},
        cancelToken: ModelDownloadCancelToken(),
      );

      expect(fileRequests, 2);
      final whisperKit = models.firstWhere(
        (item) => item.id == 'whisperkit_large_v3_turbo',
      );
      expect(whisperKit.state, ModelInstallState.installed);
      expect(whisperKit.installedFiles, 1);
      expect(whisperKit.installedBytes, payload.length);
      expect(
        await File('${whisperKit.localPath}/config.json').readAsString(),
        '{"model":"test"}',
      );

      final loaded = await store.loadModels();
      expect(
        loaded
            .firstWhere((item) => item.id == 'whisperkit_large_v3_turbo')
            .state,
        ModelInstallState.installed,
      );
    },
  );
}
