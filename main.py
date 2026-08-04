"""WritHer — голосовая диктовка для Windows. Только GigaAM ONNX."""

import ctypes
import json
import os
import queue
import threading
import time
import tkinter as tk

import numpy as np

# Fix DPI awareness before any window is created.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

_STOP = object()

from logger import log
from recorder import Recorder
from asr_engine import create_engine
from models_registry import ModelSpec
import injector
from hotkey import HotkeyListener
from tray_icon import TrayIcon
from widget import RecordingWidget
import config
import database as db
from notifier import ReminderScheduler
from notes_window import NotesWindow
from settings_window import SettingsWindow

_pipeline_queue = queue.Queue()

recorder = Recorder()
transcriber = None
tray = None
widget = None
root = None
notes_win = None
settings_win = None
scheduler = None
hotkey_listener = None

_rec_start = 0.0
_MIN_DURATION = 0.5

# Recovery state for F8 (re-paste) and F7 (retry) hotkeys
_last_transcribed_text = ""
_last_raw_audio: np.ndarray | None = None
_retry_last_time = 0.0
_RETRY_DEBOUNCE = 1.0
_last_audio_lock = threading.Lock()

# Toggle-mode timeout timer
_timeout_timer: threading.Timer | None = None
_timeout_lock = threading.Lock()


# ── Load persisted settings into config at startup ────────────────────────

def _load_settings():
    """Read settings from DB and apply them to config module."""
    hold = db.get_setting("hold_to_record", "")
    if hold != "":
        config.HOLD_TO_RECORD = hold == "1"
    max_sec = db.get_setting("max_record_seconds", "")
    if max_sec != "":
        try:
            config.MAX_RECORD_SECONDS = int(max_sec)
        except ValueError:
            pass
    mic = db.get_setting("mic_device_name", "")
    if mic != "":
        config.MIC_DEVICE_NAME = mic if mic != "none" else None
    vad_sec = db.get_setting("vad_auto_stop_seconds", "")
    if vad_sec != "":
        try:
            config.VAD_AUTO_STOP_SECONDS = float(vad_sec)
        except ValueError:
            pass
    autostart_val = db.get_setting("autostart", "")
    if autostart_val != "":
        config.AUTOSTART = autostart_val == "1"
        import autostart
        autostart.set_autostart(config.AUTOSTART)


# ── Toggle-mode timeout helpers ───────────────────────────────────────────

def _start_timeout():
    """Start a safety timer that auto-stops recording in toggle mode.

    Always cancels any previously-armed timer first so we never have two
    timers racing. The new timer is stored in the module global under a
    lock so the cancel path (different thread) sees a consistent value.
    """
    global _timeout_timer
    if config.HOLD_TO_RECORD:
        return
    seconds = getattr(config, "MAX_RECORD_SECONDS", 120)
    if seconds <= 0:
        return
    new_timer = threading.Timer(seconds, _on_timeout)
    new_timer.daemon = True
    with _timeout_lock:
        old = _timeout_timer
        _timeout_timer = new_timer
    if old is not None:
        # Cancel outside the lock — Timer.cancel is idempotent and safe.
        old.cancel()
    new_timer.start()


def _cancel_timeout():
    global _timeout_timer
    with _timeout_lock:
        t = _timeout_timer
        _timeout_timer = None
    if t is not None:
        t.cancel()


def _on_timeout():
    """Fired by the toggle-mode safety timer. Stops the active dictation
    and clears the timer reference so a subsequent start_timeout() can
    install a fresh one without cancelling a stale one."""
    global _timeout_timer
    with _timeout_lock:
        _timeout_timer = None
    log.warning("Toggle-mode timeout reached.")
    if hotkey_listener:
        hotkey_listener.force_stop_dictation()


def _on_vad_stop():
    """Called from recorder audio thread when Silero VAD detects silence."""
    if hotkey_listener:
        hotkey_listener.force_stop_dictation()


