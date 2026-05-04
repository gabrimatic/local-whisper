import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import 'history_store.dart';
import 'models.dart';

class ModelStore {
  ModelStore(this._historyStore, {Directory? modelDirectory})
    : _modelDirectoryOverride = modelDirectory;

  final HistoryStore _historyStore;
  final Directory? _modelDirectoryOverride;

  static const catalog = [
    LocalModel(
      id: 'qwen3_asr',
      name: 'Qwen3-ASR',
      kind: ModelKind.transcription,
      description:
          'English ASR model family from the desktop Local Whisper MLX engine.',
      sizeLabel: '~3.8 GB MLX pack',
      state: ModelInstallState.notInstalled,
      runtime: ModelRuntime.mlx,
      minimumIosMajor: 18,
      repoId: 'mlx-community/Qwen3-ASR-1.7B-bf16',
      installNote:
          'Same Qwen3-ASR model family as the desktop engine. Requires a native MLX/Core ML iOS adapter before it can transcribe.',
    ),
    LocalModel(
      id: 'parakeet_tdt_v3',
      name: 'Parakeet-TDT v3',
      kind: ModelKind.transcription,
      description: 'Default desktop Local Whisper long-form ASR model family.',
      sizeLabel: '~2.3 GB MLX pack',
      state: ModelInstallState.notInstalled,
      runtime: ModelRuntime.mlx,
      minimumIosMajor: 18,
      repoId: 'mlx-community/parakeet-tdt-0.6b-v3',
      installNote:
          'Same Parakeet-TDT v3 model family as the desktop default engine. Requires a native MLX/Core ML iOS adapter before it can transcribe.',
    ),
    LocalModel(
      id: 'kokoro_tts',
      name: 'Kokoro-82M TTS',
      kind: ModelKind.tts,
      description:
          'Offline text-to-speech voice model family used by Local Whisper voice output.',
      sizeLabel: '~371 MB MLX voice pack',
      state: ModelInstallState.notInstalled,
      runtime: ModelRuntime.mlx,
      minimumIosMajor: 18,
      repoId: 'mlx-community/Kokoro-82M-bf16',
      installNote:
          'Same Kokoro model family as desktop Local Whisper TTS. Requires native iOS playback synthesis before it can speak.',
    ),
    LocalModel(
      id: 'whisperkit_large_v3_turbo',
      name: 'WhisperKit Large v3',
      kind: ModelKind.transcription,
      description:
          'WhisperKit/Core ML transcription pack for private offline recording on iPhone.',
      sizeLabel: '~550 MB Core ML pack',
      state: ModelInstallState.notInstalled,
      runtime: ModelRuntime.whisperKit,
      minimumIosMajor: 14,
      repoId: 'argmaxinc/whisperkit-coreml',
      snapshotPath: 'openai_whisper-large-v3-v20240930_547MB',
      installNote:
          'WhisperKit large-v3 Core ML pack used by the native iOS recorder.',
    ),
    LocalModel(
      id: 'local_cleanup',
      name: 'Local Cleanup Engine',
      kind: ModelKind.cleanup,
      description:
          'Bundled rule-based post-processing. This is not a separate AI model.',
      sizeLabel: 'Bundled',
      state: ModelInstallState.bundled,
      runtime: ModelRuntime.bundled,
      minimumIosMajor: 14,
    ),
  ];

  Future<List<LocalModel>> loadModels() async {
    final saved = await _historyStore.loadModelState();
    final modelRoot = await _modelDirectory();
    final models = <LocalModel>[];
    var changed = false;
    for (final catalogModel in catalog) {
      final savedModel = saved[catalogModel.id];
      if (savedModel == null ||
          savedModel.state == ModelInstallState.notInstalled ||
          savedModel.state == ModelInstallState.unavailable) {
        final discovered = await _discoverInstalledModel(
          catalogModel,
          modelRoot,
        );
        if (discovered == null) {
          models.add(catalogModel);
        } else {
          models.add(discovered);
          changed = true;
        }
        continue;
      }
      final merged = catalogModel.copyWith(
        state: savedModel.state,
        localPath: savedModel.localPath,
        installedBytes: savedModel.installedBytes,
        installedFiles: savedModel.installedFiles,
        progress: savedModel.progress,
      );
      if (merged.state == ModelInstallState.installed &&
          !await _isInstalledModelValid(merged)) {
        final discovered = await _discoverInstalledModel(
          catalogModel,
          modelRoot,
        );
        if (discovered == null) {
          models.add(
            catalogModel.copyWith(
              state: ModelInstallState.notInstalled,
              localPath: '',
              installedBytes: 0,
              installedFiles: 0,
              progress: 0,
            ),
          );
        } else {
          models.add(discovered);
        }
        changed = true;
      } else {
        models.add(merged);
      }
    }
    if (changed) {
      await _historyStore.saveModelState(models);
    }
    return models;
  }

