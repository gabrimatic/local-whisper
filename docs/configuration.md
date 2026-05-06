# Configuration

Local Whisper stores settings in `~/.whisper/config.toml`.

This file is the full config reference. Most users should change settings from the app or with `wh config`; edit the TOML directly only when you need manual control.

## Full Reference

```toml
[hotkey]
key = "alt_r"              # alt_r, alt_l, ctrl_r, ctrl_l, cmd_r, cmd_l,
                           # shift_r, shift_l, caps_lock, f1-f12
double_tap_threshold = 0.4 # seconds

[transcription]
engine = "parakeet_v3"    # "parakeet_v3" (default), "qwen3_asr", or "whisperkit"

[parakeet_v3]
model = "mlx-community/parakeet-tdt-0.6b-v3"
timeout = 0                 # 0 = no limit
chunk_duration = 120.0      # 0 disables chunking
overlap_duration = 15.0
decoding = "greedy"         # "greedy" or "beam"
beam_size = 5
length_penalty = 0.013
patience = 3.5
duration_reward = 0.67
local_attention = false
local_attention_context_size = 256

[qwen3_asr]
model = "mlx-community/Qwen3-ASR-1.7B-bf16"
timeout = 0                # 0 = no limit
temperature = 0.0
top_p = 1.0
top_k = 0
repetition_context_size = 100
repetition_penalty = 1.2
chunk_duration = 1200.0    # max chunk length in seconds
max_tokens = 0             # 0 = auto from duration

[whisper]
model = "whisper-large-v3-v20240930"
language = "auto"
url = "http://localhost:50060/v1/audio/transcriptions"
check_url = "http://localhost:50060/"
timeout = 0
temperature = 0.0
compression_ratio_threshold = 2.4
no_speech_threshold = 0.6
logprob_threshold = -1.0
temperature_fallback_count = 5
prompt_preset = "none"     # "none", "technical", "dictation", or "custom"
prompt = ""                # used only when prompt_preset = "custom"

[grammar]
backend = "apple_intelligence"  # "apple_intelligence", "ollama", or "lm_studio"
enabled = false

[ollama]
url = "http://localhost:11434/api/generate"
check_url = "http://localhost:11434/"
model = "gemma3:4b-it-qat"
keep_alive = "60m"
timeout = 0
max_chars = 0
max_predict = 0
num_ctx = 0
unload_on_exit = false

[apple_intelligence]
max_chars = 0
timeout = 0

[lm_studio]
url = "http://localhost:1234/v1/chat/completions"
check_url = "http://localhost:1234/"
model = "google/gemma-3-4b"
max_chars = 0
max_tokens = 0
timeout = 0

[replacements]
enabled = false

[replacements.rules]
# "gonna" = "going to"
# "wanna" = "want to"

[audio]
sample_rate = 16000
min_duration = 0
max_duration = 0           # 0 = no limit
min_rms = 0.005            # silence threshold (0.0-1.0)
vad_enabled = true
noise_reduction = true
normalize_audio = true
pre_buffer = 0.0           # seconds before hotkey (0.0 = disabled)

[backup]
directory = "~/.whisper"
history_limit = 100        # max entries for text and audio history (1-1000)

[ui]
show_overlay = true
overlay_opacity = 0.92
sounds_enabled = true
notifications_enabled = false
auto_paste = false         # paste at cursor, preserving clipboard

[shortcuts]
enabled = true
proofread = "ctrl+shift+g"
rewrite = "ctrl+shift+r"
prompt_engineer = "ctrl+shift+p"

[tts]
enabled = false            # toggle from Settings -> Voice or the menu bar
provider = "kokoro"
speak_shortcut = "alt+t"

[kokoro_tts]
model = "mlx-community/Kokoro-82M-bf16"
voice = "af_sky"           # See README for available voices
```
