import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'models.dart';

class HistoryStore {
  static const _historyKey = 'history.v1';
  static const _settingsKey = 'settings.v1';
  static const _modesKey = 'modes.v1';
  static const _modelsKey = 'models.v1';
  static const _onboardingKey = 'onboarding.v1';

  Future<List<TranscriptEntry>> loadHistory() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_historyKey);
    if (raw == null || raw.isEmpty) return const [];
    try {
      final decoded = jsonDecode(raw) as List<dynamic>;
      return decoded
          .whereType<Map>()
          .map((entry) => Map<String, Object?>.from(entry))
          .map(TranscriptEntry.fromJson)
          .toList(growable: false);
    } catch (_) {
      return const [];
    }
  }

  Future<void> saveHistory(List<TranscriptEntry> entries) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _historyKey,
      jsonEncode(entries.map((entry) => entry.toJson()).toList()),
    );
  }

  Future<AppSettings> loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_settingsKey);
    if (raw == null || raw.isEmpty) return const AppSettings();
    try {
      return AppSettings.fromJson(jsonDecode(raw) as Map<String, Object?>);
    } catch (_) {
      return const AppSettings();
    }
  }

  Future<void> saveSettings(AppSettings settings) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_settingsKey, jsonEncode(settings.toJson()));
  }

  Future<bool> loadOnboardingComplete() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_onboardingKey) ?? false;
  }

  Future<void> saveOnboardingComplete(bool complete) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_onboardingKey, complete);
  }

  Future<List<DictationMode>> loadModes() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_modesKey);
    if (raw == null || raw.isEmpty) return DictationMode.defaults;
    try {
      final decoded = jsonDecode(raw) as List<dynamic>;
      final custom = decoded
          .whereType<Map>()
          .map((mode) => Map<String, Object?>.from(mode))
          .map(DictationMode.fromJson)
          .toList(growable: false);
      return custom.isEmpty ? DictationMode.defaults : custom;
    } catch (_) {
      return DictationMode.defaults;
    }
  }

  Future<void> saveModes(List<DictationMode> modes) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _modesKey,
      jsonEncode(modes.map((mode) => mode.toJson()).toList()),
    );
  }

  Future<Map<String, LocalModel>> loadModelState() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_modelsKey);
    if (raw == null || raw.isEmpty) return const {};
    try {
      final decoded = jsonDecode(raw) as List<dynamic>;
      return {
        for (final model
            in decoded
                .whereType<Map>()
                .map((item) => Map<String, Object?>.from(item))
                .map(LocalModel.fromJson))
          model.id: model,
      };
    } catch (_) {
      return const {};
    }
  }

  Future<void> saveModelState(List<LocalModel> models) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _modelsKey,
      jsonEncode(models.map((model) => model.toJson()).toList()),
    );
  }
}