  Future<List<LocalModel>> removeModel(LocalModel model) async {
    if (model.localPath != null) {
      final type = await FileSystemEntity.type(model.localPath!);
      if (type == FileSystemEntityType.directory) {
        await Directory(model.localPath!).delete(recursive: true);
      } else if (type == FileSystemEntityType.file) {
        await File(model.localPath!).delete();
      }
    }
    final models = (await loadModels())
        .map(
          (item) => item.id == model.id
              ? item.copyWith(
                  state: ModelInstallState.notInstalled,
                  localPath: '',
                  installedBytes: 0,
                  installedFiles: 0,
                  progress: 0,
                )
              : item,
        )
        .toList(growable: false);
    await _historyStore.saveModelState(models);
    return models;
  }

  Future<List<LocalModel>> downloadModel(
    LocalModel model, {
    required void Function(LocalModel model) onProgress,
    required ModelDownloadCancelToken cancelToken,
  }) async {
    cancelToken.throwIfCanceled();
    if (model.repoId != null) {
      return _downloadSnapshot(
        model,
        onProgress: onProgress,
        cancelToken: cancelToken,
      );
    }

    final url = model.downloadUrl;
    if (url == null) return loadModels();
    final dir = await _modelDirectory();
    final target = File('${dir.path}/${model.id}.modelpack');
    final partial = File('${target.path}.download');
    final client = HttpClient();
    try {
      cancelToken.onCancel(client.close);
      final request = await client.getUrl(Uri.parse(url));
      final response = await request.close();
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw LocalWhisperException(
          'Model download failed with HTTP ${response.statusCode}.',
        );
      }

      final sink = partial.openWrite();
      var received = 0;
      final total = response.contentLength > 0 ? response.contentLength : null;
      await for (final chunk in response) {
        cancelToken.throwIfCanceled();
        received += chunk.length;
        sink.add(chunk);
        onProgress(
          model.copyWith(
            state: ModelInstallState.downloading,
            installedBytes: received,
            progress: total == null ? 0 : received / total,
          ),
        );
      }
      await sink.close();
      if (await target.exists()) {
        await target.delete();
      }
      await partial.rename(target.path);
      cancelToken.throwIfCanceled();

      final models = (await loadModels())
          .map(
            (item) => item.id == model.id
                ? item.copyWith(
                    state: ModelInstallState.installed,
                    localPath: target.path,
                    installedBytes: received,
                    installedFiles: 1,
                    progress: 1,
                  )
                : item,
          )
          .toList(growable: false);
      await _historyStore.saveModelState(models);
      return models;
    } on ModelDownloadCanceledException {
      if (await partial.exists()) {
        await partial.delete();
      }
      rethrow;
    } finally {
      client.close(force: true);
    }
  }

  Future<List<LocalModel>> _downloadSnapshot(
    LocalModel model, {
    required void Function(LocalModel model) onProgress,
    required ModelDownloadCancelToken cancelToken,
  }) async {
    final repoId = model.repoId;
    if (repoId == null) return loadModels();
    cancelToken.throwIfCanceled();

    final modelRoot = await _modelDirectory();
    final target = Directory('${modelRoot.path}/${model.id}');
    final partial = Directory('${target.path}.download');
    if (await partial.exists()) {
      await partial.delete(recursive: true);
    }
    await partial.create(recursive: true);

    final client = HttpClient();
    try {
      cancelToken.onCancel(client.close);
      final files = await _fetchSnapshotFiles(
        client,
        repoId,
        model.revision,
        snapshotPath: model.snapshotPath,
      );
      cancelToken.throwIfCanceled();
      if (files.isEmpty) {
        throw const LocalWhisperException('Model repository has no files.');
      }

      final totalBytes = files.fold<int>(0, (sum, file) => sum + file.size);
      var receivedBytes = 0;
      var installedFiles = 0;

      for (final file in files) {
        final relativePath = _safeRelativePath(
          file.path,
          stripPrefix: model.snapshotPath,
        );
        final destination = File('${partial.path}/$relativePath');
        await destination.parent.create(recursive: true);
        receivedBytes += await _downloadFile(
          client: client,
          cancelToken: cancelToken,
          repoId: repoId,
          revision: model.revision,
          path: file.path,
          destination: destination,
          declaredSize: file.size,
          onChunk: (bytes) {
            onProgress(
              model.copyWith(
                state: ModelInstallState.downloading,
                localPath: partial.path,
                installedBytes: receivedBytes + bytes,
                installedFiles: installedFiles,
                progress: totalBytes <= 0
                    ? 0
                    : (receivedBytes + bytes) / totalBytes,
              ),
            );
          },
        );
        installedFiles += 1;
        onProgress(
          model.copyWith(
            state: ModelInstallState.downloading,
            localPath: partial.path,
            installedBytes: receivedBytes,
            installedFiles: installedFiles,
            progress: totalBytes <= 0 ? 0 : receivedBytes / totalBytes,
          ),
        );
      }

      final manifest = File('${partial.path}/local-whisper-model.json');
      await manifest.writeAsString(
        const JsonEncoder.withIndent('  ').convert({
          'id': model.id,
          'name': model.name,
          'repoId': repoId,
          'revision': model.revision,
          'runtime': model.runtime.name,
          'minimumIosMajor': model.minimumIosMajor,
          'files': [
            for (final file in files)
              {
                'sourcePath': file.path,
                'path': _safeRelativePath(
                  file.path,
                  stripPrefix: model.snapshotPath,
                ),
                'size': file.size,
              },
          ],
        }),
      );

      if (await target.exists()) {
        await target.delete(recursive: true);
      }
      await partial.rename(target.path);
      cancelToken.throwIfCanceled();

      final models = (await loadModels())
          .map(
            (item) => item.id == model.id
                ? item.copyWith(
                    state: ModelInstallState.installed,
                    localPath: target.path,
                    installedBytes: receivedBytes,
                    installedFiles: installedFiles,
                    progress: 1,
                  )
                : item,
          )
          .toList(growable: false);
      await _historyStore.saveModelState(models);
      return models;
    } catch (_) {
      if (await partial.exists()) {
        await partial.delete(recursive: true);
      }
      rethrow;
    } finally {
      client.close(force: true);
    }
  }

  Future<List<_SnapshotFile>> _fetchSnapshotFiles(
    HttpClient client,
    String repoId,
    String revision, {
    String? snapshotPath,
  }) async {
    final treePath = snapshotPath == null || snapshotPath.isEmpty
        ? '/api/models/$repoId/tree/$revision'
        : '/api/models/$repoId/tree/$revision/$snapshotPath';
    final uri = Uri.https('huggingface.co', treePath, {'recursive': 'true'});
    final request = await client.getUrl(uri);
    final response = await request.close();
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw LocalWhisperException(
        'Model manifest failed with HTTP ${response.statusCode}.',
      );
    }
    final body = await utf8.decoder.bind(response).join();
    final decoded = jsonDecode(body);
    if (decoded is! List) {
      throw const LocalWhisperException('Model manifest response is invalid.');
    }
    return decoded
        .whereType<Map<String, Object?>>()
        .where((item) => item['type'] == 'file')
        .map(
          (item) => _SnapshotFile(
            item['path'] as String? ?? '',
            (item['size'] as num?)?.toInt() ?? 0,
          ),
        )
        .where((file) => file.path.isNotEmpty)
        .toList(growable: false);
  }

  Future<int> _downloadFile({
    required HttpClient client,
    required ModelDownloadCancelToken cancelToken,
    required String repoId,
    required String revision,
    required String path,
    required File destination,
    required int declaredSize,
    required void Function(int bytes) onChunk,
  }) async {
    cancelToken.throwIfCanceled();
    final uri = Uri.https('huggingface.co', '/$repoId/resolve/$revision/$path');
    final request = await client.getUrl(uri);
    final response = await request.close();
    cancelToken.throwIfCanceled();
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw LocalWhisperException(
        'Model file "$path" failed with HTTP ${response.statusCode}.',
      );
    }
    final sink = destination.openWrite();
    var received = 0;
    try {
      await for (final chunk in response) {
        cancelToken.throwIfCanceled();
        received += chunk.length;
        sink.add(chunk);
        onChunk(received);
      }
    } finally {
      await sink.close();
    }
    if (declaredSize > 0 && received != declaredSize) {
      throw LocalWhisperException(
        'Model file "$path" downloaded $received bytes, expected $declaredSize.',
      );
    }
    if (received <= 0) {
      throw LocalWhisperException('Model file "$path" downloaded empty.');
    }
    return received;
  }

  String _safeRelativePath(String path, {String? stripPrefix}) {
    var normalized = path;
    if (stripPrefix != null && stripPrefix.isNotEmpty) {
      final prefix = stripPrefix.endsWith('/') ? stripPrefix : '$stripPrefix/';
      if (normalized == stripPrefix) {
        normalized = '';
      } else if (normalized.startsWith(prefix)) {
        normalized = normalized.substring(prefix.length);
      }
    }
    final parts = normalized
        .split('/')
        .where((part) => part.isNotEmpty && part != '.' && part != '..')
        .toList(growable: false);
    if (parts.isEmpty) {
      throw LocalWhisperException('Invalid model file path: "$path".');
    }
    return parts.join('/');
  }

  Future<bool> _isInstalledModelValid(LocalModel model) async {
    final path = model.localPath;
    if (path == null || path.isEmpty) return false;
    final type = await FileSystemEntity.type(path);
    if (type == FileSystemEntityType.notFound) return false;
    if (type == FileSystemEntityType.file) return model.installedBytes > 0;
    if (type != FileSystemEntityType.directory) return false;

    final manifest = File('$path/local-whisper-model.json');
    if (!await manifest.exists()) return false;
    try {
      final decoded =
          jsonDecode(await manifest.readAsString()) as Map<String, Object?>;
      if (decoded['id'] != model.id || decoded['repoId'] != model.repoId) {
        return false;
      }
      final files = decoded['files'];
      if (files is! List || files.isEmpty) return false;
      for (final item in files) {
        if (item is! Map) return false;
        final relativePath = item['path'] as String?;
        final expectedSize = (item['size'] as num?)?.toInt() ?? 0;
        if (relativePath == null || relativePath.isEmpty) return false;
        final file = File('$path/${_safeRelativePath(relativePath)}');
        if (!await file.exists()) return false;
        if (expectedSize > 0 && await file.length() != expectedSize) {
          return false;
        }
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<LocalModel?> _discoverInstalledModel(
    LocalModel catalogModel,
    Directory modelRoot,
  ) async {
    if (!catalogModel.canDownload) return null;
    final discovered = catalogModel.copyWith(
      state: ModelInstallState.installed,
      localPath: '${modelRoot.path}/${catalogModel.id}',
      progress: 1,
    );
    if (!await _isInstalledModelValid(discovered)) return null;
    return discovered.copyWith(
      installedBytes: await _installedByteCount(discovered.localPath!),
      installedFiles: await _installedFileCount(discovered.localPath!),
    );
  }

  Future<int> _installedByteCount(String path) async {
    final type = await FileSystemEntity.type(path);
    if (type == FileSystemEntityType.file) return File(path).length();
    if (type != FileSystemEntityType.directory) return 0;
    var total = 0;
    await for (final entity in Directory(path).list(recursive: true)) {
      if (entity is File) {
        total += await entity.length();
      }
    }
    return total;
  }

  Future<int> _installedFileCount(String path) async {
    final type = await FileSystemEntity.type(path);
    if (type == FileSystemEntityType.file) return 1;
    if (type != FileSystemEntityType.directory) return 0;
    var total = 0;
    await for (final entity in Directory(path).list(recursive: true)) {
      if (entity is File &&
          !entity.path.endsWith('/local-whisper-model.json')) {
        total += 1;
      }
    }
    return total;
  }

  Future<Directory> _modelDirectory() async {
    final override = _modelDirectoryOverride;
    if (override != null) {
      if (!await override.exists()) {
        await override.create(recursive: true);
      }
      return override;
    }
    final documents = await getApplicationDocumentsDirectory();
    final dir = Directory('${documents.path}/models');
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    return dir;
  }
}

class _SnapshotFile {
  const _SnapshotFile(this.path, this.size);

  final String path;
  final int size;
}

class ModelDownloadCancelToken {
  bool _isCanceled = false;
  final List<void Function()> _callbacks = [];

  bool get isCanceled => _isCanceled;

  void cancel() {
    if (_isCanceled) return;
    _isCanceled = true;
    for (final callback in List<void Function()>.from(_callbacks)) {
      callback();
    }
    _callbacks.clear();
  }

  void onCancel(void Function() callback) {
    if (_isCanceled) {
      callback();
    } else {
      _callbacks.add(callback);
    }
  }

  void throwIfCanceled() {
    if (_isCanceled) throw const ModelDownloadCanceledException();
  }
}

class ModelDownloadCanceledException implements Exception {
  const ModelDownloadCanceledException();

  @override
  String toString() => 'Model download canceled.';
}
