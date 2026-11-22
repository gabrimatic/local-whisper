package info.gabrimatic.localwhisper

import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.inputmethodservice.InputMethodService
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.Settings
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONException

class LocalWhisperInputMethodService : InputMethodService() {
    private val verificationToken = "[[LOCAL_WHISPER_KEYBOARD_VERIFIED]]"

    override fun onCreateInputView(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(18, 14, 18, 44)
            setBackgroundColor(Color.rgb(9, 16, 19))
        }
        root.addView(
            LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(4, 0, 4, 10)
                addView(
                    TextView(this@LocalWhisperInputMethodService).apply {
                        text = "Local Whisper Keyboard"
                        setTextColor(Color.rgb(200, 208, 218))
                        textSize = 15f
                        gravity = Gravity.CENTER
                    },
                    LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f),
                )
                addView(
                    key("Settings") {
                        startActivity(
                            Intent(Settings.ACTION_INPUT_METHOD_SETTINGS).addFlags(
                                Intent.FLAG_ACTIVITY_NEW_TASK,
                            ),
                        )
                    },
                    LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.WRAP_CONTENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT,
                    ),
                )
            },
        )
        root.addView(
            row(
                key("Insert latest transcript") {
                    val transcript = latestTranscript()
                    if (transcript != null) {
                        commit(transcript)
                    } else {
                        Toast.makeText(this, "No saved transcript", Toast.LENGTH_SHORT).show()
                    }
                },
                key("Verify") {
                    markKeyboardSeen()
                    commit(verificationToken)
                },
            ),
        )
        if (quickInsertEnabled()) {
            root.addView(
                row(
                    key("Clean") { commit("[Clean] ") },
                    key("Message") { commit("[Message] ") },
                    key("Notes") { commit("[Notes]\n") },
                    key("Prompt") { commit("[Prompt] ") },
                ),
            )
            root.addView(
                row(
                    key(",") { commit(", ") },
                    key(".") { commit(". ") },
                    key("?") { commit("? ") },
                    key("!") { commit("! ") },
                ),
            )
        }
        root.addView(
            row(
                key("Space") { commit(" ") },
                key("New line") { commit("\n") },
                key("Delete") {
                    currentInputConnection?.deleteSurroundingText(1, 0)
                },
            ),
        )
        return root
    }

    private fun row(vararg buttons: Button): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            setPadding(0, 4, 0, 4)
            buttons.forEach { button ->
                addView(
                    button,
                    LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                        .apply { setMargins(4, 0, 4, 0) },
                )
            }
        }
    }

    private fun key(label: String, action: () -> Unit): Button {
        return Button(this).apply {
            text = label
            isAllCaps = false
            setOnClickListener {
                maybeVibrate()
                action()
            }
        }
    }

    private fun commit(text: String) {
        currentInputConnection?.commitText(text, 1)
    }

    private fun latestTranscript(): String? {
        // HistoryStore uses the legacy Flutter SharedPreferences backend and
        // saves newest first. Read at tap time so deleting or clearing history
        // takes effect immediately, without a separate keyboard copy.
        val preferences = getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
        val raw = preferences.getString("flutter.history.v1", null) ?: return null
        val entries = try {
            JSONArray(raw)
        } catch (_: JSONException) {
            return null
        }
        for (index in 0 until entries.length()) {
            val text = entries.optJSONObject(index)?.opt("finalText") as? String
            if (!text.isNullOrBlank()) return text
        }
        return null
    }

    private fun markKeyboardSeen() {
        getSharedPreferences("local_whisper_setup", Context.MODE_PRIVATE)
            .edit()
            .putBoolean("keyboardSeen", true)
            .apply()
    }

    private fun maybeVibrate() {
        val prefs = getSharedPreferences("local_whisper_setup", Context.MODE_PRIVATE)
        if (!prefs.getBoolean("haptics", true)) return
        val vibrator = getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator ?: return
        if (!vibrator.hasVibrator()) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            try {
                vibrator.vibrate(
                    VibrationEffect.createOneShot(18, VibrationEffect.DEFAULT_AMPLITUDE),
                )
            } catch (_: SecurityException) {
            }
        } else {
            @Suppress("DEPRECATION")
            try {
                vibrator.vibrate(18)
            } catch (_: SecurityException) {
            }
        }
    }

    private fun quickInsertEnabled(): Boolean {
        val prefs = getSharedPreferences("local_whisper_setup", Context.MODE_PRIVATE)
        return prefs.getBoolean("quickInsert", true)
    }
}
