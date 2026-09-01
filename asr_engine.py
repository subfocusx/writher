"""GigaAM v3 E2E CTC ASR engine via onnx-asr — Russian-only.

Single backend only. No factory, no switching.
"""

import threading
import os
import re
import site
import sys
from pathlib import Path

import numpy as np
from logger import log
from models_registry import ModelSpec, nice_label, builtin_default_spec


_PUNCT_RUN = re.compile(r"^[^\w]+|[^\w]+$")


def _stitch_overlap_texts(pieces: list[str], overlap_samples: int, sr: int) -> str:
    """Join overlapping transcription pieces, removing duplicated text in
    the overlap region.

    Strategy: walk adjacent pairs, find the longest suffix of piece[i]
    that matches a prefix of piece[i+1] over a window of words. Keep that
    shared span only once.

    Comparison is *normalized*: the ASR decoder tends to restart a
    "sentence" at a slice boundary (capitalising the first word, adding a
    full stop, gluing commas to the previous word), so raw token matching
    misses the overlap and duplicates the tail. We therefore compare
    lowercase, edge-punctuation-stripped tokens, but always emit the
    original tokens. The search window is capped by the real overlap
    duration (approx. words per second), so a model hallucination that
    "repeats" more than the physical overlap cannot eat genuine content.

    Falls back to joining with a space if no good overlap match is found
    (in which case the model just didn't repeat the boundary words).
    """
    if not pieces:
        return ""
    if len(pieces) == 1:
        return pieces[0].strip()

    def _tokenize(s: str) -> list[str]:
        return [w for w in re.split(r"\s+", s.strip()) if w]

    def _norm(w: str) -> str:
        """Case- and edge-punctuation-insensitive form, used for comparison only."""
        return _PUNCT_RUN.sub("", w.lower())

    # Max words the real overlap can cover: speech ~4 words/sec, +2 safety.
    overlap_secs = (overlap_samples or 0) / sr if sr else 0.0
    cap = max(4, int(overlap_secs * 4) + 2) if overlap_secs > 0 else 12

    def _lcp_suffix_prefix(a: list[str], b: list[str]) -> int:
        """Longest k such that norm(a[-k:]) == norm(b[:k]). Capped at ``cap``."""
        if not a or not b:
            return 0
        max_k = min(cap, len(a), len(b))
        na = [_norm(w) for w in a]
        nb = [_norm(w) for w in b]
        for k in range(max_k, 0, -1):
            if na[-k:] == nb[:k]:
                return k
        return 0

    out_tokens: list[str] = []
    prev_tokens: list[str] = []
    for i, piece in enumerate(pieces):
        tokens = _tokenize(piece)
        if not tokens:
            continue
        if i == 0:
            out_tokens.extend(tokens)
            prev_tokens = tokens
            continue
        k = _lcp_suffix_prefix(prev_tokens, tokens)
        if k > 0:
            out_tokens.extend(tokens[k:])
        else:
            out_tokens.extend(tokens)
        prev_tokens = tokens

    return " ".join(out_tokens).strip()


# ── CUDA DLL path registration (Windows) ───────────────────────────────────

def _register_cuda_dll_paths():
    """Make nvidia-cublas / cuda-runtime / cuda-nvrtc DLLs findable."""
    candidates = []
    candidates += list(getattr(site, "getsitepackages", lambda: [])())
    candidates += [os.path.dirname(os.path.abspath(__file__))]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(meipass)
    if getattr(sys, "frozen", False):
        candidates.append(os.path.dirname(sys.executable))

    seen_bins = set()
    for site_dir in candidates:
        if not site_dir:
            continue
        for pkg in ("cublas", "cuda_runtime", "cuda_nvrtc"):
            bin_dir = os.path.join(site_dir, "nvidia", pkg, "bin")
            if os.path.isdir(bin_dir) and bin_dir not in seen_bins:
                seen_bins.add(bin_dir)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                try:
                    os.add_dll_directory(bin_dir)
                except (OSError, AttributeError):
                    pass


# ── Model path resolution ────────────────────────────────────────────────────

_INT8_DIR: str | None = None
_INT8_LOCK = threading.Lock()


def _int8_model_dir() -> str:
    """Path to locally-cached int8 model.

    Tries in order:
      1. <script_dir>/models/           (bundled with app, dev and frozen)
      2. ~/.cache/huggingface/models--istupakov--gigaam-v3-onnx-int8  (HF hub cache)

    Thread-safe: at most one thread performs the (slow) directory walk +
    HuggingFace download even if many threads call this concurrently.
    Double-checked locking: the fast path reads the global without the
    lock (safe because str is immutable and we only ever write a single
    reference). The slow path takes the lock for the full resolution.
    """
    global _INT8_DIR
    if _INT8_DIR is not None:
        return _INT8_DIR
    with _INT8_LOCK:
        if _INT8_DIR is not None:
            return _INT8_DIR
        _INT8_DIR = _resolve_int8_dir_unlocked()
    return _INT8_DIR


