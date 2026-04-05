"""Tests for writeless.constants — app constants and model definitions."""

import re

from writeless.constants import (
    APP_VERSION,
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


class TestTimeouts:
    def test_start_timeout_positive(self):
        assert RECORDING_START_TIMEOUT_SEC > 0

    def test_stall_timeout_greater_than_start(self):
        assert RECORDING_STALL_TIMEOUT_SEC > RECORDING_START_TIMEOUT_SEC


class TestAudioConfig:
    def test_sample_rate_is_16khz(self):
        assert SAMPLE_RATE == 16000
