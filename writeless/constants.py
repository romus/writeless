"""Application constants."""

APP_VERSION = "1.0.5"

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