def _resolve_int8_dir_unlocked() -> str:
    """Inner helper: must be called with _INT8_LOCK held.

    Same logic as the previous in-line body; extracted so the lock scope
    is unambiguous.
    """
    # 1. Pre-downloaded location used during development / benchmarking
    if getattr(sys, "frozen", False):
        # In PyInstaller onedir mode, executable is at <app>/WritHer_v2.exe,
        # and _internal/ is a sibling subdirectory containing all bundled assets.
        _base = os.path.dirname(sys.executable)
        pre_downloaded = os.path.join(_base, "_internal", "models")
    else:
        pre_downloaded = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    if Path(pre_downloaded, "v3_e2e_ctc.int8.onnx").exists():
        return pre_downloaded

    # 2. HuggingFace hub cache (network needed on first run)
    repo = "istupakov/gigaam-v3-onnx"
    cache_dir = Path.home() / ".cache" / "huggingface" / f"models--{repo.replace('/', '--')}-int8"
    cache_dir.mkdir(parents=True, exist_ok=True)

    needed = {"v3_e2e_ctc.int8.onnx", "v3_e2e_ctc_vocab.txt", "config.json"}
    present = {f.name for f in cache_dir.iterdir() if f.is_file()}
    missing = needed - present

    expected_sizes = {
        "v3_e2e_ctc.int8.onnx": 224_893_347,   # ~225 MB
        "v3_e2e_ctc_vocab.txt": 2_007,
        "config.json": 135,
    }
    min_sizes = {
        "v3_e2e_ctc.int8.onnx": 100_000_000,
    }

    corrupt = []
    for fname in present:
        if fname in expected_sizes:
            fpath = cache_dir / fname
            actual = fpath.stat().st_size
            min_sz = min_sizes.get(fname, expected_sizes[fname])
            if actual < min_sz:
                corrupt.append((fname, actual, min_sz))
                log.warning("Corrupt file in HF cache: %s (%d bytes, expected ≥%d) — will re-download",
                            fname, actual, min_sz)

    if missing or corrupt:
        log.info("Downloading GigaAM int8 model files from HuggingFace ...")
        from huggingface_hub import hf_hub_download
        download_set = missing | {f for f, _, _ in corrupt}
        for fname in sorted(download_set):
            path = hf_hub_download(
                repo_id=repo,
                filename=fname,
                local_dir=str(cache_dir),
            )
            actual_size = os.path.getsize(path)
            if fname in expected_sizes:
                min_sz = min_sizes.get(fname, expected_sizes[fname])
                if actual_size < min_sz:
                    os.remove(path)
                    raise RuntimeError(
                        f"Downloaded {fname} is too small ({actual_size} bytes, "
                        f"expected ≥{min_sz}). File is corrupt — removed from cache."
                    )
        log.info("Download complete.")

    return str(cache_dir)


def _load_onnx_asr():
    return __import__("onnx_asr", fromlist=["load_model"])


def default_spec() -> ModelSpec:
    """The built-in default model spec (bundled int8 GigaAM v3 CTC).

    Prefers the spec discovered from the bundled ``models`` dir so its id
    matches what the registry/UI discovers; falls back to the download path
    (frozen / HuggingFace cache) when the bundled folder is absent.
    """
    try:
        builtin = builtin_default_spec()
    except Exception:
        builtin = None
    if builtin is not None:
        return builtin
    return ModelSpec(
        id="builtin::gigaam-v3-e2e-ctc",
        display_name=nice_label("gigaam-v3-e2e-ctc"),
        model_type="gigaam-v3-e2e-ctc",
        path=_int8_model_dir(),
        quantization="int8",
        default=True,
    )


# ── Engine ──────────────────────────────────────────────────────────────────

