"""Unit tests for injector.py — text injection into Windows applications."""
import pytest


class TestInject:
    """Tests for inject() — the main injection function."""

    def test_inject_accepts_hwnd_and_text(self):
        """inject() accepts (text, hwnd) and does not raise."""
        from injector import inject
        # Should not raise even with invalid hwnd
        inject("test", 0x1234)

    def test_inject_returns_value(self):
        """inject() returns None or True, not raises."""
        from injector import inject
        # inject(text, target_hwnd=None) — text is str, target_hwnd is int
        result = inject("test text", None)
        # Returns None on early exit (empty text) or True on success
        # Does not raise
        assert result is None or isinstance(result, bool)

    def test_inject_accepts_hwnd(self):
        """inject() accepts (text, target_hwnd) as positional args."""
        from injector import inject
        inject("test", 0x1234)  # should not raise


class TestClipboardOperations:
    """Tests for clipboard helper functions."""

    def test_set_clipboard_text_sets(self):
        """_set_clipboard_text sets clipboard content."""
        from injector import _set_clipboard_text, _get_clipboard_text
        _set_clipboard_text("hello")
        assert _get_clipboard_text() == "hello"

    def test_get_clipboard_text(self):
        """_get_clipboard_text returns clipboard content."""
        from injector import _get_clipboard_text
        result = _get_clipboard_text()
        assert isinstance(result, str)

    def test_open_clipboard(self):
        """_open_clipboard returns True on success."""
        from injector import _open_clipboard
        result = _open_clipboard()
        assert isinstance(result, bool)

    def test_open_clipboard_standalone(self):
        """_open_clipboard works as a standalone call."""
        from injector import _open_clipboard
        _open_clipboard()  # should not raise


class TestClearClipboard:
    """Tests for _clear_clipboard() — fallback, called only when clipboard
    restore fails. It empties the buffer so a stray manual Ctrl+V in
    another window won't re-paste the dictated text."""

    def test_clear_clipboard_empties_text(self):
        """After _set_clipboard_text('x') + _clear_clipboard(), clipboard is empty."""
        from injector import _set_clipboard_text, _clear_clipboard, _get_clipboard_text
        _set_clipboard_text("hello world")
        assert _get_clipboard_text() == "hello world"
        result = _clear_clipboard()
        assert result is True
        assert _get_clipboard_text() == ""

    def test_clear_clipboard_returns_bool(self):
        """_clear_clipboard returns a bool."""
        from injector import _clear_clipboard
        result = _clear_clipboard()
        assert isinstance(result, bool)

    def test_clear_clipboard_idempotent(self):
        """Clearing an already-empty clipboard is fine."""
        from injector import _clear_clipboard
        _clear_clipboard()
        # second call should still succeed (empty stays empty)
        result = _clear_clipboard()
        assert result is True


class TestCtrlV:
    """Tests for _send_ctrl_v()."""

    def test_send_ctrl_v_accepts_hwnd(self):
        """_send_ctrl_v() accepts hwnd and does not raise."""
        from injector import _send_ctrl_v
        _send_ctrl_v(0x1234)  # should not raise

    def test_send_ctrl_v_with_none(self):
        """_send_ctrl_v(None) uses GetForegroundWindow."""
        from injector import _send_ctrl_v
        _send_ctrl_v(None)  # should not raise


class TestRecovery:
    """Tests for recovery mechanism (_save_recovery)."""

    def test_recovery_path_constant(self):
        """RECOVERY_PATH is defined and non-empty."""
        from injector import RECOVERY_PATH
        assert isinstance(RECOVERY_PATH, str)
        assert len(RECOVERY_PATH) > 0


class TestConstants:
    """Tests for module-level constants."""

    def test_vk_v(self):
        """VK_V is the V key virtual key code."""
        from injector import VK_V
        assert isinstance(VK_V, int)

    def test_vk_control(self):
        """VK_CONTROL is the Ctrl virtual key code."""
        from injector import VK_CONTROL
        assert isinstance(VK_CONTROL, int)

    def test_keyscan_constants(self):
        """Scan code constants are defined."""
        from injector import SCAN_V, SCAN_CTRL
        assert isinstance(SCAN_V, int)
        assert isinstance(SCAN_CTRL, int)

    def test_clipboard_format(self):
        """CF_UNICODETEXT is the Windows clipboard format for unicode text."""
        from injector import CF_UNICODETEXT
        assert isinstance(CF_UNICODETEXT, int)
        assert CF_UNICODETEXT == 13  # standard Windows value

    def test_max_retries(self):
        """_MAX_RETRIES is a positive integer."""
        from injector import _MAX_RETRIES
        assert isinstance(_MAX_RETRIES, int)
        assert _MAX_RETRIES > 0

    def test_retry_delay(self):
        """_RETRY_DELAY is a positive number."""
        from injector import _RETRY_DELAY
        assert isinstance(_RETRY_DELAY, (int, float))
        assert _RETRY_DELAY > 0


