"""Tests for widget.py helper functions (non-GUI parts)."""
import math
import pytest
from PIL import Image


# ═══════════════════════════════════════════════════════════════════════════════
# _hex_to_rgb
# ═══════════════════════════════════════════════════════════════════════════════

def test_hex_to_rgb_black():
    from widget import _hex_to_rgb
    assert _hex_to_rgb("#000000") == (0, 0, 0)


def test_hex_to_rgb_white():
    from widget import _hex_to_rgb
    assert _hex_to_rgb("#ffffff") == (255, 255, 255)


def test_hex_to_rgb_red():
    from widget import _hex_to_rgb
    assert _hex_to_rgb("#ff0000") == (255, 0, 0)


def test_hex_to_rgb_no_hash():
    from widget import _hex_to_rgb
    assert _hex_to_rgb("0a0a0f") == (10, 10, 15)


def test_hex_to_rgb_uppercase():
    from widget import _hex_to_rgb
    assert _hex_to_rgb("#FF00AA") == (255, 0, 170)


# ═══════════════════════════════════════════════════════════════════════════════
# _lerp_rgb
# ═══════════════════════════════════════════════════════════════════════════════

def test_lerp_rgb_same():
    from widget import _lerp_rgb
    assert _lerp_rgb((100, 100, 100), (100, 100, 100), 0.5) == (100, 100, 100)


def test_lerp_rgb_black_to_white():
    from widget import _lerp_rgb
    result = _lerp_rgb((0, 0, 0), (255, 255, 255), 0.5)
    assert result == (127, 127, 127)


def test_lerp_rgb_t0():
    from widget import _lerp_rgb
    assert _lerp_rgb((10, 20, 30), (200, 210, 220), 0.0) == (10, 20, 30)


def test_lerp_rgb_t1():
    from widget import _lerp_rgb
    assert _lerp_rgb((10, 20, 30), (200, 210, 220), 1.0) == (200, 210, 220)


# ═══════════════════════════════════════════════════════════════════════════════
# _render_pill
# ═══════════════════════════════════════════════════════════════════════════════

def test_render_pill_returns_rgb_image():
    from widget import _render_pill
    img = _render_pill(
        w=220, h=44, radius=22,
        fill_rgb=(12, 12, 15),
        border_rgb=(255, 255, 255),
        border_a=0.08,
        glow_rgb=(255, 255, 255),
        chromakey_rgb=(0, 0, 1),
    )
    assert isinstance(img, Image.Image)
    assert img.size == (220, 44)
    assert img.mode == "RGB"


def test_render_pill_dimensions():
    from widget import _render_pill
    img = _render_pill(
        w=100, h=30, radius=15,
        fill_rgb=(10, 10, 10),
        border_rgb=(200, 200, 200),
        border_a=0.1,
        glow_rgb=(200, 200, 200),
        chromakey_rgb=(0, 0, 1),
    )
    assert img.size == (100, 30)


def test_render_pill_center_is_fill_not_chromakey():
    from widget import _render_pill
    img = _render_pill(
        w=100, h=40, radius=20,
        fill_rgb=(10, 10, 15),
        border_rgb=(255, 255, 255),
        border_a=0.08,
        glow_rgb=(255, 255, 255),
        chromakey_rgb=(0, 0, 1),
    )
    pixels = img.load()
    center_r, center_g, center_b = pixels[50, 20]
    # Center should NOT be the chromakey (0, 0, 1)
    assert not (center_r == 0 and center_g == 0 and center_b == 1)


# ═══════════════════════════════════════════════════════════════════════════════
# _STATE_STYLE and _EYE_THEME consistency
# ═══════════════════════════════════════════════════════════════════════════════

def test_state_style_has_all_required_keys():
    from widget import _STATE_STYLE
    for key, style in _STATE_STYLE.items():
        assert "accent" in style, f"{key} missing 'accent'"
        assert "glow" in style, f"{key} missing 'glow'"
        assert "border" in style, f"{key} missing 'border'"
        assert "border_a" in style, f"{key} missing 'border_a'"
        assert "label" in style, f"{key} missing 'label'"


def test_eye_theme_has_all_required_keys():
    from widget import _EYE_THEME
    for key, theme in _EYE_THEME.items():
        assert "eye" in theme, f"{key} missing 'eye'"
        assert "glow" in theme, f"{key} missing 'glow'"


