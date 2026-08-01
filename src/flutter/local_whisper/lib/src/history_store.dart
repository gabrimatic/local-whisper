import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'models.dart';

/// Serializes async operations that read-modify-write the same underlying
/// storage so overlapping calls (e.g. two quick deletes, or a delete racing
/// a save) apply in order instead of one clobbering the other's result.
class _WriteQueue {
  Future<void> _tail = Future<void>.value();

  Future<T> run<T>(Future<T> Function() task) {
    final result = _tail.then((_) => task());
    _tail = result.then((_) {}, onError: (_) {});
    return result;
  }
}

/// Decodes a JSON list, parsing each entry independently so one malformed
/// record doesn't discard every other valid record in the same list.
List<T> _decodeListLenient<T>(
  String raw,
  T Function(Map<String, Object?> json) fromJson,
) {
  final decoded = jsonDecode(raw) as List<dynamic>;
  final results = <T>[];
  for (final item in decoded) {
    if (item is! Map) continue;
    try {
      results.add(fromJson(Map<String, Object?>.from(item)));
    } catch (_) {
      // Skip only this malformed record; keep the rest of the list intact.
    }
  }
  return results;
}

class HistoryStore {
  static const _historyKey = 'history.v1';
  static const _settingsKey = 'settings.v1';
  static const _modesKey = 'modes.v1';
  static const _modelsKey = 'models.v1';
  static const _onboardingKey = 'onboarding.v1';

  final _queue = _WriteQueue();

  Future<List<TranscriptEntry>> loadHistory() {
    return _queue.run(() async {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_historyKey);
      if (raw == null || raw.isEmpty) return const [];
      try {
        return _decodeListLenient(raw, TranscriptEntry.fromJson);
      } catch (_) {
        return const [];
      }
    });
  }

  Future<void> saveHistory(List<TranscriptEntry> entries) {
    return _queue.run(() async {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(
        _historyKey,
        jsonEncode(entries.map((entry) => entry.toJson()).toList()),
      );
    });
  }

  Future<void> deleteHistoryEntry(String id) {
    return _queue.run(() async {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_historyKey);
      final entries = raw == null || raw.isEmpty
          ? const <TranscriptEntry>[]
          : _decodeListLenient(raw, TranscriptEntry.fromJson);
      final filtered = entries
          .where((entry) => entry.id != id)
          .toList(growable: false);
      await prefs.setString(
        _historyKey,
        jsonEncode(filtered.map((entry) => entry.toJson()).toList()),
      );
    });
  }

  Future<void> clearHistory() {
    return _queue.run(() async {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_historyKey);
    });
  }

  static String exportMarkdown(List<TranscriptEntry> entries) {
    final buffer = StringBuffer()
      ..writeln('# Local Whisper History')
      ..writeln();
    if (entries.isEmpty) {
      buffer.writeln('No local transcriptions exported.');
      return buffer.toString().trimRight();
    }

    for (final entry in entries) {
      buffer
        ..writeln('## ${_exportDate(entry.createdAt)}')
        ..writeln()
        ..writeln('- Mode: ${entry.modeName}')
        ..writeln('- Locale: ${entry.localeId}')
        ..writeln('- Duration: ${entry.duration.toStringAsFixed(1)}s')
        ..writeln()
        ..writeln('### Final')
        ..writeln()
        ..writeln(entry.finalText.trim())
        ..writeln()
        ..writeln('### Raw')
        ..writeln()
        ..writeln(entry.rawText.trim())
        ..writeln();
    }
    return buffer.toString().trimRight();
  }

  static String _exportDate(DateTime value) {
    final utc = value.toUtc();
    String two(int number) => number.toString().padLeft(2, '0');
    return '${utc.year}-${two(utc.month)}-${two(utc.day)} '
        '${two(utc.hour)}:${two(utc.minute)} UTC';
  }

  Future<AppSettings> loadSettings() {
    return _queue.run(() async {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_settingsKey);
      if (raw == null || raw.isEmpty) return const AppSettings();
      try {
        return AppSettings.fromJson(jsonDecode(raw) as Map<String, Object?>);
      } catch (_) {
        return const AppSettings();
      }
    });
  }

  Future<void> saveSettings(AppSettings settings) {
    return _queue.run(() async {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_settingsKey, jsonEncode(settings.toJson()));
    });
  }

  Future<bool> loadOnboardingComplete() {
    return _queue.run(() async {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getBool(_onboardingKey) ?? false;
    });
  }

  Future<void> saveOnboardingComplete(bool complete) {
    return _queue.run(() async {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_onboardingKey, complete);
    });
  }

  Future<List<DictationMode>> loadModes() {
    return _queue.run(() async {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_modesKey);
      if (raw == null || raw.isEmpty) return DictationMode.defaults;
      try {
        final custom = _decodeListLenient(raw, DictationMode.fromJson);
        return custom.isEmpty ? DictationMode.defaults : custom;
      } catch (_) {
        return DictationMode.defaults;
      }
    });
  }

  Future<void> saveModes(List<DictationMode> modes) {
    return _queue.run(() async {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(
        _modesKey,
        jsonEncode(modes.map((mode) => mode.toJson()).toList()),
      );
    });
  }

  Future<Map<String, LocalModel>> loadModelState() {
    return _queue.run(() async {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_modelsKey);
      if (raw == null || raw.isEmpty) return const {};
      try {
        final models = _decodeListLenient(raw, LocalModel.fromJson);
        return {for (final model in models) model.id: model};
      } catch (_) {
        return const {};
      }
    });
  }

  Future<void> saveModelState(List<LocalModel> models) {
    return _queue.run(() async {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(
        _modelsKey,
        jsonEncode(models.map((model) => model.toJson()).toList()),
      );
    });
  }

  /// Atomically merges a single model's state into whatever is currently
  /// persisted, instead of overwriting the whole blob from a snapshot that
  /// may have gone stale during a long-running download. This keeps two
  /// concurrent model operations (e.g. two downloads finishing close
  /// together) from clobbering each other's saved state.
  Future<void> updateModelState(LocalModel model) {
    return _queue.run(() async {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_modelsKey);
      final current = <String, LocalModel>{};
      if (raw != null && raw.isNotEmpty) {
        try {
          for (final saved in _decodeListLenient(raw, LocalModel.fromJson)) {
            current[saved.id] = saved;
          }
        } catch (_) {
          // Corrupt blob: proceed with just this model's state rather than
          // losing the update entirely.
        }
      }
      current[model.id] = model;
      await prefs.setString(
        _modelsKey,
        jsonEncode(current.values.map((m) => m.toJson()).toList()),
      );
    });
  }
}
