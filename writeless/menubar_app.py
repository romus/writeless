"""Menubar application implementation."""

import os
import sys
import threading
import time

import numpy as np
import rumps
import sounddevice as sd
import whisper

from writeless.audio_diagnostics import (
    AudioProbeResult,
    get_audio_device_status,
    probe_audio_input,
)
from writeless.constants import (
    DOWNLOADING_ICON,
    HOTKEY,
    HOTKEY_LABEL,
    IDLE_ICON,
    PROCESSING_ICON,
    RECORDING_START_TIMEOUT_SEC,
    RECORDING_STALL_TIMEOUT_SEC,
    RECORDING_ICON,
    SAMPLE_RATE,
)
from writeless.settings import get as get_setting, set as set_setting
from writeless.system_services import (
    copy_to_clipboard,
    get_notification_status,
    get_permission_status,
    notify_user,
    open_settings_url,
    request_notification_permission,
    set_app_icon,
    show_alert,
)


class SayLessApp(rumps.App):
    def __init__(self):
        super().__init__("Write Less", icon=None, title=IDLE_ICON)
        set_app_icon()
        request_notification_permission()
        self.notifications_enabled = get_setting("notifications_enabled")
        notif_state = "On" if self.notifications_enabled else "Off"
        self.notifications_item = rumps.MenuItem(
            f"Notifications: {notif_state}",
            callback=self.toggle_notifications,
        )
        self.permissions_item = rumps.MenuItem("Permissions: Checking...")
        self.accessibility_settings_item = rumps.MenuItem(
            "Open Accessibility Settings",
            callback=self.open_accessibility_settings,
        )
        self.input_monitoring_settings_item = rumps.MenuItem(
            "Open Input Monitoring Settings",
            callback=self.open_input_monitoring_settings,
        )
        self.notification_settings_item = rumps.MenuItem(
            "Open Notification Settings",
            callback=self.open_notification_settings,
        )
        self.menu = [
            rumps.MenuItem("Record", callback=self.toggle_recording),
            self.notifications_item,
            self.permissions_item,
            None,  # separator
            rumps.MenuItem("Diagnostics", callback=self.show_diagnostics),
            rumps.MenuItem("Show Audio Diagnostics", callback=self.show_audio_diagnostics),
            self.accessibility_settings_item,
            self.input_monitoring_settings_item,
            self.notification_settings_item,
        ]
        self.recording = False
        self.audio_frames: list[np.ndarray] = []
        self.stream: sd.InputStream | None = None
        self._recording_session = 0
        self._recording_lock = threading.Lock()
        self._received_audio_frame = False
        self._last_audio_frame_at = 0.0
        self.model = None  # lazy-loaded
        self.hotkey_listener = None
        self.permission_refresh_timer = rumps.Timer(self._refresh_permission_menu, 3.0)
        self._refresh_permission_menu()

    def _set_menu_item_visible(self, item: rumps.MenuItem, visible: bool) -> None:
        """Best-effort visibility toggle for a menu item."""
        try:
            if hasattr(item, "hidden"):
                item.hidden = not visible
                return
            native_item = getattr(item, "_menuitem", None)
            if native_item is not None and hasattr(native_item, "setHidden_"):
                native_item.setHidden_(not visible)
                return
        except Exception:
            pass

        # Fallback for wrappers without hide support.
        if not visible:
            item.title = ""

    def _refresh_permission_menu(self, _sender=None):
        status = get_permission_status()
        notif_status = get_notification_status()

        if status.accessibility is False:
            self._set_menu_item_visible(self.accessibility_settings_item, True)
            self.accessibility_settings_item.title = (
                "Open Accessibility Settings (Permission Missing)"
            )
        elif status.accessibility is True:
            self._set_menu_item_visible(self.accessibility_settings_item, False)
        else:
            self._set_menu_item_visible(self.accessibility_settings_item, True)
            self.accessibility_settings_item.title = "Open Accessibility Settings"

        if status.input_monitoring is False:
            self._set_menu_item_visible(self.input_monitoring_settings_item, True)
            self.input_monitoring_settings_item.title = (
                "Open Input Monitoring Settings (Permission Missing)"
            )
        elif status.input_monitoring is True:
            self._set_menu_item_visible(self.input_monitoring_settings_item, False)
        else:
            self._set_menu_item_visible(self.input_monitoring_settings_item, True)
            self.input_monitoring_settings_item.title = "Open Input Monitoring Settings"

        if notif_status != "authorized":
            self._set_menu_item_visible(self.notification_settings_item, True)
            self.notification_settings_item.title = (
                "Open Notification Settings (Permission Missing)"
            )
        else:
            self._set_menu_item_visible(self.notification_settings_item, False)

        missing = []
        if status.accessibility is False:
            missing.append("Accessibility")
        if status.input_monitoring is False:
            missing.append("Input Monitoring")
        if notif_status != "authorized":
            missing.append("Notifications")

        if missing:
            self.permissions_item.title = f"Permissions: {' + '.join(missing)} MISSING"
        elif status.accessibility is True and status.input_monitoring is True:
            self.permissions_item.title = "Permissions: OK"
        else:
            self.permissions_item.title = "Permissions: Unknown"

    def _model_download_required(self, model_name: str) -> bool:
        """Return True if Whisper model file is not present in local cache."""
        try:
            model_url = whisper._MODELS.get(model_name)  # type: ignore[attr-defined]
            if not model_url:
                return False
            model_file = os.path.basename(model_url)
            cache_dir = os.path.expanduser("~/.cache/whisper")
            return not os.path.exists(os.path.join(cache_dir, model_file))
        except Exception:
            return False

    def toggle_notifications(self, _sender=None):
        self.notifications_enabled = not self.notifications_enabled
        set_setting("notifications_enabled", self.notifications_enabled)
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
        self._recording_session += 1
        session_id = self._recording_session
        self._received_audio_frame = False
        self._last_audio_frame_at = time.monotonic()
        self.title = RECORDING_ICON
        self.menu["Record"].title = "Stop"

        def audio_callback(indata, frames, time_info, status):
            del frames, time_info, status
            with self._recording_lock:
                self.audio_frames.append(indata.copy())
                self._received_audio_frame = True
                self._last_audio_frame_at = time.monotonic()

        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=audio_callback,
            )
            self.stream.start()
        except Exception as exc:
            self.recording = False
            self.stream = None
            self.title = IDLE_ICON
            self.menu["Record"].title = "Record"
            notify_user(f"Failed to start recording: {exc}", self.notifications_enabled)
            return

        threading.Thread(
            target=self._recording_watchdog_loop,
            args=(session_id,),
            daemon=True,
        ).start()

    def _recording_watchdog_loop(self, session_id: int):
        while True:
            time.sleep(0.5)
            if not self.recording or self._recording_session != session_id:
                return

            with self._recording_lock:
                received_audio_frame = self._received_audio_frame
                last_frame_at = self._last_audio_frame_at

            timeout_sec = (
                RECORDING_STALL_TIMEOUT_SEC
                if received_audio_frame
                else RECORDING_START_TIMEOUT_SEC
            )
            if time.monotonic() - last_frame_at < timeout_sec:
                continue

            self._stop_recording_on_main_thread(
                timeout_reached=True,
                timeout_seconds=timeout_sec,
            )
            return

    def _stop_recording_on_main_thread(
        self,
        timeout_reached: bool = False,
        timeout_seconds: int | None = None,
    ):
        def stop():
            if not self.recording:
                return
            self._stop_recording(
                timeout_reached=timeout_reached,
                timeout_seconds=timeout_seconds,
            )

        try:
            from PyObjCTools import AppHelper

            AppHelper.callAfter(stop)
        except Exception:
            stop()

    def _stop_recording(
        self,
        timeout_reached: bool = False,
        timeout_seconds: int | None = None,
    ):
        self.recording = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as exc:
                notify_user(f"Failed to stop audio stream: {exc}", self.notifications_enabled)
            self.stream = None

        self.title = IDLE_ICON
        self.menu["Record"].title = "Record"

        if timeout_reached:
            timeout_value = (
                timeout_seconds if timeout_seconds is not None else RECORDING_STALL_TIMEOUT_SEC
            )
            notify_user(
                f"Recording stopped: no audio data for {timeout_value} seconds.",
                self.notifications_enabled,
            )

        with self._recording_lock:
            has_audio = bool(self.audio_frames)

        if not has_audio:
            notify_user("No audio recorded.", self.notifications_enabled)
            return

        with self._recording_lock:
            audio = np.concatenate(self.audio_frames, axis=0).flatten()
            self.audio_frames = []

        self.title = PROCESSING_ICON
        threading.Thread(target=self._transcribe, args=(audio,), daemon=True).start()

    # -- transcription -------------------------------------------------------

    def _transcribe(self, audio: np.ndarray):
        try:
            if self.model is None:
                model_name = "small"
                download_required = self._model_download_required(model_name)
                if download_required:
                    self.title = DOWNLOADING_ICON
                    notify_user(
                        "Downloading Whisper model for first use...",
                        self.notifications_enabled,
                    )
                self.model = whisper.load_model(model_name)
                if download_required:
                    self.title = IDLE_ICON
                    notify_user(
                        "Whisper model downloaded.",
                        self.notifications_enabled,
                    )

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
        except Exception as exc:
            self.title = IDLE_ICON
            notify_user(f"Error: {exc}", self.notifications_enabled)

    # -- diagnostics ---------------------------------------------------------

    def show_diagnostics(self, _sender=None):
        status = get_permission_status()
        notif_status = get_notification_status()
        bundle_id = "N/A"
        try:
            from Foundation import NSBundle
            bundle = NSBundle.mainBundle()
            if bundle:
                bundle_id = bundle.bundleIdentifier() or "None"
        except Exception:
            pass

        # Whisper model info
        model_name = "small"
        model_loaded = self.model is not None
        cache_dir = os.path.expanduser("~/.cache/whisper")
        model_file = os.path.join(cache_dir, f"{model_name}.pt")
        model_path = model_file if os.path.exists(model_file) else None

        lines = [
            f"Process: {os.path.basename(sys.executable)}",
            f"Executable: {sys.executable}",
            f"Bundle ID: {bundle_id}",
            f"Accessibility: {status.accessibility}",
            f"Input Monitoring: {status.input_monitoring}",
            f"Notifications: {notif_status}",
            f"Hotkey: {HOTKEY_LABEL}",
            f"Whisper model: {model_name} (downloaded: {'yes' if model_path else 'no'}, in memory: {'yes' if model_loaded else 'no'})",
            f"Model path: {model_path or 'N/A'}",
        ]
        show_alert("Diagnostics", "\n".join(lines))

    def show_audio_diagnostics(self, _sender=None):
        device = get_audio_device_status()
        if self.recording:
            probe = AudioProbeResult(
                duration_sec=2.0,
                samplerate=SAMPLE_RATE,
                total_frames=0,
                callbacks=0,
                rms=0.0,
                peak=0.0,
                status_flags=(),
                verdict="ERROR",
                error="Recording is currently active.",
            )
        else:
            probe = probe_audio_input(duration_sec=2.0, samplerate=SAMPLE_RATE, channels=1)

        default_input = (
            "None"
            if device.default_input_index is None
            else f"{device.default_input_index}: {device.default_input_name}"
        )
        callback_status = ", ".join(probe.status_flags) if probe.status_flags else "none"
        verdict = f"Audio probe: {probe.verdict}"
        if probe.verdict == "ERROR" and probe.error:
            verdict = f"{verdict}: {probe.error}"

        lines = [
            f"Process: {os.path.basename(sys.executable)}",
            f"Executable: {sys.executable}",
            f"Default Input Device: {default_input}",
            f"Input Channels: {device.max_input_channels}",
            f"Default Sample Rate: {device.default_samplerate}",
            f"Probe Duration: {probe.duration_sec:.1f}s",
            f"Probe Sample Rate: {probe.samplerate}",
            f"Frames Received: {probe.total_frames}",
            f"Callbacks: {probe.callbacks}",
            f"RMS: {probe.rms:.6f}",
            f"Peak: {probe.peak:.6f}",
            f"Callback Status: {callback_status}",
            verdict,
        ]
        if device.error:
            lines.append(f"Device Query Error: {device.error}")

        show_alert("Audio Diagnostics", "\n".join(lines))

    # -- settings ------------------------------------------------------------

    def open_accessibility_settings(self, _sender=None):
        open_settings_url(
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        )
        self._refresh_permission_menu()

    def open_input_monitoring_settings(self, _sender=None):
        open_settings_url(
            "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
        )

    def open_notification_settings(self, _sender=None):
        open_settings_url(
            "x-apple.systempreferences:com.apple.preference.notifications"
        )
        self._refresh_permission_menu()

    # -- hotkey --------------------------------------------------------------

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

        self.hotkey_listener = keyboard.GlobalHotKeys({HOTKEY: on_activate})
        self.hotkey_listener.daemon = True
        self.hotkey_listener.start()

    def run(self, **kwargs):
        try:
            status = get_permission_status()
            self._setup_hotkey()
            self.permission_refresh_timer.start()
            notify_user(f"Hotkey active: {HOTKEY_LABEL}", self.notifications_enabled)
            if status.accessibility is False or status.input_monitoring is False:
                notify_user(
                    "Grant Accessibility and Input Monitoring to the current process.",
                    self.notifications_enabled,
                )
        except Exception as exc:
            notify_user(
                f"Hotkey {HOTKEY_LABEL} unavailable: {exc}",
                self.notifications_enabled,
            )
        super().run(**kwargs)
