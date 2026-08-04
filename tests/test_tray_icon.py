"""Tests for tray_icon.py — system tray icon."""
import types
import sys
import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# TrayIcon init
# ═══════════════════════════════════════════════════════════════════════════════

def test_tray_icon_init():
    from tray_icon import TrayIcon
    quit_fn = lambda: None
    t = TrayIcon(on_quit=quit_fn)
    assert t._on_quit is quit_fn
    assert t._on_show_settings is None
    assert t._icon is None


def test_tray_icon_init_with_settings():
    from tray_icon import TrayIcon
    quit_fn = lambda: None
    settings_fn = lambda: None
    t = TrayIcon(on_quit=quit_fn, on_show_settings=settings_fn)
    assert t._on_show_settings is settings_fn


# ═══════════════════════════════════════════════════════════════════════════════
# set_recording
# ═══════════════════════════════════════════════════════════════════════════════

def test_set_recording_noop_when_no_icon():
    from tray_icon import TrayIcon
    t = TrayIcon(on_quit=lambda: None)
    t.set_recording(True)  # Should not raise


def test_set_recording_updates_icon(monkeypatch):
    from tray_icon import TrayIcon
    import tray_icon

    t = TrayIcon(on_quit=lambda: None)
    fake_icon = types.SimpleNamespace(icon=None, title="")
    t._icon = fake_icon

    monkeypatch.setattr(tray_icon, "make_tray_icon",
                        lambda recording: f"icon_{recording}")
    monkeypatch.setattr(tray_icon, "locales", types.SimpleNamespace(
        get=lambda key: key
    ))

    t.set_recording(True)
    assert fake_icon.icon == "icon_True"
    assert fake_icon.title == "tray_recording"

    t.set_recording(False)
    assert fake_icon.icon == "icon_False"
    assert fake_icon.title == "tray_idle"


# ═══════════════════════════════════════════════════════════════════════════════
# set_tooltip
# ═══════════════════════════════════════════════════════════════════════════════

def test_set_tooltip_noop_when_no_icon():
    from tray_icon import TrayIcon
    t = TrayIcon(on_quit=lambda: None)
    t.set_tooltip("text")  # Should not raise


def test_set_tooltip_updates_title():
    from tray_icon import TrayIcon
    t = TrayIcon(on_quit=lambda: None)
    t._icon = types.SimpleNamespace(title="")
    t.set_tooltip("Warning!")
    assert t._icon.title == "Warning!"


# ═══════════════════════════════════════════════════════════════════════════════
# stop
# ═══════════════════════════════════════════════════════════════════════════════

def test_stop_noop_when_no_icon():
    from tray_icon import TrayIcon
    t = TrayIcon(on_quit=lambda: None)
    t.stop()  # Should not raise


def test_stop_calls_icon_stop():
    from tray_icon import TrayIcon
    t = TrayIcon(on_quit=lambda: None)
    stopped = []
    t._icon = types.SimpleNamespace(stop=lambda: stopped.append(True))
    t.stop()
    assert stopped


# ═══════════════════════════════════════════════════════════════════════════════
# _quit callback
# ═══════════════════════════════════════════════════════════════════════════════

def test_quit_callback_stops_icon_and_calls_on_quit():
    from tray_icon import TrayIcon
    quit_calls = []
    t = TrayIcon(on_quit=lambda: quit_calls.append(True))
    stopped = []
    fake_icon = types.SimpleNamespace(stop=lambda: stopped.append(True))
    t._quit(fake_icon, None)
    assert stopped
    assert quit_calls


# ═══════════════════════════════════════════════════════════════════════════════
# _show_settings callback
# ═══════════════════════════════════════════════════════════════════════════════

def test_show_settings_callback():
    from tray_icon import TrayIcon
    settings_calls = []
    t = TrayIcon(on_quit=lambda: None, on_show_settings=lambda: settings_calls.append(True))
    t._show_settings(None, None)
    assert settings_calls


def test_show_settings_noop_when_no_callback():
    from tray_icon import TrayIcon
    t = TrayIcon(on_quit=lambda: None, on_show_settings=None)
    t._show_settings(None, None)  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# _build_menu — pystray is imported locally, so we inject it into sys.modules
# ═══════════════════════════════════════════════════════════════════════════════

def _setup_pystray_mock(monkeypatch):
    """Inject a fake pystray module into sys.modules so local imports succeed."""
    items_captured = []

    class FakeMenu:
        SEPARATOR = "---SEP---"
        def __init__(self, *items):
            items_captured.extend(items)

    class FakeMenuItem:
        def __init__(self, text, callback, enabled=True):
            items_captured.append(text)

    fake_pystray = types.SimpleNamespace(
        Menu=FakeMenu,
        MenuItem=FakeMenuItem,
        MenuSeparator="---SEP---",
    )
    monkeypatch.setitem(sys.modules, "pystray", fake_pystray)
    return items_captured


def test_build_menu_with_settings(monkeypatch):
    import locales
    from tray_icon import TrayIcon

    items_captured = _setup_pystray_mock(monkeypatch)
    monkeypatch.setattr(locales, "get", lambda key: key)

    t = TrayIcon(on_quit=lambda: None, on_show_settings=lambda: None)
    t._build_menu()
    assert "tray_settings" in items_captured
    assert "tray_quit" in items_captured


def test_build_menu_without_settings(monkeypatch):
    import locales
    from tray_icon import TrayIcon

    items_captured = _setup_pystray_mock(monkeypatch)
    monkeypatch.setattr(locales, "get", lambda key: key)

    t = TrayIcon(on_quit=lambda: None, on_show_settings=None)
    t._build_menu()
    assert "tray_settings" not in items_captured
    assert "tray_quit" in items_captured


# ═══════════════════════════════════════════════════════════════════════════════
# start — pystray is imported locally
# ═══════════════════════════════════════════════════════════════════════════════

def test_start_creates_icon(monkeypatch):
    import locales
    from tray_icon import TrayIcon

    icons = []

    class FakeIcon:
        def __init__(self, name, img, tooltip, menu=None):
            icons.append(name)
            self.icon = img
            self.title = tooltip
        def run_detached(self):
            pass

    class FakeMenu:
        SEPARATOR = "---SEP---"
        def __init__(self, *items):
            pass

    fake_pystray = types.SimpleNamespace(
        Icon=FakeIcon,
        Menu=FakeMenu,
        MenuItem=lambda *a, **kw: None,
        MenuSeparator="---SEP---",
    )
    monkeypatch.setitem(sys.modules, "pystray", fake_pystray)
    monkeypatch.setattr(locales, "get", lambda key: key)

    import tray_icon as ti
    monkeypatch.setattr(ti, "make_tray_icon",
                        lambda recording=False: "fake_img")

    t = TrayIcon(on_quit=lambda: None)
    t.start()
    assert len(icons) == 1
    assert t._icon is not None
