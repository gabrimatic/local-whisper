import 'models.dart';

class TextPolisher {
  static final _fillerPattern = RegExp(
    r'\b(um+|uh+|erm+|ah+|like|you know|i mean)\b[,]?\s*',
    caseSensitive: false,
  );

  String polish(
    String input, {
    required DictationMode mode,
    bool removeFillers = true,
    bool smartPunctuation = true,
  }) {
    var text = input.trim();
    if (text.isEmpty) return text;

    text = _applyDictationCommands(text);
    if (removeFillers) {
      text = text.replaceAll(_fillerPattern, '');
    }
    text = text
        .split('\n')
        .map((line) => line.replaceAll(RegExp(r'[ \t]+'), ' ').trim())
        .join('\n')
        .replaceAll(RegExp(r'\n{3,}'), '\n\n')
        .trim();
    if (smartPunctuation) {
      text = _fixPunctuation(text);
    }
    text = _applyMode(text, mode);
    return text.trim();
  }

  String _applyDictationCommands(String text) {
    final replacements = <RegExp, String>{
      RegExp(r'\bnew paragraph\b', caseSensitive: false): '\n\n',
      RegExp(r'\bnew line\b', caseSensitive: false): '\n',
      RegExp(r'\bperiod\b', caseSensitive: false): '.',
      RegExp(r'\bcomma\b', caseSensitive: false): ',',
      RegExp(r'\bquestion mark\b', caseSensitive: false): '?',
      RegExp(r'\bexclamation mark\b', caseSensitive: false): '!',
      RegExp(r'\bcolon\b', caseSensitive: false): ':',
      RegExp(r'\bsemicolon\b', caseSensitive: false): ';',
    };
    var output = text;
    for (final entry in replacements.entries) {
      output = output.replaceAll(entry.key, entry.value);
    }
    return output;
  }

  String _fixPunctuation(String text) {
    var output = text
        .replaceAllMapped(RegExp(r'\s+([,.!?;:])'), (match) => match.group(1)!)
        .replaceAllMapped(
          RegExp(r'([,.!?;:])([^\s\n])'),
          (match) => '${match.group(1)!} ${match.group(2)!}',
        )
        .replaceAll(RegExp(r'\s+\n'), '\n')
        .replaceAll(RegExp(r'\n\s+'), '\n')
        .trim();
    if (!RegExp(r'[.!?]$').hasMatch(output)) {
      output = '$output.';
    }
    return _capitalizeSentences(output);
  }

  String _capitalizeSentences(String text) {
    final buffer = StringBuffer();
    var shouldCapitalize = true;
    for (final rune in text.runes) {
      final char = String.fromCharCode(rune);
      if (shouldCapitalize && RegExp(r'[A-Za-z]').hasMatch(char)) {
        buffer.write(char.toUpperCase());
        shouldCapitalize = false;
      } else {
        buffer.write(char);
      }
      if ('.!?\n'.contains(char)) {
        shouldCapitalize = true;
      }
    }
    return buffer.toString();
  }

  String _applyMode(String text, DictationMode mode) {
    return switch (mode.id) {
      'message' => text.replaceAll(RegExp(r'\s*\n+\s*'), ' '),
      'notes' => _notes(text),
      'prompt' => 'Task: $text',
      _ => text,
    };
  }

  String _notes(String text) {
    final sentences = text
        .split(RegExp(r'(?<=[.!?])\s+'))
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty);
    return sentences.map((line) => '- $line').join('\n');
  }
}
