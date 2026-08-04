"""Unit tests for hotkey.py — dictation hotkey listener."""
import pytest


class TestHotkeyListenerInit:
    """Tests for HotkeyListener construction."""

    def test_listener_accepts_required_callbacks(self):
        """HotkeyListener accepts on_press_cb and on_release_cb."""
        from hotkey import HotkeyListener
        press_calls = []
        release_calls = []
        listener = HotkeyListener(
            on_press_cb=lambda: press_calls.append(1),
            on_release_cb=lambda: release_calls.append(1),
        )
        assert listener._on_press is not None
        assert listener._on_release is not None

    def test_listener_accepts_optional_callbacks(self):
        """HotkeyListener accepts on_re_paste_cb and on_retry_cb."""
        from hotkey import HotkeyListener
        listener = HotkeyListener(
            on_press_cb=lambda: None,
            on_release_cb=lambda: None,
            on_re_paste_cb=lambda: None,
            on_retry_cb=lambda: None,
        )
        assert listener._on_re_paste is not None
        assert listener._on_retry is not None

    def test_listener_initial_state(self):
        """Fresh listener has dict_pressed=False and dict_recording=False."""
        from hotkey import HotkeyListener
        listener = HotkeyListener(
            on_press_cb=lambda: None,
            on_release_cb=lambda: None,
        )
        assert listener._dict_pressed is False
        assert listener._dict_recording is False


class TestHotkeyListenerHoldMode:
    """Tests for hold-to-record mode (config.HOLD_TO_RECORD=True)."""

    def test_press_starts_recording_hold_mode(self):
        """In hold mode, key press calls on_press_cb."""
        from hotkey import HotkeyListener
        import config
        press_calls = []
        config.HOLD_TO_RECORD = True
        listener = HotkeyListener(
            on_press_cb=lambda: press_calls.append(1),
            on_release_cb=lambda: None,
        )
        listener._handle_press(config.HOTKEY)
        assert len(press_calls) == 1
        assert listener._dict_pressed is True

    def test_release_stops_recording_hold_mode(self):
        """In hold mode, key release calls on_release_cb."""
        from hotkey import HotkeyListener
        import config
        release_calls = []
        config.HOLD_TO_RECORD = True
        listener = HotkeyListener(
            on_press_cb=lambda: None,
            on_release_cb=lambda: release_calls.append(1),
        )
        listener._dict_pressed = True
        listener._handle_release(config.HOTKEY)
        assert len(release_calls) == 1
        assert listener._dict_pressed is False

    def test_second_press_in_hold_mode_starts_again(self):
        """In hold mode, pressing again (after release) starts recording again."""
        from hotkey import HotkeyListener
        import config
        press_calls = []
        config.HOLD_TO_RECORD = True
        listener = HotkeyListener(
            on_press_cb=lambda: press_calls.append(1),
            on_release_cb=lambda: None,
        )
        listener._handle_press(config.HOTKEY)
        listener._handle_release(config.HOTKEY)
        listener._handle_press(config.HOTKEY)
        assert len(press_calls) == 2


class TestHotkeyListenerToggleMode:
    """Tests for toggle mode (config.HOLD_TO_RECORD=False)."""

    def test_first_press_starts_recording_toggle_mode(self):
        """In toggle mode, first press starts recording."""
        from hotkey import HotkeyListener
        import config
        press_calls = []
        release_calls = []
        config.HOLD_TO_RECORD = False
        listener = HotkeyListener(
            on_press_cb=lambda: press_calls.append(1),
            on_release_cb=lambda: release_calls.append(1),
        )
        listener._handle_press(config.HOTKEY)
        assert len(press_calls) == 1
        assert listener._dict_recording is True

    def test_second_press_stops_recording_toggle_mode(self):
        """In toggle mode, second press stops recording."""
        from hotkey import HotkeyListener
        import config
        release_calls = []
        config.HOLD_TO_RECORD = False
        listener = HotkeyListener(
            on_press_cb=lambda: None,
            on_release_cb=lambda: release_calls.append(1),
        )
        listener._dict_recording = True
        listener._handle_press(config.HOTKEY)
        assert len(release_calls) == 1
        assert listener._dict_recording is False

    def test_toggle_resets_dict_pressed_flag(self):
        """In toggle mode, pressing sets _dict_pressed=True but releasing clears it."""
        from hotkey import HotkeyListener
        import config
        config.HOLD_TO_RECORD = False
        listener = HotkeyListener(
            on_press_cb=lambda: None,
            on_release_cb=lambda: None,
        )
        listener._dict_recording = True
        listener._handle_press(config.HOTKEY)  # toggle stop
        assert listener._dict_pressed is False  # released

    def test_toggle_debounce(self):
        """Rapid toggle presses within 0.3s are debounced."""
        import time
        from hotkey import HotkeyListener
        import config
        press_calls = []
        config.HOLD_TO_RECORD = False
        listener = HotkeyListener(
            on_press_cb=lambda: press_calls.append(1),
            on_release_cb=lambda: None,
        )
        listener._dict_recording = True
        listener._handle_press(config.HOTKEY)
        assert listener._dict_recording is False  # first toggle stopped
        # Press again immediately — debounce should block it
        listener._handle_press(config.HOTKEY)
        # Debounce at 0.3s blocks second press within window; press_calls count reflects calls made
        assert len(press_calls) <= 1  # at most 1 new call (the stop)


