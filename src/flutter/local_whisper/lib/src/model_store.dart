import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:path_provider/path_provider.dart';

import 'history_store.dart';
import 'models.dart';

class ModelStore {
  ModelStore(
    this._historyStore, {
    Directory? modelDirectory,
    Uri? huggingFaceBaseUri,
    int maxDownloadAttempts = 3,
    Duration downloadRetryDelay = const Duration(milliseconds: 350),
  }) : _modelDirectoryOverride = modelDirectory,
       _huggingFaceBaseUri =
           huggingFaceBaseUri ?? Uri.parse('https://huggingface.co'),
       _maxDownloadAttempts = maxDownloadAttempts < 1 ? 1 : maxDownloadAttempts,
       _downloadRetryDelay = downloadRetryDelay;

  final HistoryStore _historyStore;
  final Directory? _modelDirectoryOverride;
  final Uri _huggingFaceBaseUri;
  final int _maxDownloadAttempts;
  final Duration _downloadRetryDelay;
  bool _didCleanOrphanedDownloads = false;

  static const catalog = [
    LocalModel(
      id: 'qwen3_asr',
      name: 'Qwen3-ASR',
      kind: ModelKind.transcription,
      description:
          'Multilingual ASR model family from the desktop Local Whisper MLX '
          'engine, with language detection handled by the model.',
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
      sizeLabel: '~626 MB Core ML pack',
      state: ModelInstallState.notInstalled,
      runtime: ModelRuntime.whisperKit,
      minimumIosMajor: 14,
      repoId: 'argmaxinc/whisperkit-coreml',
      snapshotPath: 'openai_whisper-large-v3-v20240930_626MB',
      installNote:
          'WhisperKit large-v3 Core ML pack used by the native iOS recorder.',
    ),
    LocalModel(
      id: 'apple_speech',
      name: 'Apple SpeechTranscriber',
      kind: ModelKind.transcription,
      description:
          'Apple\'s on-device SpeechAnalyzer model for live and long-form transcription.',
      sizeLabel: 'Apple managed',
      state: ModelInstallState.notInstalled,
      runtime: ModelRuntime.appleSpeech,
      minimumIosMajor: 26,
      installNote:
          'iOS downloads, updates, and shares the selected language asset. Availability depends on the device and locale.',
    ),
    LocalModel(
      id: 'parakeet_tdt_v3_sherpa',
      name: 'Parakeet-TDT v3',
      kind: ModelKind.transcription,
      description:
          'Default Android offline ASR pack. Same model family as the macOS Parakeet engine, converted to INT8 ONNX for sherpa-onnx.',
      sizeLabel: '~640 MB ONNX pack',
      state: ModelInstallState.notInstalled,
      runtime: ModelRuntime.sherpaOnnx,
      minimumIosMajor: 14,
      repoId: 'csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8',
      installNote:
          'Best Android default: private on-device transcription for English, German, and 25 European languages through sherpa-onnx.',
    ),
    LocalModel(
      id: 'qwen3_asr_sherpa',
      name: 'Qwen3-ASR 0.6B',
      kind: ModelKind.transcription,
      description:
          'Broader multilingual Android ASR pack for sherpa-onnx, including Persian, Arabic, CJK, and European languages.',
      sizeLabel: '~940 MB ONNX pack',
      state: ModelInstallState.notInstalled,
      runtime: ModelRuntime.sherpaOnnx,
      minimumIosMajor: 14,
      repoId: 'pantinor/sherpa-onnx-qwen3-asr-0.6b-int8',
      installNote:
          'Use when broader language coverage matters. Transcript text is wired first; timestamp quality must be proven before exposing segments.',
    ),
    LocalModel(
      id: 'oruk_fourier_2b_sherpa',
      name: 'Oruk Fourier 2B',
      kind: ModelKind.transcription,
      description:
          'English transcription on Android. The weights are licensed by Oruk for noncommercial use (CC BY-NC 4.0).',
      sizeLabel: '2.41 GB ONNX pack',
      state: ModelInstallState.notInstalled,
      runtime: ModelRuntime.sherpaOnnx,
      minimumIosMajor: 14,
      repoId: 'oruk/oruk-fourier-2b',
      revision: '3fda023e157ce7986f137f76fcf326ed6e08fa73',
      snapshotPath: 'onnx/sherpa-int8',
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
    await _cleanOrphanedDownloadsOnce(modelRoot);
    final models = <LocalModel>[];
    var changed = false;
    for (final catalogModel in catalog) {
      if (catalogModel.runtime == ModelRuntime.appleSpeech) {
        models.add(catalogModel);
        continue;
      }
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

  // An immutable revision identifies exactly which bytes may safely be reused.
  static String? _resumeDirectoryName(LocalModel model) {
    if (!RegExp(r'^[0-9a-f]{40}$').hasMatch(model.revision)) return null;
    final identity = jsonEncode([
      model.repoId,
      model.revision,
      model.snapshotPath,
    ]);
    return '${model.id}.${sha256.convert(utf8.encode(identity))}.resume';
  }

  Future<List<LocalModel>> removeModel(LocalModel model) async {
    final resumeName = _resumeDirectoryName(model);
    if (resumeName != null) {
      final root = await _modelDirectory();
      final partial = Directory('${root.path}/$resumeName');
      if (await partial.exists()) await partial.delete(recursive: true);
    }
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
    final removed = models.firstWhere((item) => item.id == model.id);
    await _historyStore.updateModelState(removed);
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
      final installed = models.firstWhere((item) => item.id == model.id);
      await _historyStore.updateModelState(installed);
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
    final resumeName = _resumeDirectoryName(model);
    final resumable = resumeName != null;
    final partial = Directory(
      resumeName == null
          ? '${target.path}.download'
          : '${modelRoot.path}/$resumeName',
    );
    if (!resumable && await partial.exists()) {
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
        cancelToken: cancelToken,
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
          resumable: resumable,
          digest: file.sha256,
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
          'snapshotPath': model.snapshotPath,
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

      cancelToken.throwIfCanceled();
      if (await target.exists()) {
        await target.delete(recursive: true);
      }
      await partial.rename(target.path);

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
      final installed = models.firstWhere((item) => item.id == model.id);
      await _historyStore.updateModelState(installed);
      return models;
    } catch (_) {
      if (!resumable && await partial.exists()) {
        await partial.delete(recursive: true);
      }
      cancelToken.throwIfCanceled();
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
    required ModelDownloadCancelToken cancelToken,
  }) async {
    return _withDownloadRetries('Model manifest', () async {
      cancelToken.throwIfCanceled();
      final treePath = snapshotPath == null || snapshotPath.isEmpty
          ? '/api/models/$repoId/tree/$revision'
          : '/api/models/$repoId/tree/$revision/$snapshotPath';
      final uri = _huggingFaceUri(treePath, {'recursive': 'true'});
      final request = await client.getUrl(uri);
      final response = await request.close();
      cancelToken.throwIfCanceled();
      if (response.statusCode < 200 || response.statusCode >= 300) {
        await response.drain<void>();
        final message =
            'Model manifest failed with HTTP ${response.statusCode}.';
        if (_isRetryableStatus(response.statusCode)) {
          throw _RetryableModelDownloadException(message);
        }
        throw LocalWhisperException(message);
      }
      final body = await utf8.decoder.bind(response).join();
      final decoded = jsonDecode(body);
      if (decoded is! List) {
        throw const LocalWhisperException(
          'Model manifest response is invalid.',
        );
      }
      return decoded
          .whereType<Map<String, Object?>>()
          .where((item) => item['type'] == 'file')
          .map(
            (item) => _SnapshotFile(
              item['path'] as String? ?? '',
              (item['size'] as num?)?.toInt() ?? 0,
              item['lfs'] is Map
                  ? (item['lfs'] as Map)['oid'] as String?
                  : null,
            ),
          )
          .where((file) => file.path.isNotEmpty)
          .toList(growable: false);
    }, cancelToken: cancelToken);
  }

  Future<int> _downloadFile({
    required HttpClient client,
    required ModelDownloadCancelToken cancelToken,
    required String repoId,
    required String revision,
    required String path,
    required File destination,
    required int declaredSize,
    required bool resumable,
    required String? digest,
    required void Function(int bytes) onChunk,
  }) async {
    // Only completed, validated files have their final names in the staging
    // directory. A .part file remains safe to resume after process death.
    if (resumable &&
        declaredSize > 0 &&
        await destination.exists() &&
        await destination.length() == declaredSize) {
      return declaredSize;
    }
    final part = File('${destination.path}.part');
    return _withDownloadRetries('Model file "$path"', () async {
      cancelToken.throwIfCanceled();
      var offset = resumable && declaredSize > 0 && await part.exists()
          ? await part.length()
          : 0;
      if (offset > declaredSize) offset = 0;
      if (offset == 0 || offset < declaredSize) {
        final request = await client.getUrl(
          _huggingFaceUri('/$repoId/resolve/$revision/$path'),
        );
        // Validate byte ranges against the uncompressed bytes written to disk.
        request.headers.set(HttpHeaders.acceptEncodingHeader, 'identity');
        if (offset > 0)
          request.headers.set(HttpHeaders.rangeHeader, 'bytes=$offset-');
        final response = await request.close();
        cancelToken.throwIfCanceled();
        if (response.statusCode == HttpStatus.partialContent) {
          final range = response.headers.value(HttpHeaders.contentRangeHeader);
          if (offset == 0 ||
              range != 'bytes $offset-${declaredSize - 1}/$declaredSize') {
            await response.drain<void>();
            await _deleteIfExists(part);
            throw _RetryableModelDownloadException(
              'Unexpected byte range for "$path".',
            );
          }
        } else if (response.statusCode == HttpStatus.ok) {
          // A server is allowed to ignore Range and send the entire file.
          offset = 0;
        } else {
          await response.drain<void>();
          if (response.statusCode == HttpStatus.requestedRangeNotSatisfiable) {
            await _deleteIfExists(part);
            throw _RetryableModelDownloadException(
              'Range expired for "$path".',
            );
          }
          final message =
              'Model file "$path" failed with HTTP ${response.statusCode}.';
          if (_isRetryableStatus(response.statusCode)) {
            throw _RetryableModelDownloadException(message);
          }
          throw LocalWhisperException(message);
        }
        final sink = part.openWrite(
          mode: offset > 0 ? FileMode.append : FileMode.write,
        );
        try {
          await for (final chunk in response) {
            cancelToken.throwIfCanceled();
            sink.add(chunk);
            offset += chunk.length;
            onChunk(offset);
          }
        } finally {
          await sink.close();
        }
      }
      cancelToken.throwIfCanceled();
      if (offset <= 0 || (declaredSize > 0 && offset != declaredSize)) {
        throw _RetryableModelDownloadException(
          'Model file "$path" has $offset bytes, expected $declaredSize.',
        );
      }
      if (resumable &&
          digest != null &&
          (await sha256.bind(part.openRead()).first).toString() != digest) {
        await _deleteIfExists(part);
        throw _RetryableModelDownloadException('SHA-256 mismatch for "$path".');
      }
      await part.rename(destination.path);
      return offset;
    }, cancelToken: cancelToken);
  }

  Future<T> _withDownloadRetries<T>(
    String label,
    Future<T> Function() operation, {
    ModelDownloadCancelToken? cancelToken,
  }) async {
    Object? lastError;
    for (var attempt = 1; attempt <= _maxDownloadAttempts; attempt += 1) {
      try {
        cancelToken?.throwIfCanceled();
        return await operation();
      } on _RetryableModelDownloadException catch (error) {
        lastError = error;
      } on SocketException catch (error) {
        lastError = error;
      } on HttpException catch (error) {
        lastError = error;
      } on HandshakeException catch (error) {
        lastError = error;
      } on TimeoutException catch (error) {
        lastError = error;
      }

      cancelToken?.throwIfCanceled();
      if (attempt >= _maxDownloadAttempts) break;
      cancelToken?.throwIfCanceled();
      if (_downloadRetryDelay > Duration.zero) {
        await Future<void>.delayed(_downloadRetryDelay * attempt);
      }
    }
    final reason = lastError?.toString() ?? 'unknown error';
    throw LocalWhisperException(
      '$label could not be downloaded after $_maxDownloadAttempts attempts: $reason',
    );
  }

  Uri _huggingFaceUri(String path, [Map<String, String>? queryParameters]) {
    final basePath = _huggingFaceBaseUri.path;
    final normalizedBase = basePath == '/' || basePath.isEmpty
        ? ''
        : basePath.replaceFirst(RegExp(r'/+$'), '');
    final normalizedPath = path.replaceFirst(RegExp(r'^/+'), '');
    return _huggingFaceBaseUri.replace(
      path: '$normalizedBase/$normalizedPath',
      queryParameters: queryParameters,
    );
  }

  static bool _isRetryableStatus(int statusCode) {
    return statusCode == HttpStatus.requestTimeout ||
        statusCode == HttpStatus.tooManyRequests ||
        statusCode >= 500;
  }

  Future<void> _deleteIfExists(File file) async {
    if (await file.exists()) {
      await file.delete();
    }
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
      if (_resumeDirectoryName(model) != null && decoded['revision'] != model.revision) {
        return false;
      }
      final expectedSnapshot = model.snapshotPath;
      if (expectedSnapshot != null && expectedSnapshot.isNotEmpty) {
        final manifestSnapshot = decoded['snapshotPath'] as String?;
        if (manifestSnapshot != null && manifestSnapshot != expectedSnapshot) {
          return false;
        }
      }
      final files = decoded['files'];
      if (files is! List || files.isEmpty) return false;
      for (final item in files) {
        if (item is! Map) return false;
        final sourcePath = item['sourcePath'] as String?;
        final expectedSnapshot = model.snapshotPath;
        if (expectedSnapshot != null && expectedSnapshot.isNotEmpty) {
          final prefix = expectedSnapshot.endsWith('/')
              ? expectedSnapshot
              : '$expectedSnapshot/';
          if (sourcePath == null || !sourcePath.startsWith(prefix)) {
            return false;
          }
        }
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

  /// A `*.download` staging folder only exists while a download is
  /// actively writing it; force-quitting or crashing mid-download is the
  /// only way one survives past that. A running process would have that
  /// download tracked in memory and never re-enter this cleanup for it, so
  /// gating on `_didCleanOrphanedDownloads` (once per ModelStore instance,
  /// i.e. once per app launch, before any download in this session could
  /// possibly be in flight) makes it safe to sweep unconditionally rather
  /// than leaving orphaned partial downloads to grow forever.
  Future<void> _cleanOrphanedDownloadsOnce(Directory modelRoot) async {
    if (_didCleanOrphanedDownloads) return;
    _didCleanOrphanedDownloads = true;
    if (!await modelRoot.exists()) return;
    await for (final entity in modelRoot.list()) {
      final name = entity.path.split(Platform.pathSeparator).last;
      final obsoleteResume =
          name.endsWith('.resume') &&
          !catalog.any((model) => _resumeDirectoryName(model) == name);
      if (name.endsWith('.download') || obsoleteResume) {
        try {
          await entity.delete(recursive: true);
        } catch (_) {
          // Best-effort cleanup; leave it for next launch if it fails.
        }
      }
    }
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
  const _SnapshotFile(this.path, this.size, this.sha256);

  final String path;
  final int size;
  final String? sha256;
}

class _RetryableModelDownloadException implements Exception {
  const _RetryableModelDownloadException(this.message);

  final String message;

  @override
  String toString() => message;
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
