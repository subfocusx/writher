"""Tests for debug_keys.py — key debugger utility functions.

debug_keys.py is a script module that runs at import time (starts a pynput
listener). We test its on_press/on_release functions by mocking pynput.
"""
import types
import sys
import os
import pytest

project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _FakeListener:
    """Mock pynput Listener that supports `with` statement."""
    def __init__(self, on_press=None, on_release=None):
        self._on_press = on_press
        self._on_release = on_release
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def join(self):
        pass


@pytest.fixture
def debug_keys_module(monkeypatch):
    """Import debug_keys.py with pynput mocked to prevent listener start."""
    if project not in sys.path:
        sys.path.insert(0, project)

    fake_pynput = types.ModuleType("pynput")
    fake_keyboard = types.ModuleType("pynput.keyboard")

    class FakeKey:
        alt_r = "alt_r"
        ctrl_l = "ctrl_l"
        esc = "esc"

    class FakeKeyCode:
        def __init__(self, vk=None):
            self.vk = vk

    fake_keyboard.Key = FakeKey
    fake_keyboard.KeyCode = FakeKeyCode
    fake_keyboard.Listener = _FakeListener
    fake_pynput.keyboard = fake_keyboard

    monkeypatch.setitem(sys.modules, "pynput", fake_pynput)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", fake_keyboard)

    if "debug_keys" in sys.modules:
        del sys.modules["debug_keys"]

    import debug_keys as dk
    return dk, FakeKey, FakeKeyCode


def test_on_press_plain_key(debug_keys_module, capsys):
    dk, FakeKey, FakeKeyCode = debug_keys_module
    key = FakeKeyCode(vk=65)
    dk.on_press(key)
    captured = capsys.readouterr()
    assert "PRESS" in captured.out
    assert "vk=65" in captured.out


def test_on_press_hotkey_alt_r(debug_keys_module, capsys):
    dk, FakeKey, FakeKeyCode = debug_keys_module
    dk.on_press(FakeKey.alt_r)
    captured = capsys.readouterr()
    assert "HOTKEY" in captured.out


def test_on_press_hotkey_via_vk(debug_keys_module, capsys):
    dk, FakeKey, FakeKeyCode = debug_keys_module
    dk.on_press(FakeKeyCode(vk=165))
    captured = capsys.readouterr()
    assert "HOTKEY" in captured.out


def test_on_release_normal_key(debug_keys_module, capsys):
    dk, FakeKey, FakeKeyCode = debug_keys_module
    key = FakeKeyCode(vk=65)
    result = dk.on_release(key)
    assert result is None  # None means keep listening
    captured = capsys.readouterr()
    assert "RELEASE" in captured.out


def test_on_release_esc_returns_false(debug_keys_module, capsys):
    dk, FakeKey, FakeKeyCode = debug_keys_module
    result = dk.on_release(FakeKey.esc)
    assert result is False  # False stops the listener


def test_on_release_key_without_vk(debug_keys_module, capsys):
    dk, FakeKey, FakeKeyCode = debug_keys_module
    dk.on_release(FakeKey.ctrl_l)
    captured = capsys.readouterr()
    assert "RELEASE" in captured.out