class TestKeybdEventTiming:
    """Tests for Ctrl+V keybd_event timing — fast machines need gaps
    between down/up so the OS doesn't collapse the chord. Without
    the gaps, the target app sees only Ctrl-down/Ctrl-up and never
    receives the V (the 'в буфер не попадает' symptom)."""

    def test_keybd_event_calls_have_gaps(self, monkeypatch):
        """_send_ctrl_v() interleaves sleeps between keybd_event calls."""
        from injector import _user32
        events = []

        def fake_keybd(bVk, bScan, flags, extra):
            events.append((bVk, bScan, flags, extra))

        sleeps = []

        def fake_sleep(s):
            sleeps.append(s)

        monkeypatch.setattr(_user32, "keybd_event", fake_keybd)
        # Patch time.sleep in the injector module's namespace.
        import injector
        monkeypatch.setattr(injector.time, "sleep", fake_sleep)

        injector._send_ctrl_v(None)

        # We expect at least 3 sleeps between the 4 keybd_event calls.
        assert len(events) == 4, f"expected 4 keybd_event calls, got {len(events)}"
        # Scan codes for Ctrl and V are sent down then up.
        # Each call should be the right keystroke; combined flags include
        # KEYEVENTF_SCANCODE; the V-up and Ctrl-up calls also set KEYUP.
        for bVk, bScan, flags, _extra in events:
            assert bVk == 0, "bVk must be 0 when KEYEVENTF_SCANCODE is set"
            assert flags & 0x0008, "KEYEVENTF_SCANCODE must be set"  # 0x0008
        # At least 3 sleeps occurred between the 4 events.
        assert len(sleeps) >= 3, f"expected ≥3 sleeps between 4 events, got {len(sleeps)}"
        # Each inter-event sleep should be non-trivial (>0).
        for s in sleeps:
            assert s > 0, f"sleep between keybd events must be >0, got {s}"


class TestInjectPostPasteDelay:
    """Tests for the post-Ctrl+V sleep before restoring the clipboard.
    Too short → heavy editors (Word, big contenteditable, Electron)
    haven't read the clipboard yet → we restore the user's old content
    and the dictated text's paste silently drops. Recovery file has the
    text either way, but the user's screen never receives it."""

    def test_inject_sleeps_before_restore(self, monkeypatch):
        """inject() must sleep ≥ 0.8s between Ctrl+V and clipboard restore."""
        import injector
        from injector import _set_clipboard_text, _clear_clipboard, _get_clipboard_text

        # Real clipboard helpers: set the dictation text, empty by default so
        # original_clipboard is "" → inject() calls _clear_clipboard() at the end.
        monkeypatch.setattr(injector, "_send_ctrl_v", lambda _hwnd: None)
        # Make _get_clipboard_text return "" (no original content) so the
        # inject() path ends with the clear branch.
        monkeypatch.setattr(injector, "_get_clipboard_text", lambda: "")

        # Track the sleeps that happen inside inject().
        sleeps = []
        original_sleep = injector.time.sleep

        def fake_sleep(s):
            sleeps.append(s)
            # Do not actually sleep — keep the test fast.
        monkeypatch.setattr(injector.time, "sleep", fake_sleep)

        injector.inject("hello world", 0x1234)

        # We need at least one sleep ≥ 0.8s after the Ctrl+V simulation
        # but before the clipboard is cleared/restored.
        max_sleep = max(sleeps) if sleeps else 0
        assert max_sleep >= 0.8, (
            f"inject() must sleep ≥0.8s before touching clipboard again, "
            f"max observed sleep = {max_sleep}"
        )

    def test_inject_restores_original_clipboard(self, monkeypatch):
        """inject() must restore the user's original clipboard content after paste."""
        import injector

        restored = []

        def fake_set(text):
            restored.append(text)
            return True

        def fake_get():
            return "пользовательский текст"

        monkeypatch.setattr(injector, "_send_ctrl_v", lambda _hwnd: None)
        monkeypatch.setattr(injector, "_get_clipboard_text", fake_get)
        monkeypatch.setattr(injector, "_set_clipboard_text", fake_set)
        monkeypatch.setattr(injector.time, "sleep", lambda s: None)

        injector.inject("диктуемый текст", 0x1234)

        # The original clipboard content must be restored at the end (last set).
        assert restored[-1] == "пользовательский текст"

    def test_inject_clears_when_no_original(self, monkeypatch):
        """inject() clears the clipboard when there was no original text."""
        import injector
        from injector import _clear_clipboard

        cleared = []
        monkeypatch.setattr(injector, "_send_ctrl_v", lambda _hwnd: None)
        monkeypatch.setattr(injector, "_get_clipboard_text", lambda: "")
        monkeypatch.setattr(injector, "_set_clipboard_text", lambda _t: True)
        monkeypatch.setattr(injector, "_clear_clipboard", lambda: cleared.append(True) or True)
        monkeypatch.setattr(injector.time, "sleep", lambda s: None)

        injector.inject("диктуемый текст", 0x1234)

        assert len(cleared) == 1