class GigaAMEngine:
    """GigaAM v3 E2E CTC via onnx-asr — Russian-only ASR.

    Uses the int8-quantized ONNX model (~225 MB on disk, ~244 MB RSS).
    No torch, no faster-whisper.
    """

    def __init__(self, spec: ModelSpec | None = None):
        self._spec = spec
        self._loaded_spec: ModelSpec | None = None
        self._asr = None
        self._sample_rate = 16000
        self._lock = threading.RLock()

    # ── spec / lifecycle ──────────────────────────────────────────────────

    @property
    def current_spec(self) -> ModelSpec:
        """The spec currently in use (or the one that would load next)."""
        if self._spec is not None:
            return self._spec
        return default_spec()

    def _resolved_spec(self) -> ModelSpec:
        return self._spec if self._spec is not None else default_spec()

    def _load_locked(self) -> None:
        """Load ``_resolved_spec()``. Caller must hold ``self._lock``."""
        if self._asr is not None:
            return
        spec = self._resolved_spec()
        try:
            onnx_asr = _load_onnx_asr()
            load_model = onnx_asr.load_model
        except Exception as exc:
            log.error("Failed to import onnx_asr: %s", exc)
            raise
        log.info("Loading ASR model: %s", spec.label)
        _register_cuda_dll_paths()
        self._asr = load_model(
            spec.model_type,
            path=spec.path,
            quantization=spec.quantization,
            providers=["CPUExecutionProvider"],
        )
        self._loaded_spec = spec
        log.info("ASR model loaded: %s", spec.label)

    def _unload_locked(self) -> None:
        """Release the ONNX session. Caller must hold ``self._lock``."""
        if self._asr is None:
            return
        del self._asr
        self._asr = None
        import gc
        gc.collect()
        log.info("ASR model unloaded.")

    def load(self) -> None:
        """Load the configured model (no-op if already loaded)."""
        with self._lock:
            self._load_locked()

    def unload(self) -> None:
        """Release the ONNX session (no-op if not loaded)."""
        with self._lock:
            self._unload_locked()

    def switch(self, spec: ModelSpec) -> None:
        """Hot-swap to another model: unload the current one, load ``spec``.

        Blocks transcription while swapping (the same reentrant lock guards
        ``transcribe()``), so dictation is paused for a few seconds.
        """
        with self._lock:
            if self._loaded_spec is not None and self._asr is not None \
               and self._loaded_spec.model_type == spec.model_type \
               and self._loaded_spec.quantization == spec.quantization:
                log.info("Model already active: %s", spec.label)
                self._spec = spec
                return
            log.info("Switching ASR model -> %s", spec.label)
            self._unload_locked()
            self._spec = spec
            self._load_locked()

    def warmup(self) -> None:
        """Run a short inference to warm up the ONNX session."""
        with self._lock:
            self._load_locked()
            silence = np.zeros(int(self._sample_rate * 0.5), dtype=np.float32)
            self._transcribe_locked(silence)

    # ── transcription ─────────────────────────────────────────────────────

    _CHUNK_SECONDS = 30  # Max chunk size before using chunked transcription
    _SLICE_SECONDS = 4  # Slice length for short-audio overlap chunking
    _SLICE_OVERLAP = 1.0  # Overlap between slices (helps CTC avoid mid-audio blanking)
    _TAIL_PAD_SECONDS = 0.4  # Silence padding appended to each slice so CTC
                              # doesn't blank the trailing words (a known
                              # GigaAM v3 behaviour: the model needs a
                              # silence tail to emit the final token).
    _RNNT_MODEL_TYPE = "gigaam-v3-e2e-rnnt"  # Transducer models decode whole
                                             # utterances — no CTC slicing.

    def _transcribe_locked(self, audio: np.ndarray) -> str:
        """Run ASR on a float32 waveform. Caller must hold ``self._lock``."""
        self._load_locked()
        duration = len(audio) / self._sample_rate

        if duration <= self._CHUNK_SECONDS:
            return self._asr.recognize(audio, sample_rate=self._sample_rate)

        log.info("Long audio (%.1fs), chunking into %ds segments", duration, self._CHUNK_SECONDS)
        chunk_size = int(self._CHUNK_SECONDS * self._sample_rate)
        texts = []

        for i in range(0, len(audio), chunk_size):
            chunk = audio[i:i + chunk_size]
            text = self._asr.recognize(chunk, sample_rate=self._sample_rate)
            texts.append(text)
            log.info("Chunk %d: %.1fs audio -> %d chars: %r", i // chunk_size,
                     len(chunk) / self._sample_rate, len(text), text[:200])

        result = " ".join(texts)
        log.info("Chunked transcription: %d chars total", len(result))
        return result

    def _transcribe_overlap_locked(self, audio: np.ndarray,
                                   slice_seconds: float | None = None,
                                   overlap_seconds: float | None = None) -> str:
        """Transcribe short-to-medium audio with overlapping slices.

        CTC models (GigaAM v3) tend to blank out on the *middle* of long
        continuous speech when there's no clear silence break — even on a
        single-pass recognize() of 4-12 s audio. Slicing into ~4 s windows
        with 1 s overlap forces the model to re-attend to each region with
        fresh context, dramatically reducing mid-utterance drops.

        Each slice is also padded with a short silence tail (see
        ``_TAIL_PAD_SECONDS``) so the CTC decoder emits its final token
        instead of swallowing the last word into the silence region.

        Slices are joined by stitching on the longest common suffix/prefix
        of the words in the overlap region.

        ``slice_seconds`` / ``overlap_seconds`` optionally override the
        class defaults (used by RNN-T long-audio chunking).
        """
        self._load_locked()
        sr = self._sample_rate
        duration = len(audio) / sr
        slice_len = int((slice_seconds if slice_seconds is not None else self._SLICE_SECONDS) * sr)
        overlap = int((overlap_seconds if overlap_seconds is not None else self._SLICE_OVERLAP) * sr)
        step = slice_len - overlap
        tail_pad = int(self._TAIL_PAD_SECONDS * sr)

        if len(audio) <= slice_len:
            # Single slice: still pad with silence so the trailing words
            # of an utterance that ends right at the recording boundary
            # aren't lost to CTC silence-suppression.
            padded = np.concatenate([audio, np.zeros(tail_pad, dtype=audio.dtype)])
            return self._asr.recognize(padded, sample_rate=sr)

        log.info("Overlap-slicing %.2fs audio: %ds slices, %.1fs overlap, %.2fs tail pad",
                 duration, slice_len / sr, overlap / sr,
                 self._TAIL_PAD_SECONDS)
        pieces: list[str] = []
        i = 0
        idx = 0
        while i < len(audio):
            chunk = audio[i:i + slice_len]
            if len(chunk) < int(0.3 * sr):  # < 0.3s tail — drop
                break
            # Append silence padding so the last word of each slice isn't
            # swallowed by the decoder's silence region.
            padded_chunk = np.concatenate([chunk, np.zeros(tail_pad, dtype=chunk.dtype)])
            text = self._asr.recognize(padded_chunk, sample_rate=sr)
            log.info("Slice %d (%.2fs -> %.2fs): %d chars: %r",
                     idx, i / sr, min(i + len(chunk), len(audio)) / sr, len(text),
                     text[:200])
            pieces.append(text)
            if i + len(chunk) >= len(audio):
                break
            i += step
            idx += 1

        return _stitch_overlap_texts(pieces, overlap_samples=overlap, sr=sr)

    def _is_rnnt(self) -> bool:
        """True when the active model is the E2E RNN-T (transducer)."""
        try:
            return self._resolved_spec().model_type == self._RNNT_MODEL_TYPE
        except Exception:
            return False

    def _transcribe_rnnt_locked(self, audio: np.ndarray) -> str:
        """Transcribe with the E2E RNN-T model — no CTC slicing.

        The transducer decodes an utterance with full context in one pass;
        cutting it into 4 s slices with 1 s overlap is what caused the
        tail duplicates and word reordering (each slice "restarts" the
        sentence, so boundary words get said twice and punctuation hops).
        Audio up to ``_CHUNK_SECONDS`` (30 s) is therefore recognized as
        a single unit (plus the silence tail pad so the final words are
        not swallowed). Longer audio reuses overlap chunking with 30 s
        slices so stitching still drops only the small true overlap.
        """
        self._load_locked()
        sr = self._sample_rate
        duration = len(audio) / sr
        tail_pad = int(self._TAIL_PAD_SECONDS * sr)

        if duration <= self._CHUNK_SECONDS:
            padded = np.concatenate([audio, np.zeros(tail_pad, dtype=audio.dtype)])
            text = self._asr.recognize(padded, sample_rate=sr)
            log.info("RNN-T single pass: %.2fs audio -> %d chars: %r",
                     duration, len(text), text[:200])
            return text

        log.info("RNN-T long audio (%.1fs): overlap chunking with %ds slices",
                 duration, self._CHUNK_SECONDS)
        return self._transcribe_overlap_locked(
            audio, slice_seconds=float(self._CHUNK_SECONDS),
            overlap_seconds=self._SLICE_OVERLAP)

    def transcribe(self, audio: np.ndarray) -> str:
        """Run ASR on a float32 waveform (mono, 16 kHz).

        The E2E RNN-T model decodes the whole utterance in one pass (no
        slicing), because for a transducer the CTC-style 4 s overlap
        slicing caused boundary words to be repeated/reordered. Longer
        audio (>30 s) is chunked into 30 s overlapping slices. The CTC
        models keep the existing 4 s overlap-slice path.
        """
        with self._lock:
            if self._is_rnnt():
                return self._transcribe_rnnt_locked(audio)
            duration = len(audio) / self._sample_rate if self._sample_rate else 0
            if duration <= self._CHUNK_SECONDS:
                return self._transcribe_overlap_locked(audio)
            return self._transcribe_locked(audio)


# ── Singleton factory (single backend, no switching) ────────────────────────

_engine: GigaAMEngine | None = None


def create_engine(spec: ModelSpec | None = None) -> GigaAMEngine:
    """Return the singleton GigaAM engine instance (optionally pre-set a spec)."""
    global _engine
    if _engine is None:
        _engine = GigaAMEngine(spec)
    elif spec is not None and _engine._spec is None:
        _engine._spec = spec
    return _engine
