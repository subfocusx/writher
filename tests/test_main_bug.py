"""Unit tests for main.py — core pipeline logic.

Tests cover: HWND ordering bug, timeout, VAD callback, hotkey release,
audio recovery, retry/re-paste, settings loading, and shutdown.
"""
import threading
import types
import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# HWND ordering (core regression bug)
# ═══════════════════════════════════════════════════════════════════════════════

def test_hwnd_saved_BEFORE_recorder_start_in_dictation_press(main_module):
    """HWND must be saved BEFORE recorder.start(), not after.

    The bug: GetForegroundWindow was called AFTER recorder.start(),
    so focus had already shifted to the recording widget.
    """
    m, calls, rec = main_module
    m._on_hotkey_press()
    start_idx = calls.index("recorder.start")
    hwnd_idx = calls.index("GetForegroundWindow")
    assert hwnd_idx < start_idx, (
        f"HWND captured AFTER recorder.start(). "
        f"HWND at {hwnd_idx}, recorder.start at {start_idx}"
    )


def test_hwnd_not_captured_on_release(main_module):
    """HWND is NOT re-captured on hotkey release (only on press)."""
    m, calls, rec = main_module
    calls.clear()
    m._on_hotkey_release()
    assert "GetForegroundWindow" not in calls


# ═══════════════════════════════════════════════════════════════════════════════
# Timeout (start / cancel)
# ═══════════════════════════════════════════════════════════════════════════════

def test_start_timeout_skips_when_HOLD_TO_RECORD(main_module, monkeypatch):
    """_start_timeout() returns early when HOLD_TO_RECORD is True."""
    m, calls, rec = main_module
    monkeypatch.setattr(m.config, "HOLD_TO_RECORD", True)
    timer_before = m._timeout_timer
    m._start_timeout()
    # Timer must not be created
    assert m._timeout_timer is timer_before


def test_start_timeout_creates_timer(main_module, monkeypatch):
    """_start_timeout() creates a threading.Timer when HOLD_TO_RECORD is False."""
    m, calls, rec = main_module
    monkeypatch.setattr(m.config, "HOLD_TO_RECORD", False)
    monkeypatch.setattr(m.config, "MAX_RECORD_SECONDS", 30)
    m._start_timeout()
    assert m._timeout_timer is not None
    assert isinstance(m._timeout_timer, threading.Timer)


def test_cancel_timeout_cancels_active_timer(main_module, monkeypatch):
    """_cancel_timeout() calls cancel() on the stored timer."""
    m, calls, rec = main_module
    cancelled = []
    fake_timer = type("T", (), {"cancel": lambda s: cancelled.append(True)})()
    m._timeout_timer = fake_timer
    m._cancel_timeout()
    assert cancelled


def test_cancel_timeout_idempotent_when_none(main_module, monkeypatch):
    """_cancel_timeout() does nothing when _timeout_timer is None."""
    m, calls, rec = main_module
    m._timeout_timer = None
    # Should not raise
    m._cancel_timeout()


# ═══════════════════════════════════════════════════════════════════════════════
# Timeout callback (_on_timeout)
# ═══════════════════════════════════════════════════════════════════════════════

def test_on_timeout_calls_force_stop_dictation(main_module, monkeypatch):
    """_on_timeout() calls hotkey_listener.force_stop_dictation()."""
    m, calls, rec = main_module
    calls.clear()
    m.hotkey_listener = types.SimpleNamespace(
        force_stop_dictation=lambda: calls.append("force_stop"))
    m._on_timeout()
    assert "force_stop" in calls


def test_on_timeout_clears_timer_reference(main_module, monkeypatch):
    """_on_timeout() resets _timeout_timer to None."""
    m, calls, rec = main_module
    fake_timer = type("T", (), {"cancel": lambda s: None})()
    m._timeout_timer = fake_timer
    m._on_timeout()
    assert m._timeout_timer is None


# ═══════════════════════════════════════════════════════════════════════════════
# VAD stop callback (_on_vad_stop)
# ═══════════════════════════════════════════════════════════════════════════════

def test_on_vad_stop_calls_force_stop_dictation(main_module):
    """_on_vad_stop() calls hotkey_listener.force_stop_dictation()."""
    m, calls, rec = main_module
    calls.clear()
    m.hotkey_listener = types.SimpleNamespace(
        force_stop_dictation=lambda: calls.append("force_stop"))
    m._on_vad_stop()
    assert "force_stop" in calls


# ═══════════════════════════════════════════════════════════════════════════════
# Hotkey release (_on_hotkey_release)
# ═══════════════════════════════════════════════════════════════════════════════

