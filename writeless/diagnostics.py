"""Audio device diagnostics, signal probe helpers, and diagnostics text formatting."""

import os
import sys
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

from writeless.constants import HOTKEY_LABEL
from writeless.system_services import get_notification_status, get_permission_status


@dataclass(frozen=True)
class AudioDeviceStatus:
    default_input_index: int | None
    default_input_name: str | None
    max_input_channels: int | None
    default_samplerate: float | None
    error: str | None


@dataclass(frozen=True)
class AudioProbeResult:
    duration_sec: float
    samplerate: int
    total_frames: int
    callbacks: int
    rms: float
    peak: float
    status_flags: tuple[str, ...]
    verdict: str
    error: str | None


def get_audio_device_status() -> AudioDeviceStatus:
    """Return default input audio device details."""
    try:
        device_info = sd.query_devices(kind="input")
        input_index = int(device_info["index"])
        return AudioDeviceStatus(
            default_input_index=input_index,
            default_input_name=str(device_info.get("name", "Unknown")),
            max_input_channels=int(device_info.get("max_input_channels", 0)),
            default_samplerate=float(device_info.get("default_samplerate", 0.0)),
            error=None,
        )
    except Exception as exc:
        return AudioDeviceStatus(None, None, None, None, str(exc))


def probe_audio_input(duration_sec: float = 2.0, samplerate: int = 16000, channels: int = 1) -> AudioProbeResult:
    """Capture a short input sample and report signal stats."""
    captured_frames: list[np.ndarray] = []
    callback_statuses: set[str] = set()
    callback_count = 0

    def probe_callback(indata, frames, time_info, status):
        del frames, time_info
        nonlocal callback_count
        callback_count += 1
        if status:
            callback_statuses.add(str(status))
        captured_frames.append(indata.copy())

    try:
        with sd.InputStream(
            samplerate=samplerate,
            channels=channels,
            dtype="float32",
            callback=probe_callback,
        ):
            sd.sleep(int(duration_sec * 1000))
    except Exception as exc:
        return AudioProbeResult(
            duration_sec=float(duration_sec),
            samplerate=int(samplerate),
            total_frames=0,
            callbacks=callback_count,
            rms=0.0,
            peak=0.0,
            status_flags=tuple(sorted(callback_statuses)),
            verdict="ERROR",
            error=str(exc),
        )

    total_frames = 0
    rms = 0.0
    peak = 0.0

    if captured_frames:
        audio = np.concatenate(captured_frames, axis=0).astype(np.float32, copy=False).flatten()
        total_frames = int(audio.size)
        if audio.size > 0:
            rms = float(np.sqrt(np.mean(np.square(audio))))
            peak = float(np.max(np.abs(audio)))

    epsilon = 1e-4
    verdict = "OK" if total_frames > 0 and (rms > epsilon or peak > epsilon) else "SILENT_OR_EMPTY"

    return AudioProbeResult(
        duration_sec=float(duration_sec),
        samplerate=int(samplerate),
        total_frames=total_frames,
        callbacks=callback_count,
        rms=rms,
        peak=peak,
        status_flags=tuple(sorted(callback_statuses)),
        verdict=verdict,
        error=None,
    )


def format_diagnostics_text(
    ssl_verification_enabled: bool,
    model_loaded: bool,
    model_name: str = "small",
) -> str:
    """Gather system info and return formatted diagnostics text."""
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

    cache_dir = os.path.expanduser("~/.cache/whisper")
    model_file = os.path.join(cache_dir, f"{model_name}.pt")
    model_path = model_file if os.path.exists(model_file) else None

    device = get_audio_device_status()
    input_device = device.default_input_name or "None"

    acc = "OK" if status.accessibility else "MISSING"
    inp = "OK" if status.input_monitoring else "MISSING"
    notif_label = "OK" if notif_status == "authorized" else f"MISSING ({notif_status})"
    model_status = "yes" if model_path else "no"
    model_mem = "yes" if model_loaded else "no"

    lines = [
        "— App —",
        f"  Process:    {os.path.basename(sys.executable)}",
        f"  Bundle ID:  {bundle_id}",
        f"  Executable: {sys.executable}",
        "",
        "— Audio —",
        f"  Input Device: {input_device}",
        f"  Hotkey:       {HOTKEY_LABEL}",
        "",
        "— Permissions —",
        f"  Accessibility:    {acc}",
        f"  Input Monitoring: {inp}",
        f"  Notifications:    {notif_label}",
        "",
        "— Whisper —",
        f"  Model:      {model_name} (downloaded: {model_status}, loaded: {model_mem})",
        f"  Model path: {model_path or 'N/A'}",
        "",
        "— Network —",
        f"  SSL verification: {'On' if ssl_verification_enabled else 'Off'}",
    ]
    return "\n".join(lines)
