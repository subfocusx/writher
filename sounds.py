"""Notification tones — Windows system sounds, no external files needed.

At most one tone is in flight at any time. If a new tone is requested
while the previous one is still playing, the new request is dropped
(sounds are cosmetic — we never queue them). This prevents a runaway
thread count when the user toggles recording rapidly.
"""
import winsound
import os
import threading


_tone_lock = threading.Lock()
_tone_busy = threading.Event()  # set while a tone is playing


def _play_async(wave_path: str):
    """Play a .wav file in a background thread, deduped.

    If a tone is already playing, this request is a no-op.
    """
    def _run():
        try:
            winsound.PlaySound(wave_path, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
        except Exception:
            pass
        finally:
            _tone_busy.clear()

    with _tone_lock:
        if _tone_busy.is_set():
            return  # skip — previous tone still playing
        _tone_busy.set()
    threading.Thread(target=_run, daemon=True).start()


def play_start_tone():
    """Short 'ding' — recording started."""
    _play_async(r"C:\Windows\Media\ding.wav")


def play_stop_tone():
    """Melodic chimes — recording finished."""
    _play_async(r"C:\Windows\Media\chimes.wav")

