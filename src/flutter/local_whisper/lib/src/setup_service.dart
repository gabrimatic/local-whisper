import 'package:flutter/services.dart';

const keyboardVerificationToken = '[[LOCAL_WHISPER_KEYBOARD_VERIFIED]]';

class KeyboardSetupStatus {
  const KeyboardSetupStatus({
    required this.keyboardSeen,
    required this.message,
  });

  const KeyboardSetupStatus.unknown()
    : keyboardSeen = false,
      message =
          'Keyboard has not been verified yet. Add it in Settings, switch to it in the practice field, then tap Verify on the keyboard.';

  const KeyboardSetupStatus.verified()
    : keyboardSeen = true,
      message = 'Local Whisper Keyboard was opened and verified.';

  final bool keyboardSeen;
  final String message;

  factory KeyboardSetupStatus.fromJson(Map<Object?, Object?> json) {
    return KeyboardSetupStatus(
      keyboardSeen: json['keyboardSeen'] == true,
      message:
          json['message'] as String? ??
          'Keyboard has not been verified yet. Add it in Settings, switch to it in the practice field, then tap Verify on the keyboard.',
    );
  }
}

class NativeSetupService {
  static const _method = MethodChannel('local_whisper/setup');

  Future<bool> openKeyboardSettings() async {
    return await _method.invokeMethod<bool>('openKeyboardSettings') ?? false;
  }

  Future<bool> openAppSettings() async {
    return await _method.invokeMethod<bool>('openAppSettings') ?? false;
  }

  Future<KeyboardSetupStatus> keyboardStatus() async {
    final value = await _method.invokeMapMethod<Object?, Object?>(
      'keyboardStatus',
    );
    return KeyboardSetupStatus.fromJson(value ?? const {});
  }

  Future<void> markKeyboardSeen() async {
    await _method.invokeMethod<void>('markKeyboardSeen');
  }

  Future<void> syncKeyboardSettings({
    required bool haptics,
    required bool quickInsert,
  }) async {
    await _method.invokeMethod<void>('syncKeyboardSettings', {
      'haptics': haptics,
      'quickInsert': quickInsert,
    });
  }
}
