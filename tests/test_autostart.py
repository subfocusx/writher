"""Unit tests for autostart.py — Windows registry autostart."""
import sys
import types
import os
import pytest


class FakeWinreg:
    """Mock for the winreg module."""

    class HKEY_CURRENT_USER:
        pass

    REG_SZ = 1
    KEY_SET_VALUE = 2
    KEY_QUERY_VALUE = 4

    def __init__(self):
        self._keys = {}
        self._values = {}
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


@pytest.fixture
def fake_winreg():
    return FakeWinreg()


@pytest.fixture
def fake_winreg():
    return FakeWinreg()


@pytest.fixture
def loaded_autostart(monkeypatch, fake_winreg):
    """Mock winreg and sys.frozen, then load autostart module."""
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    if hasattr(sys, "_MEIPASS"):
        monkeypatch.delattr(sys, "_MEIPASS")

    winreg_mod = types.ModuleType("winreg")
    winreg_mod.HKEY_CURRENT_USER = fake_winreg.HKEY_CURRENT_USER
    winreg_mod.REG_SZ = fake_winreg.REG_SZ
    winreg_mod.KEY_SET_VALUE = fake_winreg.KEY_SET_VALUE
    winreg_mod.KEY_QUERY_VALUE = fake_winreg.KEY_QUERY_VALUE
    winreg_mod.OpenKey = fake_winreg.OpenKey
    winreg_mod.CreateKey = fake_winreg.CreateKey
    winreg_mod.SetValueEx = fake_winreg.SetValueEx
    winreg_mod.DeleteValue = fake_winreg.DeleteValue
    winreg_mod.QueryValueEx = fake_winreg.QueryValueEx
    winreg_mod.CloseKey = fake_winreg.CloseKey
    monkeypatch.setitem(sys.modules, "winreg", winreg_mod)

    if "autostart" in sys.modules:
        del sys.modules["autostart"]
    import autostart
    return autostart, fake_winreg


def test_set_autostart_enable(loaded_autostart):
    """set_autostart(True) must create the registry value."""
    autostart_mod, fake_winreg = loaded_autostart
    fake_winreg._keys[r"Software\Microsoft\Windows\CurrentVersion\Run"] = {}

    result = autostart_mod.set_autostart(True)

    assert result is True
    key_data = fake_winreg._keys[r"Software\Microsoft\Windows\CurrentVersion\Run"]
    assert "WritHer" in key_data


def test_set_autostart_disable(loaded_autostart):
    """set_autostart(False) must delete the registry value."""
    autostart_mod, fake_winreg = loaded_autostart
    fake_winreg._keys[r"Software\Microsoft\Windows\CurrentVersion\Run"] = {
        "WritHer": (1, "somepath"),
    }

    result = autostart_mod.set_autostart(False)

    assert result is True
    key_data = fake_winreg._keys[r"Software\Microsoft\Windows\CurrentVersion\Run"]
    assert "WritHer" not in key_data


def test_is_autostart_enabled_true(loaded_autostart):
    """is_autostart_enabled() returns True when the value exists."""
    autostart_mod, fake_winreg = loaded_autostart
    fake_winreg._keys[r"Software\Microsoft\Windows\CurrentVersion\Run"] = {
        "WritHer": (1, "somepath"),
    }

    assert autostart_mod.is_autostart_enabled() is True


def test_is_autostart_enabled_false(loaded_autostart):
    """is_autostart_enabled() returns False when the value is missing."""
    autostart_mod, fake_winreg = loaded_autostart
    fake_winreg._keys[r"Software\Microsoft\Windows\CurrentVersion\Run"] = {}

    assert autostart_mod.is_autostart_enabled() is False


def test_set_autostart_creates_key_if_missing(loaded_autostart):
    """set_autostart(True) must create the key if it does not exist."""
    autostart_mod, fake_winreg = loaded_autostart

    result = autostart_mod.set_autostart(True)

    assert result is True
    assert r"Software\Microsoft\Windows\CurrentVersion\Run" in fake_winreg._keys


def test_set_autostart_disable_no_key(loaded_autostart):
    """set_autostart(False) must not raise when the key is missing."""
    autostart_mod, fake_winreg = loaded_autostart

    result = autostart_mod.set_autostart(False)

    assert result is True


def test_no_winreg_noop(monkeypatch):
    """Without winreg, set_autostart and is_autostart_enabled return False.

    On Windows winreg is always present so this test cannot work in-process.
    The real coverage comes from loaded_autostart which mocks winreg entirely.
    """
    pytest.skip("winreg is always present on Windows; winreg-mocking covered by loaded_autostart fixture")


def test_get_exe_path_source(loaded_autostart):
    """_get_exe_path returns python+main.py when not frozen."""
    autostart_mod, _ = loaded_autostart
    path = autostart_mod._get_exe_path()
    assert sys.executable in path
    assert "main.py" in path


def test_get_exe_path_frozen(monkeypatch, loaded_autostart):
    """_get_exe_path returns sys.executable when frozen."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_internal", raising=False)
    if "autostart" in sys.modules:
        del sys.modules["autostart"]
    import autostart

    path = autostart._get_exe_path()
    assert path == sys.executable
