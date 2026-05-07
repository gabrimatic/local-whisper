import 'dart:io';
import 'dart:isolate';
import 'dart:math' as math;

import 'package:sherpa_onnx/sherpa_onnx.dart' as sherpa;

import 'models.dart';

class SherpaSpeechService {
  Future<NativeSpeechResult> transcribeFile({
    required String audioPath,
    required String model,
    required String modelPath,
    required String locale,
    required double duration,
  }) async {
    final payload =
        await Isolate.run(
          () => _transcribeWithSherpaPayload(
            audioPath: audioPath,
            model: model,
            modelPath: modelPath,
            locale: locale,
            duration: duration,
          ),
        ).whenComplete(() async {
          try {
            await File(audioPath).delete();
          } catch (_) {
            // Temporary recording cleanup is best-effort.
          }
        });
    final error = payload['error'] as String?;
    if (error != null && error.isNotEmpty) {
      throw LocalWhisperException(error);
    }
    return NativeSpeechResult.fromJson(payload);
  }

  void dispose() {}
}

Map<String, Object?> _transcribeWithSherpaPayload({
  required String audioPath,
  required String model,
  required String modelPath,
  required String locale,
  required double duration,
}) {
  try {
    final result = _transcribeWithSherpa(
      audioPath: audioPath,
      model: model,
      modelPath: modelPath,
      locale: locale,
      duration: duration,
    );
    return {
      'transcript': result.transcript,
      'rawTranscript': result.rawTranscript,
      'duration': result.duration,
      'localeId': result.localeId,
      'onDevice': result.onDevice,
      'engine': result.engine,
      'modelId': result.modelId,
      'elapsedMs': result.elapsedMs,
      'rtf': result.rtf,
    };
  } catch (error) {
    return {'error': error.toString()};
  }
}

NativeSpeechResult _transcribeWithSherpa({
  required String audioPath,
  required String model,
  required String modelPath,
  required String locale,
  required double duration,
}) {
  final file = File(audioPath);
  if (!file.existsSync()) {
    throw const LocalWhisperException(
      'Recorded audio file is missing before transcription.',
    );
  }
  if (modelPath.isEmpty || !Directory(modelPath).existsSync()) {
    throw LocalWhisperException(
      'Download ${_displayModelName(model)} before recording.',
    );
  }

  sherpa.initBindings();
  final config = _recognizerConfig(model: model, modelPath: modelPath);
  final recognizer = sherpa.OfflineRecognizer(config);
  final stream = recognizer.createStream();
  final startedAt = DateTime.now();
  try {
    final wave = sherpa.readWave(audioPath);
    if (wave.sampleRate <= 0 || wave.samples.isEmpty) {
      throw const LocalWhisperException(
        'Recorded audio could not be read as WAV.',
      );
    }
    stream.acceptWaveform(samples: wave.samples, sampleRate: wave.sampleRate);
    recognizer.decode(stream);
    final result = recognizer.getResult(stream);
    final text = result.text.trim();
    if (text.isEmpty) {
      throw const LocalWhisperException('No speech was detected.');
    }
    final elapsed = DateTime.now().difference(startedAt);
    return NativeSpeechResult(
      transcript: text,
      rawTranscript: text,
      duration: duration,
      localeId: result.lang.isNotEmpty ? result.lang : locale,
      onDevice: true,
      engine: 'sherpa_onnx',
      modelId: model,
      elapsedMs: elapsed.inMilliseconds,
      rtf: duration > 0 ? elapsed.inMilliseconds / 1000 / duration : null,
    );
  } finally {
    stream.free();
    recognizer.free();
  }
}

sherpa.OfflineRecognizerConfig _recognizerConfig({
  required String model,
  required String modelPath,
}) {
  return switch (model) {
    'parakeet_tdt_v3_sherpa' => _parakeetConfig(modelPath),
    'qwen3_asr_sherpa' => _qwen3Config(modelPath),
    _ => throw LocalWhisperException(
      '${_displayModelName(model)} is not wired for Android transcription.',
    ),
  };
}

sherpa.OfflineRecognizerConfig _parakeetConfig(String modelPath) {
  _requireFiles(modelPath, const [
    'encoder.int8.onnx',
    'decoder.int8.onnx',
    'joiner.int8.onnx',
    'tokens.txt',
  ]);
  return sherpa.OfflineRecognizerConfig(
    model: sherpa.OfflineModelConfig(
      transducer: sherpa.OfflineTransducerModelConfig(
        encoder: '$modelPath/encoder.int8.onnx',
        decoder: '$modelPath/decoder.int8.onnx',
        joiner: '$modelPath/joiner.int8.onnx',
      ),
      tokens: '$modelPath/tokens.txt',
      modelType: 'nemo_transducer',
      numThreads: _threadCount(),
      debug: false,
      provider: 'cpu',
    ),
  );
}

sherpa.OfflineRecognizerConfig _qwen3Config(String modelPath) {
  _requireFiles(modelPath, const [
    'conv_frontend.onnx',
    'encoder.int8.onnx',
    'decoder.int8.onnx',
    'tokenizer/merges.txt',
    'tokenizer/vocab.json',
    'tokenizer/tokenizer_config.json',
  ]);
  return sherpa.OfflineRecognizerConfig(
    model: sherpa.OfflineModelConfig(
      qwen3Asr: sherpa.OfflineQwen3AsrModelConfig(
        convFrontend: '$modelPath/conv_frontend.onnx',
        encoder: '$modelPath/encoder.int8.onnx',
        decoder: '$modelPath/decoder.int8.onnx',
        tokenizer: '$modelPath/tokenizer',
        maxNewTokens: 512,
      ),
      tokens: '',
      numThreads: _threadCount(),
      debug: false,
      provider: 'cpu',
    ),
  );
}

void _requireFiles(String modelPath, List<String> files) {
  for (final relative in files) {
    if (!File('$modelPath/$relative').existsSync()) {
      throw LocalWhisperException('Installed model pack is missing $relative.');
    }
  }
}

int _threadCount() {
  final processors = Platform.numberOfProcessors;
  return math.max(1, math.min(4, processors - 1));
}

String _displayModelName(String model) {
  return switch (model) {
    'parakeet_tdt_v3_sherpa' => 'Parakeet-TDT v3',
    'qwen3_asr_sherpa' => 'Qwen3-ASR 0.6B',
    _ => model,
  };
}