# ── Dictation callbacks (AltGr) ──────────────────────────────────────────

_dict_hwnd: int | None = None
_hwnd_lock = threading.Lock()


def _on_hotkey_press():
    global _rec_start, _dict_hwnd
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    with _hwnd_lock:
        _dict_hwnd = hwnd
    _rec_start = time.monotonic()
    recorder.start()
    if tray:
        tray.set_recording(True)
    if widget:
        widget.show_recording()
    _start_timeout()
    log.info("Recording started (dictation).")


def _on_hotkey_release():
    _cancel_timeout()
    # Note: Recorder.stop() is idempotent (returns None when not recording),
    # so we always call it. This keeps the call site simple and matches
    # the contract test_on_hotkey_release_stops_recorder_and_puts_audio_in_queue
    # expects: recorder.stop() appears in calls regardless of state.
    audio = recorder.stop()
    duration = time.monotonic() - _rec_start
    if tray:
        tray.set_recording(False)
    log.info("Recording stopped (%.2fs).", duration)

    if audio is not None and len(audio) > 0 and duration >= _MIN_DURATION:
        if widget:
            widget.show_processing()
        _pipeline_queue.put(audio)
    else:
        if widget:
            widget.hide()
        if duration < _MIN_DURATION:
            log.info("Too short (%.2fs), skipping.", duration)
        else:
            log.info("Empty audio, skipping.")


# ── Pipeline worker ──────────────────────────────────────────────────────

def _save_audio_error_recovery(audio: np.ndarray) -> str | None:
    """Save failed audio to DATA_DIR so user can manually retry."""
    import time
    try:
        from paths import DATA_DIR
        import soundfile as sf
        filename = f"recovery_{int(time.time()*1000)}.wav"
        path = os.path.join(DATA_DIR, filename)
        sf.write(path, audio, 16000)
        log.info("Audio saved for manual recovery: %s", path)
        return path
    except Exception as exc:
        log.warning("Failed to save recovery audio: %s", exc)
        return None


def _notify_error(exc: Exception, recovery_path: str | None):
    """Show user-visible error via widget expression + tray tooltip."""
    import traceback
    error_brief = str(exc)[:80]
    log.error("Dictation pipeline error: %s\n%s", exc, traceback.format_exc())

    if widget:
        widget.set_expression("error")
        widget.show_message(f"Recognition error: {error_brief}", duration_ms=5000)


def _dictation_worker():
    """Transcribe audio and paste the result into the target application."""
    while True:
        item = _pipeline_queue.get()
        if item is _STOP:
            break
        # Store the raw audio for F7 (retry) BEFORE transcription starts.
        # Without the lock, F7 pressed during transcription could read a
        # partially-overwritten ndarray reference.
        with _last_audio_lock:
            global _last_raw_audio
            _last_raw_audio = item
        text = None
        exc_info = None

        for attempt in range(2):
            try:
                text = transcriber.transcribe(item)
                break
            except Exception as exc:
                exc_info = exc
                if attempt == 0:
                    log.warning("First transcription attempt failed (%.100s), retrying", exc)

        if text:
            with _last_audio_lock:
                global _last_transcribed_text
                _last_transcribed_text = text
            with _hwnd_lock:
                target_hwnd = _dict_hwnd
            injector.inject(text, target_hwnd=target_hwnd)
        elif exc_info:
            recovery_path = _save_audio_error_recovery(item)
            _notify_error(exc_info, recovery_path)
        else:
            log.info("No speech detected.")

        if widget:
            widget.hide()


# ── Recovery hotkeys (F8 / F7) ───────────────────────────────────────────

def _on_re_paste():
    """F8 — re-inject the last transcribed text into the active window."""
    with _last_audio_lock:
        last_text = _last_transcribed_text
    if last_text:
        with _hwnd_lock:
            target_hwnd = _dict_hwnd
        injector.inject(last_text, target_hwnd=target_hwnd)