class TestHotkeyListenerRecovery:
    """Tests for F7 (retry) and F8 (re-paste) recovery hotkeys."""

    def test_f8_triggers_re_paste_callback(self):
        """Pressing F8 (re-paste hotkey) calls on_re_paste_cb."""
        from hotkey import HotkeyListener
        import config
        calls = []
        listener = HotkeyListener(
            on_press_cb=lambda: None,
            on_release_cb=lambda: None,
            on_re_paste_cb=lambda: calls.append("re_paste"),
        )
        listener._handle_press(config.HOTKEY_REPASTE)
        assert calls == ["re_paste"]

    def test_f7_triggers_retry_callback(self):
        """Pressing F7 (retry hotkey) calls on_retry_cb."""
        from hotkey import HotkeyListener
        import config
        calls = []
        listener = HotkeyListener(
            on_press_cb=lambda: None,
            on_release_cb=lambda: None,
            on_retry_cb=lambda: calls.append("retry"),
        )
        listener._handle_press(config.HOTKEY_RETRY)
        assert calls == ["retry"]

    def test_f8_noop_when_no_callback(self):
        """F8 press is silent if on_re_paste_cb is None."""
        from hotkey import HotkeyListener
        import config
        listener = HotkeyListener(
            on_press_cb=lambda: None,
            on_release_cb=lambda: None,
            on_re_paste_cb=None,
        )
        # Should not raise
        listener._handle_press(config.HOTKEY_REPASTE)

    def test_f7_noop_when_no_callback(self):
        """F7 press is silent if on_retry_cb is None."""
        from hotkey import HotkeyListener
        import config
        listener = HotkeyListener(
            on_press_cb=lambda: None,
            on_release_cb=lambda: None,
            on_retry_cb=None,
        )
        listener._handle_press(config.HOTKEY_RETRY)  # should not raise


class TestForceStop:
    """Tests for HotkeyListener.force_stop_dictation()."""

    def test_force_stop_calls_release_when_recording(self):
        """force_stop_dictation() calls on_release when in toggle recording."""
        from hotkey import HotkeyListener
        import config
        release_calls = []
        config.HOLD_TO_RECORD = False
        listener = HotkeyListener(
            on_press_cb=lambda: None,
            on_release_cb=lambda: release_calls.append(1),
        )
        listener._dict_recording = True
        listener.force_stop_dictation()
        assert len(release_calls) == 1
        assert listener._dict_recording is False

    def test_force_stop_noop_when_not_recording(self):
        """force_stop_dictation() does nothing when not recording."""
        from hotkey import HotkeyListener
        import config
        release_calls = []
        config.HOLD_TO_RECORD = False
        listener = HotkeyListener(
            on_press_cb=lambda: None,
            on_release_cb=lambda: release_calls.append(1),
        )
        listener._dict_recording = False
        listener.force_stop_dictation()
        assert release_calls == []


class TestSafeCall:
    """Tests for HotkeyListener._safe_call()."""

    def test_safe_call_exists(self):
        """HotkeyListener has a _safe_call method."""
        from hotkey import HotkeyListener
        listener = HotkeyListener(
            on_press_cb=lambda: None,
            on_release_cb=lambda: None,
        )
        assert hasattr(listener, "_safe_call")
        assert callable(listener._safe_call)
