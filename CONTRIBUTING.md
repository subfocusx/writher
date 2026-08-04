# Contributing to WritHer

Thank you for your interest in contributing! WritHer is a young open-source project, and every
contribution matters — whether it's code, a bug report, a translation, or just feedback.

## Getting Started

### Prerequisites

- **Python 3.10+** (3.11/3.12 recommended)
- **Windows 10/11** (current target platform)
- Git

### Setup

```powershell
git clone https://github.com/subfocusx/writher.git
cd writher
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Run

```powershell
python main.py
```

WritHer runs in the background (tray icon). Hold **AltGr** to dictate. The default GigaAM v3
model is downloaded automatically on first run from Hugging Face; see the README for details.

## Project Structure

```
main.py             - Entry point, orchestration, Tk event loop
config.py           - Default settings (hotkeys, audio, VAD)
asr_engine.py       - onnx-asr engine, model loading / switching
models_registry.py  - ModelSpec + model discovery / registry
recorder.py         - Microphone capture (sounddevice) + Silero VAD
hotkey.py           - Global hotkey listener (hold / toggle modes)
injector.py         - Type / paste text into the focused window
notes_window.py     - Notes, Agenda & Reminders UI (CustomTkinter)
settings_window.py  - Settings UI (CustomTkinter)
widget.py           - Floating recording indicator
tray_icon.py        - System tray icon (pystray)
notifier.py         - Toast notifications + reminder scheduler
database.py         - SQLite storage (notes, appointments, reminders, settings)
paths.py            - Data path resolution (source vs frozen)
locales.py          - i18n string tables (EN, RU)
theme.py            - Unified colour palette and fonts
brand.py            - Title-bar branding assets
sounds.py           - Start / stop tones
autostart.py        - Registry autostart
logger.py           - Rotating file + console logger
```

## How to Contribute

### Reporting Bugs

Open an [issue](https://github.com/subfocusx/writher/issues) with:

- What you expected to happen
- What actually happened
- Steps to reproduce
- Your operating system and Python version
- Any relevant output from `writher.log`

### Suggesting Features

Open an issue with the `enhancement` label. Describe the use case and why it would be useful.

### Submitting Code

1. Fork the repository.
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Make your changes.
4. Test manually (run the app, try the feature).
5. Commit with a clear message: `git commit -m "feat: add your feature"`
6. Push to your fork: `git push origin feat/your-feature`
7. Open a Pull Request.

There's no rigid review process — just describe what you changed and why.

## Areas Where Help is Needed

### Porting to other platforms

WritHer currently targets Windows and uses a few platform-specific pieces:

- `injector.py` — uses the `keyboard` library to inject keystrokes into the focused window.
  A cross-platform alternative would need a per-OS input-injection strategy.
- `notifier.py` — Windows toast notifications (`winotify`).
- `tray_icon.py` — `pystray` (cross-platform, but the action menu is implemented per-OS).
- `widget.py` — a transparent, click-through overlay (uses Windows-specific Tk features).
- `autostart.py` — runs on login via the Windows registry.
- `paths.py` — resolves data under `%APPDATA%\WritHer` when frozen.

### New languages

Adding a language is straightforward:

1. Open `locales.py`.
2. Copy the `"en"` dictionary.
3. Translate all values.
4. Add it under your language code (e.g. `"de"`, `"es"`, `"fr"`).

No code changes beyond `locales.py` are needed.

### Additional ASR models

The model registry (`models_registry.py`) discovers `onnx-asr`-compatible models. If you have a
model that doesn't match the built-in families, extend the registry or make sure the folder
layout is detectable by `scan_dir`. Contributions that add new model families or improve the
registry (better dedupe, better default selection) are welcome.

### UI/UX improvements

The UI uses CustomTkinter with a unified theme in `theme.py`. All colours and fonts are
centralized there:

- Edit `theme.py` for colours and fonts.
- Edit `notes_window.py` or `settings_window.py` for layout.
- The floating widget (`widget.py`) uses raw Tkinter + PIL for the overlay behavior.

## Code Style

- No strict linter is enforced, but keep it clean and readable.
- Follow the existing patterns in the codebase.
- Use `log.info()` / `log.error()` for logging (never `print()` for diagnostics).
- Add i18n strings to `locales.py` for any user-facing text (both EN and RU).
- Use `theme.py` constants for colours and fonts in UI code.
- Persist user settings via `database.save_setting()` / `database.get_setting()`.
- Keep hard-coded paths out of source; use `paths.py` for data location.

## Commit Messages

We use conventional-style commit messages:

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `chore:` — maintenance, dependencies, config

## Questions?

Open an issue or start a discussion. No question is too small.
