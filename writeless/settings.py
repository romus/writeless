"""Persistent user settings stored as JSON."""

import json
import os

_SETTINGS_DIR = os.path.expanduser(
    "~/Library/Application Support/dev.romus.app.writeless"
)
_SETTINGS_FILE = os.path.join(_SETTINGS_DIR, "settings.json")

_DEFAULTS = {
    "notifications_enabled": True,
}


def _load() -> dict:
    try:
        with open(_SETTINGS_FILE) as f:
            return {**_DEFAULTS, **json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULTS)


def _save(data: dict) -> None:
    os.makedirs(_SETTINGS_DIR, exist_ok=True)
    with open(_SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get(key: str):
    return _load()[key]


def set(key: str, value) -> None:
    data = _load()
    data[key] = value
    _save(data)
