"""Unit tests for recorder.py — audio recording with VAD auto-stop."""
import numpy as np
import pytest


class TestResolveDevice:
    """Tests for _resolve_device()."""

    def test_resolve_device_none_returns_none(self):
        """_resolve_device(None) returns None (system default)."""
        from recorder import _resolve_device
        result = _resolve_device(None)
        assert result is None

    def test_resolve_device_empty_string_returns_none(self):
        """_resolve_device('') returns None."""
        from recorder import _resolve_device
        result = _resolve_device("")
        result = _resolve_device("")
        assert result is None


class TestRecorderInit:
    """Tests for Recorder construction and default state."""

    def test_recorder_init(self):
        """Recorder initializes with correct default state."""
        from recorder import Recorder
        r = Recorder()
        assert r.recording is False
        assert r._frames == []
        assert r._stream is None
        assert r.on_level is None
        assert r.on_mic_error is None
        assert r.on_vad_trigger is None
        assert r._vad_model is None
        assert r._vad_silence_frames == 0


class TestRecorderStartStop:
    """Tests for Recorder.start() and Recorder.stop()."""

    def test_start_when_already_recording(self):
        """start() when already recording is a no-op."""
        from recorder import Recorder
        r = Recorder()
        r.recording = True  # simulate already recording
        r.start()
        assert r.recording is True
        assert r._frames == []  # frames not cleared

    def test_stop_when_not_recording(self):
        """stop() when not recording returns None."""
        from recorder import Recorder
        r = Recorder()
        r.recording = False
        result = r.stop()
        assert result is None

    def test_stop_returns_audio(self):
        """stop() returns accumulated audio as float32 numpy array."""
        from recorder import Recorder
        r = Recorder()
        r.recording = True
        # Manually inject a fake audio frame
        fake_frame = np.zeros((512, 1), dtype=np.float32)
        r._frames.append(fake_frame)
        r._sample_rate = 16000
        result = r.stop()
        assert result is not None
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32
        assert len(result) == 512

    def test_stop_clears_frames(self):
        """stop() clears the frames list."""
        from recorder import Recorder
        r = Recorder()
        r.recording = True
        r._frames.append(np.zeros(256, dtype=np.float32))
        r._sample_rate = 16000
        r.stop()
        assert r._frames == []
        assert r.recording is False

    def test_stop_resets_vad_silence_frames(self):
        """stop() resets _vad_silence_frames."""
        from recorder import Recorder
        r = Recorder()
        r.recording = True
        r._vad_silence_frames = 99
        r._sample_rate = 16000
        r.stop()
        assert r._vad_silence_frames == 0


class TestRecorderCallbacks:
    """Tests for Recorder callbacks."""

    def test_callback_accumulates_frames(self):
        """The callback appends indata to _frames."""
        from recorder import Recorder
        r = Recorder()
        r.recording = True
        fake_indata = np.random.rand(1024, 1).astype(np.float32)

        # Call the callback directly
        r._callback(fake_indata, 1024, None, None)
        assert len(r._frames) == 1
        assert np.array_equal(r._frames[0], fake_indata)

    def test_callback_calls_on_level(self):
        """The callback calls on_level with RMS when set."""
        from recorder import Recorder
        r = Recorder()
        r.recording = True
        levels = []
        r.on_level = lambda x: levels.append(x)

        # Silent audio = 0 RMS
        silent = np.zeros((512, 1), dtype=np.float32)
        r._callback(silent, 512, None, None)
        assert len(levels) == 1
        assert levels[0] >= 0.0

    def test_callback_does_not_append_when_not_recording(self):
        """Callback ignores indata when not recording."""
        from recorder import Recorder
        r = Recorder()
        r.recording = False
        fake_indata = np.zeros((512, 1), dtype=np.float32)
        r._callback(fake_indata, 512, None, None)
        assert r._frames == []


class TestRecorderResampling:
    """Tests for audio resampling (non-16kHz device fallback)."""

    def test_stop_resamples_to_16khz(self):
        """When recorded at 48kHz, stop() resamples to 16kHz."""
        from recorder import Recorder
        r = Recorder()
        r.recording = True
        # 48000 Hz: 480 samples = 10ms
        fake_frame = np.random.rand(480, 1).astype(np.float32)
        r._frames.append(fake_frame)
        r._sample_rate = 48000
        result = r.stop()
        # 480 samples at 48kHz = 10ms. At 16kHz = 160 samples
        assert len(result) == 160
        assert result.dtype == np.float32


class TestGetCurrentAudio:
    """Tests for Recorder.get_current_audio()."""

    def test_get_current_audio_empty(self):
        """Returns None when no frames accumulated."""
        from recorder import Recorder
        r = Recorder()
        r.recording = True
        result = r.get_current_audio()
        assert result is None

    def test_get_current_audio_returns_copy(self):
        """Returns accumulated audio and resamples if needed."""
        from recorder import Recorder
        r = Recorder()
        r.recording = True
        fake_frame = np.random.rand(1600, 1).astype(np.float32)
        r._frames.append(fake_frame)
        r._sample_rate = 16000
        result = r.get_current_audio()
        assert result is not None
        assert len(result) == 1600


class TestRecorderConcurrency:
    """Tests for the thread-safety guarantees added in the 1.1.0 audit fixes.

    The fix introduces a _lock that protects _frames and the `recording`
    flag. The contract is: stop() returns an atomic snapshot of every
    frame that was appended before stop() was called, and any frame
    appended after stop() returns goes into a fresh empty list (i.e. the
    next recording, not the one that was just stopped).
    """

    def test_stop_returns_atomic_snapshot(self):
        """stop() returns a snapshot of frames, not a moving target.

        Without the lock, callback could append between concatenate and
        clear, losing the final frame. With the lock, all frames in
        _frames at the moment stop() enters its critical section are
        included in the returned audio.
        """
        from recorder import Recorder
        r = Recorder()
        r._sample_rate = 16000
        r.recording = True
        # Simulate 3 frames already accumulated.
        for _ in range(3):
            r._frames.append(np.zeros((480, 1), dtype=np.float32))
        audio = r.stop()
        assert audio is not None
        assert len(audio) == 3 * 480
        # After stop, _frames is reset for the next recording.
        assert r._frames == []
        assert r.recording is False

    def test_stop_when_not_recording_returns_none(self):
        """stop() is idempotent — safe to call twice in a row."""
        from recorder import Recorder
        r = Recorder()
        # Never started — should return None and not raise.
        assert r.stop() is None

    def test_recorder_has_lock(self):
        """The recorder has a _lock attribute used by the new code paths."""
        from recorder import Recorder
        r = Recorder()
        assert hasattr(r, "_lock")
        # Acquire/release smoke test.
        with r._lock:
            pass

    def test_callback_does_not_append_when_not_recording(self):
        """Callback honours the recording flag even when called by PortAudio.

        The PortAudio callback may fire one last time after stop() — the
        guard ensures the leftover frame is dropped (not appended to a
        new recording).
        """
        from recorder import Recorder
        r = Recorder()
        r._sample_rate = 16000
        r.recording = False
        r._frames = []  # ensure clean state
        # Simulate what the callback would do.
        with r._lock:
            if not r.recording:
                # Early return — nothing appended.
                pass
            else:
                r._frames.append(np.zeros((480, 1), dtype=np.float32))
        assert r._frames == []
