"""Hotkey listener for dictation (AltGr) and recovery (F7/F8).

Supports two recording modes controlled by config.HOLD_TO_RECORD:
  - Hold mode (True):  press=start, release=stop
  - Toggle mode (False): press=start, press again=stop
"""

import time
from pynput import keyboard
import config
from logger import log

_DEBOUNCE_SEC = 0.3


class HotkeyListener:
    def __init__(self, on_press_cb, on_release_cb,
                 on_re_paste_cb=None, on_retry_cb=None):
        self._on_press = on_press_cb
        self._on_release = on_release_cb
        self._on_re_paste = on_re_paste_cb
        self._on_retry = on_retry_cb
        self._dict_pressed = False
        self._dict_recording = False
        self._dict_last_toggle = 0.0
        self._listener = None

    def _is_hold_mode(self) -> bool:
        return getattr(config, "HOLD_TO_RECORD", True)

    def _handle_press(self, key):
        if key == config.HOTKEY:
            if self._is_hold_mode():
                if not self._dict_pressed:
                    self._dict_pressed = True
                    self._safe_call(self._on_press, "Dictation press")
            else:
                now = time.monotonic()
                if now - self._dict_last_toggle < _DEBOUNCE_SEC:
                    return
                self._dict_last_toggle = now
                if not self._dict_recording:
                    self._dict_recording = True
                    self._safe_call(self._on_press, "Dictation toggle-start")
                else:
                    self._dict_recording = False
                    self._safe_call(self._on_release, "Dictation toggle-stop")

        elif key == config.HOTKEY_REPASTE and self._on_re_paste:
            self._safe_call(self._on_re_paste, "Re-paste")

        elif key == config.HOTKEY_RETRY and self._on_retry:
            self._safe_call(self._on_retry, "Retry transcribe")

    def _handle_release(self, key):
        if key == config.HOTKEY:
            if self._is_hold_mode():
                if self._dict_pressed:
                    self._dict_pressed = False
                    self._safe_call(self._on_release, "Dictation release")
            else:
                self._dict_pressed = False

    def force_stop_dictation(self):
        """Called by the timeout timer to stop a toggle-mode recording."""
        if self._dict_recording:
            self._dict_recording = False
            self._dict_pressed = False
            self._safe_call(self._on_release, "Dictation timeout-stop")

    @staticmethod
    def _safe_call(fn, label: str):
        try:
            fn()
        except Exception as exc:
            log.error("%s error: %s", label, exc)

    def start(self):
        self._listener = keyboard.Listener(
            on_press=self._handle_press,
            on_release=self._handle_release,
        )
        self._listener.start()
        self._listener.wait()

    def stop(self):
        if self._listener is not None:
            self._listener.stop()
