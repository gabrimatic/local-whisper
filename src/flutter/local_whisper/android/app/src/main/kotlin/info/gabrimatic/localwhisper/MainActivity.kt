package info.gabrimatic.localwhisper

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.media.MediaRecorder
import android.net.Uri
import android.os.Build
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
import java.util.Locale

class MainActivity : FlutterActivity() {
    private val speechChannel = "local_whisper/speech"
    private val levelsChannel = "local_whisper/levels"
    private val setupChannel = "local_whisper/setup"
    private val permissionRequestCode = 4417
    private val handler = Handler(Looper.getMainLooper())
    private var permissionResult: MethodChannel.Result? = null
    private var levelSink: EventChannel.EventSink? = null
    private var recorder: MediaRecorder? = null
    private var recordingFile: File? = null
    private var recordingStartedAt: Long = 0
    private val levelTicker = object : Runnable {
        override fun run() {
            val amplitude = try {
                recorder?.maxAmplitude ?: 0
            } catch (_: RuntimeException) {
                0
            }
            levelSink?.success((amplitude / 32767.0).coerceIn(0.0, 1.0))
            if (recorder != null) {
                handler.postDelayed(this, 120)
            }
        }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, speechChannel)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "status" -> result.success(speechStatus(call.argument<String>("locale") ?: "en-US"))
                    "requestPermissions" -> requestMicrophonePermission(result)
                    "start" -> startRecording(result)
                    "stop" -> stopRecording(result)
                    "cancel" -> {
                        cancelRecording()
                        result.success(null)
                    }
                    "debugTranscribeFile" -> result.success(debugTranscription(call.argument<String>("locale") ?: "en-US"))
                    else -> result.notImplemented()
                }
            }
        EventChannel(flutterEngine.dartExecutor.binaryMessenger, levelsChannel)
            .setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                    levelSink = events
                }

                override fun onCancel(arguments: Any?) {
                    levelSink = null
                }
            })
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, setupChannel)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "openKeyboardSettings" -> result.success(openKeyboardSettings())
                    "openAppSettings" -> result.success(openAppSettings())
                    "keyboardStatus" -> result.success(keyboardStatus())
                    "markKeyboardSeen" -> {
                        prefs().edit().putBoolean("keyboardSeen", true).apply()
                        result.success(null)
                    }
                    "syncKeyboardSettings" -> {
                        prefs().edit()
                            .putBoolean("haptics", call.argument<Boolean>("haptics") ?: true)
                            .putBoolean("quickInsert", call.argument<Boolean>("quickInsert") ?: true)
                            .apply()
                        result.success(null)
                    }
                    else -> result.notImplemented()
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
            "message" to if (granted) {
                "Android local recorder ready. Audio stays on-device and no cloud speech service is used."
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
        if (recorder != null) {
            result.error("already_recording", "A recording is already active.", null)
            return
        }
        val target = File.createTempFile("local-whisper-android-", ".m4a", cacheDir)
        val nextRecorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(this)
        } else {
            @Suppress("DEPRECATION")
            MediaRecorder()
        }
        try {
            nextRecorder.setAudioSource(MediaRecorder.AudioSource.MIC)
            nextRecorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            nextRecorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            nextRecorder.setAudioEncodingBitRate(128000)
            nextRecorder.setAudioSamplingRate(16000)
            nextRecorder.setOutputFile(target.absolutePath)
            nextRecorder.prepare()
            nextRecorder.start()
            recorder = nextRecorder
            recordingFile = target
            recordingStartedAt = System.currentTimeMillis()
            handler.post(levelTicker)
            result.success(null)
        } catch (error: Exception) {
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
        try {
            activeRecorder.stop()
        } catch (error: RuntimeException) {
            cancelRecording()
            result.error("recording_too_short", "No usable local audio was captured.", null)
            return
        } finally {
            activeRecorder.release()
            recorder = null
            handler.removeCallbacks(levelTicker)
            levelSink?.success(0.0)
        }
        val locale = Locale.getDefault().toLanguageTag()
        result.success(
            mapOf(
                "transcript" to "Local Android recording captured.",
                "rawTranscript" to "Local Android recording captured.",
                "duration" to duration,
                "localeId" to locale,
                "onDevice" to true,
            ),
        )
    }

    private fun cancelRecording() {
        val activeRecorder = recorder
        recorder = null
        handler.removeCallbacks(levelTicker)
        levelSink?.success(0.0)
        try {
            activeRecorder?.stop()
        } catch (_: RuntimeException) {
        } finally {
            activeRecorder?.release()
            recordingFile?.delete()
            recordingFile = null
        }
    }

    private fun debugTranscription(locale: String): Map<String, Any> {
        return mapOf(
            "transcript" to "Local Android fixture transcription.",
            "rawTranscript" to "Local Android fixture transcription.",
            "duration" to 1.2,
            "localeId" to locale,
            "onDevice" to true,
        )
    }

    private fun openKeyboardSettings(): Boolean {
        return openIntent(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS))
    }

    private fun openAppSettings(): Boolean {
        return openIntent(
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                data = Uri.parse("package:$packageName")
            },
        )
    }

    private fun openIntent(intent: Intent): Boolean {
        return try {
            startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            true
        } catch (_: Exception) {
            false
        }
    }

    private fun keyboardStatus(): Map<String, Any> {
        val enabled = isKeyboardEnabled()
        val seen = prefs().getBoolean("keyboardSeen", false)
        val message = when {
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

    private fun hasMicrophonePermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.RECORD_AUDIO,
        ) == PackageManager.PERMISSION_GRANTED
    }

    private fun prefs(): SharedPreferences {
        return getSharedPreferences("local_whisper_setup", Context.MODE_PRIVATE)
    }
}
