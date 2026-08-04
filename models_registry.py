"""Model registry — discovery + auto-detection of onnx-asr models.

Scans model folders (bundled with the app + user-specified folders) and
auto-detects the onnx-asr ``model_type`` and quantization from the files
present, so a folder containing a model only needs to be added once and it
shows up in the settings UI.

The onnx-asr file naming convention is:

    <base>.onnx          -> fp32 (no quantization)
    <base>.<quant>.onnx  -> quantized (e.g. <base>.int8.onnx)

This module is dependency-light (only stdlib + logger) and never imports
``asr_engine``, so it can be used by the UI and tests without cycles.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from logger import log


# onnx-asr model families: (model_type, (base filename tokens required)).
# The base token is matched as <base>.onnx (fp32) or <base>.<quant>.onnx.
_FAMILIES: list[tuple[str, tuple[str, ...]]] = [
    ("gigaam-v3-e2e-ctc", ("v3_e2e_ctc",)),
    ("gigaam-v3-e2e-rnnt", ("v3_e2e_rnnt_encoder", "v3_e2e_rnnt_decoder", "v3_e2e_rnnt_joint")),
    ("gigaam-multilingual-ctc", ("multilingual_ctc",)),
    ("gigaam-multilingual-large-ctc", ("multilingual_large_ctc",)),
    ("gigaam-v2-ctc", ("v2_ctc",)),
    ("gigaam-v2-rnnt", ("v2_rnnt_encoder", "v2_rnnt_decoder", "v2_rnnt_joint")),
]

# Human-friendly labels for the known families.
_NICE: dict[str, str] = {
    "gigaam-v3-e2e-ctc": "GigaAM v3 E2E CTC",
    "gigaam-v3-e2e-rnnt": "GigaAM v3 E2E RNN-T",
    "gigaam-multilingual-ctc": "GigaAM Multilingual CTC",
    "gigaam-multilingual-large-ctc": "GigaAM Multilingual Large CTC",
    "gigaam-v2-ctc": "GigaAM v2 CTC",
    "gigaam-v2-rnnt": "GigaAM v2 RNN-T",
}

# onnx-asr model_type names accepted through the generic config.json path.
_KNOWN_TYPES = set(_NICE) | {
    "gigaam-v3-ctc", "gigaam-v3-rnnt",
    "nemo-conformer-ctc", "kaldi-rnnt", "t-one-ctc",
    "vosk", "whisper", "whisper-ort",
}


def nice_label(model_type: str) -> str:
    """Return a human-friendly label for a model_type."""
    return _NICE.get(model_type, model_type)


@dataclass(frozen=True)
class ModelSpec:
    id: str
    display_name: str
    model_type: str
    path: str
    quantization: str | None = None
    default: bool = False

    @property
    def label(self) -> str:
        """Dropdown label — display_name + quantization tag."""
        if self.quantization:
            return f"{self.display_name} ({self.quantization})"
        return self.display_name

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict, default: "ModelSpec | None" = None) -> "ModelSpec | None":
        if not d or not isinstance(d, dict):
            return default if default is not None else None
        try:
            return cls(
                id=str(d["id"]),
                display_name=str(d["display_name"]),
                model_type=str(d["model_type"]),
                path=str(d["path"]),
                quantization=d.get("quantization"),
                default=bool(d.get("default", False)),
            )
        except (KeyError, ValueError, TypeError):
            log.warning("Stored model spec is invalid; falling back to default.")
            return default if default is not None else None


# ── Path helpers ─────────────────────────────────────────────────────────────

def bundled_models_dir() -> str:
    """Directory bundled with the app (frozen -> _internal/models, else models/)."""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "_internal", "models")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")


# ── Detection ────────────────────────────────────────────────────────────────

def _match_base(path: Path, base: str):
    """Return ``(Model file, quantization)`` for a base token, else ``(None, None)``.

    Matches ``<base>.onnx`` (fp32) first, then ``<base>.<quant>.onnx``.
    """
    exact = list(path.glob(f"{base}.onnx"))
    if len(exact) == 1:
        return exact[0], None
    quanted = list(path.glob(f"{base}.*.onnx"))
    if len(quanted) == 1:
        name = quanted[0].name
        inner = name[len(base) + 1:-len(".onnx")]
        return quanted[0], (inner or None)
    return None, None


def _make_spec(p: Path, model_type: str, quantization: str | None) -> ModelSpec:
    qtag = quantization or "fp32"
    return ModelSpec(
        id=f"{model_type}::{qtag}::{p.as_posix()}",
        display_name=nice_label(model_type),
        model_type=model_type,
        path=str(p),
        quantization=quantization,
        default=False,
    )


def detect_spec(path: str | os.PathLike) -> ModelSpec | None:
    """Try to detect a single model in ``path``.

    Returns a :class:`ModelSpec` if the directory looks like a known onnx-asr
    model, else ``None``.
    """
    p = Path(path)
    if not p.is_dir():
        return None

    for model_type, bases in _FAMILIES:
        found: dict[str, Path] = {}
        quant: str | None = None
        ok = True
        for base in bases:
            file, q = _match_base(p, base)
            if file is None:
                ok = False
                break
            found[base] = file
            if q is not None:
                quant = q
        if ok and found:
            return _make_spec(p, model_type, quant)

    # Generic fallback: a config.json that names a known onnx-asr model_type.
    cfg = p / "config.json"
    if cfg.is_file():
        try:
            cfg_data = json.loads(cfg.read_text(encoding="utf-8"))
        except Exception:
            cfg_data = None
        if isinstance(cfg_data, dict):
            mt = cfg_data.get("model_type")
            if mt in _KNOWN_TYPES:
                return _make_spec(p, mt, None)

    return None


def scan_dir(root: str | os.PathLike) -> list[ModelSpec]:
    """Scan a root directory: itself plus its immediate subdirectories."""
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    candidates = [root_path] + [c for c in root_path.iterdir() if c.is_dir()]
    specs: list[ModelSpec] = []
    for c in candidates:
        spec = detect_spec(c)
        if spec is not None:
            specs.append(spec)
    return specs


def builtin_default_spec() -> ModelSpec | None:
    """Return the bundled int8 GigaAM v3 E2E CTC spec (marked ``default``).

    Returns ``None`` when the bundled model is not present (e.g. the folder
    was removed after packaging); callers should then fall back to the
    download path handled by the engine.
    """
    bdir = bundled_models_dir()
    if not os.path.isdir(bdir):
        return None
    for spec in scan_dir(bdir):
        if spec.model_type == "gigaam-v3-e2e-ctc" and spec.quantization == "int8":
            return ModelSpec(
                id=spec.id,
                display_name=spec.display_name,
                model_type=spec.model_type,
                path=spec.path,
                quantization=spec.quantization,
                default=True,
            )
    return None


def discover_models(custom_dirs: list[str] | None = None) -> list[ModelSpec]:
    """Discover all models from the bundled dir + custom dirs.

    Deduplicates by ``(model_type, quantization)`` keeping the first match,
    so a bundled int8 model does not duplicate an identical one found in a
    custom folder.
    """
    roots: list[str] = []
    bdir = bundled_models_dir()
    if os.path.isdir(bdir):
        roots.append(bdir)
    for d in (custom_dirs or []):
        if d and os.path.isdir(d) and d not in roots:
            roots.append(d)

    specs: list[ModelSpec] = []
    seen: set[tuple[str, str | None]] = set()
    for root in roots:
        for spec in scan_dir(root):
            key = (spec.model_type, spec.quantization)
            if key in seen:
                continue
            seen.add(key)
            specs.append(spec)
    return specs
