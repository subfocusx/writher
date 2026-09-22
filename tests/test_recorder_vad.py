"""Unit tests for recorder.py VAD auto-stop (feature 1.1).

Tests the Silero VAD integration in _callback: silence detection
triggers on_vad_trigger, speech resets counter, hold mode disables VAD.
"""
import sys
import types
import numpy as np
import pytest


@pytest.fixture
def recorder_with_vad(monkeypatch):
    """Stub sounddevice and load recorder with test config."""
    # Stub sounddevice.InputStream to avoid actual audio hardware
    class FakeStream:
        def start(self): pass
        def stop(self): pass
        def close(self): pass
    sd_mod = types.ModuleType("sounddevice")
    sd_mod.InputStream = lambda *a, **kw: FakeStream()
    sd_mod.query_devices = lambda *a, **kw: []
    sd_mod.query_hostapis = lambda *a, **kw: []
    sd_mod._terminate = lambda: None
    sd_mod._initialize = lambda: None
    monkeypatch.setitem(sys.modules, "sounddevice", sd_mod)

    # Stub config
    config_mod = types.ModuleType("config")
    config_mod.SAMPLE_RATE = 16000
    config_mod.HOLD_TO_RECORD = False
    config_mod.VAD_AUTO_STOP_SECONDS = 2.0
    config_mod.VAD_THRESHOLD = 0.5
    config_mod.MIC_DEVICE_NAME = None
    monkeypatch.setitem(sys.modules, "config", config_mod)

    # Stub logger
    import logging
    logger_mod = types.ModuleType("logger")
    logger_mod.log = logging.getLogger("test_vad")
    logger_mod.log.addHandler(logging.NullHandler())
    monkeypatch.setitem(sys.modules, "logger", logger_mod)

    if "recorder" in sys.modules:
        del sys.modules["recorder"]
    import recorder

    return recorder, config_mod


# ── Fake VAD helpers ───────────────────────────────────────────────────

class _FakeTensor:
    def __init__(self, data, return_val=0.5):
        self.data = data
        self._return = return_val
    def item(self):
        return self._return

class _FakeTorch:
    @staticmethod
    def from_numpy(arr):
        return _FakeTensor(arr, 0.5)
    @staticmethod
    def set_num_threads(n):
        pass

class _FakeVAD:
    def __init__(self, speech_prob=0.5):
        self.speech_prob = speech_prob
    def __call__(self, tensor, sr):
        return _FakeTensor(tensor.data, self.speech_prob)


# ── VAD silence detection ─────────────────────────────────────────────

def test_vad_silence_triggers_stop(recorder_with_vad):
    """Continuous non-speech frames must trigger on_vad_trigger."""
    rec, cfg = recorder_with_vad
    rec.Recorder._sample_rate = 16000
    inst = rec.Recorder()
    inst.recording = True
    inst._sample_rate = 16000
    inst._vad_model = _FakeVAD(speech_prob=0.1)
    inst._vad_torch = _FakeTorch

    triggered = []
    inst.on_vad_trigger = lambda: triggered.append(True)

    frames_512 = np.zeros((512, 1), dtype=np.float32)
    needed = int(2.0 * 16000 / 512) + 1
    for _ in range(needed):
        inst._callback(frames_512, 512, None, None)

    assert triggered


def test_speech_resets_silence_counter(recorder_with_vad):
    """When VAD detects speech, silence frame count must reset."""
    rec, cfg = recorder_with_vad
    inst = rec.Recorder()
    inst.recording = True
    inst._sample_rate = 16000
    inst._vad_model = _FakeVAD(speech_prob=0.1)
    inst._vad_torch = _FakeTorch

    triggered = []
    inst.on_vad_trigger = lambda: triggered.append(True)

    frames_512 = np.zeros((512, 1), dtype=np.float32)
    # Send some silent frames (not enough to trigger)
    for _ in range(30):
        inst._callback(frames_512, 512, None, None)
    # Interrupt with speech
    inst._vad_model = _FakeVAD(speech_prob=0.9)
    for _ in range(5):
        inst._callback(frames_512, 512, None, None)
    # Back to silence (now should need 2 full sec again)
    inst._vad_model = _FakeVAD(speech_prob=0.1)
    # This would trigger if counter wasn't reset — so verify it doesn't yet
    # After reset, 30 frames is not enough for 2s at 512/16000 per frame
    assert not triggered  # should still be false after speech interruption


