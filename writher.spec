# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for WritHer."""

import os
import site
import customtkinter

block_cipher = None

# CustomTkinter assets path
ctk_path = os.path.dirname(customtkinter.__file__)

# Silero VAD assets path — bundle even if faster_whisper not importable
try:
    import faster_whisper as _fw
    fw_path = os.path.dirname(_fw.__file__)
except ImportError:
    fw_path = None
    for _sp in site.getsitepackages():
        _p = os.path.join(_sp, "faster_whisper")
        if os.path.isdir(_p):
            fw_path = _p
            break

# onnx_asr package path (for data files)
try:
    import onnx_asr as _oaxr
    onnx_asr_path = os.path.dirname(_oaxr.__file__)
    onnx_asr_version = _oaxr.__version__
except ImportError:
    onnx_asr_version = "0.12.0"
    onnx_asr_path = None
    for _sp in site.getsitepackages():
        _p = os.path.join(_sp, "onnx_asr")
        if os.path.isdir(_p):
            onnx_asr_path = _p
            break

# onnx_asr dist-info for importlib.metadata (fixes PackageNotFoundError in frozen exe)
if onnx_asr_path:
    onnx_asr_dist_info = os.path.join(
        onnx_asr_path, "..",
        f"onnx_asr-{onnx_asr_version}.dist-info"
    )
else:
    onnx_asr_dist_info = None

# Bundle the nvidia-cublas / cuda-runtime / cuda-nvrtc DLLs that
# ctranslate2 needs when running on GPU (DEVICE="cuda"). Without these
# the frozen exe fails with: "Library cublas64_12.dll is not found".
# They are pip-installed under <venv>/Lib/site-packages/nvidia/*/bin/.
_nvidia_datas = []
for _sitedir in site.getsitepackages():
    if not _sitedir or "site-packages" not in _sitedir:
        continue
    for _pkg in ("cublas", "cuda_runtime", "cuda_nvrtc"):
        _bin = os.path.join(_sitedir, "nvidia", _pkg, "bin")
        if os.path.isdir(_bin):
            _nvidia_datas.append((_bin, os.path.join("nvidia", _pkg, "bin")))


def _build_datas(ctk, fw, oaxr_path, oaxr_dist):
    items = [
        # CustomTkinter theme assets
        (ctk, 'customtkinter'),
    ]
    # Silero VAD ONNX model — only if faster_whisper is available
    if fw:
        items.append((os.path.join(fw, 'assets'), os.path.join('faster_whisper', 'assets')))
    # onnx_asr static data and metadata
    if oaxr_path and oaxr_dist:
        items.append((os.path.join(oaxr_path, 'preprocessors', 'data'), os.path.join('onnx_asr', 'preprocessors', 'data')))
        items.append((oaxr_dist, f'onnx_asr-{onnx_asr_version}.dist-info'))
    # GigaAM int8 model (~225 MB)
    items += [
        ('models', 'models'),
        ('writher.ico', '.'),
        ('writher_icon.png', '.'),
        ('img', 'img'),
        # brand.py — needed by notifier.py (frozen exe loses module-level imports)
        ('brand.py', '.'),
    ]
    # NVIDIA CUDA DLLs
    items += _nvidia_datas
    return items


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=_build_datas(ctk_path, fw_path, onnx_asr_path, onnx_asr_dist_info),

    hiddenimports=[
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'PIL._tkinter_finder',
        'customtkinter',
        'onnx_asr',
        'soundfile',
        'onnxruntime',
        'torch',
        'torchaudio',
        'torchvision',
        'brand',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy ML frameworks not needed by WritHer
        'tensorflow', 'tensorboard', 'tf_keras', 'keras',
        'scipy', 'matplotlib', 'pandas', 'sklearn', 'scikit-learn',
        'pytest', 'IPython', 'notebook', 'jupyter',
        'lxml', 'pygments', 'cv2', 'opencv',
        'transformers', 'datasets', 'accelerate',
        # pywin32 partial install from host env causes build errors
        'pywin32', 'pythoncom', 'pywintypes', 'win32com',
        'win32api', 'win32file', 'win32pipe', 'win32event',
        # GigaAM's vad_utils depends on pyannote (not installed)
        'pyannote', 'pyannote.audio',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WritHer_v2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,         # No console window — runs as background tray app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='writher.ico',     # Pandora Blackboard eyes icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WritHer_v2',
)