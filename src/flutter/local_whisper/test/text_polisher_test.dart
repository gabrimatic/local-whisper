import 'package:flutter_test/flutter_test.dart';
import 'package:local_whisper_flutter/src/models.dart';
import 'package:local_whisper_flutter/src/text_polisher.dart';

void main() {
  final polisher = TextPolisher();

  test(
    'cleans filler words, spoken punctuation, spacing, and capitalization',
    () {
      final result = polisher.polish(
        'um hello comma this is like local whisper period new line it works',
        mode: DictationMode.defaults.first,
      );

      expect(result, 'Hello, this is local whisper.\nIt works.');
    },
  );

  test('formats notes mode as readable bullets', () {
    final notesMode = DictationMode.defaults.firstWhere(
      (mode) => mode.id == 'notes',
    );

    final result = polisher.polish(
      'first idea period second idea question mark',
      mode: notesMode,
    );

    expect(result, '- First idea.\n- Second idea?');
  });

  test('formats prompt mode without using network services', () {
    final promptMode = DictationMode.defaults.firstWhere(
      (mode) => mode.id == 'prompt',
    );

    final result = polisher.polish(
      'summarize this recording',
      mode: promptMode,
    );

    expect(result, 'Task: Summarize this recording.');
  });
}