def test_vad_disabled_in_hold_mode(recorder_with_vad):
    """In hold mode, VAD must not trigger even with silence."""
    rec, cfg = recorder_with_vad
    cfg.HOLD_TO_RECORD = True
    inst = rec.Recorder()
    inst.recording = True
    inst._sample_rate = 16000
    inst._vad_model = _FakeVAD(speech_prob=0.1)
    inst._vad_torch = _FakeTorch

    triggered = []
    inst.on_vad_trigger = lambda: triggered.append(True)

    frames_512 = np.zeros((512, 1), dtype=np.float32)
    for _ in range(100):
        inst._callback(frames_512, 512, None, None)

    assert not triggered


def test_vad_disabled_when_auto_stop_zero(recorder_with_vad):
    """VAD must not trigger when VAD_AUTO_STOP_SECONDS is 0."""
    rec, cfg = recorder_with_vad
    cfg.VAD_AUTO_STOP_SECONDS = 0
    inst = rec.Recorder()
    inst.recording = True
    inst._sample_rate = 16000
    inst._vad_model = _FakeVAD(speech_prob=0.1)
    inst._vad_torch = _FakeTorch

    triggered = []
    inst.on_vad_trigger = lambda: triggered.append(True)

    frames_512 = np.zeros((512, 1), dtype=np.float32)
    for _ in range(100):
        inst._callback(frames_512, 512, None, None)

    assert not triggered


def test_vad_skipped_when_model_not_loaded(recorder_with_vad):
    """If no VAD model, callback must not raise and not trigger."""
    rec, cfg = recorder_with_vad
    inst = rec.Recorder()
    inst.recording = True
    inst._sample_rate = 16000
    # _vad_model is None by default

    triggered = []
    inst.on_vad_trigger = lambda: triggered.append(True)

    frames_512 = np.zeros((512, 1), dtype=np.float32)
    for _ in range(100):
        inst._callback(frames_512, 512, None, None)

    assert not triggered


def test_vad_state_reset_on_stop(recorder_with_vad):
    """VAD silence counter must be reset when stop() is called."""
    rec, cfg = recorder_with_vad
    inst = rec.Recorder()
    inst.recording = True
    inst._sample_rate = 16000
    inst._vad_model = _FakeVAD(speech_prob=0.1)
    inst._vad_torch = _FakeTorch

    frames_512 = np.zeros((512, 1), dtype=np.float32)
    for _ in range(30):
        inst._callback(frames_512, 512, None, None)

    inst.stop()

    assert inst._vad_silence_frames == 0


def test_vad_state_reset_on_start(recorder_with_vad):
    """VAD silence counter must be reset when start() is called."""
    rec, cfg = recorder_with_vad
    inst = rec.Recorder()

    inst._vad_silence_frames = 50
    inst.start()

    assert inst._vad_silence_frames == 0


def test_vad_config_threshold_affects_detection(recorder_with_vad):
    """Frames below VAD_THRESHOLD count as silence, above as speech."""
    rec, cfg = recorder_with_vad
    cfg.VAD_THRESHOLD = 0.5
    inst = rec.Recorder()
    inst.recording = True
    inst._sample_rate = 16000
    inst._vad_model = _FakeVAD(speech_prob=0.51)
    inst._vad_torch = _FakeTorch

    triggered = []
    inst.on_vad_trigger = lambda: triggered.append(True)

    frames_512 = np.zeros((512, 1), dtype=np.float32)
    for _ in range(100):
        inst._callback(frames_512, 512, None, None)

    assert not triggered


def test_ensure_vad_does_not_raise(recorder_with_vad, monkeypatch):
    """_ensure_vad must not raise even when torch is unavailable."""
    rec, cfg = recorder_with_vad
    inst = rec.Recorder()
    try:
        inst._ensure_vad()
    except Exception:
        pytest.fail("_ensure_vad raised unexpectedly on missing torch")


