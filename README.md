# WritHer

**Offline voice dictation and a personal notes / agenda / reminders organizer for Windows.**

WritHer turns your microphone into a text input: press a hotkey, speak, and your words are
transcribed and typed into whatever window you're working in — completely offline. The same
app keeps your notes, appointments, and reminders in one dark, lightweight window.

No cloud, no accounts, no telemetry. Audio and text stay on your machine.

---

## Features

- **Offline speech-to-text** — GigaAM v3 (Russian) transcribed locally through the
  `onnx-asr` engine. This is the default quality model.
- **Model selector / hot-swap** — pick the ASR model at runtime, rescan model folders, or
  point the app at any local `onnx-asr`-compatible model directory. No rebuild needed.
- **Dictate into any app** — AltGr (hold-to-record, or tap-to-toggle) captures audio,
  transcribes it, and injects the text into the focused window.
- **Silero VAD auto-stop** — in toggle mode the recording stops automatically when you
  stop speaking, so you do not need to tap the hotkey twice.
- **Recovery hotkeys** — **F7** retries the last transcription, **F8** re-injects the last
  transcribed text (handy when a paste went to the wrong window).
- **Notes, Agenda & Reminders** — a resizable, themed window with three tabs. Notes support
  free text and checklists; reminders are shown by a background scheduler.
- **Microphone selection** — choose any WASAPI input device from settings, or use the
  system default.
- **Autostart option** — run WritHer in the background on login.
- **System tray** — minimize to tray, control recording, open the notes/settings windows,
  quit.
- **Two languages** — English and Russian UI, switched at runtime.
- **Bundle-able** — ships a PyInstaller `writher.spec` for building a single-folder
  Windows executable.

## How it works

1. You press **AltGr** (or another configured hotkey) in the target app.
2. WritHer records your microphone, then runs voice-activity detection (Silero VAD) in
   toggle mode.
3. The audio is transcribed locally by your selected `onnx-asr` model (default:
   GigaAM v3 E2E CTC, INT8).
4. The resulting text is typed into the window that was active when you started speaking.

Everything lives in one Python process: a CustomTkinter UI, a background audio thread, and a
transcription worker.

## Requirements

- **Windows 10/11**
- **Python 3.10+** (3.11/3.12 recommended)
- The `onnx-asr` runtime and its dependencies (see `requirements.txt`)

The only network need is the **first** model download (see below); once cached it is fully
offline.

## Installation

Clone the repository and install the dependencies:

```powershell
git clone https://github.com/subfocusx/writher.git
cd writher
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Getting the speech model

The default GigaAM v3 model is **not bundled** (it is ~225 MB). On first run WritHer
downloads it automatically from Hugging Face:

> **Istupakov / gigaam-v3-onnx** — `https://huggingface.co/istupakov/gigaam-v3-onnx`
> files: `v3_e2e_ctc.int8.onnx`, `v3_e2e_ctc_vocab.txt`, `config.json`

You can also put these three files in a folder and point the **Settings → ASR model →
Choose folder** at it, then **Rescan**.

Because `onnx-asr` supports several model families, WritHer's model registry
(`models_registry.py`) can discover and switch between GigaAM v2/v3 (CTC, RNN-T, E2E),
multilingual CTC, large CTC, Kaldi, NeMo, T-ONE, Vosk, and Whisper models — provided you
have their files locally.

## Building a standalone EXE (optional)

A PyInstaller spec is included:

```powershell
pip install pyinstaller
pyinstaller writher.spec
```

> The bundled entrypoint is in `writher.spec` and produces a one-folder build under
> `dist/`. Do not ship `models/` (downloads on first run) unless you want to bundle it.

## Usage

### Hotkeys

| Key | Action |
|-----|--------|
| **AltGr** | Start / stop dictation (see recording mode below) |
| **F7** | Retry: re-transcribe the last recorded audio |
| **F8** | Re-paste: re-inject the last transcribed text |

> Hotkeys are defined in `config.py` (`HOTKEY`, `HOTKEY_REPASTE`, `HOTKEY_RETRY`).

### Recording modes (Settings)

- **Hold** (default): hold the hotkey, speak, release to stop.
- **Toggle**: press once to start, press again to stop — or let **Silero VAD** auto-stop
  after silence, bounded by the **max duration** slider.

### Settings window

- **Recording mode** — Hold / Toggle, plus max duration and VAD auto-stop time.
- **Microphone** — pick a WASAPI device or use the system default.
- **ASR model** — dropdown of discovered models, **Rescan**, and **Choose folder**.
- **Autostart** — toggle running on login.

### Notes, Agenda & Reminders

Open from the tray menu. The window has three tabs and stores its content in a local SQLite
database.

## Data storage

WritHer keeps its data in one folder:

- Running from source: the project directory.
- Running as a bundled EXE: `%APPDATA%\WritHer`.

It stores `writher.db` (SQLite: notes, appointments, reminders, settings, custom words),
`writher.log`, and any recovery audio written by the error-recovery path.

## Configuration

`config.py` contains the defaults (hotkeys, sample rate, VAD thresholds, autostart). Most
values are also editable from the Settings window and persisted in the database, so the
in-memory `config` is loaded from saved settings at startup.

## Project structure

```
writher/
├── main.py             # Entry point: wires everything together
├── config.py           # Defaults (hotkeys, audio, VAD)
├── asr_engine.py       # onnx-asr engine, model loading/switching
├── models_registry.py  # ModelSpec + model discovery/registry
├── recorder.py         # Microphone capture + Silero VAD
├── hotkey.py           # Global hotkey listener
├── injector.py         # Type/paste text into the focused window
├── notes_window.py     # Notes, Agenda & Reminders UI
├── settings_window.py  # Settings UI (recording, mic, model, autostart)
├── widget.py           # Floating recording widget
├── tray_icon.py        # System tray icon
├── notifier.py         # Reminder scheduler + notifications
├── database.py         # SQLite storage layer
├── paths.py            # Data path resolution (source vs frozen)
├── locales.py          # EN / RU strings
├── theme.py            # Color palette / theming
├── brand.py            # Title-bar branding assets
├── sounds.py           # Start/stop tones
├── autostart.py        # Registry autostart
├── logger.py           # Logging
├── debug_keys.py       # Debug key bindings
├── requirements.txt    # Python dependencies
├── writher.spec        # PyInstaller spec
└── tests/              # Unit tests
```

## Internationalization

UI strings live in `locales.py` and are available in English and Russian. Switch the active
language from the settings (or by editing `locales.py`).

## Tests

Run the unit tests with pytest:

```powershell
pip install -r scripts/requirements_test_gigaam.txt
pytest
```

`scripts/test_gigaam.py` is a benchmark that compares GigaAM v3 E2E CTC FP32 vs INT8 using
the sample audio in `scripts/test_audio/`.

## License

[MIT](LICENSE) © Writher Contributors.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
