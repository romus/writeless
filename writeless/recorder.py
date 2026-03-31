"""Audio recording state machine and Whisper transcription."""

import logging
import os
import shutil
import ssl
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from writeless.constants import (
    DEFAULT_WHISPER_MODEL,
    DOWNLOADING_ICON,
    IDLE_ICON,
    LOADING_ICON,
    PROCESSING_ICON,
    RECORDING_ICON,
    RECORDING_START_TIMEOUT_SEC,
    RECORDING_STALL_TIMEOUT_SEC,
    SAMPLE_RATE,
)
from writeless.diagnostics import update_audio_device_cache
from writeless.system_services import copy_to_clipboard


def _get_model_cache_dir(model_name: str) -> str:
    """Return the HuggingFace Hub cache directory for a faster-whisper model."""
    return os.path.expanduser(
        f"~/.cache/huggingface/hub/models--Systran--faster-whisper-{model_name}"
    )


def validate_model_cache(model_name: str) -> bool:
    """Check if the HuggingFace model cache is structurally valid.

    Returns True if the cache doesn't exist (clean state) or has the
    expected refs/ and snapshots/ subdirectories. Returns False if the
    directory exists but is missing required structure.
    """
    cache_dir = _get_model_cache_dir(model_name)
    if not os.path.isdir(cache_dir):
        return True
    refs_dir = os.path.join(cache_dir, "refs")
    snapshots_dir = os.path.join(cache_dir, "snapshots")
    return os.path.isdir(refs_dir) and os.path.isdir(snapshots_dir)


def clear_model_cache(model_name: str) -> bool:
    """Delete the HuggingFace Hub cache directory for a model.

    Returns True if successfully cleared (or already absent), False on error.
    """
    cache_dir = _get_model_cache_dir(model_name)
    if not os.path.exists(cache_dir):
        return True
    try:
        shutil.rmtree(cache_dir)
        return True
    except Exception:
        return False


def _ensure_ssl_cert_file() -> None:
    """Set SSL_CERT_FILE from certifi if not already set.

    Bundled py2app builds may not find system CA certificates.
    certifi is bundled as an httpx dependency.
    """
    if os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except Exception:
        pass


def configure_ssl_verification(enabled: bool) -> bool:
    """Configure global SSL certificate verification for HTTPS requests.

    Patches both stdlib ssl (for urllib-based clients) and the httpx backend
    used by huggingface_hub for model downloads.
    """
    try:
        if enabled:
            ssl._create_default_https_context = ssl.create_default_context
            _ensure_ssl_cert_file()
        else:
            ssl._create_default_https_context = ssl._create_unverified_context

        # huggingface_hub uses httpx — configure its HTTP backend directly
        try:
            from huggingface_hub.utils._http import set_client_factory
            import httpx
            verify = enabled
            if enabled:
                try:
                    import certifi
                    verify = certifi.where()
                except Exception:
                    verify = True
            set_client_factory(lambda: httpx.Client(verify=verify))
        except Exception:
            logger.debug("Could not configure huggingface_hub HTTP backend", exc_info=True)

        return True
    except Exception:
        return False


def model_download_required(model_name: str) -> bool:
    """Return True if the CTranslate2 Whisper model is not in local cache."""
    try:
        WhisperModel(model_name, device="cpu", local_files_only=True)
        return False
    except Exception:
        return True