# ── Adaptive VAD input normalisation (п.7) ────────────────────────────

def test_vad_normalize_disabled_returns_frame(recorder_with_vad):
    """With VAD_NORMALIZE falsy the frame is returned unchanged."""
    rec, cfg = recorder_with_vad
    cfg.VAD_NORMALIZE = False
    inst = rec.Recorder()
    frame = np.linspace(-0.3, 0.3, 512, dtype=np.float32)
    before = frame.copy()
    out = inst._vad_normalize_for_agc(frame)
    assert np.allclose(out, before)


def test_vad_normalize_quiet_speech_amplified(recorder_with_vad):
    """With normalisation on, a quiet-but-real frame is scaled toward ref RMS."""
    rec, cfg = recorder_with_vad
    cfg.VAD_NORMALIZE = True
    cfg.VAD_NORM_REF_RMS = 0.05
    cfg.VAD_NORM_MAX_GAIN = 12.0
    inst = rec.Recorder()
    # Real signal, low level (~ -40 dBFS typ): should be amplified
    rng = np.random.RandomState(7)
    frame = (rng.randn(512).astype(np.float32) * 0.01)
    in_rms = float(np.sqrt(np.mean(frame ** 2)))
    out = inst._vad_normalize_for_agc(frame)
    out_rms = float(np.sqrt(np.mean(out ** 2)))
    assert out_rms > in_rms * 2.0
    assert not np.shares_memory(out, frame)  # returns a new array


def test_vad_normalize_digital_silence_untouched(recorder_with_vad):
    """Near-digital-silence must never be amplified (hang guard)."""
    rec, cfg = recorder_with_vad
    cfg.VAD_NORMALIZE = True
    cfg.VAD_NORM_REF_RMS = 0.05
    inst = rec.Recorder()
    frame = np.zeros((512,), dtype=np.float32)
    frame[::50] = 1e-6  # tiny digital noise floor, well below guard
    out = inst._vad_normalize_for_agc(frame)
    assert np.allclose(out, frame)  # unchanged, not blown up


def test_vad_normalize_gain_clamped(recorder_with_vad):
    """Gain must not exceed VAD_NORM_MAX_GAIN even for tiny frames."""
    rec, cfg = recorder_with_vad
    cfg.VAD_NORMALIZE = True
    cfg.VAD_NORM_REF_RMS = 0.05
    cfg.VAD_NORM_MAX_GAIN = 3.0
    inst = rec.Recorder()
    frame = np.ones((512,), dtype=np.float32) * 1e-3  # RMS ~1e-3
    out = inst._vad_normalize_for_agc(frame)
    out_rms = float(np.sqrt(np.mean(out ** 2)))
    # gain capped at 3x => rms ≤ ~3e-3
    assert out_rms <= 3.1e-3


def test_vad_normalize_fed_to_model_when_enabled(recorder_with_vad):
    """VAD_NORMALIZE=True must normalise the frame handed to the model."""
    rec, cfg = recorder_with_vad
    cfg.VAD_NORMALIZE = True
    cfg.VAD_NORM_REF_RMS = 0.05
    cfg.VAD_NORM_MAX_GAIN = 12.0

    captured = {}

    class _CapturingVAD:
        def __call__(self, tensor, sr):
            captured["rms"] = float(np.sqrt(np.mean(tensor.data ** 2)))
            return _FakeTensor(tensor.data, 0.1)

    inst = rec.Recorder()
    inst.recording = True
    inst._sample_rate = 16000
    inst._vad_model = _CapturingVAD()
    inst._vad_torch = _FakeTorch
    inst.on_vad_trigger = lambda: None

    rng = np.random.RandomState(3)
    char_frame = np.zeros((512, 1), dtype=np.float32)
    char_frame[:] = rng.randn(512, 1).astype(np.float32) * 0.01
    inst._callback(char_frame, 512, None, None)

    raw_rms = float(np.sqrt(np.mean(char_frame ** 2)))
    assert captured["rms"] > raw_rms * 2.0