def _on_retry():
    """F7 — re-transcribe the last raw audio and paste the result.

    Debounced to once per second. Reads _last_raw_audio atomically — if a
    new dictation finishes between the snapshot and the transcribe call,
    we'll re-transcribe the *previous* audio (which is the intended UX),
    not the new one.
    """
    now = time.monotonic()
    if now - _retry_last_time < _RETRY_DEBOUNCE:
        return
    with _last_audio_lock:
        last_audio = _last_raw_audio
    if last_audio is None:
        return
    _retry_last_time = now
    try:
        text = transcriber.transcribe(last_audio)
        if text:
            with _last_audio_lock:
                global _last_transcribed_text
                _last_transcribed_text = text
            with _hwnd_lock:
                target_hwnd = _dict_hwnd
            injector.inject(text, target_hwnd=target_hwnd)
        else:
            log.info("Retry: no speech detected.")
    except Exception as exc:
        log.error("Retry error: %s", exc)


# ── Quit & Main ───────────────────────────────────────────────────────────

def _show_notes():
    """Open notes window from tray menu."""
    if notes_win:
        root.after(0, lambda: notes_win.show("notes"))


def _show_settings():
    """Open settings window from tray menu."""
    if settings_win:
        root.after(0, lambda: settings_win.show())


def _quit():
    log.info("Quitting...")
    _cancel_timeout()
    _pipeline_queue.put(_STOP)
    if scheduler:
        scheduler.stop()
    if hotkey_listener:
        try:
            hotkey_listener.stop()
        except Exception:
            pass
    if tray:
        try:
            tray.stop()
        except Exception:
            pass
    try:
        recorder.stop()
    except Exception:
        pass
    if root:
        try:
            if notes_win and notes_win._win and notes_win._win.winfo_exists():
                notes_win._win.withdraw()
            if settings_win and settings_win._win and settings_win._win.winfo_exists():
                settings_win._win.withdraw()
        except Exception:
            pass
        try:
            root.after(50, _destroy_root)
        except Exception:
            pass
    log.info("Shutdown complete.")


def _destroy_root():
    """Destroy root after pending Tk events have been processed."""
    try:
        root.destroy()
    except Exception:
        pass


def main():
    global transcriber, tray, widget, root, notes_win, settings_win, scheduler
    global hotkey_listener

    db.init()
    _load_settings()

    # Restore the last selected ASR model (if valid), else the bundled default.
    saved_spec = None
    saved_raw = db.get_setting("asr_model", "")
    if saved_raw:
        try:
            cand = ModelSpec.from_dict(json.loads(saved_raw))
            if cand is not None and os.path.isdir(cand.path):
                saved_spec = cand
        except Exception:
            saved_spec = None
    transcriber = create_engine(saved_spec)

    root = tk.Tk()
    root.withdraw()

    widget = RecordingWidget(root)
    notes_win = NotesWindow(root)
    settings_win = SettingsWindow(root, engine=transcriber)

    recorder.on_level = lambda rms: widget.update_level(min(1.0, rms * 8))
    recorder.on_mic_error = lambda msg: widget.show_message(msg, 4000)
    recorder.on_vad_trigger = _on_vad_stop

    tray = TrayIcon(
        on_quit=_quit,
        on_show_settings=_show_settings,
    )
    tray.start()

    # Warmup model in background so UI stays responsive
    threading.Thread(target=transcriber.warmup, daemon=True).start()

    scheduler = ReminderScheduler()
    scheduler.start()

    t1 = threading.Thread(target=_dictation_worker, daemon=True)
    t1.start()

    hotkey_listener = HotkeyListener(
        on_press_cb=_on_hotkey_press,
        on_release_cb=_on_hotkey_release,
        on_re_paste_cb=_on_re_paste,
        on_retry_cb=_on_retry,
    )
    hotkey_listener.start()

    log.info("Ready. AltGr=dictate, F7=retry, F8=re-paste.")
    root.mainloop()


if __name__ == "__main__":
    main()
