import 'dart:async';

import 'package:flutter/services.dart';

import 'models.dart';

class NativeSpeechService {
  static const _method = MethodChannel('local_whisper/speech');
  static const _levels = EventChannel('local_whisper/levels');

  Stream<double>? _levelStream;

  Stream<double> get levelStream {
    return _levelStream ??= _levels.receiveBroadcastStream().map((event) {
      if (event is num) return event.toDouble().clamp(0, 1);
      return 0.0;
    });
  }

  Future<NativeSpeechStatus> status({required String locale}) async {
    final value = await _method.invokeMapMethod<Object?, Object?>('status', {
      'locale': locale,
    });
    return NativeSpeechStatus.fromJson(value ?? const {});
  }

  Future<bool> requestPermissions() async {
    return await _method.invokeMethod<bool>('requestPermissions') ?? false;
  }

  Future<void> start({
    required String locale,
    required String model,
    String? modelPath,
  }) async {
    await _method.invokeMethod<void>('start', {
      'locale': locale,
      'model': model,
      if (modelPath != null && modelPath.isNotEmpty) 'modelPath': modelPath,
    });
  }

  Future<NativeSpeechResult> stop() async {
    final value = await _method.invokeMapMethod<Object?, Object?>('stop');
    return NativeSpeechResult.fromJson(value ?? const {});
  }

  Future<void> cancel() async {
    await _method.invokeMethod<void>('cancel');
  }

  Future<NativeSpeechResult> transcribeFileForTesting({
    required String audioPath,
    required String locale,
    required String model,
    required String modelPath,
  }) async {
    var debugMode = false;
    assert(() {
      debugMode = true;
      return true;
    }());
    if (!debugMode) {
      throw UnsupportedError('Debug transcription is unavailable in release.');
    }
    final value = await _method.invokeMapMethod<Object?, Object?>(
      'debugTranscribeFile',
      {
        'audioPath': audioPath,
        'locale': locale,
        'model': model,
        'modelPath': modelPath,
      },
    );
    return NativeSpeechResult.fromJson(value ?? const {});
  }

  void dispose() {}
}
