"""Audio device diagnostics, signal probe helpers, and diagnostics text formatting."""

import os
import sys
import threading
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

from writeless.constants import APP_VERSION
from writeless.hotkey_utils import pynput_to_display
from writeless.system_services import get_notification_status, get_permission_status

_device_lock = threading.Lock()
_cached_device: "AudioDeviceStatus | None" = None


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


def _query_audio_device_status() -> "AudioDeviceStatus":
    """Query PortAudio for the current default input device (no re-init)."""
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


def update_audio_device_cache(reinit: bool = False) -> None:
    """Refresh the cached device info.

    Pass reinit=True to re-initialise PortAudio first (use when no stream is
    open). Pass reinit=False (default) when the caller already did the re-init.
    """
    global _cached_device
    if reinit:
        try:
            sd._terminate()
            sd._initialize()
        except Exception:
            pass
    status = _query_audio_device_status()
    with _device_lock:
        _cached_device = status


def get_audio_device_status() -> AudioDeviceStatus:
    """Return the cached default input device, or query directly if not yet cached."""
    with _device_lock:
        if _cached_device is not None:
            return _cached_device
    return _query_audio_device_status()


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
    hotkey_pynput: str = "",
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

    model_path = None
    hf_model_dir = os.path.expanduser(
        f"~/.cache/huggingface/hub/models--Systran--faster-whisper-{model_name}"
    )
    if os.path.isdir(hf_model_dir):
        model_path = hf_model_dir

    device = get_audio_device_status()
    input_device = device.default_input_name or "None"

    acc = "OK" if status.accessibility else "MISSING"
    inp = "OK" if status.input_monitoring else "MISSING"
    notif_label = "OK" if notif_status == "authorized" else f"MISSING ({notif_status})"
    if model_path:
        refs_ok = os.path.isdir(os.path.join(hf_model_dir, "refs"))
        snaps_ok = os.path.isdir(os.path.join(hf_model_dir, "snapshots"))
        model_status = "yes" if (refs_ok and snaps_ok) else "CORRUPTED"
    else:
        model_status = "no"
    model_mem = "yes" if model_loaded else "no"

    lines = [
        "— App —",
        f"  Version:    {APP_VERSION}",
        f"  Process:    {os.path.basename(sys.executable)}",
        f"  Bundle ID:  {bundle_id}",
        f"  Executable: {sys.executable}",
        "",
        "— Audio —",
        f"  Input Device: {input_device}",
        f"  Hotkey:       {pynput_to_display(hotkey_pynput) if hotkey_pynput else 'N/A'}",
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
