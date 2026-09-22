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

# ── Adaptive VAD input normalisation (п.7) ────────────────────────────
# Silero VAD scores *raw* frames; its output depends on input level. On a
# quiet mic even voiced frames get a low score → phrase start/end clipped;
# on a loud/noisy mic noise frames score as speech → auto-stop delayed.
# An AGC that normalises each VAD frame toward a reference RMS fixes both,
# but it MUTATES what VAD sees (not the recorded audio, which is untouched).
#
# DEFAULT OFF (opt-in): changing how auto-stop fires on a real mic needs
# validation. Enable, then speak on your mic and watch for the "hang"
# (recording never stops) or clipped tails. Silence frames are NEVER
# amplified (guard below). The recorded waveform and the on_level meter
# always use the RAW frame.
VAD_NORMALIZE = False          # per-frame AGC before Silero (opt-in)
VAD_NORM_REF_RMS = 0.05        # target RMS for speech frames (~ -26 dBFS)
VAD_NORM_MAX_GAIN = 12.0       # clamp amplification, never blow up noise

# ── Windows autostart ──────────────────────────────────────────────────────
AUTOSTART = False

# ── Audio pre-processing ───────────────────────────────────────────────────
# Each stage degrades gracefully if its dependency (scipy, noisereduce) is
# not installed. Defaults tuned for typical Russian dictation: clear voice
# + light background hum from a desk mic.
#
# 2026-08-31 retune for USB headsets (e.g. "High Definition Audio Device"):
# - PP_HIGHPASS disabled: cheap USB mics already roll off below ~100 Hz, an
#   80 Hz high-pass further attenuates low-frequency consonants (в/б/д) and
#   makes sibilants at word boundaries harder to distinguish.
# - PP_PREEMPHASIS enabled: GigaAM v3 was trained with pre-emphasis 0.97;
#   without it, s/sh/shch/f at word boundaries come out clipped.
PP_HIGHPASS = False     # 80 Hz Butterworth high-pass (OFF for USB mics)
PP_NORMALIZE = True     # peak normalize to -3 dBFS before ASR
PP_DENOISE = False      # spectral gating (noisereduce, optional, OFF by default)
PP_PREEMPHASIS = True   # HF boost — required for GigaAM v3 to recognise fricatives

# ── Post-processing of ASR text ─────────────────────────────────────────────
# GigaAM punctuates unreliably; punct_normalize fixes the most common cases
# (duplicate commas, dots mid-question, mechanical commas after pause words).
# PUNCT_MODE "light" — structural cleanup only; "full" — + short-marker rules.
PUNCT_ENABLED = True
PUNCT_MODE = "full"
