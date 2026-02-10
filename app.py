#!/usr/bin/env python3
"""Write Less — Voice-to-text macOS menubar app using local Whisper model."""

import subprocess
import threading
import os
import sys
import ctypes
import ctypes.util

import numpy as np
import rumps
import sounddevice as sd
import whisper

# ---------------------------------------------------------------------------
# Transcription display
# ---------------------------------------------------------------------------

def copy_to_clipboard(text: str) -> bool:
    """Copy text to the macOS clipboard."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")

    env = os.environ.copy()
    env.setdefault("LANG", "en_US.UTF-8")
    env.setdefault("LC_ALL", "en_US.UTF-8")
    env.setdefault("LC_CTYPE", "UTF-8")

    completed = subprocess.run(
        ["/usr/bin/pbcopy"],
        input=text.encode("utf-8"),
        check=False,
        env=env,
    )
    if completed.returncode == 0:
        return True

    # Fallback: ask AppleScript to set clipboard directly.
    completed = subprocess.run(
        [
            "/usr/bin/osascript",
            "-e",
            "on run argv",
            "-e",
            "set the clipboard to item 1 of argv",
            "-e",
            "end run",
            text,
        ],
        check=False,
    )
    return completed.returncode == 0


def notify_user(message: str, enabled: bool = True) -> None:
    """Show a best-effort macOS notification."""
    if not enabled:
        return
    rumps.notification("Write Less", "", message)
    escaped = message.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{escaped}" with title "Write Less"'
    subprocess.run(["/usr/bin/osascript", "-e", script], check=False)


# ---------------------------------------------------------------------------
# Menubar application
# ---------------------------------------------------------------------------

SAMPLE_RATE = 16000  # Whisper expects 16 kHz
IDLE_ICON = "🎤"
RECORDING_ICON = "🎙️"
PROCESSING_ICON = "⚙️"
HOTKEY = "<cmd>+<alt>+<f8>"
HOTKEY_LABEL = "Cmd+Option+F8"


class SayLessApp(rumps.App):
    def __init__(self):
        super().__init__("Write Less", icon=None, title=IDLE_ICON)
        self.notifications_item = rumps.MenuItem(
            "Notifications: On",
            callback=self.toggle_notifications,
        )
        self.menu = [
            rumps.MenuItem("Record", callback=self.toggle_recording),
            self.notifications_item,
            None,  # separator
            rumps.MenuItem("Show Hotkey Diagnostics", callback=self.show_diagnostics),
            rumps.MenuItem(
                "Open Accessibility Settings",
                callback=self.open_accessibility_settings,
            ),
            rumps.MenuItem(
                "Open Input Monitoring Settings",
                callback=self.open_input_monitoring_settings,
            ),
        ]
        self.recording = False
        self.audio_frames: list[np.ndarray] = []
        self.stream: sd.InputStream | None = None
        self.model = None  # lazy-loaded
        self.hotkey_listener = None
        self.notifications_enabled = True

    def toggle_notifications(self, _sender=None):
        self.notifications_enabled = not self.notifications_enabled
        state = "On" if self.notifications_enabled else "Off"
        self.notifications_item.title = f"Notifications: {state}"

    # -- recording -----------------------------------------------------------

    def toggle_recording(self, sender=None):
        if self.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self.audio_frames = []
        self.recording = True
        self.title = RECORDING_ICON
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

        self.title = IDLE_ICON
        self.menu["Record"].title = "Record"

        if not self.audio_frames:
            notify_user("No audio recorded.", self.notifications_enabled)
            return

        audio = np.concatenate(self.audio_frames, axis=0).flatten()
        self.audio_frames = []

        self.title = PROCESSING_ICON
        threading.Thread(target=self._transcribe, args=(audio,), daemon=True).start()

    # -- transcription -------------------------------------------------------

    def _transcribe(self, audio: np.ndarray):
        try:
            if self.model is None:
                self.model = whisper.load_model("small")

            # Pass raw audio directly to Whisper to avoid ffmpeg dependency.
            audio_float32 = np.asarray(audio, dtype=np.float32)
            result = self.model.transcribe(audio_float32)
            text = result.get("text", "").strip()
            self.title = IDLE_ICON

            if text:
                copied = copy_to_clipboard(text)
                if copied:
                    notify_user(
                        "Recognized and copied to clipboard.",
                        self.notifications_enabled,
                    )
                else:
                    notify_user(
                        "Recognized, but failed to copy to clipboard.",
                        self.notifications_enabled,
                    )
            else:
                notify_user("No speech detected.", self.notifications_enabled)
        except Exception as e:
            self.title = IDLE_ICON
            notify_user(f"Error: {e}", self.notifications_enabled)

    # -- hotkey --------------------------------------------------------------

    def _permission_status(self):
        """Return macOS permission state needed for global key capture."""
        status = {"accessibility": None, "input_monitoring": None}

        # Reliable accessibility check via macOS ApplicationServices API.
        try:
            app_services = ctypes.CDLL(
                ctypes.util.find_library("ApplicationServices"),
                use_errno=True,
            )
            app_services.AXIsProcessTrusted.restype = ctypes.c_bool
            status["accessibility"] = bool(app_services.AXIsProcessTrusted())
        except Exception:
            pass

        try:
            from Quartz import CGPreflightListenEventAccess

            status["input_monitoring"] = bool(CGPreflightListenEventAccess())
        except Exception:
            pass
        return status

    def _open_settings_url(self, url: str):
        subprocess.run(["/usr/bin/open", url], check=False)

    def show_diagnostics(self, _sender=None):
        status = self._permission_status()
        lines = [
            f"Process: {os.path.basename(sys.executable)}",
            f"Executable: {sys.executable}",
            f"Accessibility: {status['accessibility']}",
            f"Input Monitoring: {status['input_monitoring']}",
            f"Hotkey: {HOTKEY_LABEL}",
        ]
        rumps.alert("Hotkey Diagnostics", "\n".join(lines))

    def open_accessibility_settings(self, _sender=None):
        self._open_settings_url(
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        )

    def open_input_monitoring_settings(self, _sender=None):
        self._open_settings_url(
            "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
        )

    def _toggle_recording_on_main_thread(self):
        """Ensure UI/state changes happen on macOS main thread."""
        try:
            from PyObjCTools import AppHelper

            AppHelper.callAfter(self.toggle_recording)
        except Exception:
            self.toggle_recording()

    def _setup_hotkey(self):
        """Register global hotkeys via pynput."""
        from pynput import keyboard

        def on_activate():
            self._toggle_recording_on_main_thread()

        self.hotkey_listener = keyboard.GlobalHotKeys(
            {
                HOTKEY: on_activate,
            }
        )
        self.hotkey_listener.daemon = True
        self.hotkey_listener.start()

    def run(self, **kwargs):
        try:
            status = self._permission_status()
            self._setup_hotkey()
            notify_user(f"Hotkey active: {HOTKEY_LABEL}", self.notifications_enabled)
            if status["accessibility"] is False or status["input_monitoring"] is False:
                notify_user(
                    "Grant Accessibility and Input Monitoring to the current process.",
                    self.notifications_enabled,
                )
        except Exception as e:
            notify_user(
                f"Hotkey {HOTKEY_LABEL} unavailable: {e}",
                self.notifications_enabled,
            )
        super().run(**kwargs)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    SayLessApp().run()
