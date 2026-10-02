import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:local_whisper_flutter/main.dart' as app;
import 'package:local_whisper_flutter/src/history_store.dart';
import 'package:local_whisper_flutter/src/model_store.dart';
import 'package:local_whisper_flutter/src/native_speech_service.dart';
import 'package:path_provider/path_provider.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('selected native engine transcribes bundled speech audio', (
    tester,
  ) async {
    app.main();
    await tester.pumpAndSettle();

    const explicitModel = String.fromEnvironment('LOCAL_WHISPER_E2E_MODEL');
    final model = explicitModel.isNotEmpty
        ? explicitModel
        : Platform.isAndroid
        ? 'parakeet_tdt_v3_sherpa'
        : 'whisperkit_large_v3_turbo';
    final service = NativeSpeechService();
    var modelPath = '';
    if (model == 'apple_speech') {
      final status = await service.appleSpeechModelStatus(locale: 'en-US');
      if (!status.available) {
        expect(status.installed, isFalse);
        return;
      }
      final installed = await service.installAppleSpeechModel(locale: 'en-US');
      expect(installed.installed, isTrue);
    } else {
      modelPath = await _resolveModelPath(model);
      if (const bool.fromEnvironment('LOCAL_WHISPER_E2E_DOWNLOAD_MODEL') &&
          !Directory(modelPath).existsSync()) {
        final store = ModelStore(
          HistoryStore(),
          modelDirectory: Directory(modelPath).parent,
        );
        final selected = (await store.loadModels()).firstWhere(
          (item) => item.id == model,
        );
        await store.downloadModel(
          selected,
          onProgress: (_) {},
          cancelToken: ModelDownloadCancelToken(),
        );
      }
      await _waitForModelFolder(modelPath);
    }

    final audioPath = await _copyFixtureToTemporaryFile();
    final result = await service.transcribeFileForTesting(
      audioPath: audioPath,
      locale: 'en-US',
      model: model,
      modelPath: modelPath,
    );

    expect(result.onDevice, isTrue);
    expect(result.modelId, model);
    expect(result.transcript.trim(), isNotEmpty);
    expect(
      result.transcript.toLowerCase(),
      anyOf(contains('local'), contains('whisper'), contains('offline')),
    );
  });
}

Future<String> _resolveModelPath(String model) async {
  const explicitPath = String.fromEnvironment('LOCAL_WHISPER_MODEL_PATH');
  if (explicitPath.isNotEmpty) return explicitPath;

  final documents = await getApplicationDocumentsDirectory();
  return '${documents.path}/models/$model';
}

Future<void> _waitForModelFolder(String modelPath) async {
  final deadline = DateTime.now().add(const Duration(seconds: 45));
  while (DateTime.now().isBefore(deadline)) {
    if (Directory(modelPath).existsSync()) return;
    await Future<void>.delayed(const Duration(seconds: 1));
  }
  fail('Install the selected model before native E2E runs: $modelPath');
}

Future<String> _copyFixtureToTemporaryFile() async {
  final bytes = await rootBundle.load('test/fixtures/local_whisper_mock.wav');
  final file = File(
    '${Directory.systemTemp.path}/local_whisper_mock_${DateTime.now().microsecondsSinceEpoch}.wav',
  );
  await file.writeAsBytes(bytes.buffer.asUint8List(), flush: true);
  return file.path;
}
