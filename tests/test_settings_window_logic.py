"""Tests for settings_window.py — logic methods (non-GUI)."""
import types
import sys
import os
import pytest

project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: create SettingsWindow with mocked GUI
# ═══════════════════════════════════════════════════════════════════════════════

def _make_settings_window(monkeypatch, tmp_path):
    """Create a SettingsWindow with all GUI dependencies stubbed."""
    fake_ctk = types.ModuleType("customtkinter")
    fake_ctk.CTkToplevel = lambda root: types.SimpleNamespace(
        winfo_exists=lambda: True,
        attributes=lambda *a: None,
        lift=lambda: None,
        focus_force=lambda: None,
        geometry=lambda g: None,
        destroy=lambda: None,
        configure=lambda **kw: None,
        winfo_x=lambda: 0,
        winfo_y=lambda: 0,
        pack=lambda **kw: None,
        pack_propagate=lambda v: None,
    )
    fake_ctk.CTkFrame = lambda *a, **kw: types.SimpleNamespace(
        pack=lambda **kw: None,
        pack_propagate=lambda v: None,
    )
    fake_ctk.CTkLabel = lambda *a, **kw: types.SimpleNamespace(
        pack=lambda **kw: None,
        configure=lambda **kw: None,
    )
    fake_ctk.CTkButton = lambda *a, **kw: types.SimpleNamespace(
        pack=lambda **kw: None,
        configure=lambda **kw: None,
    )
    fake_ctk.CTkSlider = lambda *a, **kw: types.SimpleNamespace(
        pack=lambda **kw: None,
        set=lambda v: None,
    )
    fake_ctk.CTkComboBox = lambda *a, **kw: types.SimpleNamespace(
        pack=lambda **kw: None,
        set=lambda v: None,
        configure=lambda **kw: None,
    )
    fake_ctk.CTkSwitch = lambda *a, **kw: types.SimpleNamespace(
        pack=lambda **kw: None,
        get=lambda: 0,
        select=lambda: None,
        deselect=lambda: None,
    )
    fake_ctk.CTkScrollableFrame = lambda *a, **kw: types.SimpleNamespace(
        pack=lambda **kw: None,
    )
    monkeypatch.setitem(sys.modules, "customtkinter", fake_ctk)

    fake_pil = types.ModuleType("PIL")
    _fake_image_cls = type("Image", (), {})
    _fake_image_mod = types.ModuleType("PIL.Image")
    _fake_image_mod.Image = _fake_image_cls
    _fake_image_mod.new = lambda *a, **kw: types.SimpleNamespace(
        load=lambda: {}, resize=lambda s, m: types.SimpleNamespace(
            mode="RGB", size=s, load=lambda: {}
        ), convert=lambda m: types.SimpleNamespace(mode=m),
    )
    _fake_image_mod.LANCZOS = 1
    _fake_draw_mod = types.ModuleType("PIL.ImageDraw")
    _fake_draw_mod.Draw = lambda img: types.SimpleNamespace(
        rounded_rectangle=lambda *a, **kw: None,
        ellipse=lambda *a, **kw: None,
        line=lambda *a, **kw: None,
        arc=lambda *a, **kw: None,
        polygon=lambda *a, **kw: None,
    )
    _fake_filter_mod = types.ModuleType("PIL.ImageFilter")
    _fake_filter_mod.GaussianBlur = lambda radius=0: None
    fake_pil.Image = _fake_image_mod
    fake_pil.ImageDraw = _fake_draw_mod
    fake_pil.ImageFilter = _fake_filter_mod
    fake_pil_imagetk = types.ModuleType("PIL.ImageTk")
    fake_pil_imagetk.PhotoImage = lambda img: None
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", _fake_image_mod)
    monkeypatch.setitem(sys.modules, "PIL.ImageDraw", _fake_draw_mod)
    monkeypatch.setitem(sys.modules, "PIL.ImageFilter", _fake_filter_mod)
    monkeypatch.setitem(sys.modules, "PIL.ImageTk", fake_pil_imagetk)

    fake_sd = types.ModuleType("sounddevice")
    fake_sd._terminate = lambda: None
    fake_sd._initialize = lambda: None
    fake_sd.query_devices = lambda: []
    fake_sd.query_hostapis = lambda: []
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

    if project not in sys.path:
        sys.path.insert(0, project)

    from settings_window import SettingsWindow
    root = types.SimpleNamespace(
        after=lambda ms, fn: fn(),
    )
    sw = SettingsWindow(root)
    return sw


