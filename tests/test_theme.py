"""Tests for theme.py — Pandora Blackboard theme constants."""
import theme as T


# ═══════════════════════════════════════════════════════════════════════════════
# Core palette
# ═══════════════════════════════════════════════════════════════════════════════

def test_bg_deep_is_black():
    assert T.BG_DEEP == "#000000"


def test_bg_primary():
    assert T.BG == "#050508"


def test_bg_card():
    assert T.BG_CARD == "#0a0a0f"


def test_bg_hover():
    assert T.BG_HOVER == "#111118"


def test_bg_input():
    assert T.BG_INPUT == "#0a0a0f"


def test_border():
    assert T.BORDER == "#1a1a24"


def test_border_glow():
    assert T.BORDER_GLOW == "#2a2a3a"


# ═══════════════════════════════════════════════════════════════════════════════
# Text
# ═══════════════════════════════════════════════════════════════════════════════

def test_fg_white():
    assert T.FG == "#ffffff"


def test_fg_dim():
    assert T.FG_DIM == "#a0a0b0"


def test_fg_accent():
    assert T.FG_ACCENT == "#ccccdd"


# ═══════════════════════════════════════════════════════════════════════════════
# Accent
# ═══════════════════════════════════════════════════════════════════════════════

def test_accent():
    assert T.ACCENT == "#ffffff"


def test_accent_hover():
    assert T.ACCENT_HOVER == "#ddddee"


def test_accent_dim():
    assert T.ACCENT_DIM == "#666678"


# ═══════════════════════════════════════════════════════════════════════════════
# Semantic
# ═══════════════════════════════════════════════════════════════════════════════

def test_red():
    assert T.RED == "#ff4444"


def test_red_hover():
    assert T.RED_HOVER == "#ff6666"


def test_green():
    assert T.GREEN == "#55cc77"


def test_yellow():
    assert T.YELLOW == "#ffaa00"


# ═══════════════════════════════════════════════════════════════════════════════
# Title bar
# ═══════════════════════════════════════════════════════════════════════════════

def test_title_bg():
    assert T.TITLE_BG == "#000000"


def test_close_hover():
    assert T.CLOSE_HOVER == "#ff4444"


# ═══════════════════════════════════════════════════════════════════════════════
# Fonts
# ═══════════════════════════════════════════════════════════════════════════════

def test_font_family():
    assert T.FONT_FAMILY == "Segoe UI"


def test_font_title():
    assert T.FONT_TITLE == ("Segoe UI", 14, "bold")


def test_font_body():
    assert T.FONT_BODY == ("Segoe UI", 13)


def test_font_small():
    assert T.FONT_SMALL == ("Segoe UI", 12)


def test_font_tiny():
    assert T.FONT_TINY == ("Segoe UI", 11)


# ═══════════════════════════════════════════════════════════════════════════════
# Spacing
# ═══════════════════════════════════════════════════════════════════════════════

def test_pad_s():
    assert T.PAD_S == 4


def test_pad_m():
    assert T.PAD_M == 8


def test_pad_l():
    assert T.PAD_L == 16


def test_pad_xl():
    assert T.PAD_XL == 24


# ═══════════════════════════════════════════════════════════════════════════════
# All colors are valid hex
# ═══════════════════════════════════════════════════════════════════════════════

import re
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _is_hex(color):
    return isinstance(color, str) and _HEX_RE.match(color) is not None


def test_all_palette_colors_are_hex():
    for name in ("BG_DEEP", "BG", "BG_CARD", "BG_HOVER", "BG_INPUT",
                 "BORDER", "BORDER_GLOW", "FG", "FG_DIM", "FG_ACCENT",
                 "ACCENT", "ACCENT_HOVER", "ACCENT_DIM",
                 "RED", "RED_HOVER", "GREEN", "YELLOW",
                 "TITLE_BG", "CLOSE_HOVER"):
        val = getattr(T, name)
        assert _is_hex(val), f"{name} = {val!r} is not a valid hex color"
