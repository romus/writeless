"""Tests for writeless.settings — persistent JSON settings."""

import json
import os

import writeless.settings as settings
from writeless.constants import DEFAULT_COMPLETION_SOUND


class TestDefaults:
    def test_get_returns_default_when_no_file(self, tmp_settings):
        assert settings.get("notifications_enabled") is True
        assert settings.get("hotkey") == "<cmd>+<alt>+<f8>"
        assert settings.get("whisper_model") == "small"
        assert settings.get("debug_logging") is False
        assert settings.get("completion_sound") == "Glass"

    def test_all_default_keys_present(self, tmp_settings):
        for key in settings._DEFAULTS:
            assert settings.get(key) == settings._DEFAULTS[key]

    def test_completion_sound_default_matches_constant(self, tmp_settings):
        assert settings._DEFAULTS["completion_sound"] == DEFAULT_COMPLETION_SOUND


class TestSetAndGet:
    def test_set_creates_file(self, tmp_settings):
        _, settings_file = tmp_settings
        settings.set("hotkey", "<ctrl>+a")
        assert os.path.isfile(settings_file)

    def test_roundtrip(self, tmp_settings):
        settings.set("whisper_model", "large-v3")
        assert settings.get("whisper_model") == "large-v3"

    def test_set_preserves_other_keys(self, tmp_settings):
        settings.set("hotkey", "<shift>+b")
        settings.set("whisper_model", "tiny")
        assert settings.get("hotkey") == "<shift>+b"
        assert settings.get("whisper_model") == "tiny"

    def test_set_overwrites_value(self, tmp_settings):
        settings.set("notifications_enabled", False)
        assert settings.get("notifications_enabled") is False
        settings.set("notifications_enabled", True)
        assert settings.get("notifications_enabled") is True


class TestCorruptFile:
    def test_corrupt_json_returns_defaults(self, tmp_settings):
        _, settings_file = tmp_settings
        os.makedirs(os.path.dirname(settings_file), exist_ok=True)
        with open(settings_file, "w") as f:
            f.write("{bad json")
        assert settings.get("hotkey") == settings._DEFAULTS["hotkey"]

    def test_partial_file_merges_with_defaults(self, settings_file_with):
        settings_file_with({"hotkey": "<alt>+z"})
        assert settings.get("hotkey") == "<alt>+z"
        assert settings.get("notifications_enabled") is True  # from defaults
