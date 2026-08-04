"""Windows autostart via HKCU\\...\\Run registry key.

Provides set_autostart() to enable/disable and is_autostart_enabled()
to query the current state. All functions are safe to call on non-Windows
(they return False / no-op).
"""

import os
import sys

_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "WritHer"


def _get_exe_path() -> str:
    """Return the command line to register for autostart."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return sys.executable
    main_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return f'"{sys.executable}" "{main_script}"'


def set_autostart(enabled: bool) -> bool:
    """Enable or disable Windows autostart for the current user.

    Returns True on success, False on non-Windows or error.
    """
    try:
        import winreg
    except ImportError:
        return False

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _KEY_PATH,
            0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
        )
    except OSError:
        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, _KEY_PATH)
        except OSError:
            return False

    try:
        if enabled:
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, _get_exe_path())
        else:
            try:
                winreg.DeleteValue(key, _APP_NAME)
            except FileNotFoundError:
                pass
        return True
    except OSError:
        return False
    finally:
        winreg.CloseKey(key)


def is_autostart_enabled() -> bool:
    """Check if autostart is registered in the Windows registry.

    Returns False on non-Windows.
    """
    try:
        import winreg
    except ImportError:
        return False

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _KEY_PATH,
            0, winreg.KEY_QUERY_VALUE,
        )
    except OSError:
        return False

    try:
        winreg.QueryValueEx(key, _APP_NAME)
        return True
    except FileNotFoundError:
        return False
    finally:
        winreg.CloseKey(key)
