"""Shared fixtures for the writeless test suite."""

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub out macOS-only frameworks before any writeless module is imported.
# This lets the test suite run on Linux CI runners as well as macOS.
# ---------------------------------------------------------------------------

_MACOS_MODULES = [
    "AppKit",
    "Foundation",
    "Quartz",
    "objc",
    "PyObjCTools",
    "PyObjCTools.AppHelper",
    "rumps",
]

for mod_name in _MACOS_MODULES:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()


@pytest.fixture()
def tmp_settings(tmp_path, monkeypatch):
    """Redirect writeless.settings to a temporary directory."""
    import writeless.settings as settings_mod

    settings_dir = str(tmp_path / "settings")
    settings_file = os.path.join(settings_dir, "settings.json")

    monkeypatch.setattr(settings_mod, "_SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", settings_file)

    return tmp_path, settings_file


@pytest.fixture()
def settings_file_with(tmp_settings):
    """Return a helper that pre-populates the settings JSON file."""
    _, settings_file = tmp_settings

    def _write(data: dict) -> str:
        os.makedirs(os.path.dirname(settings_file), exist_ok=True)
        with open(settings_file, "w") as f:
            json.dump(data, f)
        return settings_file

    return _write
