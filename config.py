from pynput.keyboard import Key

# ── Hotkeys ─────────────────────────────────────────────────────────────────
HOTKEY = Key.alt_gr
ASSISTANT_HOTKEY = Key.ctrl_r
HOTKEY_REPASTE = Key.f8
HOTKEY_RETRY = Key.f7

# ── Audio ──────────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000

# ── Microphone ──────────────────────────────────────────────────────────────
# None = system default. Set to device name (str) to use a specific mic.
MIC_DEVICE_NAME = None

# ── Recording mode ─────────────────────────────────────────────────────────
# True = hold key to record (release stops). False = toggle (press to start/stop).
HOLD_TO_RECORD = True

# Maximum recording duration in seconds (toggle mode only, safety net).
MAX_RECORD_SECONDS = 120

# ── Voice Activity Detection ────────────────────────────────────────────────
# Silero VAD auto-stop (toggle mode only).
# Recording auto-stops after this many seconds of continuous non-speech.
VAD_AUTO_STOP_SECONDS = 1.5

# Speech probability threshold (0.0-1.0). Lower = more sensitive.
VAD_THRESHOLD = 0.4

# ── Windows autostart ──────────────────────────────────────────────────────
AUTOSTART = False
