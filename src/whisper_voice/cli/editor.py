# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Interactive config editor and config command."""

import os
import subprocess
import sys

from .constants import C_DIM, C_GREEN, C_RED, C_RESET, C_YELLOW
from .lifecycle import _get_config_path


def _interactive_config() -> None:
    """Compact inline interactive config editor. No full-screen takeover."""
    import select as _select
    import termios
    import tty

    config_path = _get_config_path()
    if not config_path.exists():
        print(f"{C_YELLOW}Config not found: {config_path}{C_RESET}")
        return

    try:
        import tomllib
        with open(config_path, 'rb') as f:
            data = tomllib.load(f)
    except Exception as e:
        print(f"{C_RED}Error reading config: {e}{C_RESET}")
        return

    def _get(section, key, default):
        return data.get(section, {}).get(key, default)

    ITEMS = [
        {"type": "header",  "label": "Recording"},
        {"type": "choice",  "label": "Hotkey",          "section": "hotkey",        "key": "key",                    "value": _get("hotkey", "key", "alt_r"),                         "options": ["alt_r","alt_l","ctrl_r","ctrl_l","cmd_r","cmd_l","shift_r","shift_l","caps_lock"]},
        {"type": "float",   "label": "Double-tap",       "section": "hotkey",        "key": "double_tap_threshold",   "value": _get("hotkey", "double_tap_threshold", 0.4),            "hint": "sec"},
        {"type": "header",  "label": "Transcription"},
        {"type": "choice",  "label": "Engine",           "section": "transcription", "key": "engine",                 "value": _get("transcription", "engine", "qwen3_asr"),           "options": ["qwen3_asr", "whisperkit"]},
        {"type": "string",  "label": "Language",         "section": "qwen3_asr",     "key": "language",               "value": _get("qwen3_asr", "language", "auto"),                  "hint": "en  fa  auto"},
        {"type": "header",  "label": "Grammar"},
        {"type": "bool",    "label": "Enabled",          "section": "grammar",       "key": "enabled",                "value": _get("grammar", "enabled", False)},
        {"type": "choice",  "label": "Backend",          "section": "grammar",       "key": "backend",                "value": _get("grammar", "backend", "apple_intelligence"),       "options": ["apple_intelligence", "ollama", "lm_studio"]},
        {"type": "header",  "label": "Text to Speech"},
        {"type": "bool",    "label": "Enabled",          "section": "tts",           "key": "enabled",                "value": _get("tts", "enabled", True)},
        {"type": "string",  "label": "Voice",            "section": "kokoro_tts",    "key": "voice",                  "value": _get("kokoro_tts", "voice", "af_sky"),                  "hint": "af_sky  bf_emma  am_adam"},
        {"type": "string",  "label": "Shortcut",         "section": "tts",           "key": "speak_shortcut",         "value": _get("tts", "speak_shortcut", "alt+t")},
        {"type": "header",  "label": "UI"},
        {"type": "bool",    "label": "Auto-paste",       "section": "ui",            "key": "auto_paste",             "value": _get("ui", "auto_paste", False)},
        {"type": "bool",    "label": "Overlay",          "section": "ui",            "key": "show_overlay",           "value": _get("ui", "show_overlay", True)},
        {"type": "bool",    "label": "Sounds",           "section": "ui",            "key": "sounds_enabled",         "value": _get("ui", "sounds_enabled", True)},
        {"type": "bool",    "label": "Notifications",    "section": "ui",            "key": "notifications_enabled",  "value": _get("ui", "notifications_enabled", False)},
        {"type": "header",  "label": "Shortcuts"},
        {"type": "bool",    "label": "Enabled",          "section": "shortcuts",     "key": "enabled",                "value": _get("shortcuts", "enabled", True)},
        {"type": "header",  "label": "Replacements"},
        {"type": "bool",    "label": "Enabled",          "section": "replacements",  "key": "enabled",                "value": _get("replacements", "enabled", False)},
        {"type": "header",  "label": "Audio"},
        {"type": "bool",    "label": "VAD",              "section": "audio",         "key": "vad_enabled",            "value": _get("audio", "vad_enabled", True)},
        {"type": "bool",    "label": "Noise reduction",  "section": "audio",         "key": "noise_reduction",        "value": _get("audio", "noise_reduction", True)},
        {"type": "bool",    "label": "Normalize",        "section": "audio",         "key": "normalize_audio",        "value": _get("audio", "normalize_audio", True)},
        {"type": "float",   "label": "Pre-buffer",       "section": "audio",         "key": "pre_buffer",             "value": _get("audio", "pre_buffer", 0.0),                       "hint": "sec  0=off"},
    ]

    selectable = [i for i, it in enumerate(ITEMS) if it["type"] != "header"]
    cursor  = [0]   # index into selectable
    vtop    = [0]   # first ITEMS index shown in viewport
    last_n  = [0]   # lines printed in last render
    extra   = [0]   # extra lines below block left by inline edit prompt
    VLINES  = 14    # content rows visible in viewport
    LW      = 18    # label column width

    BD = "\033[1m"
    DM = "\033[2m"
    GN = "\033[92m"
    CY = "\033[96m"
    YL = "\033[93m"
    RD = "\033[91m"
    RS = "\033[0m"
    HIDE = "\033[?25l"
    SHOW = "\033[?25h"

    stdin_fd = sys.stdin.fileno()
    old_tty  = termios.tcgetattr(stdin_fd)

    def _fmt(item):
        v, t = item["value"], item["type"]
        if t == "bool":
            return f"{GN}● on{RS}" if v else f"{DM}○ off{RS}"
        hint = item.get("hint", "")
        s = f"{CY}{v}{RS}"
        return f"{s}  {DM}{hint}{RS}" if hint else s

    def _adjust_vtop():
        sel_abs = selectable[cursor[0]]
        if sel_abs < vtop[0]:
            vtop[0] = sel_abs
        elif sel_abs >= vtop[0] + VLINES:
            vtop[0] = max(0, sel_abs - VLINES + 1)

    def _render(msg="", msg_color=DM):
        _adjust_vtop()
        lines = []
        lines.append(f"  {BD}Config{RS}  {DM}{config_path}{RS}")

        visible   = ITEMS[vtop[0]: vtop[0] + VLINES]
        has_above = vtop[0] > 0
        has_below = vtop[0] + VLINES < len(ITEMS)

        for row_i, item in enumerate(visible):
            abs_i = vtop[0] + row_i
            if item["type"] == "header":
                lines.append(f"  {DM}{item['label']}{RS}")
                continue
            is_sel = (abs_i == selectable[cursor[0]])
            val_s  = _fmt(item)
            if is_sel:
                lines.append(f"  {GN}▶{RS}  {BD}{item['label']:<{LW}}{RS}  {val_s}")
            else:
                lines.append(f"     {DM}{item['label']:<{LW}}{RS}  {val_s}")

        # Scroll indicator — doubles as status message when one is present
        if msg:
            lines.append(f"  {msg_color}{msg}{RS}")
        elif has_above and has_below:
            lines.append(f"  {DM}↑ above   ↓ below{RS}")
        elif has_above:
            lines.append(f"  {DM}↑ above{RS}")
        elif has_below:
            lines.append(f"  {DM}↓ below{RS}")
        else:
            lines.append("")

        lines.append(f"  {DM}↑↓ navigate   space toggle   enter edit   q quit{RS}")

        n_up = last_n[0] + extra[0]
        if n_up:
            sys.stdout.write(f"\033[{n_up}A")
        extra[0] = 0
        sys.stdout.write("".join(f"\r\033[2K{ln}\n" for ln in lines))
        sys.stdout.flush()
        last_n[0] = len(lines)

    def _read_key():
        b = os.read(stdin_fd, 1)
        if not b:
            # EOF (stdin closed / terminal disconnected) — treat as quit
            return "\x04"
        if b == b"\x1b":
            r, _, _ = _select.select([stdin_fd], [], [], 0.15)
            if r:
                # Arrow keys are 3-byte CSI sequences: ESC [ X
                # Read exactly 2 more bytes to avoid consuming the next keypress.
                rest = os.read(stdin_fd, 2)
                if rest == b"[A":
                    return "up"
                if rest == b"[B":
                    return "down"
                return ""   # unrecognised escape sequence — ignore
            return "esc"
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            return ""

    def _save(item) -> bool:
        try:
            import fcntl as _fl

            from whisper_voice.config import _replace_in_section, _serialize_toml_value
            fd2 = os.open(str(config_path), os.O_RDWR | os.O_CREAT, 0o644)
            try:
                _fl.flock(fd2, _fl.LOCK_EX)
                content = config_path.read_text()
                content = _replace_in_section(
                    content, item["section"], item["key"],
                    _serialize_toml_value(item["value"])
                )
                config_path.write_text(content)
            finally:
                _fl.flock(fd2, _fl.LOCK_UN)
                os.close(fd2)
            return True
        except Exception:
            return False

    def _toggle() -> tuple:
        item = ITEMS[selectable[cursor[0]]]
        if item["type"] == "bool":
            item["value"] = not item["value"]
        elif item["type"] == "choice":
            opts = item["options"]
            idx = opts.index(item["value"]) if item["value"] in opts else -1
            item["value"] = opts[(idx + 1) % len(opts)]
        else:
            return ("", DM)
        ok = _save(item)
        return ("", DM) if ok else ("not saved", RD)

    def _edit() -> tuple:
        item = ITEMS[selectable[cursor[0]]]
        if item["type"] in ("bool", "choice"):
            return _toggle()

        prompt_text = f"  {item['label']} [{item['value']}]: "
        sys.stdout.write(f"{SHOW}\r\033[2K{BD}{prompt_text}{RS}")
        sys.stdout.flush()

        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_tty)
        try:
            new_raw = input()
        except (EOFError, KeyboardInterrupt):
            new_raw = ""
        finally:
            tty.setraw(stdin_fd)
            sys.stdout.write(HIDE)

        # Compute how many terminal lines the prompt + typed input occupied
        # so _render can move the cursor back to the right position.
        try:
            cols = os.get_terminal_size(stdin_fd).columns
        except OSError:
            cols = 80
        visible_len = len(prompt_text) + len(new_raw)
        extra[0] = max(1, (visible_len + cols - 1) // cols)

        v = new_raw.strip()
        if not v:
            return ("", DM)
        try:
            item["value"] = int(v)   if item["type"] == "int"   else \
                            float(v) if item["type"] == "float" else v
        except ValueError:
            return ("invalid value", YL)
        ok = _save(item)
        return ("saved", GN) if ok else ("not saved", RD)

    msg, msg_color = "", DM
    try:
        sys.stdout.write(HIDE)
        tty.setraw(stdin_fd)
        while True:
            _render(msg, msg_color)
            msg, msg_color = "", DM
            key = _read_key()
            if key in ("q", "Q", "\x03", "\x04", "esc"):
                break
            elif key == "up":
                cursor[0] = max(0, cursor[0] - 1)
            elif key == "down":
                cursor[0] = min(len(selectable) - 1, cursor[0] + 1)
            elif key == " ":
                msg, msg_color = _toggle()
            elif key in ("\r", "\n"):
                msg, msg_color = _edit()
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_tty)
        sys.stdout.write(f"{SHOW}\n")
        sys.stdout.flush()