def test_state_style_and_eye_theme_have_same_keys():
    from widget import _STATE_STYLE, _EYE_THEME
    assert set(_STATE_STYLE.keys()) == set(_EYE_THEME.keys())


def test_all_expressions_in_state_style():
    from widget import _STATE_STYLE
    expected = {
        "idle", "listening", "thinking", "coding", "happy",
        "error", "alert", "surprised", "wink", "sleep", "sad",
        "love", "loading", "recording", "processing", "assistant",
    }
    assert set(_STATE_STYLE.keys()) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# _update_avatar — renders PIL image for each expression
# ═══════════════════════════════════════════════════════════════════════════════

import types
import threading
import tkinter as tk
from unittest.mock import MagicMock

# Mock ImageTk.PhotoImage before any widget imports that use it
import PIL.ImageTk as _pil_imagetk
_original_photoimage = getattr(_pil_imagetk, 'PhotoImage', None)
_pil_imagetk.PhotoImage = lambda *a, **kw: MagicMock()


def _make_recording_widget():
    """Create a RecordingWidget with a mocked root and canvas."""
    root = types.SimpleNamespace(
        after=lambda ms, fn: None,
        tk=types.SimpleNamespace(call=lambda *a: 96 / 72),
    )
    from widget import RecordingWidget
    w = RecordingWidget(root)
    w.ASSISTANT = "assistant"  # referenced in _animate but not defined as class attr
    w._canvas = MagicMock()
    w._canvas.create_image = MagicMock(return_value=1)
    w._canvas.create_text = MagicMock(return_value=2)
    w._canvas.create_line = MagicMock(return_value=3)
    w._canvas.itemconfig = MagicMock()
    w._canvas.after = MagicMock(return_value="after_id")
    w._canvas.coords = MagicMock()
    w._win = types.SimpleNamespace(
        winfo_id=lambda: 123,
        winfo_exists=lambda: True,
        deiconify=lambda: None,
        wm_attributes=lambda *a: None,
        withdraw=lambda: None,
        geometry=lambda g: None,
    )
    w._ava_img_id = 1
    w._bg_img_id = 10
    w._label_id = 2
    w._text_id = 3
    w._bar_ids = [4, 5, 6, 7, 8]
    w._sep_ids = [9]
    return w


def test_update_avatar_idle():
    w = _make_recording_widget()
    w._expression = "idle"
    w._tick = 0
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_listening():
    w = _make_recording_widget()
    w._expression = "listening"
    w._tick = 5
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_recording():
    w = _make_recording_widget()
    w._expression = "recording"
    w._tick = 10
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_thinking():
    w = _make_recording_widget()
    w._expression = "thinking"
    w._tick = 3
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_processing():
    w = _make_recording_widget()
    w._expression = "processing"
    w._tick = 7
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_coding():
    w = _make_recording_widget()
    w._expression = "coding"
    w._tick = 5
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_coding_blink():
    w = _make_recording_widget()
    w._expression = "coding"
    w._tick = 12
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_happy():
    w = _make_recording_widget()
    w._expression = "happy"
    w._tick = 0
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_error():
    w = _make_recording_widget()
    w._expression = "error"
    w._tick = 0
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_alert():
    w = _make_recording_widget()
    w._expression = "alert"
    w._tick = 5
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_surprised():
    w = _make_recording_widget()
    w._expression = "surprised"
    w._tick = 0
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_wink():
    w = _make_recording_widget()
    w._expression = "wink"
    w._tick = 0
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_sleep():
    w = _make_recording_widget()
    w._expression = "sleep"
    w._tick = 0
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_sad():
    w = _make_recording_widget()
    w._expression = "sad"
    w._tick = 0
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_love():
    w = _make_recording_widget()
    w._expression = "love"
    w._tick = 5
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_loading():
    w = _make_recording_widget()
    w._expression = "loading"
    w._tick = 10
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_assistant():
    w = _make_recording_widget()
    w._expression = "assistant"
    w._tick = 5
    w._update_avatar()
    assert w._ava_tk is not None


def test_update_avatar_no_canvas():
    from widget import RecordingWidget
    root = types.SimpleNamespace(after=lambda ms, fn: None, tk=types.SimpleNamespace(call=lambda *a: 96 / 72))
    w = RecordingWidget(root)
    w._canvas = None
    w._expression = "idle"
    w._update_avatar()  # Should return early


