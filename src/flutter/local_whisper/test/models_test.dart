import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:local_whisper_flutter/src/history_store.dart';
import 'package:local_whisper_flutter/src/model_store.dart';
import 'package:local_whisper_flutter/src/models.dart';
import 'package:local_whisper_flutter/src/sherpa_speech_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('Fourier installs the pinned sherpa snapshot from Oruk', () {
    final model = ModelStore.catalog.singleWhere(
      (item) => item.id == 'oruk_fourier_2b_sherpa',
    );
    expect(model.runtime, ModelRuntime.sherpaOnnx);
    expect(model.repoId, 'oruk/oruk-fourier-2b');
    expect(model.revision, '3fda023e157ce7986f137f76fcf326ed6e08fa73');
    expect(model.snapshotPath, 'onnx/sherpa-int8');
    expect(model.extraSnapshotFiles, hasLength(1));
    expect(model.extraSnapshotFiles.single.path, 'config.json');
    expect(model.extraSnapshotFiles.single.size, 2479);
    expect(
      model.extraSnapshotFiles.single.sha256,
      '5bc1d99c141fc866b61efca97dcbc6412a38db25ff0934c38bf7b46fa09485a2',
    );
    expect(model.canDownload, isTrue);
  });

  test('Fourier reports a missing external graph before decoding', () async {
    final pack = await Directory.systemTemp.createTemp('fourier-incomplete-');
    addTearDown(() => pack.delete(recursive: true));
    final audio = await File('${pack.path}/clip.wav').create();
    await expectLater(
      SherpaSpeechService().transcribeFile(
        audioPath: audio.path,
        model: 'oruk_fourier_2b_sherpa',
        modelPath: pack.path,
        locale: 'en-US',
        duration: 1,
      ),
      throwsA(
        predicate((e) => e.toString().contains('encoder.int8.onnx.data')),
      ),
    );
  });

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
  for (final honorRange in [true, false]) {
    test(
      'pinned snapshot resumes after cancel (range supported: $honorRange)',
      () async {
        SharedPreferences.setMockInitialValues({});
        final root = await Directory.systemTemp.createTemp('fourier-range');
        final http = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
        addTearDown(() async {
          await http.close(force: true);
          await root.delete(recursive: true);
          SharedPreferences.resetStatic();
        });
        final payload = List<int>.generate(1048576, (i) => i % 251);
        final configPayload = utf8.encode(
          '{"model_type":"qwen3_asr"}'.padRight(2479),
        );
        final ranges = <String?>[];
        final resolvedPaths = <String>[];
        final interrupted = Completer<void>();
        final catalogModel = ModelStore.catalog.firstWhere(
          (m) => m.id == 'oruk_fourier_2b_sherpa',
        );
        final model = catalogModel.copyWith(
          extraSnapshotFiles: [
            PinnedSnapshotFile(
              path: 'config.json',
              size: configPayload.length,
              sha256: sha256.convert(configPayload).toString(),
            ),
          ],
        );
        http.listen((req) async {
          final res = req.response;
          try {
            if (req.uri.path.contains('/tree/')) {
              res.write(
                jsonEncode([
                  {
                    'type': 'file',
                    'path': '${model.snapshotPath}/model.onnx',
                    'size': payload.length,
                    'lfs': {'oid': sha256.convert(payload).toString()},
                  },
                ]),
              );
            } else if (req.uri.path.endsWith('/resolve/${model.revision}/config.json')) {
              resolvedPaths.add('config.json');
              res.add(configPayload);
            } else {
              resolvedPaths.add('${model.snapshotPath}/model.onnx');
              final range = req.headers.value(HttpHeaders.rangeHeader);
              ranges.add(range);
              if (ranges.length == 1) {
                res.bufferOutput = false;
                res.contentLength = payload.length;
                res.add(payload.sublist(0, 262144));
                await res.flush();
                await interrupted.future.timeout(const Duration(seconds: 10));
                res.add(payload.sublist(262144));
              } else if (range != null && honorRange) {
                final start = int.parse(
                  RegExp(r'bytes=(\d+)-').firstMatch(range)![1]!,
                );
                res.statusCode = 206;
                res.headers.set(
                  'Content-Range',
                  'bytes $start-${payload.length - 1}/${payload.length}',
                );
                res.add(payload.sublist(start));
              } else {
                res.add(payload);
              }
            }
            await res.close();
          } on IOException {
            // The first transfer is deliberately canceled by the client.
          }
        });
        ModelStore store() => ModelStore(
          HistoryStore(),
          modelDirectory: root,
          huggingFaceBaseUri: Uri.parse('http://127.0.0.1:${http.port}'),
          downloadRetryDelay: Duration.zero,
        );
        final token = ModelDownloadCancelToken();
        await expectLater(
          store().downloadModel(
            model,
            onProgress: (p) {
              if (p.installedBytes >= 8192 && !interrupted.isCompleted) {
                token.cancel();
                interrupted.complete();
              }
            },
            cancelToken: token,
          ),
          throwsA(isA<ModelDownloadCanceledException>()),
        );
        // Root config.json must not be fetched before the payload finishes.
        expect(resolvedPaths, ['${model.snapshotPath}/model.onnx']);
        final partial = await root
            .list(recursive: true)
            .where((f) => f is File && f.path.endsWith('.part'))
            .cast<File>()
            .single;
        final retained = await partial.length();
        expect(retained, greaterThan(0));
        expect(retained, lessThan(payload.length));
        final retry = store();
        // A fresh process must preserve this pinned partial.
        await retry.loadModels();
        final items = await retry.downloadModel(
          model,
          onProgress: (_) {},
          cancelToken: ModelDownloadCancelToken(),
        );
        final installed = items.firstWhere((m) => m.id == model.id);
        expect(ranges, [null, 'bytes=$retained-']);
        expect(resolvedPaths, [
          '${model.snapshotPath}/model.onnx',
          '${model.snapshotPath}/model.onnx',
          'config.json',
        ]);
        expect(installed.state, ModelInstallState.installed);
        expect(installed.installedFiles, 2);
        expect(
          await File('${installed.localPath}/model.onnx').readAsBytes(),
          payload,
        );
        expect(
          await File('${installed.localPath}/config.json').readAsBytes(),
          configPayload,
        );
        // Reload must accept the root config.json entry in the manifest, and
        // removeModel must delete both the payload and config.json cleanly.
        final reloaded = await retry.loadModels();
        expect(
          reloaded.firstWhere((m) => m.id == model.id).state,
          ModelInstallState.installed,
        );
        final afterRemove = await retry.removeModel(installed);
        expect(
          afterRemove.firstWhere((m) => m.id == model.id).state,
          ModelInstallState.notInstalled,
        );
        expect(await Directory(installed.localPath!).exists(), isFalse);
      },
    );
  }

  test('pinned snapshot rejects root config.json with SHA-256 mismatch', () async {
    SharedPreferences.setMockInitialValues({});
    final root = await Directory.systemTemp.createTemp('fourier-bad-config-');
    final http = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() async {
      await http.close(force: true);
      await root.delete(recursive: true);
      SharedPreferences.resetStatic();
    });
    final payload = utf8.encode('onnx-bytes');
    final badConfig = List<int>.filled(2479, 0x78);
    final model = ModelStore.catalog.firstWhere(
      (m) => m.id == 'oruk_fourier_2b_sherpa',
    );
    http.listen((req) async {
      final res = req.response;
      if (req.uri.path.contains('/tree/')) {
        res.write(
          jsonEncode([
            {
              'type': 'file',
              'path': '${model.snapshotPath}/model.onnx',
              'size': payload.length,
              'lfs': {'oid': sha256.convert(payload).toString()},
            },
          ]),
        );
      } else if (req.uri.path.endsWith('/resolve/${model.revision}/config.json')) {
        res.add(badConfig);
      } else {
        res.add(payload);
      }
      await res.close();
    });
    final store = ModelStore(
      HistoryStore(),
      modelDirectory: root,
      huggingFaceBaseUri: Uri.parse('http://127.0.0.1:${http.port}'),
      maxDownloadAttempts: 1,
      downloadRetryDelay: Duration.zero,
    );
    await expectLater(
      store.downloadModel(
        model,
        onProgress: (_) {},
        cancelToken: ModelDownloadCancelToken(),
      ),
      throwsA(predicate((e) => e.toString().contains('SHA-256 mismatch'))),
    );
    expect(await Directory('${root.path}/${model.id}').exists(), isFalse);
  });
}
