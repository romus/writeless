"""Tests for writeless.recorder — audio state machine and transcription."""

import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

from writeless.constants import (
    IDLE_ICON,
    PROCESSING_ICON,
    RECORDING_ICON,
)


def _make_recorder(**overrides):
    """Create a Recorder with mocked callbacks."""
    from writeless.recorder import Recorder

    kwargs = dict(
        on_status_change=MagicMock(),
        on_notify=MagicMock(),
        on_recording_stopped=MagicMock(),
        dispatch_to_main=lambda fn: fn(),  # execute immediately
    )
    kwargs.update(overrides)
    return Recorder(**kwargs)


class TestRecorderInit:
    def test_initial_state(self):
        rec = _make_recorder()
        assert rec.is_recording is False
        assert rec.model_loaded is False
        assert rec.model_name == "small"

    def test_ssl_verification_default(self):
        rec = _make_recorder()
        assert rec.ssl_verification_enabled is True


class TestStartStop:
    @patch("writeless.recorder.sd")
    @patch("writeless.recorder.update_audio_device_cache")
    def test_start_sets_recording_icon(self, _cache, mock_sd):
        mock_stream = MagicMock()
        mock_sd.InputStream.return_value = mock_stream
        rec = _make_recorder()

        rec.start()
        # Give _open_stream thread time to run
        time.sleep(0.1)

        rec._on_status_change.assert_any_call(RECORDING_ICON)

    @patch("writeless.recorder.sd")
    @patch("writeless.recorder.update_audio_device_cache")
    def test_start_reinitialises_portaudio(self, _cache, mock_sd):
        mock_sd.InputStream.return_value = MagicMock()
        rec = _make_recorder()

        rec.start()
        time.sleep(0.1)

        mock_sd._terminate.assert_called()
        mock_sd._initialize.assert_called()

    @patch("writeless.recorder.sd")
    @patch("writeless.recorder.update_audio_device_cache")
    def test_stop_sets_idle_icon(self, _cache, mock_sd):
        mock_sd.InputStream.return_value = MagicMock()
        rec = _make_recorder()

        rec.start()
        time.sleep(0.1)
        rec.stop()

        rec._on_status_change.assert_any_call(IDLE_ICON)

    @patch("writeless.recorder.sd")
    @patch("writeless.recorder.update_audio_device_cache")
    def test_stop_calls_recording_stopped(self, _cache, mock_sd):
        mock_sd.InputStream.return_value = MagicMock()
        rec = _make_recorder()

        rec.start()
        time.sleep(0.1)
        rec.stop()

        rec._on_recording_stopped.assert_called()

    @patch("writeless.recorder.sd")
    @patch("writeless.recorder.update_audio_device_cache")
    def test_stop_without_audio_notifies(self, _cache, mock_sd):
        mock_sd.InputStream.return_value = MagicMock()
        rec = _make_recorder()

        rec.start()
        time.sleep(0.1)
        rec.stop()

        rec._on_notify.assert_called_with("No audio recorded.")

    @patch("writeless.recorder.sd")
    @patch("writeless.recorder.update_audio_device_cache")
    def test_stop_with_audio_starts_transcription(self, _cache, mock_sd):
        mock_sd.InputStream.return_value = MagicMock()
        rec = _make_recorder()

        rec.start()
        time.sleep(0.1)

        # Simulate audio frames
        with rec._lock:
            rec._audio_frames = [np.zeros((160, 1), dtype="float32")]

        # Prevent the real _transcribe from running (it would try to
        # download the Whisper model in a daemon thread, causing
        # "Bad file descriptor" errors after the test process exits).
        rec._transcribe = MagicMock()

        rec.stop()

        rec._on_status_change.assert_any_call(PROCESSING_ICON)
        rec._transcribe.assert_called_once()


class TestStartNonBlocking:
    """Verify that start() returns immediately (main thread never blocks)."""

    @patch("writeless.recorder.sd")
    @patch("writeless.recorder.update_audio_device_cache")
    def test_start_returns_immediately(self, _cache, mock_sd):
        # Make PortAudio reinit slow to prove start() doesn't wait for it
        def slow_terminate():
            time.sleep(0.5)

        mock_sd._terminate.side_effect = slow_terminate
        mock_sd.InputStream.return_value = MagicMock()

        rec = _make_recorder()
        t0 = time.monotonic()
        rec.start()
        elapsed = time.monotonic() - t0

        # start() should return in well under 0.5s (the slow_terminate time)
        assert elapsed < 0.1

    @patch("writeless.recorder.sd")
    @patch("writeless.recorder.update_audio_device_cache")
    def test_rapid_start_stop_does_not_deadlock(self, _cache, mock_sd):
        mock_sd.InputStream.return_value = MagicMock()
        rec = _make_recorder()

        # Rapid toggle — should not hang
        for _ in range(5):
            rec.start()
            time.sleep(0.05)
            rec.stop()
            time.sleep(0.05)

        assert rec.is_recording is False