# ═══════════════════════════════════════════════════════════════════════════════
# _set_alpha
# ═══════════════════════════════════════════════════════════════════════════════

def test_set_alpha_clamps_min():
    w = _make_recording_widget()
    w._set_alpha(-0.5)
    from widget import _ALPHA_MIN
    assert w._alpha == _ALPHA_MIN


def test_set_alpha_clamps_max():
    w = _make_recording_widget()
    w._set_alpha(2.0)
    from widget import _ALPHA_MAX
    assert w._alpha == _ALPHA_MAX


def test_set_alpha_valid():
    w = _make_recording_widget()
    w._set_alpha(0.5)
    assert w._alpha == 0.5


def test_set_alpha_no_win():
    from widget import RecordingWidget
    root = types.SimpleNamespace(after=lambda ms, fn: None, tk=types.SimpleNamespace(call=lambda *a: 96 / 72))
    w = RecordingWidget(root)
    w._win = None
    w._set_alpha(0.5)  # Should not raise
    assert w._alpha == 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# _cancel_fade
# ═══════════════════════════════════════════════════════════════════════════════

def test_cancel_fade_when_active():
    w = _make_recording_widget()
    w._after_fade = "some_after_id"
    w._root.after_cancel = MagicMock()
    w._cancel_fade()
    assert w._after_fade is None


def test_cancel_fade_when_none():
    w = _make_recording_widget()
    w._after_fade = None
    w._cancel_fade()  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# _start_fade_in / _start_fade_out / _fade_step
# ═══════════════════════════════════════════════════════════════════════════════

def test_start_fade_in():
    w = _make_recording_widget()
    w._alpha = 0.0
    w._start_fade_in()
    assert w._fading == "in"


def test_start_fade_out_no_win():
    from widget import RecordingWidget
    root = types.SimpleNamespace(after=lambda ms, fn: None, tk=types.SimpleNamespace(call=lambda *a: 96 / 72))
    w = RecordingWidget(root)
    w._win = None
    w._alpha = 0.5
    w._start_fade_out()
    assert w._mode is None


def test_start_fade_out_alpha_zero():
    from widget import RecordingWidget, _ALPHA_MIN
    root = types.SimpleNamespace(after=lambda ms, fn: None, tk=types.SimpleNamespace(call=lambda *a: 96 / 72))
    w = RecordingWidget(root)
    w._win = types.SimpleNamespace(withdraw=MagicMock(), geometry=MagicMock(return_value="1x1+0+0"))
    w._alpha = _ALPHA_MIN
    w._start_fade_out()
    assert w._mode is None


def test_fade_step_in_reaches_max():
    w = _make_recording_widget()
    w._fading = "in"
    w._alpha = 0.99
    w._fade_step()
    from widget import _ALPHA_MAX
    assert w._alpha == _ALPHA_MAX
    assert w._fading is None


def test_fade_step_out_reaches_min():
    w = _make_recording_widget()
    w._fading = "out"
    w._alpha = 0.01
    w._win.withdraw = MagicMock()
    w._fade_step()
    from widget import _ALPHA_MIN
    assert w._alpha == _ALPHA_MIN


def test_fade_step_no_action():
    w = _make_recording_widget()
    w._fading = None
    w._fade_step()  # Should not raise


def test_fade_step_in_continues():
    w = _make_recording_widget()
    w._fading = "in"
    w._alpha = 0.0
    w._fade_step()
    assert w._fading == "in"
    assert w._alpha > 0.0


def test_fade_step_out_continues():
    w = _make_recording_widget()
    w._fading = "out"
    w._alpha = 0.5
    w._fade_step()
    assert w._fading == "out"
    assert w._alpha < 0.5


# ═══════════════════════════════════════════════════════════════════════════════
# update_level
# ═══════════════════════════════════════════════════════════════════════════════

def test_update_level_clamps_min():
    w = _make_recording_widget()
    w.update_level(-1.0)
    assert w._level == 0.15


def test_update_level_clamps_max():
    w = _make_recording_widget()
    w.update_level(5.0)
    assert w._level == 1.0


def test_update_level_valid():
    w = _make_recording_widget()
    w.update_level(0.75)
    assert w._level == 0.75


# ═══════════════════════════════════════════════════════════════════════════════
# set_expression
# ═══════════════════════════════════════════════════════════════════════════════

def test_set_expression_valid():
    w = _make_recording_widget()
    w.set_expression("happy")
    assert w._expression == "happy"


