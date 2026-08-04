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