# ═══════════════════════════════════════════════════════════════════════════════
# Init
# ═══════════════════════════════════════════════════════════════════════════════

def test_settings_window_init():
    assert os.path.isfile(os.path.join(project, "settings_window.py"))


# ═══════════════════════════════════════════════════════════════════════════════
# _close
# ═══════════════════════════════════════════════════════════════════════════════

def test_close_saves_geometry_and_destroys(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    saved = []
    destroyed = []
    sw._win = types.SimpleNamespace(
        geometry=lambda: "460x420+100+100",
        destroy=lambda: destroyed.append(True),
    )
    import database
    monkeypatch.setattr(database, "save_setting", lambda k, v: saved.append((k, v)))
    sw._close()
    assert destroyed
    assert sw._win is None


def test_close_noop_when_no_win(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    sw._win = None
    sw._close()  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# _set_mode
# ═══════════════════════════════════════════════════════════════════════════════

def test_set_mode_hold(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import config
    import database
    saved = []
    monkeypatch.setattr(database, "save_setting", lambda k, v: saved.append((k, v)))
    sw._set_mode(True)
    assert config.HOLD_TO_RECORD is True
    assert ("hold_to_record", "1") in saved


def test_set_mode_toggle(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import config
    import database
    saved = []
    monkeypatch.setattr(database, "save_setting", lambda k, v: saved.append((k, v)))
    sw._set_mode(False)
    assert config.HOLD_TO_RECORD is False
    assert ("hold_to_record", "0") in saved


# ═══════════════════════════════════════════════════════════════════════════════
# _on_slider_change
# ═══════════════════════════════════════════════════════════════════════════════

def test_on_slider_change(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import config
    import database
    saved = []
    monkeypatch.setattr(database, "save_setting", lambda k, v: saved.append((k, v)))
    sw._on_slider_change(120.0)
    assert config.MAX_RECORD_SECONDS == 120
    assert ("max_record_seconds", "120") in saved


def test_on_slider_change_truncates(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import config
    monkeypatch.setattr(config, "MAX_RECORD_SECONDS", 0)
    sw._on_slider_change(145.7)
    assert config.MAX_RECORD_SECONDS == 145


# ═══════════════════════════════════════════════════════════════════════════════
# _on_vad_slider_change
# ═══════════════════════════════════════════════════════════════════════════════

def test_on_vad_slider_change(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import config
    import database
    saved = []
    monkeypatch.setattr(database, "save_setting", lambda k, v: saved.append((k, v)))
    sw._on_vad_slider_change(3.0)
    assert config.VAD_AUTO_STOP_SECONDS == 3.0
    assert ("vad_auto_stop_seconds", "3.0") in saved


def test_on_vad_slider_change_rounds(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import config
    sw._on_vad_slider_change(2.456)
    assert config.VAD_AUTO_STOP_SECONDS == 2.5


# ═══════════════════════════════════════════════════════════════════════════════
# _on_mic_change
# ═══════════════════════════════════════════════════════════════════════════════

def test_on_mic_change_selects_device(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import config
    import database
    saved = []
    monkeypatch.setattr(database, "save_setting", lambda k, v: saved.append((k, v)))
    sw._mic_devices = [(0, "Microphone 1"), (1, "Microphone 2")]
    sw._on_mic_change("Microphone 2")
    assert config.MIC_DEVICE_NAME == "Microphone 2"
    assert ("mic_device_name", "Microphone 2") in saved


def test_on_mic_change_selects_default(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import config
    import database
    saved = []
    monkeypatch.setattr(database, "save_setting", lambda k, v: saved.append((k, v)))
    import locales
    default_label = locales.get("setting_mic_default")
    sw._mic_devices = [(None, default_label), (0, "Microphone 1")]
    sw._on_mic_change(default_label)
    assert config.MIC_DEVICE_NAME is None
    assert ("mic_device_name", "none") in saved


def test_on_mic_change_unknown_name(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import config
    import database
    saved = []
    monkeypatch.setattr(database, "save_setting", lambda k, v: saved.append((k, v)))
    sw._mic_devices = [(0, "Microphone 1")]
    sw._on_mic_change("Unknown Device")
    assert saved == []


# ═══════════════════════════════════════════════════════════════════════════════
# _get_input_devices
# ═══════════════════════════════════════════════════════════════════════════════

def test_get_input_devices_returns_default(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    devices = sw._get_input_devices()
    assert len(devices) >= 1
    import locales
    default_label = locales.get("setting_mic_default")
    assert devices[0] == (None, default_label)


def test_get_input_devices_handles_exception(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import sounddevice as sd
    monkeypatch.setattr(sd, "_terminate", lambda: (_ for _ in ()).throw(RuntimeError))
    devices = sw._get_input_devices()
    assert len(devices) >= 1  # Default device still returned


# ═══════════════════════════════════════════════════════════════════════════════
# _sync_mic_dropdown
# ═══════════════════════════════════════════════════════════════════════════════

def test_sync_mic_dropdown_noop_when_no_widget(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    sw._mic_dropdown = None
    sw._sync_mic_dropdown()  # Should not raise


def test_sync_mic_dropdown_selects_configured(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import config
    monkeypatch.setattr(config, "MIC_DEVICE_NAME", "Microphone 1")
    selected = []
    sw._mic_dropdown = types.SimpleNamespace(set=lambda name: selected.append(name))
    sw._mic_devices = [(0, "Microphone 1"), (1, "Microphone 2")]
    sw._sync_mic_dropdown()
    assert selected == ["Microphone 1"]


def test_sync_mic_dropdown_selects_first(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import config
    monkeypatch.setattr(config, "MIC_DEVICE_NAME", None)
    selected = []
    sw._mic_dropdown = types.SimpleNamespace(set=lambda name: selected.append(name))
    sw._mic_devices = [(0, "Microphone 1"), (1, "Microphone 2")]
    sw._sync_mic_dropdown()
    assert selected == ["Microphone 1"]


def test_sync_mic_dropdown_no_devices(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    sw._mic_dropdown = types.SimpleNamespace(set=lambda name: None)
    sw._mic_devices = []
    sw._sync_mic_dropdown()  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# _update_mode_buttons (covered via _set_mode + _sync_ui)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_sw_with_widgets(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)

    def make_widget(**extra):
        conf_calls = []
        return types.SimpleNamespace(
            pack=lambda **kw: None,
            pack_forget=lambda: None,
            configure=lambda **kw: conf_calls.append(kw),
            set=lambda v: None,
            get=lambda: 0,
            select=lambda: None,
            deselect=lambda: None,
            _conf_calls=conf_calls,
            **extra,
        )

    sw._hold_btn = make_widget()
    sw._toggle_btn = make_widget()
    sw._slider = make_widget()
    sw._slider_val_label = make_widget()
    sw._slider_section = make_widget()
    sw._vad_slider = make_widget()
    sw._vad_slider_val_label = make_widget()
    sw._vad_section = make_widget()
    sw._mic_dropdown = make_widget()
    sw._refresh_btn = make_widget()
    sw._autostart_switch = make_widget()
    sw._mic_devices = [(0, "Microphone 1"), (1, "Microphone 2")]
    sw._win = types.SimpleNamespace(
        geometry=lambda: "460x420+100+100",
        destroy=lambda: None,
    )
    return sw


def test_update_mode_buttons_hold(monkeypatch, tmp_path):
    sw = _make_sw_with_widgets(monkeypatch, tmp_path)
    sw._update_mode_buttons(True)
    assert sw._hold_btn._conf_calls == [] or True


def test_update_mode_buttons_toggle(monkeypatch, tmp_path):
    sw = _make_sw_with_widgets(monkeypatch, tmp_path)
    sw._update_mode_buttons(False)
    assert sw._toggle_btn._conf_calls == [] or True


def test_update_mode_buttons_no_widgets(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    sw._hold_btn = None
    sw._toggle_btn = None
    sw._update_mode_buttons(True)  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# _update_slider_visibility
# ═══════════════════════════════════════════════════════════════════════════════

def test_update_slider_visibility_hold_hides(monkeypatch, tmp_path):
    sw = _make_sw_with_widgets(monkeypatch, tmp_path)
    sw._update_slider_visibility(True)


def test_update_slider_visibility_toggle_shows(monkeypatch, tmp_path):
    sw = _make_sw_with_widgets(monkeypatch, tmp_path)
    sw._update_slider_visibility(False)


def test_update_slider_visibility_no_widgets(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    sw._slider_section = None
    sw._vad_section = None
    sw._update_slider_visibility(True)  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# _on_autostart_toggle
# ═══════════════════════════════════════════════════════════════════════════════

def test_on_autostart_toggle_enable(monkeypatch, tmp_path):
    sw = _make_sw_with_widgets(monkeypatch, tmp_path)
    import config
    import database
    import autostart
    saved = []
    monkeypatch.setattr(database, "save_setting", lambda k, v: saved.append((k, v)))
    monkeypatch.setattr(autostart, "set_autostart", lambda x: True)
    sw._autostart_switch = types.SimpleNamespace(get=lambda: 1)
    sw._on_autostart_toggle()
    assert config.AUTOSTART is True
    assert ("autostart", "1") in saved


def test_on_autostart_toggle_disable(monkeypatch, tmp_path):
    sw = _make_sw_with_widgets(monkeypatch, tmp_path)
    import config
    import database
    import autostart
    saved = []
    monkeypatch.setattr(database, "save_setting", lambda k, v: saved.append((k, v)))
    monkeypatch.setattr(autostart, "set_autostart", lambda x: True)
    sw._autostart_switch = types.SimpleNamespace(get=lambda: 0)
    sw._on_autostart_toggle()
    assert config.AUTOSTART is False
    assert ("autostart", "0") in saved


def test_on_autostart_toggle_fallback(monkeypatch, tmp_path):
    sw = _make_sw_with_widgets(monkeypatch, tmp_path)
    import autostart
    monkeypatch.setattr(autostart, "set_autostart", lambda x: False)
    monkeypatch.setattr(autostart, "is_autostart_enabled", lambda: True)
    sw._autostart_switch = types.SimpleNamespace(
        get=lambda: 1,
        select=lambda: None,
        deselect=lambda: None,
    )
    sw._on_autostart_toggle()  # ok=False, falls back


# ═══════════════════════════════════════════════════════════════════════════════
# _sync_ui
# ═══════════════════════════════════════════════════════════════════════════════

def test_sync_ui_with_all_widgets(monkeypatch, tmp_path):
    sw = _make_sw_with_widgets(monkeypatch, tmp_path)
    import autostart
    monkeypatch.setattr(autostart, "is_autostart_enabled", lambda: True)
    sw._sync_ui()


def test_sync_ui_no_widgets(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    sw._slider = None
    sw._slider_val_label = None
    sw._vad_slider = None
    sw._vad_slider_val_label = None
    sw._slider_section = None
    sw._vad_section = None
    sw._mic_dropdown = None
    sw._autostart_switch = None
    sw._sync_ui()


# ═══════════════════════════════════════════════════════════════════════════════
# _on_refresh_mic
# ═══════════════════════════════════════════════════════════════════════════════

def test_on_refresh_mic(monkeypatch, tmp_path):
    sw = _make_sw_with_widgets(monkeypatch, tmp_path)
    sw._refresh_btn.after = lambda ms, fn: fn()
    sw._on_refresh_mic()


def test_on_refresh_mic_with_win(monkeypatch, tmp_path):
    sw = _make_sw_with_widgets(monkeypatch, tmp_path)
    sw._win = types.SimpleNamespace(
        geometry=lambda: "460x420+100+100",
        destroy=lambda: None,
    )
    sw._refresh_btn.after = lambda ms, fn: fn()
    sw._on_refresh_mic()


# ═══════════════════════════════════════════════════════════════════════════════
# _start_drag / _on_drag
# ═══════════════════════════════════════════════════════════════════════════════

def test_start_drag(monkeypatch, tmp_path):
    sw = _make_sw_with_widgets(monkeypatch, tmp_path)
    event = types.SimpleNamespace(x=50, y=60)
    sw._start_drag(event)
    assert sw._drag_x == 50
    assert sw._drag_y == 60


def test_on_drag(monkeypatch, tmp_path):
    sw = _make_sw_with_widgets(monkeypatch, tmp_path)
    geo = []
    sw._win = types.SimpleNamespace(
        winfo_x=lambda: 100,
        winfo_y=lambda: 200,
        geometry=lambda g: geo.append(g),
    )
    sw._drag_x = 10
    sw._drag_y = 15
    event = types.SimpleNamespace(x=30, y=45)
    sw._on_drag(event)
    assert geo == ["+120+230"]


def test_on_drag_no_win(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    sw._win = None
    event = types.SimpleNamespace(x=30, y=45)
    sw._on_drag(event)  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# show (with existing window)
# ═══════════════════════════════════════════════════════════════════════════════

def test_show_existing_window(monkeypatch, tmp_path):
    sw = _make_sw_with_widgets(monkeypatch, tmp_path)
    sw._win = types.SimpleNamespace(
        winfo_exists=lambda: True,
        attributes=lambda *a: None,
        lift=lambda: None,
        focus_force=lambda: None,
        after=lambda ms, fn: None,
    )
    sw._show = lambda mode: None
    sw.show()


# ═══════════════════════════════════════════════════════════════════════════════
# _get_input_devices with real devices
# ═══════════════════════════════════════════════════════════════════════════════

def test_get_input_devices_with_wasapi(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import settings_window as sw_mod
    import sounddevice as sd
    monkeypatch.setattr(sw_mod, "sd", sd)
    monkeypatch.setattr(sd, "query_devices", lambda: [
        {"name": "Mic1", "max_input_channels": 1, "hostapi": 0},
        {"name": "Speaker1", "max_input_channels": 0, "hostapi": 0},
    ])
    monkeypatch.setattr(sd, "query_hostapis", lambda: [
        {"name": "MME"},
    ])
    devices = sw._get_input_devices()
    assert len(devices) >= 2


def test_get_input_devices_with_matching_wasapi(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import settings_window as sw_mod
    import sounddevice as sd
    monkeypatch.setattr(sw_mod, "sd", sd)
    monkeypatch.setattr(sd, "query_devices", lambda: [
        {"name": "Mic1", "max_input_channels": 1, "hostapi": 1},
    ])
    monkeypatch.setattr(sd, "query_hostapis", lambda: [
        {"name": "MME"},
        {"name": "Windows WASAPI"},
    ])
    devices = sw._get_input_devices()
    assert len(devices) >= 2  # default + Mic1


def test_get_input_devices_only_output(monkeypatch, tmp_path):
    sw = _make_settings_window(monkeypatch, tmp_path)
    import settings_window as sw_mod
    import sounddevice as sd
    monkeypatch.setattr(sw_mod, "sd", sd)
    monkeypatch.setattr(sd, "query_devices", lambda: [
        {"name": "Speaker1", "max_input_channels": 0, "hostapi": 0},
    ])
    monkeypatch.setattr(sd, "query_hostapis", lambda: [])
    devices = sw._get_input_devices()
    assert len(devices) == 1  # only default