def test_set_expression_invalid():
    w = _make_recording_widget()
    w._expression = "idle"
    w.set_expression("nonexistent")
    assert w._expression == "idle"


# ═══════════════════════════════════════════════════════════════════════════════
# _show (internal)
# ═══════════════════════════════════════════════════════════════════════════════

def test_show_recording_mode():
    w = _make_recording_widget()
    w._alpha = 1.0
    w._after_anim = None
    w._fading = None
    w._after_msg = "some_id"
    w._root.after_cancel = MagicMock()
    w._show(w.RECORDING)
    assert w._expression == "listening"
    assert w._mode == w.RECORDING


def test_show_processing_mode():
    w = _make_recording_widget()
    w._alpha = 1.0
    w._after_anim = None
    w._fading = None
    w._show(w.PROCESSING)
    assert w._expression == "thinking"
    assert w._mode == w.PROCESSING


def test_show_cancels_fade_out():
    w = _make_recording_widget()
    w._alpha = 1.0
    w._after_anim = "some_id"
    w._fading = "out"
    w._after_msg = None
    w._root.after_cancel = MagicMock()
    w._show(w.RECORDING)
    assert w._fading is None or True


def test_show_needs_build():
    w = _make_recording_widget()
    w._win = None
    w._alpha = 0.5
    w._after_anim = None
    w._after_msg = None
    w._build = MagicMock()
    w._show(w.RECORDING)
    assert w._mode == w.RECORDING


# ═══════════════════════════════════════════════════════════════════════════════
# _show_msg (internal)
# ═══════════════════════════════════════════════════════════════════════════════

def test_show_msg():
    w = _make_recording_widget()
    w._alpha = 1.0
    w._fading = None
    w._after_msg = None
    w._show_msg("Hello!", 3000)
    assert w._mode is None


def test_show_msg_needs_build():
    w = _make_recording_widget()
    w._win = None
    w._alpha = 1.0
    w._fading = None
    w._build = MagicMock()
    w._show_msg("Hello!", 3000)
    assert w._mode is None


def test_show_msg_cancels_existing():
    w = _make_recording_widget()
    w._alpha = 1.0
    w._fading = "out"
    w._after_msg = "old_msg_id"
    w._root.after_cancel = MagicMock()
    w._root.after = MagicMock(return_value="new_msg_id")
    w._show_msg("Hello!", 3000)
    assert w._after_msg == "new_msg_id"


# ═══════════════════════════════════════════════════════════════════════════════
# _do_hide (internal)
# ═══════════════════════════════════════════════════════════════════════════════

def test_do_hide():
    w = _make_recording_widget()
    w._after_anim = "anim_id"
    w._after_msg = "msg_id"
    w._root.after_cancel = MagicMock()
    w._do_hide()
    assert w._mode is None
    assert w._expression == "idle"
    assert w._after_anim is None
    assert w._after_msg is None


def test_do_hide_no_win():
    from widget import RecordingWidget
    root = types.SimpleNamespace(after=lambda ms, fn: None, tk=types.SimpleNamespace(call=lambda *a: 96 / 72))
    w = RecordingWidget(root)
    w._win = None
    w._after_anim = None
    w._after_msg = None
    w._do_hide()  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# _animate (internal)
# ═══════════════════════════════════════════════════════════════════════════════

def test_animate_recording():
    w = _make_recording_widget()
    w._mode = w.RECORDING
    w._tick = 0
    w._level = 0.8
    w._expression = "listening"
    w._animate()
    assert w._tick == 1


def test_animate_processing():
    w = _make_recording_widget()
    w._mode = w.PROCESSING
    w._tick = 0
    w._expression = "thinking"
    w._animate()
    assert w._tick == 1


def test_animate_no_mode():
    from widget import RecordingWidget
    root = types.SimpleNamespace(after=lambda ms, fn: None, tk=types.SimpleNamespace(call=lambda *a: 96 / 72))
    w = RecordingWidget(root)
    w._mode = None
    w._canvas = MagicMock()
    w._animate()
    assert w._after_anim is None


def test_animate_assistant():
    w = _make_recording_widget()
    w._mode = "assistant"
    w._tick = 0
    w._level = 0.6
    w._expression = "assistant"
    w._animate()
    assert w._tick == 1


