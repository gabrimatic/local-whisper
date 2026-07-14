# SPDX-License-Identifier: MIT
# Copyright (c) 2025-2026 Soroush Yousefpour
"""Tests for the dictionary persistence layer: TOML table rewrites against a
real temp config file — quoting, control characters, bare keys, delta
semantics, and refusal on unparseable files."""

import sys
import tomllib

import pytest


BASE_CONFIG = """[hotkey]
key = "alt_r"

[replacements]
enabled = true

[replacements.rules]
"existing" = "kept"

[dictation]
enabled = true

[ui]
show_overlay = true
"""


@pytest.fixture
def cfg(tmp_path):
    """Fresh whisper_voice.config bound to a temp config.toml."""
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(BASE_CONFIG, encoding="utf-8")

    for mod in list(sys.modules.keys()):
        if "whisper_voice" in mod:
            del sys.modules[mod]

    import whisper_voice.config.loader as loader_mod
    import whisper_voice.config.schema as schema_mod
    from whisper_voice import config as cfg_mod

    schema_mod.CONFIG_DIR = tmp_path
    schema_mod.CONFIG_FILE = cfg_file
    loader_mod._config = None
    loader_mod.load_config()
    return cfg_mod, cfg_file


def _parse(cfg_file):
    return tomllib.loads(cfg_file.read_text(encoding="utf-8"))


class TestAddRemoveReplacement:
    def test_add_new_rule(self, cfg):
        cfg_mod, cfg_file = cfg
        assert cfg_mod.add_replacement("open ai", "OpenAI")
        data = _parse(cfg_file)
        assert data["replacements"]["rules"]["open ai"] == "OpenAI"
        assert data["replacements"]["rules"]["existing"] == "kept"
        # In-memory config synced too.
        assert cfg_mod.get_config().replacements.rules["open ai"] == "OpenAI"

    def test_update_existing_rule(self, cfg):
        cfg_mod, cfg_file = cfg
        assert cfg_mod.add_replacement("existing", "updated")
        assert _parse(cfg_file)["replacements"]["rules"]["existing"] == "updated"

    def test_remove_rule(self, cfg):
        cfg_mod, cfg_file = cfg
        assert cfg_mod.remove_replacement("existing")
        assert "existing" not in _parse(cfg_file)["replacements"]["rules"]

    def test_remove_missing_rule_returns_false(self, cfg):
        cfg_mod, _ = cfg
        assert not cfg_mod.remove_replacement("nope")

    def test_bulk_add(self, cfg):
        cfg_mod, cfg_file = cfg
        assert cfg_mod.add_replacements({"a": "1", "b": "2", "existing": "3"})
        rules = _parse(cfg_file)["replacements"]["rules"]
        assert rules == {"a": "1", "b": "2", "existing": "3"}

    def test_unrelated_sections_preserved(self, cfg):
        cfg_mod, cfg_file = cfg
        cfg_mod.add_replacement("x", "y")
        data = _parse(cfg_file)
        assert data["hotkey"]["key"] == "alt_r"
        assert data["ui"]["show_overlay"] is True

    def test_no_tmp_file_left_behind(self, cfg, tmp_path):
        cfg_mod, _ = cfg
        cfg_mod.add_replacement("x", "y")
        assert not (tmp_path / "config.toml.tmp").exists()


class TestQuotingAndEscaping:
    @pytest.mark.parametrize("spoken,replacement", [
        ('with "quotes"', 'value "quoted"'),
        ("back\\slash", "v\\alue"),
        ("tab\tkey", "tab\tvalue"),
        ("new\nline", "multi\nline"),
        ("unicode straße", "Straße 中文"),
        ("equals = sign", "a = b"),
        ("#hash", "# not a comment"),
    ])
    def test_roundtrip(self, cfg, spoken, replacement):
        cfg_mod, cfg_file = cfg
        assert cfg_mod.add_replacement(spoken, replacement)
        # File must stay parseable and the value must round-trip exactly.
        rules = _parse(cfg_file)["replacements"]["rules"]
        assert rules[spoken] == replacement

    def test_control_chars_do_not_corrupt_file(self, cfg):
        # The historical failure: a raw newline in a basic string makes the
        # whole config unparseable, and the next load runs on defaults.
        cfg_mod, cfg_file = cfg
        assert cfg_mod.add_replacement("sig", "line1\nline2")
        data = _parse(cfg_file)  # would raise if corrupt
        assert data["replacements"]["rules"]["sig"] == "line1\nline2"


