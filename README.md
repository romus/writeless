# Write Less

Voice-to-text macOS menubar app powered by OpenAI Whisper. Record speech with a global hotkey and get instant transcription — all processed locally on your machine.

## Requirements

- macOS 12+
- Python 3.10+

## Run from source

```bash
pip install -r requirements.txt
python app.py
```

## Build .app and .dmg

Install dependencies and run the build script:

```bash
pip install -r requirements.txt
bash build.sh
```

This produces `Write Less.dmg` in the project root. Open the DMG and move `Write Less.app` to your Applications folder.

## Usage

- The app lives in the menubar (no Dock icon)
- **Cmd+Shift+R** — start/stop recording
- After recording stops, Whisper transcribes the audio and shows the result in a window
- The Whisper model (~461 MB) is downloaded automatically on first use

## Permissions

macOS will prompt for:

- **Microphone** — required for audio recording
- **Accessibility** — required for the global hotkey
