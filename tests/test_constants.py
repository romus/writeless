"""Tests for writeless.constants — app constants and model definitions."""

import re

from writeless.constants import (
    APP_VERSION,
    COMPLETION_SOUND_OFF,
    COMPLETION_SOUNDS,
    DEFAULT_COMPLETION_SOUND,
    DEFAULT_WHISPER_MODEL,
    HOTKEY,
    RECORDING_START_TIMEOUT_SEC,
    RECORDING_STALL_TIMEOUT_SEC,
    SAMPLE_RATE,
    WHISPER_MODELS,
)


class TestAppVersion:
    def test_semver_format(self):
        assert re.match(r"^\d+\.\d+\.\d+$", APP_VERSION)


class TestWhisperModels:
    def test_models_is_nonempty(self):
        assert len(WHISPER_MODELS) > 0

    def test_each_model_is_id_label_pair(self):
        for model_id, label in WHISPER_MODELS:
            assert isinstance(model_id, str)
            assert isinstance(label, str)
            assert len(model_id) > 0

    def test_default_model_in_list(self):
        model_ids = [mid for mid, _ in WHISPER_MODELS]
        assert DEFAULT_WHISPER_MODEL in model_ids


class TestCompletionSounds:
    def test_off_is_first_entry(self):
        assert COMPLETION_SOUNDS[0] == (COMPLETION_SOUND_OFF, "Off")

    def test_default_sound_in_list_and_not_off(self):
        sound_ids = [sid for sid, _ in COMPLETION_SOUNDS]
        assert DEFAULT_COMPLETION_SOUND in sound_ids
        assert DEFAULT_COMPLETION_SOUND != COMPLETION_SOUND_OFF

    def test_ids_are_unique(self):
        sound_ids = [sid for sid, _ in COMPLETION_SOUNDS]
        assert len(set(sound_ids)) == len(sound_ids)

    def test_each_sound_is_id_label_pair(self):
        for sound_id, label in COMPLETION_SOUNDS:
            assert isinstance(sound_id, str) and sound_id
            assert isinstance(label, str) and label


class TestTimeouts:
    def test_start_timeout_positive(self):
        assert RECORDING_START_TIMEOUT_SEC > 0

    def test_stall_timeout_greater_than_start(self):
        assert RECORDING_STALL_TIMEOUT_SEC > RECORDING_START_TIMEOUT_SEC


class TestAudioConfig:
    def test_sample_rate_is_16khz(self):
        assert SAMPLE_RATE == 16000
