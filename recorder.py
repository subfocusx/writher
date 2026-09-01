import threading
import time

import numpy as np
import sounddevice as sd
import config
import sounds
from logger import log

# ── Resampling backends (priority: soxr > scipy > np.interp) ────────────────
try:
    import soxr
    _HAS_SOXR = True
except Exception:
    _HAS_SOXR = False
try:
    from scipy.signal import resample_poly
    from fractions import Fraction
    _HAS_SCIPY = True
except Exception:
    _HAS_SCIPY = False


def _resample_to_16k(audio: np.ndarray, src_rate: int) -> np.ndarray:
    """High-quality resample mono float32 audio to 16 kHz.

    Priority: soxr (best, native) → scipy.signal.resample_poly (FIR) → np.interp.
    The last-resort np.interp preserves the previous behaviour so the app
    keeps working even when no high-quality library is installed. When falling
    back, a moving-average anti-aliasing low-pass is applied before decimation.
    """
    if src_rate == 16000 or audio.size == 0:
        return audio
    if _HAS_SOXR:
        return soxr.resample(audio, src_rate, 16000, quality="HQ").astype(np.float32)
    if _HAS_SCIPY:
        frac = Fraction(16000, src_rate).limit_denominator(1000)
        return resample_poly(audio, frac.numerator, frac.denominator).astype(np.float32)
    # Last-resort: previous behaviour, plus moving-average AA filter for >32k src.
    duration = len(audio) / src_rate
    target_len = int(duration * 16000)
    if target_len < 2:
        return audio.astype(np.float32, copy=False)
    if src_rate > 32000:
        kernel = max(3, int(src_rate / 16000) * 2 + 1)
        if kernel % 2 == 0:
            kernel += 1
        pad = kernel // 2
        padded = np.concatenate([
            np.full(pad, audio[0], dtype=audio.dtype),
            audio,
            np.full(pad, audio[-1], dtype=audio.dtype),
        ])
        kernel_arr = np.ones(kernel, dtype=np.float32) / kernel
        audio = np.convolve(padded, kernel_arr, mode="valid").astype(np.float32)
    indices = np.linspace(0, len(audio) - 1, target_len)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


# Shared lock around PortAudio's private terminate/initialise API.
# sd._terminate() / sd._initialize() are undocumented and racy when called
# from multiple threads — they tear down and re-create the host API state.
# Recorder (on start) and SettingsWindow (on mic refresh) both call them,
# so we serialise through this lock. Lock is module-level so both modules
# see the same instance.
_sd_lock = threading.Lock()


def _resolve_device(name: str | None) -> int | None:
    """Resolve a device name to a WASAPI device index at call time.

    Returns None (system default) if name is None or not found.
    Prefers WASAPI host API for reliable Windows audio.
    Re-initializes PortAudio to get fresh device indices.
    """
    if not name:
        return None
    try:
        # Re-init PortAudio to get current indices. Locked because
        # SettingsWindow._get_input_devices() also calls these.
        with _sd_lock:
            sd._terminate()
            sd._initialize()

        host_apis = sd.query_hostapis()
        wasapi_idx = None
        for i, api in enumerate(host_apis):
            if "WASAPI" in api.get("name", ""):
                wasapi_idx = i
                break

        all_devs = sd.query_devices()

        # First pass: exact match on WASAPI
        for i, dev in enumerate(all_devs):
            if dev["max_input_channels"] <= 0:
                continue
            if wasapi_idx is not None and dev.get("hostapi") != wasapi_idx:
                continue
            if dev["name"] == name:
                return i

        # Second pass: partial match on WASAPI
        target = name.lower()
        for i, dev in enumerate(all_devs):
            if dev["max_input_channels"] <= 0:
                continue
            if wasapi_idx is not None and dev.get("hostapi") != wasapi_idx:
                continue
            if target in dev["name"].lower():
                return i

        # Third pass: any host API, exact match
        for i, dev in enumerate(all_devs):
            if dev["max_input_channels"] <= 0:
                continue
            if dev["name"] == name:
                return i

        log.warning("Microphone '%s' not found, falling back to default", name)
    except Exception as exc:
        log.warning("Device resolution failed: %s", exc)
    return None


