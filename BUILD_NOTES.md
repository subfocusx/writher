# Build notes — v1.1.0

The build is reproducible entirely inside the project directory.
No global Python is required.

## Environment

- **Embedded Python**: `.python\python.exe` (CPython 3.11.9, embeddable layout)
- **Tcl/Tk 8.6.12**: extracted from `python-3.11.9-amd64.exe` full installer (per-user
  install into a throwaway `.python_full` directory that was deleted afterwards).
  Files placed in `.python\DLLs\`, `.python\tcl\`, and `.python\Lib\tkinter\`.
- **`.python\python311._pth`** lists `python311.zip / . / Lib / Lib\site-packages / DLLs / import site`
  so the embeddable can locate `tkinter` and `_tkinter.pyd` without `site.py` being broken.

## Working PyInstaller command

```powershell
.\.python\python.exe -m PyInstaller `
  --noconfirm --onedir --windowed --name Writher `
  --paths . --paths .python\Lib\site-packages `
  --collect-all onnx_asr --collect-all silero_vad --collect-all torch `
  --collect-all winotify --collect-all plyer --collect-all customtkinter `
  --collect-all darkdetect --collect-all noisereduce --collect-all pystray `
  --hidden-import soundfile --hidden-import noisereduce --hidden-import _tkinter `
  --add-data ".python\tcl;tcl" main.py
```

The `--collect-all pystray` and `--collect-all customtkinter` flags are mandatory —
both are imported inside function bodies (lazy imports), so PyInstaller's static
analysis misses them without `--collect-all`.

## Smoke test (2026-08-31)

```powershell
$p = Start-Process -FilePath '.\dist\Writher\Writher.exe' -PassThru `
     -RedirectStandardOutput '.\.smoke_out.log' `
     -RedirectStandardError '.\.smoke_err.log'
Start-Sleep -Seconds 6
# → ALIVE pid=…
```

**stderr:**
```
2026-08-31 00:51:48 [INFO] Loading ASR model: GigaAM v3 E2E RNN-T
2026-08-31 00:51:48 [INFO] Ready. AltGr=dictate, F7=retry, F8=re-paste.
```

Process stays alive in tray. Killing the smoke-test process does not crash anything.

## Tests

```powershell
.\.python\python.exe -m pytest -q
# 487 passed, 1 skipped, 7 warnings in ~20s
```

### Bug fixes added 2026-08-31 — five new tests cover them

The user reported that recorded phrases were being truncated at both ends and
that the same text was sometimes being recognised twice. Root causes and fixes:

1. **Pre-roll in `recorder.py`** — when the user pressed AltGr, the first ~250 ms
   of audio was lost because the stream was started and `recording` was set to
   `True` together, but the first callback fires only after one PortAudio
   block (~42 ms @ 48 kHz). Fix: keep a small pre-roll buffer of the last N
   blocks, flush it on the first frame after `recording=True`. New tests:
   `TestRecorderPreRoll` (3 cases).
2. **Drain before close in `recorder.py`** — PortAudio's internal ring buffer
   was being truncated on `stream.close()`, dropping the last ~100 ms of
   the held phrase. Fix: `time.sleep(0.1)` between `stream.stop()` and
   `stream.close()`. New tests: `TestRecorderDrain` (2 cases).
3. **Clipboard clear in `injector.py`** — after the simulated Ctrl+V pasted the
   dictated text, the clipboard was still holding that text, so a stray
   manual Ctrl+V elsewhere would re-paste the same phrase. Fix:
   `_clear_clipboard()` after the paste, with the text already in
   `recovery_notes.txt`. New tests: `TestClearClipboard` (3 cases).

### Bug fixes added 2026-08-31 — GigaAM CTC mid-utterance blanking