class TestBareKeysAndDrift:
    def test_hand_edited_bare_key_consumed_by_rewrite(self, cfg):
        cfg_mod, cfg_file = cfg
        content = cfg_file.read_text(encoding="utf-8")
        content = content.replace(
            '"existing" = "kept"', '"existing" = "kept"\ngonna = "going to"'
        )
        cfg_file.write_text(content, encoding="utf-8")

        assert cfg_mod.add_replacement("new", "rule")
        # No duplicate-key corruption; bare-key rule preserved via reparse.
        rules = _parse(cfg_file)["replacements"]["rules"]
        assert rules["gonna"] == "going to"
        assert rules["new"] == "rule"

    def test_delta_merges_on_disk_changes_from_other_writers(self, cfg):
        # Another process added a rule directly to the file; our in-memory
        # view doesn't know it. The delta rewrite must keep it.
        cfg_mod, cfg_file = cfg
        content = cfg_file.read_text(encoding="utf-8")
        content = content.replace(
            '"existing" = "kept"',
            '"existing" = "kept"\n"from other writer" = "survives"',
        )
        cfg_file.write_text(content, encoding="utf-8")

        assert cfg_mod.add_replacement("mine", "also survives")
        rules = _parse(cfg_file)["replacements"]["rules"]
        assert rules["from other writer"] == "survives"
        assert rules["mine"] == "also survives"


class TestUnparseableRefusal:
    def test_mutation_refused_when_config_broken(self, cfg, capsys):
        cfg_mod, cfg_file = cfg
        cfg_file.write_text("[replacements\nbroken = ", encoding="utf-8")
        assert not cfg_mod.add_replacement("x", "y")
        # The broken file is left exactly as-is for recovery.
        assert cfg_file.read_text(encoding="utf-8") == "[replacements\nbroken = "

    def test_update_config_field_refused_when_broken(self, cfg):
        cfg_mod, cfg_file = cfg
        cfg_file.write_text("not [valid toml", encoding="utf-8")
        assert not cfg_mod.update_config_field("ui", "show_overlay", False)


class TestUpdateConfigFieldStrictness:
    def test_unknown_section_rejected(self, cfg):
        cfg_mod, cfg_file = cfg
        assert not cfg_mod.update_config_field("bogus_section", "key", "v")
        assert "bogus_section" not in cfg_file.read_text(encoding="utf-8")

    def test_unknown_key_rejected(self, cfg):
        cfg_mod, cfg_file = cfg
        assert not cfg_mod.update_config_field("ui", "bogus_key", "v")
        assert "bogus_key" not in cfg_file.read_text(encoding="utf-8")

    def test_known_field_written(self, cfg):
        cfg_mod, cfg_file = cfg
        assert cfg_mod.update_config_field("ui", "show_overlay", False)
        assert _parse(cfg_file)["ui"]["show_overlay"] is False


class TestDictationCommandMutations:
    def test_add_command_creates_table(self, cfg):
        cfg_mod, cfg_file = cfg
        assert cfg_mod.add_dictation_command("next bullet", "\n- ")
        data = _parse(cfg_file)
        assert data["dictation"]["commands"]["next bullet"] == "\n- "

    def test_casefolded_override(self, cfg):
        cfg_mod, cfg_file = cfg
        assert cfg_mod.add_dictation_command("Period", "。")
        commands = _parse(cfg_file)["dictation"]["commands"]
        assert commands == {"period": "。"}

    def test_remove_command(self, cfg):
        cfg_mod, cfg_file = cfg
        cfg_mod.add_dictation_command("smiley", " :)")
        assert cfg_mod.remove_dictation_command("smiley")
        assert _parse(cfg_file)["dictation"]["commands"] == {}

    def test_remove_missing_returns_false(self, cfg):
        cfg_mod, _ = cfg
        assert not cfg_mod.remove_dictation_command("nope")


class TestBrokenConfigBackup:
    def test_loader_backs_up_broken_config(self, cfg, tmp_path):
        cfg_mod, cfg_file = cfg
        cfg_file.write_text("[broken", encoding="utf-8")
        import whisper_voice.config.loader as loader_mod
        loader_mod._config = None
        loader_mod.load_config()
        backups = list(tmp_path.glob("config.toml.broken-*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == "[broken"


class TestSpliceEdgeCases:
    def test_no_trailing_newline_does_not_relocate_parent_keys(self, cfg):
        cfg_mod, cfg_file = cfg
        # Hand-edited file: no rules table, no trailing newline.
        cfg_file.write_text(
            "[hotkey]\nkey = \"alt_r\"\n\n[replacements]\nenabled = true",
            encoding="utf-8",
        )
        assert cfg_mod.add_replacement("gonna", "going to")
        data = _parse(cfg_file)
        assert data["replacements"]["enabled"] is True
        assert data["replacements"]["rules"] == {"gonna": "going to"}

    def test_padded_ondisk_key_removable_by_stripped_name(self, cfg):
        cfg_mod, cfg_file = cfg
        content = cfg_file.read_text(encoding="utf-8").replace(
            '"existing" = "kept"', '" existing " = "kept"'
        )
        cfg_file.write_text(content, encoding="utf-8")
        assert cfg_mod.remove_replacement("existing")
        assert "existing" not in _parse(cfg_file)["replacements"]["rules"]


class TestWriteFailureRollback:
    def test_in_memory_value_rolls_back_when_write_refused(self, cfg):
        cfg_mod, cfg_file = cfg
        original = cfg_mod.get_config().ui.show_overlay
        cfg_file.write_text("not [valid toml", encoding="utf-8")
        assert not cfg_mod.update_config_field("ui", "show_overlay", not original)
        # The snapshot the UI would render must match what's persisted.
        assert cfg_mod.get_config().ui.show_overlay is original