class Recorder:
    def __init__(self):
        self._frames = []
        self._stream = None
        self.recording = False
        self._lock = threading.Lock()  # protects _frames and recording
        self.on_level = None       # optional callback(rms: float) set by main
        self.on_mic_error = None   # optional callback(msg: str) set by main
        self.on_vad_trigger = None # called from audio thread when VAD detects silence
        self._vad_model = None     # lazy-loaded Silero VAD model
        self._vad_torch = None     # torch module reference (avoids re-import in callback)
        self._vad_silence_frames = 0
        # Pre-roll buffer: filled while the stream is open but recording
        # is still False, so the first ~300 ms of audio is never lost to
        # PortAudio startup latency (typically 50-200 ms before the first
        # _callback fires). Populated in start(), flushed in _callback.
        self._preroll = []
        self._preroll_max_frames = 6  # ~6 * 50ms = 300ms at 20ms blocks
        # Drain timing for stop(): let PortAudio flush the final blocks
        # before we close the stream, otherwise the trailing 50-100 ms
        # (and the last consonant / sibilant with it) is lost.
        self._drain_seconds = 0.1

    def _ensure_vad(self):
        """Lazy-initialise Silero VAD model. Safe to call from any thread."""
        if self._vad_model is not None:
            return
        try:
            import torch
            torch.set_num_threads(1)
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
            )
            self._vad_model = model
            self._vad_torch = torch
            log.info("Silero VAD model loaded.")
        except Exception as exc:
            log.warning("Failed to load Silero VAD: %s", exc)

    def _callback(self, indata, frames, time, status):
        # Snapshot `recording` and append the frame in a single critical
        # section. We don't hold the lock around VAD inference (which can
        # take 50-200ms with Silero) — VAD state is a single int that's
        # safe to race on, and any in-flight inference will see a stale
        # value for one frame at most.
        with self._lock:
            if not self.recording:
                # Pre-roll: stream is open but user hasn't started speaking
                # yet (or is between recordings). Buffer up to N frames so
                # the very first utterance isn't clipped.
                if len(self._preroll) < self._preroll_max_frames:
                    self._preroll.append(indata.copy())
                return
            # First frame after recording=True: flush pre-roll BEFORE
            # the live frame, so the audio timeline starts at the moment
            # the user pressed the hotkey, not at the moment the OS
            # delivered the first callback.
            if self._preroll:
                self._frames.extend(self._preroll)
                self._preroll.clear()
            self._frames.append(indata.copy())
        if self.on_level is not None:
            rms = float(np.sqrt(np.mean(indata ** 2)))
            self.on_level(rms)

        # VAD auto-stop (toggle mode, 16 kHz only)
        if (not config.HOLD_TO_RECORD
                and self._vad_model is not None
                and self._sample_rate == 16000
                and config.VAD_AUTO_STOP_SECONDS > 0):
            try:
                speech_prob = self._vad_model(
                    self._vad_torch.from_numpy(indata.flatten()), 16000
                ).item()
                if speech_prob < config.VAD_THRESHOLD:
                    self._vad_silence_frames += 1
                    frame_sec = len(indata) / self._sample_rate
                    if self._vad_silence_frames * frame_sec >= config.VAD_AUTO_STOP_SECONDS:
                        if self.on_vad_trigger:
                            self.on_vad_trigger()
                        self._vad_silence_frames = 0
                else:
                    self._vad_silence_frames = 0
            except Exception as exc:
                log.warning("VAD frame error: %s", exc)

    def start(self):
        if self.recording:
            return
        self._frames = []
        self._preroll = []
        self._sample_rate = config.SAMPLE_RATE
        self._vad_silence_frames = 0
        # NOTE: do NOT set self.recording = True here. We open the stream
        # first; the first _callback after stream.start() flips recording
        # to True and flushes the pre-roll buffer so no audio is lost.
        sounds.play_start_tone()
        if not config.HOLD_TO_RECORD and config.VAD_AUTO_STOP_SECONDS > 0:
            self._ensure_vad()
        try:
            device_name = getattr(config, "MIC_DEVICE_NAME", None)
            device_idx = _resolve_device(device_name)
            log.info("Opening mic: name=%s resolved_idx=%s", device_name, device_idx)

            # Always try 16000 Hz first (what Whisper expects).
            # Only fall back to device native rate if 16kHz is not supported.
            sample_rate = config.SAMPLE_RATE
            try:
                self._stream = sd.InputStream(
                    samplerate=sample_rate,
                    channels=1,
                    dtype="float32",
                    device=device_idx,
                    callback=self._callback,
                )
                self._stream.start()
                self._sample_rate = sample_rate
                self.recording = True
                return
            except (sd.PortAudioError, OSError):
                # 16kHz not supported by this device, try native rate
                log.info("Device does not support %d Hz, trying native rate", sample_rate)

            # Fall back to device default sample rate + resample later
            if device_idx is not None:
                dev_info = sd.query_devices(device_idx)
                sample_rate = int(dev_info.get("default_samplerate", 48000))
            else:
                sample_rate = 48000
            log.info("Using device native sample rate: %d Hz (will resample to %d)",
                     sample_rate, config.SAMPLE_RATE)

            self._stream = sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                device=device_idx,
                callback=self._callback,
            )
            self._stream.start()
            self._sample_rate = sample_rate
            self.recording = True
        except (sd.PortAudioError, OSError, Exception) as exc:
            log.error("Failed to open microphone: %s", exc)
            self.recording = False
            self._stream = None
            if self.on_mic_error:
                self.on_mic_error("🎤 No microphone detected")

    def get_current_audio(self) -> np.ndarray | None:
        """Return a copy of the accumulated audio recorded so far.

        DEPRECATED: unused by the current pipeline (kept for future
        streaming). Marked for removal if no consumer shows up by 1.2.0.
        """
        frames = list(self._frames)
        if not frames:
            return None
        audio = np.concatenate(frames, axis=0).flatten()
        target_rate = config.SAMPLE_RATE
        if self._sample_rate != target_rate:
            audio = _resample_to_16k(audio.astype(np.float32, copy=False), self._sample_rate)
        return audio

    def stop(self):
        if not self.recording:
            return None
        # Atomic snapshot: take everything currently in _frames under the
        # lock, then release the lock so the audio callback can keep
        # appending (it won't, because recording=False below, but the lock
        # makes the read+clear a single critical section).
        with self._lock:
            self.recording = False
            # Final flush: pull any pre-roll the user never triggered.
            # Empty when this stop() follows a real start() that already
            # flushed; non-empty when stop() runs before the first
            # _callback (very fast release after press).
            if self._preroll:
                self._frames.extend(self._preroll)
                self._preroll.clear()
            frames = list(self._frames)
            self._frames = []
        self._vad_silence_frames = 0
        sounds.play_stop_tone()
        # Stop+close the PortAudio stream outside the lock — these calls
        # block while PortAudio drains, and we never want to hold _lock
        # during a blocking native call.
        # IMPORTANT: a short sleep BEFORE close() lets PortAudio flush
        # its internal ring buffer, otherwise the final 50-100 ms of
        # audio (and the trailing sibilants / final consonants) is lost.
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            if self._drain_seconds > 0:
                time.sleep(self._drain_seconds)
            try:
                stream.close()
            except Exception:
                pass
        if not frames:
            return None
        audio = np.concatenate(frames, axis=0).flatten()

        # Resample to 16kHz if recorded at a different rate
        target_rate = config.SAMPLE_RATE
        if self._sample_rate != target_rate:
            audio = _resample_to_16k(audio.astype(np.float32, copy=False), self._sample_rate)
            log.info("Resampled audio from %d Hz to %d Hz (%d samples, backend=%s)",
                     self._sample_rate, target_rate, len(audio),
                     "soxr" if _HAS_SOXR else ("scipy" if _HAS_SCIPY else "np.interp"))

        return audio