class Recorder:
    """Manages audio recording, watchdog timeouts, and Whisper transcription.

    Communicates back to the app via callbacks — never touches UI directly.
    """

    def __init__(
        self,
        on_status_change: Callable[[str], None],
        on_notify: Callable[[str], None],
        on_recording_stopped: Callable[[], None],
        dispatch_to_main: Callable[[Callable], None],
    ):
        self._on_status_change = on_status_change
        self._on_notify = on_notify
        self._on_recording_stopped = on_recording_stopped
        self._dispatch_to_main = dispatch_to_main

        self._recording = False
        self._audio_frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._closer_thread: threading.Thread | None = None
        self._session_id = 0
        self._lock = threading.Lock()
        self._received_frame = False
        self._last_frame_at = 0.0
        self._model = None  # lazy-loaded
        self.model_name = DEFAULT_WHISPER_MODEL
        self.ssl_verification_enabled = True

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def model_loaded(self) -> bool:
        return self._model is not None

    def cleanup(self) -> None:
        """Release all audio resources. Safe to call multiple times."""
        self._recording = False
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

        closer = self._closer_thread
        self._closer_thread = None
        if closer is not None and closer.is_alive():
            closer.join(timeout=2.0)

        try:
            sd._terminate()
        except Exception:
            pass

    def start(self) -> None:
        """Begin recording audio from the default input device."""
        self._audio_frames = []
        self._recording = True
        self._session_id += 1
        session_id = self._session_id
        self._received_frame = False
        self._last_frame_at = time.monotonic()
        self._on_status_change(RECORDING_ICON)

        # Wait for any in-flight stream close from a previous session before
        # reinitialising PortAudio. Without this, sd._terminate() could race
        # with the closer thread that is still calling stream.stop().
        closer = self._closer_thread
        self._closer_thread = None
        if closer is not None and closer.is_alive():
            logger.debug("[stream] waiting for previous closer thread")
            closer.join(timeout=1.0)
            if closer.is_alive():
                logger.debug("[stream] previous closer thread still alive after join")

        # Re-initialise PortAudio so it picks up the current system default
        # device. PortAudio caches device info at startup; without this, any
        # device change (e.g. headphones disconnected) makes the next recording
        # attempt silently open the wrong or a non-existent device.
        logger.debug("[stream] reinitialising PortAudio")
        try:
            sd._terminate()
            sd._initialize()
        except Exception:
            logger.debug("[stream] PortAudio reinit failed", exc_info=True)
        update_audio_device_cache()

        def audio_callback(indata, frames, time_info, status):
            del frames, time_info, status
            with self._lock:
                self._audio_frames.append(indata.copy())
                self._received_frame = True
                self._last_frame_at = time.monotonic()

        try:
            logger.debug("[stream] opening InputStream")
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=audio_callback,
            )
            self._stream.start()
            logger.debug("[stream] InputStream started")
        except Exception as exc:
            logger.exception("Failed to start recording")
            self._recording = False
            self._stream = None
            self._on_status_change(IDLE_ICON)
            self._on_recording_stopped()
            self._on_notify(f"Failed to start recording: {exc}")
            return

        threading.Thread(
            target=self._watchdog_loop,
            args=(session_id,),
            daemon=True,
        ).start()

    def stop(
        self,
        timeout_reached: bool = False,
        timeout_seconds: int | None = None,
    ) -> None:
        """Stop recording and kick off transcription if audio was captured."""
        logger.debug("[stream] stop() called, timeout_reached=%s", timeout_reached)
        self._recording = False
        if self._stream is not None:
            stream = self._stream
            self._stream = None

            def close_stream():
                t0 = time.monotonic()
                logger.debug("[stream] close_stream: calling abort()")
                try:
                    stream.abort()
                except Exception:
                    logger.debug("[stream] abort() failed", exc_info=True)
                logger.debug("[stream] close_stream: abort() done in %.3fs", time.monotonic() - t0)
                t1 = time.monotonic()
                logger.debug("[stream] close_stream: calling close()")
                try:
                    stream.close()
                except Exception:
                    logger.debug("[stream] close() failed", exc_info=True)
                logger.debug("[stream] close_stream: close() done in %.3fs", time.monotonic() - t1)

            closer = threading.Thread(target=close_stream, daemon=True)
            self._closer_thread = closer
            closer.start()
            closer.join(timeout=0.5)
            if closer.is_alive():
                logger.debug("[stream] closer thread hung after 0.5s, force-terminating PortAudio")
                try:
                    sd._terminate()
                except Exception:
                    logger.debug("[stream] sd._terminate() failed", exc_info=True)
                closer.join(timeout=1.0)
                if closer.is_alive():
                    logger.debug("[stream] closer thread STILL alive after sd._terminate()")
                else:
                    logger.debug("[stream] closer thread finished after sd._terminate()")
                try:
                    sd._initialize()
                except Exception:
                    logger.debug("[stream] sd._initialize() failed", exc_info=True)
            else:
                logger.debug("[stream] closer thread finished normally")

        self._on_status_change(IDLE_ICON)
        self._on_recording_stopped()

        if timeout_reached:
            timeout_value = (
                timeout_seconds
                if timeout_seconds is not None
                else RECORDING_STALL_TIMEOUT_SEC
            )
            self._on_notify(
                f"Recording stopped: no audio data for {timeout_value} seconds."
            )

        with self._lock:
            has_audio = bool(self._audio_frames)

        if not has_audio:
            self._on_notify("No audio recorded.")
            return

        with self._lock:
            audio = np.concatenate(self._audio_frames, axis=0).flatten()
            self._audio_frames = []

        self._on_status_change(PROCESSING_ICON)
        threading.Thread(target=self._transcribe, args=(audio,), daemon=True).start()

    def _watchdog_loop(self, session_id: int) -> None:
        while True:
            time.sleep(0.5)
            if not self._recording or self._session_id != session_id:
                return

            with self._lock:
                received = self._received_frame
                last_at = self._last_frame_at

            timeout_sec = (
                RECORDING_STALL_TIMEOUT_SEC
                if received
                else RECORDING_START_TIMEOUT_SEC
            )
            if time.monotonic() - last_at < timeout_sec:
                continue

            self._stop_on_main_thread(
                timeout_reached=True,
                timeout_seconds=timeout_sec,
            )
            return

    def _stop_on_main_thread(
        self,
        timeout_reached: bool = False,
        timeout_seconds: int | None = None,
    ) -> None:
        def do_stop():
            if not self._recording:
                return
            self.stop(
                timeout_reached=timeout_reached,
                timeout_seconds=timeout_seconds,
            )

        self._dispatch_to_main(do_stop)

    def _transcribe(self, audio: np.ndarray) -> None:
        try:
            if self._model is None:
                model_name = self.model_name

                if not validate_model_cache(model_name):
                    logger.warning("Model cache corrupted, clearing")
                    self._on_notify("Model cache corrupted. Clearing...")
                    clear_model_cache(model_name)

                needs_download = model_download_required(model_name)
                if needs_download:
                    self._on_status_change(DOWNLOADING_ICON)
                    msg = "Downloading Whisper model for first use..."
                    if not self.ssl_verification_enabled:
                        msg = "Downloading Whisper model with SSL verification disabled."
                    self._on_notify(msg)
                else:
                    self._on_status_change(LOADING_ICON)
                    self._on_notify("Loading Whisper model...")

                try:
                    self._model = WhisperModel(
                        model_name, device="cpu", compute_type="float32"
                    )
                except Exception as load_exc:
                    exc_msg = str(load_exc).lower()
                    retryable = (
                        "snapshot" in exc_msg
                        or "locate the files" in exc_msg
                        or "client has been closed" in exc_msg
                    )
                    if retryable:
                        logger.warning(
                            "Model load failed (retryable), clearing cache: %s",
                            load_exc,
                        )
                        try:
                            from huggingface_hub.utils import close_session
                            close_session()
                        except Exception:
                            pass
                        clear_model_cache(model_name)
                        self._on_status_change(DOWNLOADING_ICON)
                        try:
                            self._model = WhisperModel(
                                model_name, device="cpu", compute_type="float32"
                            )
                        except Exception as retry_exc:
                            logger.exception("Model download retry failed")
                            raise RuntimeError(
                                "Could not download Whisper model. "
                                "Check your internet connection.\n"
                                "Try toggling 'SSL Verification' in Settings."
                            ) from retry_exc
                    else:
                        raise

                if needs_download:
                    self._on_notify("Whisper model downloaded.")

            audio_float32 = np.asarray(audio, dtype=np.float32)
            segments, _info = self._model.transcribe(audio_float32)
            text = " ".join(seg.text for seg in segments).strip()
            self._on_status_change(IDLE_ICON)

            if text:
                copied = copy_to_clipboard(text)
                if copied:
                    self._on_notify("Recognized and copied to clipboard.")
                else:
                    self._on_notify("Recognized, but failed to copy to clipboard.")
            else:
                self._on_notify("No speech detected.")
        except Exception as exc:
            logger.exception("Transcription error")
            self._on_status_change(IDLE_ICON)
            message = f"Error: {exc}"
            if "CERTIFICATE_VERIFY_FAILED" in str(exc):
                if self.ssl_verification_enabled:
                    message = (
                        f"{message}. "
                        "Disable SSL Verification in app menu and try again."
                    )
            self._on_notify(message)
