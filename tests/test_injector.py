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
