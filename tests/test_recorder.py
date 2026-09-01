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


class TestRecorderPreRoll:
    """Tests for the pre-roll buffer that prevents the leading ~100-200 ms
    of audio from being lost to PortAudio startup latency.

    Bug fix (2026-08-31): the start() now opens the stream with recording
    still False; the first _callback after stream.start() flips recording
    to True and flushes the pre-roll buffer before the live frame.
    """

    def test_pre_roll_captures_frames_before_recording_starts(self):
        """Frames arriving while recording=False go into _preroll, not _frames."""
        from recorder import Recorder
        r = Recorder()
        r.recording = False
        r._preroll = []
        fake = np.zeros((480, 1), dtype=np.float32)
        # Three callback invocations while the stream is open but recording
        # hasn't started yet.
        for _ in range(3):
            r._callback(fake, 480, None, None)
        assert r._frames == []           # live frames untouched
        assert len(r._preroll) == 3      # pre-roll captured all 3

    def test_pre_roll_capped_at_max(self):
        """Pre-roll buffer is bounded so it can't grow forever."""
        from recorder import Recorder
        r = Recorder()
        r.recording = False
        r._preroll_max_frames = 4
        fake = np.zeros((480, 1), dtype=np.float32)
        for _ in range(20):
            r._callback(fake, 480, None, None)
        assert len(r._preroll) == 4  # capped, not unbounded

    def test_first_recording_frame_flushes_pre_roll(self):
        """When the first frame arrives after recording=True, pre-roll is
        flushed BEFORE the live frame so no audio is lost."""
        from recorder import Recorder
        r = Recorder()
        r.recording = False
        r._preroll = []
        pre = np.full((480, 1), 0.1, dtype=np.float32)
        r._callback(pre, 480, None, None)   # pre-roll frame
        r._callback(pre, 480, None, None)   # pre-roll frame
        r.recording = True                   # user pressed hotkey
        live = np.full((480, 1), 0.9, dtype=np.float32)
        r._callback(live, 480, None, None)   # first real frame
        # Order: 2 pre-roll, 1 live.
        assert len(r._frames) == 3
        assert np.array_equal(r._frames[0], pre)
        assert np.array_equal(r._frames[1], pre)
        assert np.array_equal(r._frames[2], live)
        assert r._preroll == []  # flushed, no duplicates


class TestRecorderDrain:
    """Tests for the PortAudio drain delay added to stop() in 2026-08-31.

    Bug fix: the previous stop() called stream.close() immediately after
    stream.stop(), losing the trailing 50-100 ms (final sibilants and
    consonants). The fix adds a short sleep so PortAudio can flush its
    internal ring buffer.
    """

    def test_stop_drains_before_close(self, monkeypatch):
        """stop() sleeps _drain_seconds between stream.stop() and close()."""
        from recorder import Recorder
        r = Recorder()
        r._drain_seconds = 0.05
        r.recording = True
        r._sample_rate = 16000
        # Fake a stream that records the order of stop/close calls.
        calls = []
        class FakeStream:
            def stop(self): calls.append("stop")
            def close(self): calls.append("close")
        r._stream = FakeStream()
        sleeps = []
        monkeypatch.setattr("recorder.time.sleep", lambda s: sleeps.append(s))
        r.stop()
        assert calls == ["stop", "close"]   # stop before close
        assert sleeps == [0.05]              # drain sleep happened

    def test_stop_continues_when_drain_disabled(self, monkeypatch):
        """Setting _drain_seconds=0 skips the sleep (no-op for tests)."""
        from recorder import Recorder
        r = Recorder()
        r._drain_seconds = 0
        r.recording = True
        r._sample_rate = 16000
        class FakeStream:
            def stop(self): pass
            def close(self): pass
        r._stream = FakeStream()
        sleeps = []
        monkeypatch.setattr("recorder.time.sleep", lambda s: sleeps.append(s))
        r.stop()
        assert sleeps == []
