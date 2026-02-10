# Write Less

Voice-to-text macOS menubar app powered by OpenAI Whisper. Record speech with a global hotkey and get instant
transcription - all processed locally on your machine.

## Requirements

- macOS 12+
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
- After recording stops, Whisper transcribes the audio and shows the result in a window
- The Whisper model (~461 MB) is downloaded automatically on first use

## Permissions

macOS will prompt for:

- **Microphone** - required for audio recording
- **Accessibility** - required for the global hotkey
- **Input Monitoring** - recommended for reliable global hotkey capture

If hotkeys do not respond, open menubar menu:

- **Show Hotkey Diagnostics**
- **Open Accessibility Settings**
- **Open Input Monitoring Settings**
