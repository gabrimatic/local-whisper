package info.gabrimatic.localwhisper

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.inputmethod.InputMethodManager
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileOutputStream
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.abs
import kotlin.math.max

class MainActivity : FlutterActivity() {
    private val speechChannel = "local_whisper/speech"
    private val levelsChannel = "local_whisper/levels"
    private val setupChannel = "local_whisper/setup"
    private val permissionRequestCode = 4417
    private val audioSampleRate = 16000
    private val audioChannel = AudioFormat.CHANNEL_IN_MONO
    private val audioEncoding = AudioFormat.ENCODING_PCM_16BIT
    private val handler = Handler(Looper.getMainLooper())
    private var permissionResult: MethodChannel.Result? = null
    private var levelSink: EventChannel.EventSink? = null
    private var recorder: AudioRecord? = null
    private var recordingFile: File? = null
    private var recordingThread: Thread? = null
    private var recordingStartedAt: Long = 0
    private val recordingActive = AtomicBoolean(false)

    @Volatile private var latestLevel: Double = 0.0

    @Volatile private var recordedPcmBytes: Long = 0
    private val levelTicker =
        object : Runnable {
            override fun run() {
                levelSink?.success(latestLevel.coerceIn(0.0, 1.0))
                if (recordingActive.get()) {
                    handler.postDelayed(this, 120)
                }
            }
        }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, speechChannel)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "status" -> {
                        result.success(speechStatus(call.argument<String>("locale") ?: "en-US"))
                    }

                    "requestPermissions" -> {
                        requestMicrophonePermission(result)
                    }

                    "start" -> {
                        startRecording(result)
                    }

                    "stop" -> {
                        stopRecording(result)
                    }

                    "cancel" -> {
                        cancelRecording()
                        result.success(null)
                    }

                    "debugTranscribeFile" -> {
                        result.success(debugTranscription(call.argument<String>("locale") ?: "en-US"))
                    }

                    else -> {
                        result.notImplemented()
                    }
                }
            }
        EventChannel(flutterEngine.dartExecutor.binaryMessenger, levelsChannel)
            .setStreamHandler(
                object : EventChannel.StreamHandler {
                    override fun onListen(
                        arguments: Any?,
                        events: EventChannel.EventSink?,
                    ) {
                        levelSink = events
                    }

                    override fun onCancel(arguments: Any?) {
                        levelSink = null
                    }
                },
            )
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, setupChannel)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "openKeyboardSettings" -> {
                        result.success(openKeyboardSettings())
                    }

                    "openAppSettings" -> {
                        result.success(openAppSettings())
                    }

                    "keyboardStatus" -> {
                        result.success(keyboardStatus())
                    }

                    "markKeyboardSeen" -> {
                        prefs().edit().putBoolean("keyboardSeen", true).apply()
                        result.success(null)
                    }

                    "syncKeyboardSettings" -> {
                        prefs()
                            .edit()
                            .putBoolean("haptics", call.argument<Boolean>("haptics") ?: true)
                            .putBoolean("quickInsert", call.argument<Boolean>("quickInsert") ?: true)
                            .apply()
                        result.success(null)
                    }

                    else -> {
                        result.notImplemented()
                    }
                }
            }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs().edit().putBoolean("appOpened", true).apply()
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == permissionRequestCode) {
            val granted = grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED
            permissionResult?.success(granted)
            permissionResult = null
        }
    }

    private fun speechStatus(locale: String): Map<String, Any> {
        val granted = hasMicrophonePermission()
        return mapOf(
            "permissionsGranted" to granted,
            "onDeviceAvailable" to true,
            "recognitionAvailable" to true,
            "localeId" to locale,
            "message" to
                if (granted) {
                    "Android offline recorder ready. Audio stays on-device and transcribes through the local model pack."
                } else {
                    "Microphone permission is needed before Android can record locally."
                },
        )
    }

    private fun requestMicrophonePermission(result: MethodChannel.Result) {
        if (hasMicrophonePermission()) {
            result.success(true)
            return
        }
        if (permissionResult != null) {
            result.error("permission_in_progress", "Microphone permission is already being requested.", null)
            return
        }
        permissionResult = result
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.RECORD_AUDIO),
            permissionRequestCode,
        )
    }

    private fun startRecording(result: MethodChannel.Result) {
        if (!hasMicrophonePermission()) {
            result.error("microphone_permission", "Microphone permission is required for local recording.", null)
            return
        }
        if (recorder != null || recordingActive.get()) {
            result.error("already_recording", "A recording is already active.", null)
            return
        }
        val target = File.createTempFile("local-whisper-android-", ".wav", cacheDir)
        val minBufferSize = AudioRecord.getMinBufferSize(audioSampleRate, audioChannel, audioEncoding)
        if (minBufferSize <= 0) {
            target.delete()
            result.error("recording_start_failed", "Android could not allocate a local PCM recorder.", null)
            return
        }
        val bufferSize = max(minBufferSize, audioSampleRate / 5 * 2)
        val nextRecorder =
            AudioRecord(
                MediaRecorder.AudioSource.MIC,
                audioSampleRate,
                audioChannel,
                audioEncoding,
                bufferSize,
            )
        if (nextRecorder.state != AudioRecord.STATE_INITIALIZED) {
            nextRecorder.release()
            target.delete()
            result.error("recording_start_failed", "Android microphone recorder did not initialize.", null)
            return
        }

        try {
            writeWavHeader(target, 0)
            nextRecorder.startRecording()
            recordingActive.set(true)
            recordedPcmBytes = 0
            latestLevel = 0.0
            recorder = nextRecorder
            recordingFile = target
            recordingStartedAt = System.currentTimeMillis()
            recordingThread =
                Thread(
                    { recordPcmToWav(nextRecorder, target, bufferSize) },
                    "LocalWhisperAndroidRecorder",
                ).also { it.start() }
            handler.post(levelTicker)
            result.success(null)
        } catch (error: Exception) {
            recordingActive.set(false)
            nextRecorder.release()
            target.delete()
            recorder = null
            recordingFile = null
            result.error("recording_start_failed", error.localizedMessage, null)
        }
    }

    private fun stopRecording(result: MethodChannel.Result) {
        val activeRecorder = recorder
        if (activeRecorder == null) {
            result.error("not_recording", "No local recording is active.", null)
            return
        }
        val duration = ((System.currentTimeMillis() - recordingStartedAt).coerceAtLeast(0)) / 1000.0
        val activeFile = recordingFile
        try {
            recordingActive.set(false)
            activeRecorder.stop()
        } catch (error: RuntimeException) {
            cancelRecording()
            result.error("recording_too_short", "No usable local audio was captured.", null)
            return
        } finally {
            recordingThread?.join(1200)
            activeRecorder.release()
            recorder = null
            recordingThread = null
            handler.removeCallbacks(levelTicker)
            latestLevel = 0.0
            levelSink?.success(0.0)
        }
        if (activeFile == null || !activeFile.exists() || recordedPcmBytes <= 0) {
            activeFile?.delete()
            recordingFile = null
            result.error("recording_empty", "No usable local audio was captured.", null)
            return
        }
        updateWavHeader(activeFile, recordedPcmBytes)
        val locale = Locale.getDefault().toLanguageTag()
        recordingFile = null
        result.success(
            mapOf(
                "audioPath" to activeFile.absolutePath,
                "duration" to duration,
                "localeId" to locale,
                "onDevice" to true,
                "sampleRate" to audioSampleRate,
            ),
        )
    }

    private fun cancelRecording() {
        val activeRecorder = recorder
        recorder = null
        recordingActive.set(false)
        handler.removeCallbacks(levelTicker)
        latestLevel = 0.0
        levelSink?.success(0.0)
        try {
            activeRecorder?.stop()
        } catch (_: RuntimeException) {
        } finally {
            recordingThread?.join(1200)
            activeRecorder?.release()
            recordingThread = null
            recordingFile?.delete()
            recordingFile = null
        }
    }

    private fun recordPcmToWav(
        audioRecord: AudioRecord,
        target: File,
        bufferSize: Int,
    ) {
        val samples = ShortArray(bufferSize / 2)
        val bytes = ByteArray(samples.size * 2)
        try {
            FileOutputStream(target, true).use { output ->
                while (recordingActive.get()) {
                    val read = audioRecord.read(samples, 0, samples.size)
                    if (read <= 0) continue
                    val byteBuffer = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
                    var peak = 0
                    for (index in 0 until read) {
                        val sample = samples[index]
                        peak = max(peak, abs(sample.toInt()))
                        byteBuffer.putShort(sample)
                    }
                    output.write(bytes, 0, read * 2)
                    recordedPcmBytes += read * 2L
                    latestLevel = (peak / 32767.0).coerceIn(0.0, 1.0)
                }
            }
        } catch (_: Exception) {
            recordingActive.set(false)
        }
    }

    private fun writeWavHeader(
        file: File,
        dataBytes: Long,
    ) {
        RandomAccessFile(file, "rw").use { access ->
            access.setLength(0)
            writeWavHeader(access, dataBytes)
        }
    }

    private fun updateWavHeader(
        file: File,
        dataBytes: Long,
    ) {
        RandomAccessFile(file, "rw").use { access ->
            access.seek(0)
            writeWavHeader(access, dataBytes)
        }
    }

    private fun writeWavHeader(
        access: RandomAccessFile,
        dataBytes: Long,
    ) {
        val byteRate = audioSampleRate * 2
        access.writeBytes("RIFF")
        access.writeIntLe((36 + dataBytes).coerceAtMost(Int.MAX_VALUE.toLong()).toInt())
        access.writeBytes("WAVE")
        access.writeBytes("fmt ")
        access.writeIntLe(16)
        access.writeShortLe(1)
        access.writeShortLe(1)
        access.writeIntLe(audioSampleRate)
        access.writeIntLe(byteRate)
        access.writeShortLe(2)
        access.writeShortLe(16)
        access.writeBytes("data")
        access.writeIntLe(dataBytes.coerceAtMost(Int.MAX_VALUE.toLong()).toInt())
    }

    private fun RandomAccessFile.writeIntLe(value: Int) {
        write(
            ByteBuffer
                .allocate(4)
                .order(ByteOrder.LITTLE_ENDIAN)
                .putInt(value)
                .array(),
        )
    }

    private fun RandomAccessFile.writeShortLe(value: Int) {
        write(
            ByteBuffer
                .allocate(2)
                .order(ByteOrder.LITTLE_ENDIAN)
                .putShort(value.toShort())
                .array(),
        )
    }

    private fun debugTranscription(locale: String): Map<String, Any> =
        mapOf(
            "transcript" to "Local Android fixture transcription.",
            "rawTranscript" to "Local Android fixture transcription.",
            "duration" to 1.2,
            "localeId" to locale,
            "onDevice" to true,
        )

    private fun openKeyboardSettings(): Boolean = openIntent(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS))

    private fun openAppSettings(): Boolean =
        openIntent(
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                data = Uri.parse("package:$packageName")
            },
        )

    private fun openIntent(intent: Intent): Boolean =
        try {
            startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            true
        } catch (_: Exception) {
            false
        }

    private fun keyboardStatus(): Map<String, Any> {
        val enabled = isKeyboardEnabled()
        val seen = prefs().getBoolean("keyboardSeen", false)
        val message =
            when {
                seen -> "Local Whisper Keyboard was opened and verified."
                enabled -> "Local Whisper Keyboard is enabled. Select it in the practice field, then tap Verify."
                else -> "Enable Local Whisper Keyboard in Android keyboard settings, return here, then verify it in the practice field."
            }
        return mapOf("keyboardSeen" to seen, "message" to message)
    }

    private fun isKeyboardEnabled(): Boolean {
        val manager = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        return manager.enabledInputMethodList.any { info ->
            info.packageName == packageName
        }
    }

    private fun hasMicrophonePermission(): Boolean =
        ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.RECORD_AUDIO,
        ) == PackageManager.PERMISSION_GRANTED

    private fun prefs(): SharedPreferences = getSharedPreferences("local_whisper_setup", Context.MODE_PRIVATE)
}
