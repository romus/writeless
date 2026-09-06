"""Tests for writeless.system_services — completion sound playback."""

from unittest.mock import MagicMock, patch

import pytest

import writeless.system_services as system_services
from writeless.constants import COMPLETION_SOUND_OFF


@pytest.fixture(autouse=True)
def _reset_current_sound(monkeypatch):
    """_current_sound is module state; isolate it between tests."""
    monkeypatch.setattr(system_services, "_current_sound", None)


class TestPlaySystemSound:
    def test_off_is_silent(self):
        with patch("AppKit.NSSound") as ns_sound:
            assert system_services.play_system_sound(COMPLETION_SOUND_OFF) is False
            ns_sound.soundNamed_.assert_not_called()

    def test_empty_name_is_silent(self):
        with patch("AppKit.NSSound") as ns_sound:
            assert system_services.play_system_sound("") is False
            ns_sound.soundNamed_.assert_not_called()

    def test_known_name_plays(self):
        with patch("AppKit.NSSound") as ns_sound:
            assert system_services.play_system_sound("Glass") is True
            ns_sound.soundNamed_.assert_called_once_with("Glass")
            ns_sound.soundNamed_.return_value.play.assert_called_once_with()

    def test_unknown_name_returns_false(self):
        with patch("AppKit.NSSound") as ns_sound:
            ns_sound.soundNamed_.return_value = None
            assert system_services.play_system_sound("Nope") is False

    def test_previous_sound_is_stopped_before_next_plays(self):
        with patch("AppKit.NSSound") as ns_sound:
            first, second = MagicMock(), MagicMock()
            ns_sound.soundNamed_.side_effect = [first, second]

            system_services.play_system_sound("Glass")
            system_services.play_system_sound("Pop")

            first.stop.assert_called_once_with()
            second.play.assert_called_once_with()

    def test_appkit_failure_returns_false(self):
        with patch("AppKit.NSSound") as ns_sound:
            ns_sound.soundNamed_.side_effect = RuntimeError("no AppKit")
            assert system_services.play_system_sound("Glass") is False
