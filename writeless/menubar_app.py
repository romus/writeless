"""Menubar application — thin orchestrator."""

import atexit
import logging
import os
import signal
import threading
import time

import rumps

_APP_LOGGER_NAME = "writeless"

logger = logging.getLogger(__name__)

from writeless.constants import COMPLETION_SOUNDS, DEFAULT_COMPLETION_SOUND, IDLE_ICON
from writeless.diagnostics import format_diagnostics_text, update_audio_device_cache
from writeless.hotkey_utils import pynput_to_display, pynput_to_ns_key_equivalent
from writeless.recorder import Recorder, clear_model_cache, configure_ssl_verification
from writeless.settings import get as get_setting, set as set_setting
from writeless.system_services import (
    get_notification_status,
    get_permission_status,
    notify_user,
    open_settings_url,
    play_system_sound,
    request_notification_permission,
    set_app_icon,
    show_alert,
)


class WriteLessApp(rumps.App):
    def __init__(self):
        super().__init__("Write Less", icon=None, title=IDLE_ICON)

        self.debug_logging = get_setting("debug_logging")
        self._apply_log_level()

        self.ssl_verification_enabled = get_setting("ssl_verification_enabled")
        configure_ssl_verification(self.ssl_verification_enabled)
        set_app_icon()
        request_notification_permission()
        self.notifications_enabled = get_setting("notifications_enabled")
        self.current_hotkey = get_setting("hotkey")
        self.current_model = get_setting("whisper_model")
        self.completion_sound = get_setting("completion_sound")
        if self.completion_sound not in {sid for sid, _ in COMPLETION_SOUNDS}:
            self.completion_sound = DEFAULT_COMPLETION_SOUND  # hand-edited settings.json

        self.recorder = Recorder(
            on_status_change=self._set_status,
            on_notify=self._notify,
            on_recording_stopped=self._on_recording_stopped,
            dispatch_to_main=self._dispatch_to_main,
            on_transcription_success=self._on_transcription_success,
        )
        self.recorder.ssl_verification_enabled = self.ssl_verification_enabled
        self.recorder.model_name = self.current_model

        self.hotkey_listener = None
        self._settings_window = None
        self._build_menu()

        self.permission_refresh_timer = rumps.Timer(self._refresh_permission_menu, 3.0)
        self._refresh_permission_menu()

    # -- internal wiring -----------------------------------------------------

    def _set_status(self, icon: str) -> None:
        self.title = icon

    def _notify(self, message: str) -> None:
        notify_user(message, self.notifications_enabled)

    def _on_recording_stopped(self) -> None:
        self.record_item.title = "Record"

    def _on_transcription_success(self) -> None:
        # Called on the transcription thread; NSSound is AppKit, so hop to main.
        self._dispatch_to_main(lambda: play_system_sound(self.completion_sound))

    @staticmethod
    def _dispatch_to_main(fn) -> None:
        try:
            from PyObjCTools import AppHelper

            AppHelper.callAfter(fn)
        except Exception:
            fn()

    # -- menu ----------------------------------------------------------------

    def _build_menu(self) -> None:
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
        self.record_item = rumps.MenuItem("Record", callback=self.toggle_recording)
        self._update_record_key_equivalent()
        self.menu = [
            self.record_item,
            rumps.MenuItem("Settings…", callback=self.open_settings),
            self.permissions_item,
            None,  # separator
            rumps.MenuItem("Diagnostics", callback=self.show_diagnostics),
            rumps.MenuItem("Clear Model Cache", callback=self.clear_model_cache),
            self.accessibility_settings_item,
            self.input_monitoring_settings_item,
            self.notification_settings_item,
        ]

    def _update_record_key_equivalent(self) -> None:
        """Update the Record menu item to show the current hotkey shortcut."""
        try:
            key_char, mask = pynput_to_ns_key_equivalent(self.current_hotkey)
            ns_item = self.record_item._menuitem
            ns_item.setKeyEquivalent_(key_char)
            ns_item.setKeyEquivalentModifierMask_(mask)
        except Exception:
            pass

    # -- permissions ---------------------------------------------------------

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
        import threading

        def _check():
            status = get_permission_status()
            notif_status = get_notification_status()
            self._dispatch_to_main(lambda: self._apply_permission_menu(status, notif_status))

        threading.Thread(target=_check, daemon=True).start()

    def _apply_permission_menu(self, status, notif_status):
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

    # -- callbacks -----------------------------------------------------------

    def toggle_recording(self, sender=None):
        if self.recorder.is_recording:
            self.recorder.stop()
        else:
            self.record_item.title = "Stop"
            self.recorder.start()

    def open_settings(self, _sender=None):
        from writeless.settings_window import SettingsWindow

        if self._settings_window is None:
            self._settings_window = SettingsWindow(
                current_hotkey=self.current_hotkey,
                notifications_enabled=self.notifications_enabled,
                ssl_verification_enabled=self.ssl_verification_enabled,
                current_model=self.current_model,
                debug_logging=self.debug_logging,
                completion_sound=self.completion_sound,
                on_hotkey_change=self._on_hotkey_change,
                on_notifications_change=self._on_notifications_change,
                on_ssl_change=self._on_ssl_change,
                on_model_change=self._on_model_change,
                on_debug_logging_change=self._on_debug_logging_change,
                on_completion_sound_change=self._on_completion_sound_change,
            )
        else:
            self._settings_window.update_state(
                notifications_enabled=self.notifications_enabled,
                ssl_verification_enabled=self.ssl_verification_enabled,
                current_hotkey=self.current_hotkey,
                current_model=self.current_model,
                debug_logging=self.debug_logging,
                completion_sound=self.completion_sound,
            )
        self._settings_window.show()

    def _on_hotkey_change(self, pynput_str: str) -> None:
        self.current_hotkey = pynput_str
        set_setting("hotkey", pynput_str)
        self._update_record_key_equivalent()
        # Defer to next run loop iteration so any in-progress event handling finishes.
        self._dispatch_to_main(self._restart_hotkey_listener)

    def _on_notifications_change(self, enabled: bool) -> None:
        self.notifications_enabled = enabled
        set_setting("notifications_enabled", enabled)

    def _on_completion_sound_change(self, sound_id: str) -> None:
        logger.info("Completion sound changed: %s", sound_id)
        self.completion_sound = sound_id
        set_setting("completion_sound", sound_id)
        play_system_sound(sound_id)  # preview; AppKit action, already on main thread

    def _on_model_change(self, model_id: str) -> None:
        logger.info("Whisper model changed: %s", model_id)
        self.current_model = model_id
        set_setting("whisper_model", model_id)
        self.recorder.model_name = model_id
        self.recorder._model = None  # unload; will reload on next recording

    def _on_ssl_change(self, enabled: bool) -> None:
        logger.info("SSL verification changed: %s", enabled)
        self.ssl_verification_enabled = enabled
        set_setting("ssl_verification_enabled", enabled)
        configure_ssl_verification(enabled)
        self.recorder.ssl_verification_enabled = enabled

    def _on_debug_logging_change(self, enabled: bool) -> None:
        logger.info("Debug logging changed: %s", enabled)
        self.debug_logging = enabled
        set_setting("debug_logging", enabled)
        self._apply_log_level()

    def _apply_log_level(self) -> None:
        level = logging.DEBUG if self.debug_logging else logging.INFO
        logging.getLogger(_APP_LOGGER_NAME).setLevel(level)

    def clear_model_cache(self, _sender=None):
        """Delete the cached Whisper model so it will be re-downloaded."""
        model = self.current_model
        success = clear_model_cache(model)
        if success:
            self.recorder._model = None
            show_alert(
                "Model Cache Cleared",
                f"The Whisper {model} model cache has been removed. "
                "The model will be re-downloaded on next recording.",
            )
        else:
            show_alert(
                "Clear Failed",
                "Could not remove the model cache directory. "
                "Try manually deleting:\n"
                f"~/.cache/huggingface/hub/models--Systran--faster-whisper-{model}/",
            )

    def show_diagnostics(self, _sender=None):
        if not self.recorder.is_recording:
            update_audio_device_cache(reinit=True)
        text = format_diagnostics_text(
            ssl_verification_enabled=self.ssl_verification_enabled,
            model_loaded=self.recorder.model_loaded,
            model_name=self.current_model,
            hotkey_pynput=self.current_hotkey,
        )
        show_alert("Diagnostics", text)

    # -- settings navigation -------------------------------------------------

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

    # -- hotkey & lifecycle --------------------------------------------------

    def _toggle_recording_on_main_thread(self):
        """Ensure UI/state changes happen on macOS main thread."""
        self._dispatch_to_main(self.toggle_recording)

    def _setup_hotkey(self):
        """Register global hotkey via NSEvent global monitor.

        Uses NSEvent instead of pynput to avoid TSMGetInputSourceProperty
        being called off the main queue (crashes on macOS 26+).
        """
        import AppKit
        from writeless.hotkey_utils import pynput_to_ns_keycode_and_mask

        key_code, modifier_mask = pynput_to_ns_keycode_and_mask(self.current_hotkey)
        if key_code is None:
            raise ValueError(f"Cannot map hotkey to keycode: {self.current_hotkey}")

        check_mask = (
            AppKit.NSEventModifierFlagCommand
            | AppKit.NSEventModifierFlagOption
            | AppKit.NSEventModifierFlagControl
            | AppKit.NSEventModifierFlagShift
        )

        def handler(event):
            flags = event.modifierFlags() & check_mask
            if event.keyCode() == key_code and flags == modifier_mask:
                self._toggle_recording_on_main_thread()

        self.hotkey_listener = AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            AppKit.NSKeyDownMask,
            handler,
        )

    def _restart_hotkey_listener(self):
        """Stop the old monitor and register a new one with updated hotkey."""
        import AppKit
        old = self.hotkey_listener
        self.hotkey_listener = None
        if old is not None:
            try:
                AppKit.NSEvent.removeMonitor_(old)
            except Exception:
                pass
        try:
            self._setup_hotkey()
            hotkey_label = pynput_to_display(self.current_hotkey)
            notify_user(f"Hotkey changed: {hotkey_label}", self.notifications_enabled)
        except Exception as exc:
            hotkey_label = pynput_to_display(self.current_hotkey)
            notify_user(
                f"Hotkey {hotkey_label} unavailable: {exc}",
                self.notifications_enabled,
            )

    def _on_quit(self):
        logger.info("Write Less shutting down")
        self.recorder.cleanup()

    def run(self, **kwargs):
        logger.info("Write Less starting")

        rumps.events.before_quit.register(self._on_quit)
        atexit.register(self.recorder.cleanup)

        def _sigterm_handler(signum, frame):
            # Hard exit fallback — if cleanup deadlocks, force-kill after 3s.
            def _force_exit():
                time.sleep(3)
                os._exit(1)
            threading.Thread(target=_force_exit, daemon=True).start()
            self.recorder.cleanup()
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, _sigterm_handler)

        try:
            status = get_permission_status()
            self._setup_hotkey()
            self.permission_refresh_timer.start()
            if status.accessibility is False or status.input_monitoring is False:
                notify_user(
                    "Grant Accessibility and Input Monitoring to the current process.",
                    self.notifications_enabled,
                )
        except Exception as exc:
            logger.exception("Hotkey setup failed")
            hotkey_label = pynput_to_display(self.current_hotkey)
            notify_user(
                f"Hotkey {hotkey_label} unavailable: {exc}",
                self.notifications_enabled,
            )
        super().run(**kwargs)
