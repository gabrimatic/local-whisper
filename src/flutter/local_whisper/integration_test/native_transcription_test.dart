import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:local_whisper_flutter/main.dart' as app;
import 'package:local_whisper_flutter/src/native_speech_service.dart';
import 'package:path_provider/path_provider.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('native WhisperKit transcribes bundled mock speech audio', (
    tester,
  ) async {
    app.main();
    await tester.pumpAndSettle();

    final modelPath = await _resolveModelPath();
    await _waitForModelFolder(modelPath);

    final audioPath = await _copyFixtureToTemporaryFile();
    final result = await NativeSpeechService().transcribeFileForTesting(
      audioPath: audioPath,
      locale: 'en-US',
      model: 'whisperkit_large_v3_turbo',
      modelPath: modelPath,
    );

    expect(result.onDevice, isTrue);
    expect(result.transcript.trim(), isNotEmpty);
    expect(
      result.transcript.toLowerCase(),
      anyOf(contains('local'), contains('whisper'), contains('offline')),
    );
  });
}

Future<String> _resolveModelPath() async {
  const explicitPath = String.fromEnvironment('LOCAL_WHISPER_MODEL_PATH');
  if (explicitPath.isNotEmpty) return explicitPath;

  final documents = await getApplicationDocumentsDirectory();
  return '${documents.path}/models/whisperkit_large_v3_turbo';
}

Future<void> _waitForModelFolder(String modelPath) async {
  final deadline = DateTime.now().add(const Duration(seconds: 45));
  while (DateTime.now().isBefore(deadline)) {
    if (Directory(modelPath).existsSync()) return;
    await Future<void>.delayed(const Duration(seconds: 1));
  }
  fail('WhisperKit model folder must exist before native E2E runs: $modelPath');
}

Future<String> _copyFixtureToTemporaryFile() async {
  final bytes = await rootBundle.load('test/fixtures/local_whisper_mock.wav');
  final file = File(
    '${Directory.systemTemp.path}/local_whisper_mock_${DateTime.now().microsecondsSinceEpoch}.wav',
  );
  await file.writeAsBytes(bytes.buffer.asUint8List(), flush: true);
  return file.path;
}
