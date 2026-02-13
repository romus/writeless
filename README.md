# Write Less

Voice-to-text macOS menubar app powered by OpenAI Whisper. Record speech with a global hotkey and get instant
transcription copied straight to your clipboard - all processed locally on your machine.

## Requirements

- macOS 26+
- Python 3.14+

## Run from source

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

## Build .app and .dmg

```bash
bash make.sh
```

The script creates a virtual environment, installs dependencies, and produces `build/dist/Write Less.dmg`. Open the DMG and
move `Write Less.app` to your Applications folder.

## Usage

- The app lives in the menubar (no Dock icon)
- **Cmd+Option+F8** - start/stop recording
- If recording stalls with no incoming audio, it auto-stops after 10-25 seconds
- After recording stops, Whisper transcribes the audio and copies the result to the clipboard
- The Whisper model (~461 MB) is downloaded automatically on first use
- Menubar icon indicates state: 🎤 idle, 🎙️ recording, ⚙️ processing, ⬇️ downloading model

## Permissions

macOS will prompt for:

- **Microphone** - required for audio recording
- **Accessibility** - required for the global hotkey
- **Input Monitoring** - recommended for reliable global hotkey capture

Permission status is shown in the menubar menu with OK/MISSING indicators. If hotkeys do not respond, use the menu items to troubleshoot:

- **Diagnostics** - hotkey and system diagnostics
- **Show Audio Diagnostics** - audio device probing
- **Open Accessibility Settings**
- **Open Input Monitoring Settings**
- **Open Notification Settings**
