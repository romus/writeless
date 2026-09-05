"""System-level helpers for notifications, clipboard, sounds, and permissions."""

import ctypes
import ctypes.util
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import rumps

from writeless.constants import COMPLETION_SOUND_OFF


@dataclass(frozen=True)
class PermissionStatus:
    accessibility: bool | None
    input_monitoring: bool | None


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


def _load_user_notifications():
    """Load the UserNotifications framework via objc bridge."""
    import objc

    objc.loadBundle(
        "UserNotifications",
        bundle_path="/System/Library/Frameworks/UserNotifications.framework",
        module_globals=globals(),
    )

    # Register block signatures missing from PyObjC metadata.
    # requestAuthorizationWithOptions:completionHandler: → void (^)(BOOL, NSError*)
    objc.registerMetaDataForSelector(
        b"UNUserNotificationCenter",
        b"requestAuthorizationWithOptions:completionHandler:",
        {
            "arguments": {
                3: {
                    "callable": {
                        "retval": {"type": b"v"},
                        "arguments": {
                            0: {"type": b"^v"},
                            1: {"type": b"Z"},
                            2: {"type": b"@"},
                        },
                    }
                }
            }
        },
    )
    # addNotificationRequest:withCompletionHandler: → void (^)(NSError*)
    objc.registerMetaDataForSelector(
        b"UNUserNotificationCenter",
        b"addNotificationRequest:withCompletionHandler:",
        {
            "arguments": {
                3: {
                    "callable": {
                        "retval": {"type": b"v"},
                        "arguments": {
                            0: {"type": b"^v"},
                            1: {"type": b"@"},
                        },
                    }
                }
            }
        },
    )
    # getNotificationSettingsWithCompletionHandler: → void (^)(UNNotificationSettings*)
    objc.registerMetaDataForSelector(
        b"UNUserNotificationCenter",
        b"getNotificationSettingsWithCompletionHandler:",
        {
            "arguments": {
                2: {
                    "callable": {
                        "retval": {"type": b"v"},
                        "arguments": {
                            0: {"type": b"^v"},
                            1: {"type": b"@"},
                        },
                    }
                }
            }
        },
    )


_load_user_notifications()

# Constants from UNAuthorizationOptions
_UNAuthorizationOptionAlert = 1 << 0
_UNAuthorizationOptionSound = 1 << 1


def request_notification_permission() -> None:
    """Request notification permission from the user. Call once at app startup."""
    center = UNUserNotificationCenter.currentNotificationCenter()  # noqa: F821
    center.requestAuthorizationWithOptions_completionHandler_(
        _UNAuthorizationOptionAlert | _UNAuthorizationOptionSound,
        lambda granted, error: None,
    )


def get_notification_status() -> str:
    """Return notification authorization status: 'authorized', 'denied', 'notDetermined', or 'unknown'."""
    import threading

    result = ["unknown"]
    event = threading.Event()

    # UNAuthorizationStatus: 0=notDetermined, 1=denied, 2=authorized, 3=provisional, 4=ephemeral
    _status_map = {0: "notDetermined", 1: "denied", 2: "authorized", 3: "provisional", 4: "ephemeral"}

    def handler(settings):
        try:
            result[0] = _status_map.get(settings.authorizationStatus(), "unknown")
        except Exception:
            pass
        event.set()

    center = UNUserNotificationCenter.currentNotificationCenter()  # noqa: F821
    center.getNotificationSettingsWithCompletionHandler_(handler)
    event.wait(timeout=2.0)
    return result[0]


def notify_user(message: str, enabled: bool = True) -> None:
    """Show a macOS notification via UNUserNotificationCenter."""
    if not enabled:
        return
    import uuid

    content = UNMutableNotificationContent.alloc().init()  # noqa: F821
    content.setTitle_("Write Less")
    content.setBody_(message)
    request = UNNotificationRequest.requestWithIdentifier_content_trigger_(  # noqa: F821
        str(uuid.uuid4()), content, None
    )
    center = UNUserNotificationCenter.currentNotificationCenter()  # noqa: F821
    center.addNotificationRequest_withCompletionHandler_(request, None)


def get_permission_status() -> PermissionStatus:
    """Return macOS permission state needed for global key capture."""
    accessibility = None
    input_monitoring = None

    # Reliable accessibility check via macOS ApplicationServices API.
    try:
        app_services = ctypes.CDLL(
            ctypes.util.find_library("ApplicationServices"),
            use_errno=True,
        )
        app_services.AXIsProcessTrusted.restype = ctypes.c_bool
        accessibility = bool(app_services.AXIsProcessTrusted())
    except Exception:
        pass

    try:
        from Quartz import CGPreflightListenEventAccess

        input_monitoring = bool(CGPreflightListenEventAccess())
    except Exception:
        pass

    return PermissionStatus(
        accessibility=accessibility,
        input_monitoring=input_monitoring,
    )


def open_settings_url(url: str) -> None:
    """Open a macOS System Settings URL."""
    subprocess.run(["/usr/bin/open", url], check=False)


def _resolve_app_icon_path() -> str | None:
    """Resolve app icon path for source and bundled runs."""
    try:
        from Foundation import NSBundle

        bundle = NSBundle.mainBundle()
        if bundle is not None:
            bundle_icon = bundle.pathForResource_ofType_("icon", "icns")
            if bundle_icon:
                return str(bundle_icon)
    except Exception:
        pass

    root = Path(__file__).resolve().parents[1]
    icon_path = root / "icon.icns"
    if icon_path.exists():
        return str(icon_path)
    return None


def set_app_icon() -> None:
    """Set NSApplication icon from project/bundle icon file."""
    try:
        from AppKit import NSApp, NSImage

        icon_path = _resolve_app_icon_path()
        if not icon_path:
            return
        image = NSImage.alloc().initWithContentsOfFile_(icon_path)
        if image is None:
            return
        app = NSApp()
        if app is not None:
            app.setApplicationIconImage_(image)
    except Exception:
        pass


def show_alert(title: str, message: str) -> None:
    """Show a modal alert using app icon when available."""
    try:
        from AppKit import NSAlert, NSImage

        alert = NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("OK")

        app_icon = None
        icon_path = _resolve_app_icon_path()
        if icon_path:
            app_icon = NSImage.alloc().initWithContentsOfFile_(icon_path)
        if app_icon is not None:
            alert.setIcon_(app_icon)

        alert.runModal()
    except Exception:
        rumps.alert(title, message)


# Reference to the sound most recently started. Lets the next call stop it
# (NSSound.play returns NO while the same instance is still playing) and
# keeps the object alive for the duration of playback.
_current_sound = None


def play_system_sound(name: str) -> bool:
    """Play a named macOS system sound (e.g. "Glass"). Returns True if playback started."""
    global _current_sound
    if not name or name == COMPLETION_SOUND_OFF:
        return False
    try:
        from AppKit import NSSound

        sound = NSSound.soundNamed_(name)
        if sound is None:
            return False
        if _current_sound is not None:
            _current_sound.stop()
        _current_sound = sound
        return bool(sound.play())
    except Exception:
        return False
