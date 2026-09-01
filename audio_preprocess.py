"""Lightweight audio pre-processing for ASR.

Pipeline order (matters):
    raw audio (16 kHz mono float32)
        → spectral denoise           (noisereduce, optional, OFF by default)
        → high-pass @ 80 Hz          (scipy Butterworth, optional)
        → pre-emphasis 0.97          (numpy, optional, OFF by default)
        → peak normalize to -3 dBFS  (numpy, always if peaks > 0)

All steps degrade gracefully: if a dependency is missing, the corresponding
stage is skipped. The module is safe to import on any venv that has numpy.
"""

from __future__ import annotations

import numpy as np

try:
    from scipy.signal import butter, sosfiltfilt
    _HAS_SCIPY = True
except Exception:  # ImportError, OSError on missing DLL
    _HAS_SCIPY = False

try:
    import noisereduce as nr
    _HAS_NOISEREDUCE = True
except Exception:
    _HAS_NOISEREDUCE = False

from logger import log

DEFAULT_SR = 16000


def highpass(audio: np.ndarray, cutoff_hz: float = 80.0, sr: int = DEFAULT_SR) -> np.ndarray:
    """Zero-phase 4th-order Butterworth high-pass filter.

    Removes low-frequency rumble: PC fans, network hum, mechanical mic stand
    vibration, mouth pops. 80 Hz is conservative for speech — doesn't touch
    fundamental frequency of male voice (~85-180 Hz) but kills everything
    below 80 Hz.
    """
    if not _HAS_SCIPY or audio.size < 32:
        return audio
    try:
        sos = butter(4, cutoff_hz, btype="highpass", fs=sr, output="sos")
        return sosfiltfilt(sos, audio).astype(np.float32)
    except Exception as exc:
        log.debug("highpass failed: %s", exc)
        return audio


def preemphasis(audio: np.ndarray, coef: float = 0.97) -> np.ndarray:
    """y[n] = x[n] - coef * x[n-1]. Boosts high frequencies.

    Standard pre-processing for acoustic models. GigaAM was NOT explicitly
    trained with pre-emphasis — leaving OFF by default. Enable only if you
    observe muffled recognition of fricatives.
    """
    if audio.size == 0:
        return audio
    out = np.empty_like(audio, dtype=np.float32)
    out[0] = audio[0]
    out[1:] = audio[1:] - coef * audio[:-1]
    return out


def normalize_peak(audio: np.ndarray, target_dbfs: float = -3.0) -> np.ndarray:
    """Peak-normalize so max(|x|) == 10**(target_dbfs/20).

    -3 dBFS leaves headroom to avoid clipping after subsequent stages.
    """
    if audio.size == 0:
        return audio
    peak = float(np.abs(audio).max())
    if peak < 1e-6:
        return audio
    target = 10.0 ** (target_dbfs / 20.0)
    gain = target / peak
    if 0.99 <= gain <= 1.01:
        return audio
    return (audio * gain).astype(np.float32)


def denoise(audio: np.ndarray, sr: int = DEFAULT_SR) -> np.ndarray:
    """Spectral gating noise reduction (noisereduce, non-stationary mode).

    Heavier stage — ~50-150 ms per 1 s of audio on CPU. Skip by default.
    Enable for recordings in noisy environments (street, cafe, fan noise).
    """
    if not _HAS_NOISEREDUCE or audio.size < int(0.5 * sr):
        return audio
    try:
        return nr.reduce_noise(y=audio, sr=sr, stationary=False).astype(np.float32)
    except Exception as exc:
        log.debug("denoise failed: %s", exc)
        return audio


def preprocess(
    audio: np.ndarray,
    sr: int = DEFAULT_SR,
    *,
    do_denoise: bool = False,
    do_highpass: bool = True,
    do_preemphasis: bool = False,
    do_normalize: bool = True,
) -> np.ndarray:
    """Apply selected pre-processing stages.

    Args:
        audio: mono float32 waveform, 16 kHz.
        sr: sample rate (default 16 kHz — what GigaAM expects).
        do_denoise: spectral gating (noisereduce, optional dependency).
        do_highpass: 80 Hz high-pass (scipy optional, falls back to skip).
        do_preemphasis: HF boost (numpy only).
        do_normalize: peak normalize to -3 dBFS (numpy only).

    Returns:
        Pre-processed mono float32 audio, same length.
    """
    if audio is None or audio.size == 0:
        return audio
    # Ensure float32 (some sources may already be)
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32, copy=False)

    if do_denoise:
        audio = denoise(audio, sr)
    if do_highpass:
        audio = highpass(audio, 80.0, sr)
    if do_preemphasis:
        audio = preemphasis(audio, 0.97)
    if do_normalize:
        audio = normalize_peak(audio, -3.0)
    return audio


def available_backends() -> dict:
    """Diagnostic info — what optional dependencies are present."""
    return {
        "scipy": _HAS_SCIPY,
        "noisereduce": _HAS_NOISEREDUCE,
    }
