"""Tests for brand.py — Pandora Blackboard brand assets."""
import os
import sys
import pytest
from PIL import Image

project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════════════════════════════
# get_notification_icon_path
# ═══════════════════════════════════════════════════════════════════════════════

def test_get_notification_icon_path():
    from brand import get_notification_icon_path
    path = get_notification_icon_path()
    assert isinstance(path, str)
    assert path.endswith("writher.ico")


# ═══════════════════════════════════════════════════════════════════════════════
# render_eyes
# ═══════════════════════════════════════════════════════════════════════════════

def test_render_eyes_returns_rgba():
    from brand import render_eyes
    img = render_eyes(size=64)
    assert isinstance(img, Image.Image)
    assert img.mode == "RGBA"
    assert img.size == (64, 64)


def test_render_eyes_custom_size():
    from brand import render_eyes
    img = render_eyes(size=32)
    assert img.size == (32, 32)


def test_render_eyes_no_glow_rgb():
    from brand import render_eyes
    img = render_eyes(size=32, glow_rgb=None, eye_rgb=(255, 0, 0))
    assert isinstance(img, Image.Image)
    assert img.size == (32, 32)


def test_render_eyes_no_circle_bg():
    from brand import render_eyes
    img = render_eyes(size=32, circle_bg=False)
    assert isinstance(img, Image.Image)
    assert img.mode == "RGBA"


def test_render_eyes_zero_bg_alpha():
    from brand import render_eyes
    img = render_eyes(size=32, bg_alpha=0, circle_bg=True)
    assert isinstance(img, Image.Image)


def test_render_eyes_zero_glow_alpha():
    from brand import render_eyes
    img = render_eyes(size=32, glow_alpha=0)
    assert isinstance(img, Image.Image)


def test_render_eyes_has_nonzero_pixels():
    from brand import render_eyes
    img = render_eyes(size=32)
    pixels = list(img.getdata())
    non_transparent = [p for p in pixels if p[3] > 0]
    assert len(non_transparent) > 0


def test_render_eyes_with_circle_bg_has_background():
    from brand import render_eyes
    img = render_eyes(size=64, circle_bg=True, bg_rgb=(12, 12, 15))
    pixels = list(img.getdata())
    bg_pixels = [p for p in pixels if p[0] == 12 and p[1] == 12 and p[2] == 15]
    assert len(bg_pixels) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# make_tray_icon
# ═══════════════════════════════════════════════════════════════════════════════

def test_make_tray_icon_idle():
    from brand import make_tray_icon
    img = make_tray_icon(recording=False)
    assert isinstance(img, Image.Image)
    assert img.size == (64, 64)


def test_make_tray_icon_recording():
    from brand import make_tray_icon
    img = make_tray_icon(recording=True)
    assert isinstance(img, Image.Image)
    assert img.size == (64, 64)


def test_make_tray_icon_idle_is_different_from_recording():
    from brand import make_tray_icon
    idle = make_tray_icon(recording=False)
    rec = make_tray_icon(recording=True)
    idle_pixels = list(idle.getdata())
    rec_pixels = list(rec.getdata())
    assert idle_pixels != rec_pixels


# ═══════════════════════════════════════════════════════════════════════════════
# make_title_bar_image
# ═══════════════════════════════════════════════════════════════════════════════

def test_make_title_bar_image_default_size():
    from brand import make_title_bar_image
    img = make_title_bar_image()
    assert isinstance(img, Image.Image)
    assert img.size == (20, 20)


def test_make_title_bar_image_custom_size():
    from brand import make_title_bar_image
    img = make_title_bar_image(size=40)
    assert isinstance(img, Image.Image)
    assert img.size == (40, 40)


def test_make_title_bar_image_has_eye_pixels():
    from brand import make_title_bar_image
    img = make_title_bar_image(size=64)
    assert img.mode == "RGBA"
    pixels = list(img.getdata())
    non_transparent = [p for p in pixels if p[3] > 0]
    assert len(non_transparent) > 0


def test_make_title_bar_image_is_different_from_tray_icon():
    from brand import make_title_bar_image, make_tray_icon
    title_img = make_title_bar_image(size=64)
    tray_img = make_tray_icon(recording=False)
    assert list(title_img.getdata()) != list(tray_img.getdata())
