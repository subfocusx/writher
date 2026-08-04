"""Unit tests for locales.py — Russian-only UI strings with English fallbacks."""
import pytest

import locales


@pytest.fixture
def restore_language():
    """Save and restore config.LANGUAGE around each test."""
    import config
    orig = getattr(config, "LANGUAGE", "en")
    yield config
    config.LANGUAGE = orig


# ── Basic lookup ──────────────────────────────────────────────────────────────


def test_get_tray_idle_english(restore_language):
    """tray_idle returns the English string when LANGUAGE=en."""
    restore_language.LANGUAGE = "en"
    assert locales.get("tray_idle") == "Writher — idle"


def test_get_tray_idle_russian(restore_language):
    """tray_idle returns the Russian string when LANGUAGE=ru."""
    restore_language.LANGUAGE = "ru"
    assert locales.get("tray_idle") == "Writher — ожидание"


def test_get_tray_recording_english(restore_language):
    """tray_recording returns English string."""
    restore_language.LANGUAGE = "en"
    assert locales.get("tray_recording") == "Writher — recording..."


def test_get_tray_recording_russian(restore_language):
    """tray_recording returns Russian string."""
    restore_language.LANGUAGE = "ru"
    assert locales.get("tray_recording") == "Writher — запись..."


def test_get_settings_title_english(restore_language):
    """settings_title returns English string."""
    restore_language.LANGUAGE = "en"
    assert locales.get("settings_title") == "Settings"


def test_get_settings_title_russian(restore_language):
    """settings_title returns Russian string."""
    restore_language.LANGUAGE = "ru"
    assert locales.get("settings_title") == "Настройки"


# ── Language fallback ─────────────────────────────────────────────────────────


def test_unknown_lang_falls_back_to_english(restore_language):
    """When LANGUAGE is unsupported, strings fall back to English."""
    restore_language.LANGUAGE = "de"  # not in _STRINGS
    assert locales.get("tray_idle") == "Writher — idle"
    assert locales.get("settings_title") == "Settings"


def test_missing_key_returns_key_itself(restore_language):
    """A key not present in any language returns the key name as-is."""
    restore_language.LANGUAGE = "en"
    assert locales.get("this_key_does_not_exist") == "this_key_does_not_exist"


# ── No kwargs path ────────────────────────────────────────────────────────────


def test_get_without_kwargs(restore_language):
    """locales.get() works without any kwargs."""
    restore_language.LANGUAGE = "en"
    out = locales.get("tray_idle")
    assert out == "Writher — idle"


def test_extra_kwargs_ignored(restore_language):
    """Passing extra kwargs that the template doesn't need is ignored."""
    restore_language.LANGUAGE = "en"
    out = locales.get("tray_idle", foo="bar", baz=123)
    assert out == "Writher — idle"


# ── All known English strings ────────────────────────────────────────────────


EN_KEYS = [
    "tray_idle", "tray_recording", "tray_settings", "tray_quit",
    "settings_title", "setting_record_mode", "setting_hold", "setting_toggle",
    "setting_max_duration", "setting_microphone", "setting_mic_default",
    "setting_vad_auto_stop", "setting_autostart",
]


@pytest.mark.parametrize("key", EN_KEYS)
def test_all_english_keys_present(restore_language, key):
    """Every listed English key exists and returns a non-empty string."""
    restore_language.LANGUAGE = "en"
    result = locales.get(key)
    assert isinstance(result, str)
    assert len(result) > 0
    assert result != key  # not a missing-key fallback


# ── All known Russian strings ────────────────────────────────────────────────


RU_KEYS = EN_KEYS  # same keys exist in Russian


@pytest.mark.parametrize("key", RU_KEYS)
def test_all_russian_keys_present(restore_language, key):
    """Every listed Russian key exists and returns a non-empty string."""
    restore_language.LANGUAGE = "ru"
    result = locales.get(key)
    assert isinstance(result, str)
    assert len(result) > 0
    assert result != key  # not a missing-key fallback
