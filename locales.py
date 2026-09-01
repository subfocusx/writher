"""Centralised i18n string table for Writher (Russian-only, English fallbacks)."""

import config

_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # tray_icon.py
        "tray_idle":        "Writher — idle",
        "tray_recording":   "Writher — recording...",
        "tray_settings":    "Settings",
        "tray_quit":        "Quit",

        # settings_window.py
        "settings_title":         "Settings",
        "setting_record_mode":   "Recording mode",
        "setting_hold":          "Hold to record",
        "setting_toggle":        "Press to start / stop",
        "setting_max_duration":  "Max recording (seconds)",
        "setting_microphone":     "Microphone",
        "setting_mic_default":   "System default",
        "setting_vad_auto_stop": "Auto-stop on silence (sec)",
        "setting_autostart":     "Launch at Windows startup",

        # ASR model
        "setting_asr_model":             "ASR model",
        "setting_asr_model_rescan":      "Scan",
        "setting_asr_model_choose":      "Folder...",
        "setting_asr_model_choose_title": "Select a folder with ASR models",
        "setting_asr_model_loading":     "Switching model...",
        "setting_asr_model_empty":       "No models found. Add a folder or refresh.",

        # Recognition accuracy
        "setting_accuracy":          "Recognition accuracy",
        "setting_pp_normalize":      "Normalize volume",
        "setting_pp_highpass":       "High-pass filter",
        "setting_pp_denoise":        "Noise reduction",
        "setting_pp_preemphasis":    "Pre-emphasis",
        "setting_pp_hint":           "Audio pre-processing stages applied before recognition. Changes take effect from the next dictation.",
    },
    "ru": {
        # tray_icon.py
        "tray_idle":        "Writher — ожидание",
        "tray_recording":   "Writher — запись...",
        "tray_settings":    "Настройки",
        "tray_quit":        "Выход",

        # settings_window.py
        "settings_title":         "Настройки",
        "setting_record_mode":    "Режим записи",
        "setting_hold":          "Удерживать для записи",
        "setting_toggle":        "Нажать для старта / стопа",
        "setting_max_duration":   "Макс. длительность (сек)",
        "setting_microphone":     "Микрофон",
        "setting_mic_default":   "Системный по умолчанию",
        "setting_vad_auto_stop":  "Автостоп при тишине (сек)",
        "setting_autostart":      "Запускать при старте Windows",

        # ASR model
        "setting_asr_model":             "Модель распознавания",
        "setting_asr_model_rescan":      "Сканировать",
        "setting_asr_model_choose":      "Папка...",
        "setting_asr_model_choose_title": "Выберите папку с моделями ASR",
        "setting_asr_model_loading":     "Переключение модели...",
        "setting_asr_model_empty":       "Модели не найдены. Добавьте папку или обновите.",

        # Recognition accuracy
        "setting_accuracy":          "Точность распознавания",
        "setting_pp_normalize":      "Нормализация громкости",
        "setting_pp_highpass":       "High-pass фильтр",
        "setting_pp_denoise":        "Шумоподавление",
        "setting_pp_preemphasis":    "Pre-emphasis",
        "setting_pp_hint":           "Этапы обработки звука перед распознаванием. Применяются со следующей диктовки.",
    },
}

_FALLBACK = "en"


def get(key: str, **kwargs) -> str:
    lang = getattr(config, "LANGUAGE", _FALLBACK)
    table = _STRINGS.get(lang, _STRINGS[_FALLBACK])
    template = table.get(key, _STRINGS[_FALLBACK].get(key, key))
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template
