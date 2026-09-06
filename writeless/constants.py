"""Application constants."""

APP_VERSION = "1.0.8"

SAMPLE_RATE = 16000  # Whisper expects 16 kHz
IDLE_ICON = "🎤"
RECORDING_ICON = "🎙️"
PROCESSING_ICON = "⚙️"
DOWNLOADING_ICON = "⬇️"
LOADING_ICON = "⏳"
HOTKEY = "<cmd>+<alt>+<f8>"
HOTKEY_LABEL = "Cmd+Option+F8"
RECORDING_START_TIMEOUT_SEC = 10
RECORDING_STALL_TIMEOUT_SEC = 25

# Whisper model sizes available for selection
WHISPER_MODELS = [
    ("tiny", "Tiny (~75 MB)"),
    ("base", "Base (~145 MB)"),
    ("small", "Small (~465 MB)"),
    ("medium", "Medium (~1.5 GB)"),
    ("large-v3", "Large v3 (~3 GB)"),
]
DEFAULT_WHISPER_MODEL = "small"

# Sound played after a transcription is copied to the clipboard.
# Ids are NSSound names resolved from /System/Library/Sounds/<id>.aiff;
# COMPLETION_SOUND_OFF disables the sound.
COMPLETION_SOUND_OFF = "off"
COMPLETION_SOUNDS = [(COMPLETION_SOUND_OFF, "Off")] + [
    (name, name)
    for name in (
        "Basso", "Blow", "Bottle", "Frog", "Funk", "Glass", "Hero",
        "Morse", "Ping", "Pop", "Purr", "Sosumi", "Submarine", "Tink",
    )
]
DEFAULT_COMPLETION_SOUND = "Glass"
