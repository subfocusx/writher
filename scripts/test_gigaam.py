#!/usr/bin/env python3
"""
test_gigaam.py — GigaAM v3 E2E CTC benchmark: fp32 vs int8 via onnx-asr.

Usage:
    python scripts/test_gigaam.py

Requirements (installed automatically):
    onnx-asr     — ASR framework (onnxruntime, numpy, huggingface-hub)
    soundfile    — reading audio files

Models (automatically downloaded on first run):
    fp32  → repo "istupakov/gigaam-v3-onnx",  file v3_e2e_ctc.onnx   (~886 MB)
    int8  → repo "istupakov/gigaam-v3-onnx",  file v3_e2e_ctc.int8.onnx (~215 MB)

Audio files:
    Put .wav/.mp3/.ogg files into scripts/test_audio/
"""

import os, sys, time, wave, subprocess, tempfile, json
from pathlib import Path

# ── Memory ────────────────────────────────────────────────────────────────────

def get_rss_mb() -> float:
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1024 / 1024
    except Exception:
        pass
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        pass
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        class PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]
        pmc = PMC(); pmc.cb = ctypes.sizeof(PMC)
        h = kernel32.GetCurrentProcess()
        if not kernel32.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
            return 0.0
        return pmc.WorkingSetSize / 1024 / 1024
    except Exception:
        return 0.0


# ── Audio loading ──────────────────────────────────────────────────────────────

def load_audio(path: str | Path) -> tuple["np.ndarray", int]:
    path = str(path)
    try:
        import soundfile as sf
        data, sr = sf.read(path, dtype='float32')
        if data.ndim > 1:
            data = data.mean(axis=1)
        return _resample(data, sr, 16000)
    except ImportError:
        pass

    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    tmp.close()
    try:
        r = subprocess.run(
            ['ffmpeg', '-y', '-i', path, '-ar', '16000', '-ac', '1', '-acodec', 'pcm_s16le', tmp.name],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {r.stderr}")
        import numpy as np, array
        with wave.open(tmp.name, 'rb') as wf:
            sr = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
            samples = array.array('h', raw)
            audio = np.array(samples, dtype=np.float32) / 32768.0
        return audio, sr
    finally:
        os.unlink(tmp.name)


def _resample(audio, orig_sr, target_sr):
    if orig_sr == target_sr:
        return audio, orig_sr
    import numpy as np
    duration = len(audio) / orig_sr
    target_len = int(duration * target_sr)
    indices = np.linspace(0, len(audio) - 1, target_len)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32), target_sr


# ── Punctuation check ──────────────────────────────────────────────────────────
PUNCT_CHARS = frozenset('.,!?;:"()[]{}—–-…')

def has_punctuation(text: str, min_words: int = 15) -> bool:
    words = text.split()
    return len(words) >= min_words and any(c in PUNCT_CHARS for c in text)


# ── Config ────────────────────────────────────────────────────────────────────
MODEL_NAME = "gigaam-v3-e2e-ctc"
MODEL_REPO = "istupakov/gigaam-v3-onnx"
INT8_DIR   = Path.home() / ".cache" / "huggingface" / f"models--{MODEL_REPO.replace('/', '--')}-int8"
AUDIO_DIR  = Path(__file__).parent / "test_audio"


def ensure_int8_model() -> Path:
    """Download int8 model to a dedicated local dir if not already present."""
    INT8_DIR.mkdir(parents=True, exist_ok=True)

    needed = ["v3_e2e_ctc.int8.onnx", "v3_e2e_ctc_vocab.txt", "config.json"]
    present = [f.name for f in INT8_DIR.iterdir() if f.is_file()]
    missing = [n for n in needed if n not in present]

    if missing:
        print(f"       Downloading missing files: {missing}")
        from huggingface_hub import hf_hub_download
        for fname in missing:
            hf_hub_download(repo_id=MODEL_REPO, filename=fname, local_dir=str(INT8_DIR))
    else:
        print(f"       int8 files already in cache")

    for f in INT8_DIR.iterdir():
        if f.is_file():
            print(f"       {f.name}: {f.stat().st_size / 1024 / 1024:.1f} MB")
    return INT8_DIR