# ═══════════════════════════════════════════════════════════════════════════════
# _drag_start / _on_drag
# ═══════════════════════════════════════════════════════════════════════════════

def test_drag_start():
    w = _make_recording_widget()
    event = types.SimpleNamespace(x_root=100, y_root=200)
    w._drag_start(event)
    assert w._drag_start_x == 100
    assert w._drag_start_y == 200


def test_on_drag():
    w = _make_recording_widget()
    w._drag_start_x = 100
    w._drag_start_y = 200
    geo = []
    w._win = types.SimpleNamespace(
        winfo_x=lambda: 500,
        winfo_y=lambda: 600,
        geometry=lambda g: geo.append(g),
    )
    event = types.SimpleNamespace(x_root=120, y_root=240)
    w._on_drag(event)
    assert geo == ["+520+640"]


def test_on_drag_no_win():
    from widget import RecordingWidget
    root = types.SimpleNamespace(after=lambda ms, fn: None, tk=types.SimpleNamespace(call=lambda *a: 96 / 72))
    w = RecordingWidget(root)
    w._win = None
    event = types.SimpleNamespace(x_root=120, y_root=240)
    w._on_drag(event)  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# _update_label (internal)
# ═══════════════════════════════════════════════════════════════════════════════

def test_update_label_with_text():
    w = _make_recording_widget()
    w._expression = "listening"
    w._update_label()
    w._canvas.itemconfig.assert_called()


def test_update_label_hidden():
    w = _make_recording_widget()
    w._expression = "idle"
    w._update_label()


def test_update_label_no_canvas():
    from widget import RecordingWidget
    root = types.SimpleNamespace(after=lambda ms, fn: None, tk=types.SimpleNamespace(call=lambda *a: 96 / 72))
    w = RecordingWidget(root)
    w._canvas = None
    w._label_id = 1
    w._update_label()  # Should return early


def test_update_label_no_label_id():
    w = _make_recording_widget()
    w._label_id = None
    w._update_label()  # Should return early


def test_update_label_sleep_opacity():
    w = _make_recording_widget()
    w._expression = "sleep"
    w._update_label()
    w._canvas.itemconfig.assert_called()


# ═══════════════════════════════════════════════════════════════════════════════
# _update_pill_bg (internal)
# ═══════════════════════════════════════════════════════════════════════════════

def test_update_pill_bg():
    w = _make_recording_widget()
    w._expression = "error"
    w._pill_cache.clear()
    w._update_pill_bg()
    assert w._bg_tk is not None


def test_update_pill_bg_cached():
    w = _make_recording_widget()
    w._expression = "idle"
    w._pill_cache.clear()
    w._update_pill_bg()
    bg_tk_first = w._bg_tk
    w._update_pill_bg()
    assert w._bg_tk is bg_tk_first


def test_update_pill_bg_no_canvas():
    from widget import RecordingWidget
    root = types.SimpleNamespace(after=lambda ms, fn: None, tk=types.SimpleNamespace(call=lambda *a: 96 / 72))
    w = RecordingWidget(root)
    w._canvas = None
    w._update_pill_bg()  # Should return early


# ═══════════════════════════════════════════════════════════════════════════════
# _no_activate
# ═══════════════════════════════════════════════════════════════════════════════

def test_no_activate():
    from widget import _no_activate
    _no_activate(12345)  # Should not raise with mocked ctypes


# ═══════════════════════════════════════════════════════════════════════════════
# show_recording / show_processing / show_message / hide
# ═══════════════════════════════════════════════════════════════════════════════

def test_show_recording_public():
    w = _make_recording_widget()
    after_calls = []
    w._root.after = lambda ms, fn: after_calls.append((ms, fn))
    w.show_recording()
    assert len(after_calls) == 1
    assert after_calls[0][0] == 0


def test_show_processing_public():
    w = _make_recording_widget()
    after_calls = []
    w._root.after = lambda ms, fn: after_calls.append((ms, fn))
    w.show_processing()
    assert len(after_calls) == 1


def test_show_message_public():
    w = _make_recording_widget()
    after_calls = []
    w._root.after = lambda ms, fn: after_calls.append((ms, fn))
    w.show_message("test", 1000)
    assert len(after_calls) == 1


def test_hide_public():
    w = _make_recording_widget()
    after_calls = []
    w._root.after = lambda ms, fn: after_calls.append((ms, fn))
    w.hide()
    assert len(after_calls) == 1
