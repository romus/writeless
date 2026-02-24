# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Run the app (development)
```bash
make run
```

### Build the .app bundle
```bash
make build
```

### Build the .app + .dmg installer
```bash
make dmg
```

### Build the .app + .zip archive
```bash
make zip
```

### Install/update dependencies
```bash
make setup
```

### Clean build artifacts
```bash
make clean
```

### Show current app version
```bash
make version
```

### Show all available commands
```bash
make help
```

## Architecture

**Write Less** is a macOS menubar speech-to-text app. It records audio via a global hotkey, transcribes locally with faster-whisper (CTranslate2-based Whisper), and copies the result to clipboard.

### Component Roles

- **`app.py`** — 3-line entrypoint. Creates and runs `WriteLessApp`.
- **`writeless/menubar_app.py`** — Main controller (`rumps.App` subclass). Manages lifecycle, hotkey registration via NSEvent, permission polling (every 3s), and delegates recording to `Recorder`.
- **`writeless/recorder.py`** — Audio I/O and transcription. Opens `sounddevice` stream, runs a watchdog thread (10s timeout before first audio, 25s after), transcribes in a background thread using cached Whisper model, calls back into the app via callbacks (never touches UI directly).
- **`writeless/settings_window.py`** — Native macOS settings UI built with PyObjC/AppKit. Custom `HotkeyField` captures key combos via `keyDown_`. Window hides on close instead of being destroyed.
- **`writeless/system_services.py`** — macOS integration: permission checks (ctypes into ApplicationServices), notifications (UNUserNotificationCenter), clipboard (pbcopy), icon resolution.
- **`writeless/hotkey_utils.py`** — Bidirectional conversion between pynput format (`<cmd>+<alt>+<f8>`), display format (`⌥⌘F8`), and NSEvent keyCode/modifier masks.
- **`writeless/diagnostics.py`** — Audio device probing and diagnostic info formatting for the "Diagnostics" menu item.
- **`writeless/settings.py`** — Persistent JSON settings in `~/Library/Application Support/dev.romus.app.writeless/settings.json`.
- **`writeless/constants.py`** — Shared constants: menubar icon chars, timeouts, default hotkey.

### Recording Data Flow

1. User presses hotkey → NSEvent global monitor fires → `toggle_recording()` on main thread
2. `Recorder.start()` → reinitializes PortAudio (detects device changes), opens stream, spawns watchdog thread
3. Audio frames accumulated in stream callback
4. Watchdog timeout or manual stop → `Recorder.stop()`
5. Audio concatenated → `_transcribe()` in background thread
6. Whisper model loads lazily on first use (~461 MB download to `~/.cache/whisper/`)
7. Transcription copied to clipboard via `pbcopy`
8. Callbacks update menubar icon and trigger system notification
9. All UI updates dispatched to main thread via `AppHelper.callAfter()`

### Key Design Decisions

- **NSEvent for hotkeys** (not pynput): avoids `TSMGetInputSourceProperty` crashes on macOS 26+
- **PortAudio reinitialized on each recording**: detects headphone/device changes
- **Watchdog thread**: ensures recording stops if audio device stalls or disconnects
- **Settings as JSON** (not NSUserDefaults): simpler, human-readable, inspectable
- **Callbacks-only from Recorder**: keeps audio/transcription code decoupled from UI
- **Whisper model hardcoded to `"small"`** in `recorder.py` (`_transcribe` method); cached in `~/.cache/huggingface/hub/`
- **Thread safety**: `Recorder._lock` guards audio frame list; all UI mutations go through `AppHelper.callAfter()` to reach the main thread

## Versioning & Release

- App version lives in `writeless/constants.py` (`APP_VERSION`). The Makefile and `setup.py` both read it from there — update only that one place.
- Bundle identifier: `dev.romus.app.writeless`
- Releases are tag-triggered: pushing a `v*` tag runs `.github/workflows/release.yml`, which builds a ZIP via `make zip` and creates a GitHub Release. Homebrew Cask (`brew tap romus/writeless`) points at these releases.

## Build Notes

- Requires Python 3.14 (Homebrew). System has `python3`, not `python`.
- `setuptools` pinned to `<78` — `>=78` removed `pkg_resources` which py2app 0.28.9 needs.
- `setup.py` sets `sys.setrecursionlimit(5000)` — required for modulegraph with large deps (torch) on Python 3.14.
- `Makefile` detects Python version mismatch between `.venv` and system, recreates venv if they differ.
- Build output: `build/dist/Write Less.app`
