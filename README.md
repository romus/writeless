# Write Less

Voice-to-text macOS menubar app powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Record speech with a global hotkey and get instant
transcription copied straight to your clipboard - all processed locally on your machine.

## Demo

![Write Less demo](assets/demo.gif)

## Install via Homebrew

```bash
brew tap romus/writeless
brew install --cask writeless
```

## Requirements (building from source)

- macOS 26+
- Python 3.14+

## Run from source

```bash
make run
```

This creates a virtual environment, installs dependencies, and launches the app.

## Build from source

```bash
make build       # Build Write Less.app
make dmg         # Build .app + DMG installer
make zip         # Build .app + ZIP archive
make help        # Show all available commands
```

The built app is located at `build/dist/Write Less.app`.

## Usage

- The app lives in the menubar (no Dock icon)
- **Cmd+Option+F8** (default) — start/stop recording; configurable in Settings
- If recording stalls with no incoming audio, it auto-stops after 10–25 seconds
- After recording stops, Whisper transcribes the audio and copies the result to the clipboard
- The Whisper model is downloaded automatically on first use (size depends on the selected model; `small` is ~465 MB)
- Available models: Tiny (~75 MB), Base (~145 MB), Small (~465 MB), Medium (~1.5 GB), Large v3 (~3 GB) — selectable in Settings
- Menubar icon indicates state: 🎤 idle, 🎙️ recording, ⚙️ processing, ⬇️ downloading model, ⏳ loading model

## Settings

Open **Settings…** from the menubar menu to configure:

- **Keyboard shortcut** — click the field and press any key combination to change the global hotkey
- **Whisper Model** — choose the transcription model (smaller = faster, larger = more accurate)
- **Notifications** — toggle system notifications for transcription results
- **SSL Verification** — toggle TLS certificate checks for model download (disable for problematic networks/proxies)

Settings are saved to `~/Library/Application Support/dev.romus.app.writeless/settings.json`.

## Permissions

macOS will prompt for:

- **Microphone** - required for audio recording
- **Accessibility** - required for the global hotkey
- **Input Monitoring** - required for reliable global hotkey capture
- **Notifications** - optional, for transcription result alerts

Permission status is shown in the menubar menu. Items for missing permissions appear automatically and link directly to the relevant System Settings pane. Once a permission is granted the corresponding menu item is hidden.

**If the app reports permissions missing even though System Settings shows them as granted**, macOS may be showing stale TCC database entries from a previously deleted version of the app. Fix by resetting permissions for the new app:

```bash
tccutil reset Accessibility dev.romus.app.writeless
tccutil reset ListenEvent dev.romus.app.writeless
tccutil reset Notifications dev.romus.app.writeless
```

Then restart the app — it will prompt for permissions again. Alternatively, go to System Settings → Privacy & Security → Accessibility / Input Monitoring / Notifications, remove "Write Less", and re-add it.

## Diagnostics

**Diagnostics** in the menubar menu shows app version, current hotkey, audio device info, permissions status, selected Whisper model, and SSL status.

## Troubleshooting

### Logs

Logs are written to `~/Library/Logs/WriteLess.log` (1 MB rotating). View them with:

```bash
tail -f ~/Library/Logs/WriteLess.log
```

When running from source via `make run`, logs also appear in the terminal.

### Model download fails

If the Whisper model fails to download on first use, try:

1. Check your internet connection
2. Toggle **SSL Verification** off in Settings and try again
3. Use **Clear Model Cache** from the menubar menu, then record again
4. Download the model manually:
   ```bash
   python3 -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-small')"
   ```
