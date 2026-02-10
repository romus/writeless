#!/usr/bin/env python3
"""Write Less — Voice-to-text macOS menubar app using local Whisper model."""

import tempfile
import threading

import numpy as np
import rumps
import sounddevice as sd
import whisper
from scipy.io import wavfile

# ---------------------------------------------------------------------------
# Transcription window (tkinter, runs in its own thread)
# ---------------------------------------------------------------------------

def show_transcription_window(text: str) -> None:
    """Open a simple tkinter window with the transcription and a Copy button."""
    import tkinter as tk

    def _run():
        root = tk.Tk()
        root.title("Write Less — Transcription")
        root.attributes("-topmost", True)
        root.geometry("520x260")
        root.minsize(400, 200)

        frame = tk.Frame(root, padx=12, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        text_widget = tk.Text(frame, wrap=tk.WORD, font=("SF Pro", 14))
        text_widget.insert(tk.END, text)
        text_widget.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        def copy_to_clipboard():
            root.clipboard_clear()
            root.clipboard_append(text_widget.get("1.0", tk.END).strip())
            btn.config(text="Copied!")
            root.after(1500, lambda: btn.config(text="Copy"))

        btn = tk.Button(
            frame, text="Copy", command=copy_to_clipboard,
            font=("SF Pro", 13), padx=16, pady=4,
        )
        btn.pack()

        root.mainloop()

    threading.Thread(target=_run, daemon=True).start()


# ---------------------------------------------------------------------------
# Menubar application
# ---------------------------------------------------------------------------

SAMPLE_RATE = 16000  # Whisper expects 16 kHz


class SayLessApp(rumps.App):
    def __init__(self):
        super().__init__("Write Less", icon=None, title="🎙")
        self.menu = [
            rumps.MenuItem("Record", callback=self.toggle_recording),
            None,  # separator
        ]
        self.recording = False
        self.audio_frames: list[np.ndarray] = []
        self.stream: sd.InputStream | None = None
        self.model = None  # lazy-loaded

    # -- recording -----------------------------------------------------------

    def toggle_recording(self, sender=None):
        if self.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self.audio_frames = []
        self.recording = True
        self.title = "🔴"
        self.menu["Record"].title = "Stop"

        def audio_callback(indata, frames, time_info, status):
            self.audio_frames.append(indata.copy())

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=audio_callback,
        )
        self.stream.start()

    def _stop_recording(self):
        self.recording = False
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        self.title = "🎙"
        self.menu["Record"].title = "Record"

        if not self.audio_frames:
            rumps.notification("Write Less", "", "No audio recorded.")
            return

        audio = np.concatenate(self.audio_frames, axis=0).flatten()
        self.audio_frames = []

        self.title = "⏳"
        threading.Thread(target=self._transcribe, args=(audio,), daemon=True).start()

    # -- transcription -------------------------------------------------------

    def _transcribe(self, audio: np.ndarray):
        try:
            if self.model is None:
                self.model = whisper.load_model("small")

            # Write to a temp WAV file (Whisper expects a file path)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav_path = f.name
                # scipy.io.wavfile expects int16
                audio_int16 = (audio * 32767).astype(np.int16)
                wavfile.write(wav_path, SAMPLE_RATE, audio_int16)

            result = self.model.transcribe(wav_path)
            text = result.get("text", "").strip()

            self.title = "🎙"

            if text:
                show_transcription_window(text)
            else:
                rumps.notification("Write Less", "", "No speech detected.")
        except Exception as e:
            self.title = "🎙"
            rumps.notification("Write Less", "Error", str(e))

    # -- hotkey --------------------------------------------------------------

    def _setup_hotkey(self):
        """Register Cmd+Shift+R global hotkey via pynput."""
        from pynput import keyboard

        def on_activate():
            self.toggle_recording()

        hotkey = keyboard.HotKey(
            keyboard.HotKey.parse("<cmd>+<shift>+r"),
            on_activate,
        )

        def on_press(key):
            hotkey.press(listener.canonical(key))

        def on_release(key):
            hotkey.release(listener.canonical(key))

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.daemon = True
        listener.start()

    def run(self, **kwargs):
        self._setup_hotkey()
        super().run(**kwargs)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    SayLessApp().run()
