"""Hotkey format conversion between pynput, macOS display, and NSEvent."""

import re

# pynput modifier tokens → macOS display symbols (in standard macOS order: ⌃⌥⇧⌘)
_PYNPUT_TO_SYMBOL = {
    "ctrl": "⌃",
    "alt": "⌥",
    "shift": "⇧",
    "cmd": "⌘",
}

_SYMBOL_ORDER = ["⌃", "⌥", "⇧", "⌘"]

# pynput key tokens → display names
_KEY_DISPLAY = {
    **{f"f{i}": f"F{i}" for i in range(1, 21)},
    "space": "Space",
    "tab": "Tab",
    "enter": "Return",
    "backspace": "Delete",
    "delete": "⌦",
    "escape": "Esc",
    "up": "↑",
    "down": "↓",
    "left": "←",
    "right": "→",
}

# NSEvent keyCode → function key Unicode characters (for NSMenuItem keyEquivalent)
_NS_FUNCTION_KEYS = {
    f"f{i}": chr(0xF704 + i - 1) for i in range(1, 21)
}

# Special key names → NSMenuItem keyEquivalent characters
_NS_SPECIAL_KEY_CHARS = {
    "space": " ",
    "tab": "\t",
    "enter": "\r",
    "backspace": chr(0x08),
    "delete": chr(0x7F),
    "escape": chr(0x1B),
    "up": chr(0xF700),
    "down": chr(0xF701),
    "left": chr(0xF702),
    "right": chr(0xF703),
}

# NSEvent modifier flags
_NS_MODIFIER_FLAGS = {}
try:
    import AppKit

    _NS_MODIFIER_FLAGS = {
        "cmd": AppKit.NSEventModifierFlagCommand,
        "alt": AppKit.NSEventModifierFlagOption,
        "ctrl": AppKit.NSEventModifierFlagControl,
        "shift": AppKit.NSEventModifierFlagShift,
    }
except ImportError:
    pass

# NSEvent keyCode → pynput key name (for capturing)
_NS_KEYCODE_TO_KEY = {
    # Function keys
    122: "f1", 120: "f2", 99: "f3", 118: "f4", 96: "f5", 97: "f6",
    98: "f7", 100: "f8", 101: "f9", 109: "f10", 103: "f11", 111: "f12",
    105: "f13", 107: "f14", 113: "f15", 106: "f16", 64: "f17", 79: "f18",
    80: "f19", 90: "f20",
    # Special keys
    49: "space", 48: "tab", 36: "enter", 51: "backspace", 117: "delete",
    53: "escape",
    126: "up", 125: "down", 123: "left", 124: "right",
}

# Regular key characters → key codes (for common keys)
_NS_KEYCODE_TO_CHAR = {
    0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x",
    8: "c", 9: "v", 11: "b", 12: "q", 13: "w", 14: "e", 15: "r",
    16: "y", 17: "t", 18: "1", 19: "2", 20: "3", 21: "4", 22: "6",
    23: "5", 24: "=", 25: "9", 26: "7", 27: "-", 28: "8", 29: "0",
    30: "]", 31: "o", 32: "u", 33: "[", 34: "i", 35: "p", 37: "l",
    38: "j", 39: "'", 40: "k", 41: ";", 42: "\\", 43: ",", 44: "/",
    45: "n", 46: "m", 47: ".",
}

# Reverse mappings: pynput key name / char → NSEvent keyCode
_KEY_TO_NS_KEYCODE = {v: k for k, v in _NS_KEYCODE_TO_KEY.items()}
_CHAR_TO_NS_KEYCODE = {v: k for k, v in _NS_KEYCODE_TO_CHAR.items()}


def _parse_pynput(hotkey_str: str) -> tuple[list[str], str]:
    """Parse pynput hotkey string into (modifiers, key)."""
    parts = re.findall(r"<(\w+)>|(\w+)", hotkey_str)
    modifiers = []
    key = ""
    for bracket, plain in parts:
        token = bracket or plain
        if token in _PYNPUT_TO_SYMBOL:
            modifiers.append(token)
        else:
            key = token
    return modifiers, key


def pynput_to_display(hotkey_str: str) -> str:
    """Convert pynput format to macOS display format.

    "<cmd>+<alt>+<f8>" → "⌥⌘F8"
    """
    modifiers, key = _parse_pynput(hotkey_str)
    symbols = sorted(
        [_PYNPUT_TO_SYMBOL[m] for m in modifiers],
        key=lambda s: _SYMBOL_ORDER.index(s),
    )
    key_display = _KEY_DISPLAY.get(key, key.upper() if len(key) == 1 else key)
    return "".join(symbols) + key_display


def pynput_to_ns_key_equivalent(hotkey_str: str) -> tuple[str, int]:
    """Convert pynput format to NSMenuItem key equivalent components.

    Returns (key_char, modifier_mask).
    """
    modifiers, key = _parse_pynput(hotkey_str)
    mask = 0
    for m in modifiers:
        mask |= _NS_MODIFIER_FLAGS.get(m, 0)

    if key in _NS_FUNCTION_KEYS:
        key_char = _NS_FUNCTION_KEYS[key]
    elif key in _NS_SPECIAL_KEY_CHARS:
        key_char = _NS_SPECIAL_KEY_CHARS[key]
    elif len(key) == 1:
        key_char = key.lower()
    else:
        key_char = ""

    return key_char, mask


def pynput_to_ns_keycode_and_mask(hotkey_str: str) -> tuple[int | None, int]:
    """Convert pynput format to (NSEvent keyCode, modifier flag mask).

    "<cmd>+<alt>+<f8>" → (100, NSEventModifierFlagCommand | NSEventModifierFlagOption)
    Returns (None, mask) if the key cannot be mapped to a keycode.
    """
    modifiers, key = _parse_pynput(hotkey_str)
    mask = 0
    for m in modifiers:
        mask |= _NS_MODIFIER_FLAGS.get(m, 0)
    key_code = _KEY_TO_NS_KEYCODE.get(key)
    if key_code is None:
        key_code = _CHAR_TO_NS_KEYCODE.get(key)
    return key_code, mask


def ns_event_to_pynput(key_code: int, modifier_flags: int) -> str | None:
    """Convert NSEvent key code and modifiers to pynput hotkey string.

    Returns None if the combination is invalid (no modifier or no key).
    """
    if not _NS_MODIFIER_FLAGS:
        return None

    modifiers = []
    # Check in standard order
    for name, flag in [("ctrl", "ctrl"), ("alt", "alt"), ("shift", "shift"), ("cmd", "cmd")]:
        if modifier_flags & _NS_MODIFIER_FLAGS.get(flag, 0):
            modifiers.append(name)

    if not modifiers:
        return None

    # Resolve key
    key = _NS_KEYCODE_TO_KEY.get(key_code)
    if key is None:
        key = _NS_KEYCODE_TO_CHAR.get(key_code)
    if key is None:
        return None

    parts = [f"<{m}>" for m in modifiers] + [f"<{key}>" if len(key) > 1 else key]
    return "+".join(parts)