User reported that longer phrases (6-12 s of continuous speech) were getting
their middle cut off. Root cause: GigaAM v3 E2E CTC, when given long
utterances without a silence break, occasionally emits a blank window for
the middle slice. Fix in `asr_engine.py`: split any recording longer than
6 s into 6 s slices with 1.0 s overlap, transcribe each independently,
and stitch the pieces back with a longest-common-suffix/prefix word
matcher (`_stitch_overlap_texts`, k capped at 12). New tests:
`TestStitchOverlap` (9 cases in `tests/test_asr_overlap.py`).

### Bug fixes added 2026-08-31 — RNN-T single-pass (no CTC slicing)

User switched to GigaAM v3 E2E RNN-T and reported ~40% worse recognition:
words swapped and the tail duplicated ("слово. слово", "это реально ли так.
Это реально бы так"). Root cause: `transcribe()` routed *all* audio ≤ 30 s
through the 4 s overlap-slicer + stitcher that was designed for CTC
blanking. RNN-T is a transducer: it decodes a whole utterance in one pass,
so slicing made each piece "restart" the sentence — boundary words got
said twice and reordered. Fix in `asr_engine.py`:

- `_is_rnnt()` — routes by `model_type == "gigaam-v3-e2e-rnnt"`.
- `_transcribe_rnnt_locked()` — audio ≤ 30 s is one `recognize()` call
  (plus the 0.4 s silence tail pad), no slicing, no stitching.
  Audio > 30 s reuses overlap chunking with 30 s slices.
- `_transcribe_overlap_locked()` gained optional `slice_seconds` /
  `overlap_seconds` params so the RNN-T long-audio path can reuse it.
- CTC path is unchanged. Tests: all 33 in `test_asr_overlap.py` +
  `test_asr_engine.py` still pass; real-model smoke test
  (recovery wav, RNN-T fp32) verified single-pass decode and the 30 s
  overlap path for 34 s audio.

### Bug fixes added 2026-08-31 — Ctrl+V keybd_event timing + post-paste wait

User reported "в буфер не попадает" — text was being recognised and the
log showed `INJECT: text length=N` succeeding, but nothing appeared in
the target app and the buffer was empty. Two root causes, both fixed in
`injector.py`:

1. **`_send_ctrl_v` chord collapse** — `keybd_event` was firing the four
   events (Ctrl-down, V-down, V-up, Ctrl-up) back-to-back with no gaps.
   On a fast machine Windows can collapse the down/up pair into a
   single keystroke that the target app sees as Ctrl only, and V is
   dropped. Fix: 20 ms `time.sleep` between each `keybd_event` call.
   New test: `TestKeybdEventTiming` (1 case in `tests/test_injector.py`).
2. **Premature clipboard clear** — `_clear_clipboard()` was running
   only 200 ms after Ctrl+V. Heavy editors (Word, big contenteditable
   fields, Electron apps) can take 300-600 ms to read the clipboard
   after receiving the keypress, so our clear wiped the buffer before
   the paste completed. Fix: increased the post-paste wait to
   500 ms. Recovery file already has the text either way, but the
   user's screen now actually receives it. New test:
   `TestInjectPostPasteDelay` (1 case).

## Bundle

- `dist\Writher\Writher.exe` — 47.9 MB (windowed launcher)
- `dist\Writher\_internal\` — 658 MB, dominated by `torch/` (≈440 MB) and
  `torchaudio/`. `--exclude-module` for unused torch submodules is a future
  optimization; smoke-test passes first.

## Iterations

1. First build crashed at `main.py:9` with `ModuleNotFoundError: No module named 'tkinter'`.
   → Installed Tcl/Tk 8.6.12 into `.python\`.
2. Second build crashed at `notes_window.py:15` with `ModuleNotFoundError: No module named 'customtkinter'`.
   → `pip install customtkinter darkdetect`, then rebuilt.
3. Third build crashed at `tray_icon.py:35` with `ModuleNotFoundError: No module named 'pystray'`.
   → `pip install pystray`, added `--collect-all pystray` to PyInstaller, then rebuilt.
4. Fourth build — smoke test passes.
