"""pytest conftest — stubs and shared fixtures for WritHer tests."""
import ctypes
import os
import sys
import types
import threading
import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Skip test modules that need optional dependencies not present in this
# environment (the project's embedded Python on Windows ships without
# tkinter by design). This is the recommended pytest pattern: missing
# optional dep → skip collection, not a hard collection error.
# ─────────────────────────────────────────────────────────────────────────────
collect_ignore_glob = []

try:
    import tkinter  # noqa: F401
except Exception:
    # The embedded Python that ships with the project (`.python\python.exe`)
    # doesn't include tkinter by design — adding it would mean downloading
    # tcl/tk DLLs and stitching them into the project, which contradicts the
    # "не засирай" constraint. These tests pass on a full Python install
    # (e.g. python.org 3.11.x); here we just skip collection with a clear
    # reason so the suite as a whole still runs.
    #
    # Files excluded: any that either pull tkinter at top level (widget,
    # notes_window, settings_window) or that exercise the full main.py
    # module which itself does `import tkinter as tk` at line 9.
    collect_ignore_glob.extend([
        "test_widget_helpers.py",
        "test_notes_window.py",
        "test_settings_window_logic.py",
        "test_main_bug.py",        # imports main.py which needs tkinter
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# FakeWinreg — for autostart tests that mock Windows registry
# ═══════════════════════════════════════════════════════════════════════════════

class FakeWinreg:
    HKEY_CURRENT_USER = None
    REG_SZ = 1
    KEY_SET_VALUE = 2
    KEY_QUERY_VALUE = 4

    def __init__(self):
        self._keys = {}
        self._open_keys = []

    def OpenKey(self, key, subkey, reserved=0, access=0):
        self._open_keys.append(("OpenKey", key, subkey, reserved, access))
        if subkey not in self._keys:
            raise OSError("Key not found")
        return f"key_{subkey}"

    def CreateKey(self, key, subkey):
        self._open_keys.append(("CreateKey", key, subkey))
        self._keys[subkey] = {}
        return f"key_{subkey}"

    def SetValueEx(self, key, value_name, reserved, regtype, value):
        self._open_keys.append(("SetValueEx", key, value_name, reserved, regtype, value))
        for kname, kref in self._keys.items():
            if f"key_{kname}" == key:
                kref[value_name] = (regtype, value)
                return

    def DeleteValue(self, key, value_name):
        for kname, kref in self._keys.items():
            if f"key_{kname}" == key:
                if value_name in kref:
                    del kref[value_name]
                    return
        raise FileNotFoundError

    def QueryValueEx(self, key, value_name):
        for kname, kref in self._keys.items():
            if f"key_{kname}" == key:
                if value_name in kref:
                    return kref[value_name]
        raise FileNotFoundError

    def CloseKey(self, key):
        self._open_keys.append(("CloseKey", key))


# ═══════════════════════════════════════════════════════════════════════════════
# main_module fixture — stubbed main.py for unit tests
# ═══════════════════════════════════════════════════════════════════════════════

_main_module_cache = {}


@pytest.fixture
def main_module(monkeypatch, tmp_path):
    """Load main.py with all GUI/IO dependencies stubbed out.

    Yields (m, calls, recorder) where m is the main module, calls is a list
    of all stubbed-out method calls, and recorder is the FakeRecorder instance.

    The module is cached per Python process to avoid repeated import overhead.
    Each test gets a reset state via per-test reset logic below.
    """
    project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project not in sys.path:
        sys.path.insert(0, project)

    cache_key = ("main", id(sys))
    if cache_key in _main_module_cache:
        m, calls, fake_rec = _main_module_cache[cache_key]
        # Per-test reset: clear mutable state
        fake_rec._audio = None
        fake_rec._frames = []
        fake_rec.start_called = False
        fake_rec.stop_called = False
        calls.clear()
        m._timeout_timer = None
        m._last_transcribed_text = ""
        m._last_transcribed_hwnd = None
        # Reset recording-start timestamp so a test that calls
        # _on_hotkey_release() without first calling _on_hotkey_press()
        # doesn't get a sub-_MIN_DURATION duration from the previous
        # test's leftover value.
        m._rec_start = 0.0
        return m, calls, fake_rec

    calls = []

    # ── ctypes windll stub ──────────────────────────────────────────────────
    # Must handle ANY Windows DLL entry point accessed by any transitive import
    # (customtkinter → darkdetect → ctypes.windll.advapi32, etc.)
    class _DynamicWindllStub:
        """Universal stub: any .dll.any_function returns a no-op callable.
        Uses __getattr__ to lazily create sub-DLL stubs on demand."""

        def __getattr__(self, name):
            return _DynamicWindllStub()

        def __call__(self, *args, **kwargs):
            return 0

        def __bool__(self):
            return True

    fake_windll = _DynamicWindllStub()

    def fake_get_fg():
        calls.append("GetForegroundWindow")
        return 0xDEADBEEF

    # Patch GetForegroundWindow: use object.__setattr__ to bypass __getattr__
    # and ensure it persists across all .user32 accesses.
    _user32_stub = _DynamicWindllStub()
    object.__setattr__(_user32_stub, "GetForegroundWindow", fake_get_fg)

    class _WindllWithUser32(_DynamicWindllStub):
        """Like _DynamicWindllStub but caches user32 to avoid creating a new
        instance on every attribute access, so GetForegroundWindow assignment persists."""

        def __getattr__(self, name):
            if name == "user32":
                return _user32_stub
            return _DynamicWindllStub()

    fake_windll = _WindllWithUser32()
    # Replace ctypes.windll (the LibraryLoader) with our stub. main.py
    # does `ctypes.windll.user32.GetForegroundWindow()` — that goes
    # through ctypes.windll, not ctypes._windll (which doesn't exist
    # on Python 3.12+). The earlier code assigned to ctypes._windll,
    # which silently created a new module attribute that nothing reads,
    # so the GetForegroundWindow mock never fired.
    ctypes.windll = fake_windll

    # ── FakeRecorder ────────────────────────────────────────────────────────
    class FakeRecorder:
        def __init__(self):
            self.start_called = False
            self.stop_called = False
            self._audio = None
            self._frames = []
            self._vad_config = {}
            self._device_info = {}

        def resolve_device(self, name):
            return 0

        def start(self):
            calls.append("recorder.start")
            self.start_called = True

        def stop(self):
            calls.append("recorder.stop")
            self.stop_called = True
            return self._audio

        def cleanup(self):
            calls.append("recorder.cleanup")

        on_level = None
        on_mic_error = None
        on_vad_trigger = None

    fake_rec = FakeRecorder()

    # ── FakeTranscriber ─────────────────────────────────────────────────────
    class FakeTranscriber:
        def transcribe(self, audio):
            calls.append("transcribe")
            return "тест"

        def warmup(self):
            calls.append("warmup")

        def unload(self):
            pass

    # ── FakeHotkeyListener ─────────────────────────────────────────────────
    class FakeHotkeyListener:
        def __init__(self, **kw):
            self.on_press = kw.get("on_press_cb")
            self.on_release = kw.get("on_release_cb")
            self.on_re_paste = kw.get("on_re_paste_cb")
            self.on_retry = kw.get("on_retry_cb")
            self._force_stop = False

        def start(self):
            calls.append("hotkey.start")

        def stop(self):
            calls.append("hotkey.stop")

        def force_stop_dictation(self):
            calls.append("force_stop_dictation")
            self._force_stop = True

    # ── FakeTray ────────────────────────────────────────────────────────────
    class FakeTray:
        def __init__(self, **kw):
            self._recording = False

        def start(self):
            calls.append("tray.start")

        def stop(self):
            calls.append("tray.stop")

        def set_recording(self, v):
            calls.append(f"tray.set_recording({v})")
            self._recording = v

    # ── FakeWidget ──────────────────────────────────────────────────────────
    class FakeWidget:
        def __init__(self):
            self._state = "idle"

        def show_recording(self):
            calls.append("widget.show_recording")

        def show_processing(self):
            calls.append("widget.show_processing")

        def hide(self):
            calls.append("widget.hide")

        def set_expression(self, e):
            calls.append(f"widget.set_expression({e})")

        def show_message(self, msg, duration_ms=0):
            calls.append(f"widget.show_message({msg!r})")

        def update_level(self, v):
            pass

    # ── FakeSettingsWin ────────────────────────────────────────────────────
    class FakeSettingsWin:
        _win = None

        def show(self):
            calls.append("settings_win.show")

    # ── FakeScheduler ──────────────────────────────────────────────────────
    class FakeScheduler:
        def start(self):
            calls.append("scheduler.start")

        def stop(self):
            calls.append("scheduler.stop")

    # ── helpers ────────────────────────────────────────────────────────────
    def make_stub(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        return m

    # ── FakeQueue ──────────────────────────────────────────────────────────
    class FakeQueue:
        def __init__(self):
            self.items = []
            self.get_called_with = None

        def put(self, item, block=True, timeout=None):
            self.items.append(item)

        def get(self, block=True, timeout=None):
            if not self.items:
                return None
            return self.items.pop(0)

        def qsize(self):
            return len(self.items)

        def empty(self):
            return len(self.items) == 0

    # ── Patch sys.modules before importing main ─────────────────────────────
    monkeypatch.setitem(sys.modules, "recorder",
        types.SimpleNamespace(Recorder=lambda: fake_rec))
    monkeypatch.setitem(sys.modules, "asr_engine",
        types.SimpleNamespace(create_engine=lambda: FakeTranscriber()))
    monkeypatch.setitem(sys.modules, "injector",
        make_stub("injector", inject=lambda text, target_hwnd=None: None))
    monkeypatch.setitem(sys.modules, "hotkey",
        make_stub("hotkey", HotkeyListener=FakeHotkeyListener))
    monkeypatch.setitem(sys.modules, "tray_icon",
        make_stub("tray_icon", TrayIcon=FakeTray))
    monkeypatch.setitem(sys.modules, "widget",
        make_stub("widget", RecordingWidget=lambda r: FakeWidget()))
    monkeypatch.setitem(sys.modules, "settings_window",
        make_stub("settings_window", SettingsWindow=lambda r: FakeSettingsWin()))
    monkeypatch.setitem(sys.modules, "notifier",
        make_stub("notifier", ReminderScheduler=lambda: FakeScheduler()))
    monkeypatch.setitem(sys.modules, "config",
        make_stub("config",
            HOLD_TO_RECORD=False,
            MAX_RECORD_SECONDS=120,
            VAD_AUTO_STOP_SECONDS=2.0,
            AUTOSTART=False,
            MIC_DEVICE_NAME=None,
        ))
    monkeypatch.setitem(sys.modules, "locales",
        make_stub("locales", get=lambda k, **kw: k))
    monkeypatch.setitem(sys.modules, "autostart",
        make_stub("autostart", set_autostart=lambda x: None))
    monkeypatch.setitem(sys.modules, "paths",
        make_stub("paths",
            DATA_DIR=str(tmp_path),
            LOG_PATH=str(tmp_path / "writher.log"),
            BUNDLE_DIR=str(tmp_path),
        ))
    monkeypatch.setitem(sys.modules, "soundfile",
        make_stub("soundfile", write=lambda *a, **kw: None))
    # db default: empty
    monkeypatch.setitem(sys.modules, "database",
        make_stub("database",
            init=lambda: None,
            get_setting=lambda k, d="": d))
    # notes_window pulls tkinter/customtkinter at import time. We never call
    # the real one in these tests — main.py just stores a reference.
    monkeypatch.setitem(sys.modules, "notes_window",
        make_stub("notes_window", NotesWindow=lambda r: object()))
    # models_registry only needs logger; we already stub logger below if
    # it isn't already loaded.
    try:
        import models_registry  # noqa: F401
    except Exception:
        monkeypatch.setitem(sys.modules, "models_registry",
            make_stub("models_registry",
                ModelSpec=lambda **kw: None,
                discover_models=lambda: []))

    # ── import main ────────────────────────────────────────────────────────
    import main as m

    # Replace sub-module references with our stubs
    m.recorder = fake_rec
    m.inject = lambda text, target_hwnd=None: None
    m.hotkey_listener = FakeHotkeyListener()
    m.tray = FakeTray()
    m.widget_obj = FakeWidget()
    m.settings_win = FakeSettingsWin()
    m.scheduler = FakeScheduler()

    # Init module-level state that main.py expects
    if not hasattr(m, "_dict_hwnd"):
        m._dict_hwnd = None
    if not hasattr(m, "_hwnd_lock"):
        m._hwnd_lock = threading.Lock()
    m._pipeline_queue = FakeQueue()
    m._timeout_timer = None
    m._STOP = object()
    m._last_transcribed_text = ""
    m._last_transcribed_hwnd = None
    m._retry_timer = None
    m._RETRY_DEBOUNCE = 1.0
    m._MIN_DURATION = 0.05

    # Cache and return
    _main_module_cache[cache_key] = (m, calls, fake_rec)
    return m, calls, fake_rec


# ═══════════════════════════════════════════════════════════════════════════════
# clipboard_mock fixture — for injector tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def clipboard_mock(monkeypatch):
    """Mock Windows clipboard (ctypes calls) for injector tests.

    Replaces ctypes.windll calls to GetClipboardData/SetClipboardData with
    an in-memory dict so tests don't need a real Windows clipboard.
    """
    _clipboard = {"text": ""}
    CF_UNICODETEXT = 13

    class _FakeWindll:
        @staticmethod
        def GetClipboardData(format_id):
            if format_id == CF_UNICODETEXT:
                return _clipboard["text"]
            return None

        @staticmethod
        def SetClipboardData(format_id, text):
            if format_id == CF_UNICODETEXT:
                _clipboard["text"] = text
            return text

        @staticmethod
        def OpenClipboard(hwnd):
            return True

        @staticmethod
        def CloseClipboard():
            return True

        @staticmethod
        def EmptyClipboard():
            _clipboard["text"] = ""
            return True

    monkeypatch.setattr(ctypes, "windll", _FakeWindll())

    import injector
    injector.clipboard_get = lambda: _clipboard["text"]
    injector.clipboard_set = lambda t: _clipboard.update({"text": t})

    yield _clipboard

    _clipboard.clear()
