"""Tests for writeless.hotkey_utils — hotkey format conversions."""

from unittest.mock import patch

from writeless.hotkey_utils import (
    _parse_pynput,
    pynput_to_display,
    pynput_to_ns_keycode_and_mask,
    ns_event_to_pynput,
)

# Real macOS NSEvent modifier flag values (from AppKit headers).
# Used to test ns_event_to_pynput without requiring a real AppKit import.
_REAL_FLAGS = {
    "cmd": 1 << 20,    # NSEventModifierFlagCommand
    "alt": 1 << 19,    # NSEventModifierFlagOption
    "ctrl": 1 << 18,   # NSEventModifierFlagControl
    "shift": 1 << 17,  # NSEventModifierFlagShift
}


class TestParsePynput:
    def test_cmd_alt_f8(self):
        mods, key = _parse_pynput("<cmd>+<alt>+<f8>")
        assert set(mods) == {"cmd", "alt"}
        assert key == "f8"

    def test_single_modifier_letter(self):
        mods, key = _parse_pynput("<ctrl>+a")
        assert mods == ["ctrl"]
        assert key == "a"

    def test_three_modifiers(self):
        mods, key = _parse_pynput("<ctrl>+<shift>+<cmd>+<f1>")
        assert set(mods) == {"ctrl", "shift", "cmd"}
        assert key == "f1"


class TestPynputToDisplay:
    def test_cmd_alt_f8(self):
        assert pynput_to_display("<cmd>+<alt>+<f8>") == "⌥⌘F8"

    def test_ctrl_shift_a(self):
        assert pynput_to_display("<ctrl>+<shift>+a") == "⌃⇧A"

    def test_modifier_order_is_standard(self):
        # macOS standard order: ⌃⌥⇧⌘
        result = pynput_to_display("<cmd>+<ctrl>+<alt>+<shift>+<f1>")
        assert result == "⌃⌥⇧⌘F1"

    def test_special_keys(self):
        assert pynput_to_display("<cmd>+<space>") == "⌘Space"
        assert pynput_to_display("<cmd>+<tab>") == "⌘Tab"
        assert pynput_to_display("<cmd>+<escape>") == "⌘Esc"


class TestPynputToNsKeycodeAndMask:
    def test_f8_keycode(self):
        key_code, mask = pynput_to_ns_keycode_and_mask("<cmd>+<alt>+<f8>")
        assert key_code == 100  # F8 keycode

    def test_letter_keycode(self):
        key_code, _ = pynput_to_ns_keycode_and_mask("<cmd>+a")
        assert key_code == 0  # 'a' keycode

    def test_unknown_key_returns_none(self):
        key_code, _ = pynput_to_ns_keycode_and_mask("<cmd>+<nonexistent>")
        assert key_code is None


class TestNsEventToPynput:
    """Tests that patch _NS_MODIFIER_FLAGS with real macOS values."""

    def _call(self, key_code, modifier_flags):
        with patch("writeless.hotkey_utils._NS_MODIFIER_FLAGS", _REAL_FLAGS):
            return ns_event_to_pynput(key_code, modifier_flags)

    def test_roundtrip_f8(self):
        with patch("writeless.hotkey_utils._NS_MODIFIER_FLAGS", _REAL_FLAGS):
            key_code, mask = pynput_to_ns_keycode_and_mask("<cmd>+<alt>+<f8>")
        assert key_code == 100

        result = self._call(key_code, mask)
        assert result is not None
        result_mods, result_key = _parse_pynput(result)
        assert set(result_mods) == {"cmd", "alt"}
        assert result_key == "f8"

    def test_no_modifiers_returns_none(self):
        assert self._call(100, 0) is None

    def test_unknown_keycode_returns_none(self):
        mask = _REAL_FLAGS["cmd"]
        assert self._call(999, mask) is None

    def test_single_modifier_letter(self):
        mask = _REAL_FLAGS["ctrl"]
        result = self._call(0, mask)  # keyCode 0 = 'a'
        assert result is not None
        mods, key = _parse_pynput(result)
        assert mods == ["ctrl"]
        assert key == "a"