def cmd_config(args: list):
    """Show, edit, or print path to config."""
    config_path = _get_config_path()

    if not args or args[0] == "show":
        if not sys.stdin.isatty():
            # Non-interactive: print static summary
            if not config_path.exists():
                print(f"{C_YELLOW}Config not found: {config_path}{C_RESET}")
                return
            try:
                import tomllib
                with open(config_path, 'rb') as f:
                    data = tomllib.load(f)
            except Exception as e:
                print(f"{C_RED}Error reading config: {e}{C_RESET}", file=sys.stderr)
                return
            engine = data.get("transcription", {}).get("engine", "qwen3_asr")
            language = data.get(engine, {}).get("language", "auto")
            def _on_off(v): return f"{C_GREEN}on{C_RESET}" if v else f"{C_DIM}off{C_RESET}"
            print()
            print(f"  {C_DIM}Engine{C_RESET}      {C_GREEN}{engine}{C_RESET}  {C_DIM}({language}){C_RESET}")
            print(f"  {C_DIM}Grammar{C_RESET}     {_on_off(data.get('grammar',{}).get('enabled',False))}  {C_DIM}{data.get('grammar',{}).get('backend','')}{C_RESET}")
            print(f"  {C_DIM}TTS{C_RESET}         {_on_off(data.get('tts',{}).get('enabled',True))}  {C_DIM}{data.get('kokoro_tts',{}).get('voice','af_sky')}{C_RESET}")
            print(f"  {C_DIM}Hotkey{C_RESET}      {data.get('hotkey',{}).get('key','alt_r').replace('_',' ')}")
            print()
            print(f"  {C_DIM}{config_path}{C_RESET}")
            print()
            return
        _interactive_config()
        return

    if args[0] == "edit":
        editor = os.environ.get("EDITOR", "open")
        if editor == "open":
            subprocess.run(["open", str(config_path)])
        else:
            os.execvp(editor, [editor, str(config_path)])
        return

    if args[0] == "path":
        print(config_path)
        return

    print(f"{C_RED}Unknown config subcommand: {args[0]}{C_RESET}", file=sys.stderr)
    print(f"{C_DIM}Usage: wh config [edit|path]{C_RESET}", file=sys.stderr)
    sys.exit(1)