def test_on_hotkey_release_cancels_timeout(main_module, monkeypatch):
    """_on_hotkey_release() cancels any active timeout timer."""
    m, calls, rec = main_module
    cancelled = []
    m._timeout_timer = type("T", (), {"cancel": lambda s: cancelled.append(True)})()
    m._on_hotkey_release()
    assert cancelled


def test_on_hotkey_release_stops_recorder_and_puts_audio_in_queue(main_module, monkeypatch):
    """_on_hotkey_release() calls recorder.stop() and puts audio in _pipeline_queue."""
    m, calls, rec = main_module
    calls.clear()
    q_items = []
    monkeypatch.setattr(m, "_pipeline_queue",
        types.SimpleNamespace(put=lambda x: q_items.append(x)))
    # Simulate audio in recorder
    rec._audio = "fake_audio_data"
    m._on_hotkey_release()
    assert "recorder.stop" in calls
    assert len(q_items) == 1


def test_on_hotkey_release_skips_short_audio(main_module, monkeypatch):
    """_on_hotkey_release() skips audio shorter than _MIN_DURATION."""
    m, calls, rec = main_module
    calls.clear()
    q_items = []
    monkeypatch.setattr(m, "_pipeline_queue",
        types.SimpleNamespace(put=lambda x: q_items.append(x)))
    # Audio is None (simulating short/no audio)
    rec._audio = None
    m._on_hotkey_release()
    assert "recorder.stop" in calls
    # Nothing put in queue when audio is None
    assert len(q_items) == 0


def test_on_hotkey_release_sets_tray_not_recording(main_module, monkeypatch):
    """_on_hotkey_release() calls tray.set_recording(False)."""
    m, calls, rec = main_module
    calls.clear()
    rec._audio = "fake"
    monkeypatch.setattr(m, "_pipeline_queue",
        types.SimpleNamespace(put=lambda x: None))
    m._on_hotkey_release()
    assert "tray.set_recording(False)" in calls


# ═══════════════════════════════════════════════════════════════════════════════
# Audio error recovery (_save_audio_error_recovery)
# ═══════════════════════════════════════════════════════════════════════════════

def test_save_audio_error_recovery_calls_soundfile_write(main_module, monkeypatch):
    """_save_audio_error_recovery() calls soundfile.write with audio data."""
    m, calls, rec = main_module
    written = []

    import soundfile as real_sf
    monkeypatch.setattr(real_sf, "write",
        lambda *a, **kw: written.append((a, kw)))

    audio = types.SimpleNamespace(
        sample_rate=16000,
        samples=types.SimpleNamespace(shape=(48000,)))
    result = m._save_audio_error_recovery(audio)
    assert len(written) == 1


def test_save_audio_error_recovery_returns_audio_path(main_module, monkeypatch):
    """_save_audio_error_recovery() returns the path to the saved file."""
    m, calls, rec = main_module
    import soundfile as real_sf
    monkeypatch.setattr(real_sf, "write", lambda *a, **kw: None)
    audio = types.SimpleNamespace(
        sample_rate=16000,
        samples=types.SimpleNamespace(shape=(48000,)))
    result = m._save_audio_error_recovery(audio)
    assert result is not None
    assert isinstance(result, str)