def run_benchmark(asr, audio_files: list[Path], label: str):
    """Transcribe audio files and collect metrics."""
    results = []
    total_transcribe = 0.0
    rss_start = get_rss_mb()

    for af in audio_files:
        try:
            audio, sr = load_audio(af)
            duration = len(audio) / sr
        except Exception as exc:
            print(f"  [skip] {af.name}: {exc}")
            continue

        t0 = time.monotonic()
        text = asr.recognize(audio, sample_rate=sr)
        elapsed = time.monotonic() - t0
        total_transcribe += elapsed
        rss_after = get_rss_mb()

        rtf = duration / elapsed if elapsed > 0 else 0
        ok_punct = has_punctuation(text)

        print(f"  [{label}] {af.name}: {duration:.1f}s | {elapsed:.2f}s | {rtf:.1f}x realtime | RSS {rss_after:.0f}MB | punct={'PASS' if ok_punct else 'WARN'}")
        print(f"         \"{text}\"")
        results.append(dict(file=af.name, duration=duration, time=elapsed,
                            rtf=rtf, rss_after=rss_after, punct=ok_punct, text=text))

    rss_peak = max((r['rss_after'] for r in results), default=rss_start)
    return results, total_transcribe, rss_start, rss_peak


def main():
    import numpy as np

    print("=" * 60)
    print("GigaAM v3 E2E CTC — fp32 vs int8 benchmark")
    print("=" * 60)

    # ── Ensure deps ────────────────────────────────────────────────────────
    deps = ["onnx-asr", "soundfile"]
    print("\n[setup] Installing:", " ".join(deps))
    r = subprocess.run([sys.executable, "-m", "pip", "install"] + deps, capture_output=True, text=True)
    if r.returncode != 0:
        print("[setup] FAILED:", r.stderr[-400:])
        sys.exit(1)
    print("[setup] Done.")

    # ── Packages ───────────────────────────────────────────────────────────
    print("\n[env]")
    r = subprocess.run([sys.executable, "-m", "pip", "list"], capture_output=True, text=True)
    for line in r.stdout.split('\n'):
        if 'onnxruntime' in line.lower() or 'onnx-asr' in line.lower():
            print(f"  {line.strip()}")

    import onnxruntime as ort
    print(f"  onnxruntime available EPs: {ort.get_available_providers()}")

    # ── Audio ─────────────────────────────────────────────────────────────
    suffixes = {'.wav', '.mp3', '.ogg', '.flac', '.m4a', '.opus'}
    audio_files = sorted(p for p in AUDIO_DIR.iterdir()
                         if p.is_file() and p.suffix.lower() in suffixes)

    if not audio_files:
        print(f"\n[audio] No files in {AUDIO_DIR} — put .wav/.mp3/.ogg there and re-run.")
        sys.exit(1)
    print(f"\n[audio] {len(audio_files)} file(s):")
    for af in audio_files:
        print(f"  {af.name}")

    # ── Prepare int8 local dir ─────────────────────────────────────────────
    print(f"\n[int8] Checking int8 model cache...")
    int8_dir = ensure_int8_model()

    # ── Benchmark fp32 ─────────────────────────────────────────────────────
    print(f"\n{'─' * 55}")
    print(f"BENCHMARK: fp32")
    print(f"{'─' * 55}")

    from onnx_asr import load_model

    rss_before_fp32 = get_rss_mb()
    print(f"  RSS before: {rss_before_fp32:.1f} MB")

    t0 = time.monotonic()
    asr_fp32 = load_model(MODEL_NAME, providers=["CPUExecutionProvider"])
    load_fp32 = time.monotonic() - t0
    rss_after_fp32 = get_rss_mb()

    sess_ep_fp32 = asr_fp32.asr._model.get_providers()[0]
    print(f"  Model loaded in {load_fp32:.1f}s")
    print(f"  RSS after load: {rss_after_fp32:.1f} MB (delta {rss_after_fp32 - rss_before_fp32:.1f} MB)")
    print(f"  Session EP: {sess_ep_fp32}")

    results_fp32, total_t_fp32, _, _ = run_benchmark(asr_fp32, audio_files, "fp32")

    # ── Benchmark int8 ─────────────────────────────────────────────────────
    print(f"\n{'─' * 55}")
    print(f"BENCHMARK: int8 (quantized)")
    print(f"{'─' * 55}")

    rss_before_int8 = get_rss_mb()
    print(f"  RSS before: {rss_before_int8:.1f} MB")

    t0 = time.monotonic()
    asr_int8 = load_model(MODEL_NAME, path=str(int8_dir),
                           quantization="int8", providers=["CPUExecutionProvider"])
    load_int8 = time.monotonic() - t0
    rss_after_int8 = get_rss_mb()

    sess_ep_int8 = asr_int8.asr._model.get_providers()[0]
    print(f"  Model loaded in {load_int8:.1f}s")
    print(f"  RSS after load: {rss_after_int8:.1f} MB (delta {rss_after_int8 - rss_before_int8:.1f} MB)")
    print(f"  Session EP: {sess_ep_int8}")

    results_int8, total_t_int8, _, _ = run_benchmark(asr_int8, audio_files, "int8")

    # ── Comparison table ───────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("COMPARISON TABLE")
    print(f"{'=' * 60}")
    hdr = f"{'':15} {'fp32':>10} {'int8':>10} {'diff':>10}"
    print(hdr)
    print("-" * 50)

    rss_fp32 = rss_after_fp32 - rss_before_fp32
    rss_int8 = rss_after_int8 - rss_before_int8
    print(f"{'RSS delta (MB)':15} {rss_fp32:>10.1f} {rss_int8:>10.1f} {rss_int8 - rss_fp32:>+10.1f}")
    print(f"{'Load time (s)':15} {load_fp32:>10.1f} {load_int8:>10.1f} {load_int8 - load_fp32:>+10.1f}")
    print(f"{'Total transcribe (s)':15} {total_t_fp32:>10.2f} {total_t_int8:>10.2f} {total_t_int8 - total_t_fp32:>+10.2f}")

    if results_fp32 and results_int8:
        for rf, ri in zip(results_fp32, results_int8):
            rtf_d = ri['rtf'] - rf['rtf']
            print(f"{'RTF (x realtime)':15} {rf['rtf']:>10.1f} {ri['rtf']:>10.1f} {rtf_d:>+10.1f}")
            break  # per-file rows above already printed

    print()
    print(f"  fp32 model file : {MODEL_REPO}/v3_e2e_ctc.onnx (~886 MB on disk)")
    print(f"  int8 model file : {MODEL_REPO}/v3_e2e_ctc.int8.onnx (~215 MB on disk)")
    print(f"  fp32 RSS delta  : {rss_fp32:.1f} MB")
    print(f"  int8 RSS delta  : {rss_int8:.1f} MB")
    print()

    # ── Text comparison ────────────────────────────────────────────────────
    if results_fp32 and results_int8:
        print(f"  {'='*55}")
        print(f"  TEXT COMPARISON (fp32 vs int8)")
        print(f"  {'='*55}")
        for rf, ri in zip(results_fp32, results_int8):
            same = rf['text'] == ri['text']
            print(f"\n  [{rf['file']}]")
            print(f"  fp32: {rf['text']!r}")
            print(f"  int8: {ri['text']!r}")
            print(f"  Match: {'YES' if same else 'DIFFERENT'}")

            # Word-level diff
            wf = set(rf['text'].split())
            wi = set(ri['text'].split())
            only_fp = wf - wi
            only_int = wi - wf
            if only_fp or only_int:
                print(f"  Words only in fp32: {only_fp}")
                print(f"  Words only in int8: {only_int}")

            if not rf['punct'] and ri['punct']:
                print(f"  NOTE: fp32 missing punctuation, int8 has it")
            elif rf['punct'] and not ri['punct']:
                print(f"  NOTE: fp32 has punctuation, int8 missing it")


if __name__ == "__main__":
    main()