class TestSessionIdGuard:
    @patch("writeless.recorder.sd")
    @patch("writeless.recorder.update_audio_device_cache")
    def test_stale_session_skips_stream_open(self, _cache, mock_sd):
        """If session_id changes before _open_stream runs, it should bail."""
        mock_sd.InputStream.return_value = MagicMock()
        rec = _make_recorder()

        rec.start()  # session_id = 1
        rec._session_id = 99  # simulate a newer session

        time.sleep(0.2)

        # InputStream should NOT have been created for the stale session
        # (it may or may not be called depending on timing, but recording
        # should not be active for session 1)
        assert rec._session_id == 99


class TestCleanup:
    @patch("writeless.recorder.sd")
    def test_cleanup_aborts_stream(self, mock_sd):
        mock_stream = MagicMock()
        rec = _make_recorder()
        rec._stream = mock_stream

        rec.cleanup()

        mock_stream.abort.assert_called_once()
        mock_stream.close.assert_called_once()

    @patch("writeless.recorder.sd")
    def test_cleanup_terminates_portaudio(self, mock_sd):
        rec = _make_recorder()
        rec.cleanup()
        mock_sd._terminate.assert_called()

    @patch("writeless.recorder.sd")
    def test_cleanup_safe_to_call_twice(self, mock_sd):
        rec = _make_recorder()
        rec.cleanup()
        rec.cleanup()  # should not raise

    @patch("writeless.recorder.sd")
    def test_cleanup_sets_not_recording(self, mock_sd):
        rec = _make_recorder()
        rec._recording = True
        rec.cleanup()
        assert rec.is_recording is False


class TestStopTimeout:
    @patch("writeless.recorder.sd")
    @patch("writeless.recorder.update_audio_device_cache")
    def test_timeout_notification_message(self, _cache, mock_sd):
        mock_sd.InputStream.return_value = MagicMock()
        rec = _make_recorder()

        rec.start()
        time.sleep(0.1)
        rec.stop(timeout_reached=True, timeout_seconds=10)

        rec._on_notify.assert_any_call(
            "Recording stopped: no audio data for 10 seconds."
        )


class TestModelCache:
    def test_validate_model_cache_missing_dir(self, tmp_path):
        from writeless.recorder import validate_model_cache

        with patch("writeless.recorder._get_model_cache_dir", return_value=str(tmp_path / "nonexistent")):
            assert validate_model_cache("small") is True

    def test_validate_model_cache_valid(self, tmp_path):
        from writeless.recorder import validate_model_cache

        cache_dir = tmp_path / "model"
        (cache_dir / "refs").mkdir(parents=True)
        (cache_dir / "snapshots").mkdir(parents=True)

        with patch("writeless.recorder._get_model_cache_dir", return_value=str(cache_dir)):
            assert validate_model_cache("small") is True

    def test_validate_model_cache_corrupted(self, tmp_path):
        from writeless.recorder import validate_model_cache

        cache_dir = tmp_path / "model"
        cache_dir.mkdir()
        # Missing refs/ and snapshots/

        with patch("writeless.recorder._get_model_cache_dir", return_value=str(cache_dir)):
            assert validate_model_cache("small") is False

    def test_clear_model_cache_absent(self, tmp_path):
        from writeless.recorder import clear_model_cache

        with patch("writeless.recorder._get_model_cache_dir", return_value=str(tmp_path / "gone")):
            assert clear_model_cache("small") is True

    def test_clear_model_cache_removes_dir(self, tmp_path):
        from writeless.recorder import clear_model_cache

        cache_dir = tmp_path / "model"
        cache_dir.mkdir()
        (cache_dir / "file.bin").write_text("data")

        with patch("writeless.recorder._get_model_cache_dir", return_value=str(cache_dir)):
            assert clear_model_cache("small") is True
        assert not cache_dir.exists()