def test_save_audio_error_recovery_returns_none_on_failure(main_module, monkeypatch):
    """_save_audio_error_recovery() returns None when soundfile.write fails."""
    m, calls, rec = main_module
    import soundfile as real_sf
    monkeypatch.setattr(real_sf, "write",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")))
    audio = types.SimpleNamespace(
        sample_rate=16000,
        samples=types.SimpleNamespace(shape=(48000,)))
    result = m._save_audio_error_recovery(audio)
    assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# Retry / re-paste
# ═══════════════════════════════════════════════════════════════════════════════

def test_on_re_paste_calls_inject_with_last_text(main_module, monkeypatch):
    """_on_re_paste() calls inject with the last transcribed text and target HWND."""
    m, calls, rec = main_module
    calls.clear()

    injected = []
    # Patch m.injector.inject directly (not via sys.modules — main.py imported
    # injector as a module ref, so we must patch the same reference)
    def mock_inject(text, target_hwnd=None):
        injected.append((text, target_hwnd))
    m.injector.inject = mock_inject

    # Set global state that _on_re_paste reads
    m._last_transcribed_text = "последний текст"
    m._dict_hwnd = 0xDEADBEEF

    m._on_re_paste()

    assert len(injected) == 1
    text, hwnd = injected[0]
    assert text == "последний текст"
    assert hwnd == 0xDEADBEEF


def test_on_re_paste_does_nothing_when_no_text(main_module, monkeypatch):
    """_on_re_paste() does nothing if _last_transcribed_text is empty."""
    m, calls, rec = main_module
    calls.clear()
    injected = []
    def mock_inject(text, target_hwnd=None):
        injected.append((text, target_hwnd))
    m.injector.inject = mock_inject
    m._last_transcribed_text = ""
    m._on_re_paste()
    assert len(injected) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Settings loading (_load_settings)
# ═══════════════════════════════════════════════════════════════════════════════

def test_load_settings_reads_vad_auto_stop_seconds(main_module, monkeypatch):
    """_load_settings() sets config.VAD_AUTO_STOP_SECONDS from DB key vad_auto_stop_seconds."""
    m, calls, rec = main_module
    db_values = {"vad_auto_stop_seconds": "5.0"}
    monkeypatch.setattr(m.db, "get_setting",
        lambda k, d="": db_values.get(k, d))
    monkeypatch.setattr(m.config, "VAD_AUTO_STOP_SECONDS", None)
    m._load_settings()
    assert m.config.VAD_AUTO_STOP_SECONDS == 5.0


def test_load_settings_reads_max_record_seconds(main_module, monkeypatch):
    """_load_settings() sets config.MAX_RECORD_SECONDS from DB."""
    m, calls, rec = main_module
    db_values = {"max_record_seconds": "60"}
    monkeypatch.setattr(m.db, "get_setting",
        lambda k, d="": db_values.get(k, d))
    monkeypatch.setattr(m.config, "MAX_RECORD_SECONDS", None)
    m._load_settings()
    assert m.config.MAX_RECORD_SECONDS == 60


def test_load_settings_reads_hold_to_record(main_module, monkeypatch):
    """_load_settings() sets config.HOLD_TO_RECORD from DB (key=hold_to_record)."""
    m, calls, rec = main_module
    db_values = {"hold_to_record": "1"}
    monkeypatch.setattr(m.db, "get_setting",
        lambda k, d="": db_values.get(k, d))
    monkeypatch.setattr(m.config, "HOLD_TO_RECORD", None)
    m._load_settings()
    assert m.config.HOLD_TO_RECORD is True


def test_load_settings_reads_hold_to_record_false(main_module, monkeypatch):
    """_load_settings() sets config.HOLD_TO_RECORD to False when DB has "0"."""
    m, calls, rec = main_module
    db_values = {"hold_to_record": "0"}
    monkeypatch.setattr(m.db, "get_setting",
        lambda k, d="": db_values.get(k, d))
    monkeypatch.setattr(m.config, "HOLD_TO_RECORD", None)
    m._load_settings()
    assert m.config.HOLD_TO_RECORD is False


def test_load_settings_ignores_invalid_max_seconds(main_module, monkeypatch):
    """_load_settings() ignores non-numeric max_record_seconds."""
    m, calls, rec = main_module
    db_values = {"max_record_seconds": "not_a_number"}
    monkeypatch.setattr(m.db, "get_setting",
        lambda k, d="": db_values.get(k, d))
    monkeypatch.setattr(m.config, "MAX_RECORD_SECONDS", 120)
    m._load_settings()
    assert m.config.MAX_RECORD_SECONDS == 120


def test_load_settings_reads_autostart(main_module, monkeypatch):
    """_load_settings() sets config.AUTOSTART and calls autostart.set_autostart."""
    m, calls, rec = main_module
    db_values = {"autostart": "1"}
    monkeypatch.setattr(m.db, "get_setting",
        lambda k, d="": db_values.get(k, d))
    monkeypatch.setattr(m.config, "AUTOSTART", None)

    import autostart as autostart_mod
    setup_calls = []
    monkeypatch.setattr(autostart_mod, "set_autostart",
        lambda enable: setup_calls.append(enable))

    m._load_settings()
    assert m.config.AUTOSTART is True
    assert setup_calls == [True]


def test_load_settings_reads_autostart_disabled(main_module, monkeypatch):
    """_load_settings() sets config.AUTOSTART=False when DB has "0"."""
    m, calls, rec = main_module
    db_values = {"autostart": "0"}
    monkeypatch.setattr(m.db, "get_setting",
        lambda k, d="": db_values.get(k, d))
    monkeypatch.setattr(m.config, "AUTOSTART", None)

    import autostart as autostart_mod
    setup_calls = []
    monkeypatch.setattr(autostart_mod, "set_autostart",
        lambda enable: setup_calls.append(enable))

    m._load_settings()
    assert m.config.AUTOSTART is False
    assert setup_calls == [False]


# ═══════════════════════════════════════════════════════════════════════════════
# Settings window (_show_settings)
# ═══════════════════════════════════════════════════════════════════════════════

def test_show_settings_opens_settings_window(main_module, monkeypatch):
    """_show_settings() calls settings_win.show() via root.after."""
    m, calls, rec = main_module
    calls.clear()
    shown = []
    m.settings_win = types.SimpleNamespace(
        show=lambda: shown.append(True))
    m.root = types.SimpleNamespace(
        after=lambda ms, fn: fn())
    m._show_settings()
    assert len(shown) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Quit / shutdown
# ═══════════════════════════════════════════════════════════════════════════════

def test_quit_puts_stop_sentinel_in_queue(main_module, monkeypatch):
    """_quit() puts _STOP sentinel in _pipeline_queue to terminate the worker."""
    m, calls, rec = main_module
    q_items = []
    monkeypatch.setattr(m, "_pipeline_queue",
        types.SimpleNamespace(put=lambda x: q_items.append(x)))
    m._quit()
    assert any(item is m._STOP for item in q_items), \
        f"_STOP sentinel not found in queue items: {q_items}"


def test_quit_cancels_timeout(main_module, monkeypatch):
    """_quit() cancels any active timeout timer."""
    m, calls, rec = main_module
    cancelled = []
    m._timeout_timer = type("T", (), {"cancel": lambda s: cancelled.append(True)})()
    monkeypatch.setattr(m, "_pipeline_queue",
        types.SimpleNamespace(put=lambda x: None))
    m._quit()
    assert len(cancelled) == 1


def test_quit_stops_scheduler(main_module, monkeypatch):
    """_quit() calls scheduler.stop() if scheduler exists."""
    m, calls, rec = main_module
    calls.clear()
    m.scheduler = types.SimpleNamespace(stop=lambda: calls.append("scheduler.stop"))
    monkeypatch.setattr(m, "_pipeline_queue",
        types.SimpleNamespace(put=lambda x: None))
    m._quit()
    assert "scheduler.stop" in calls


def test_quit_stops_hotkey_listener(main_module, monkeypatch):
    """_quit() calls hotkey_listener.stop() if listener exists."""
    m, calls, rec = main_module
    calls.clear()
    m.hotkey_listener = types.SimpleNamespace(stop=lambda: calls.append("hotkey.stop"))
    monkeypatch.setattr(m, "_pipeline_queue",
        types.SimpleNamespace(put=lambda x: None))
    m._quit()
    assert "hotkey.stop" in calls


def test_quit_stops_tray(main_module, monkeypatch):
    """_quit() calls tray.stop() if tray exists."""
    m, calls, rec = main_module
    calls.clear()
    m.tray = types.SimpleNamespace(stop=lambda: calls.append("tray.stop"))
    monkeypatch.setattr(m, "_pipeline_queue",
        types.SimpleNamespace(put=lambda x: None))
    m._quit()
    assert "tray.stop" in calls


def test_quit_stops_recorder(main_module, monkeypatch):
    """_quit() calls recorder.stop() if recorder exists."""
    m, calls, rec = main_module
    calls.clear()
    monkeypatch.setattr(m, "_pipeline_queue",
        types.SimpleNamespace(put=lambda x: None))
    m._quit()
    assert "recorder.stop" in calls


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level constants
# ═══════════════════════════════════════════════════════════════════════════════

def test_retry_debounce_constant(main_module):
    """_RETRY_DEBOUNCE is defined and positive."""
    m, calls, rec = main_module
    assert hasattr(m, "_RETRY_DEBOUNCE")
    assert m._RETRY_DEBOUNCE == 1.0


def test_min_duration_constant(main_module):
    """_MIN_DURATION is defined and non-negative."""
    m, calls, rec = main_module
    assert hasattr(m, "_MIN_DURATION")
    assert m._MIN_DURATION >= 0


def test_retry_debounce_is_float(main_module):
    """_RETRY_DEBOUNCE is a float for precise time comparison."""
    m, calls, rec = main_module
    assert isinstance(m._RETRY_DEBOUNCE, float)


def test_stop_sentinel_is_unique_object(main_module):
    """_STOP is a unique sentinel object (not a string or None)."""
    m, calls, rec = main_module
    assert m._STOP is not None
    assert m._STOP is not False
    assert m._STOP is m._STOP
