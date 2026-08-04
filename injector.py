"""Inject transcribed text into the active application using the clipboard.

Uses the Win32 clipboard API (via ctypes) for atomic clipboard access,
eliminating the race condition that existed with pyperclip.
Uses keybd_event with hardware scan codes to simulate Ctrl+V — the proven
method from boppreh/keyboard (4k+ stars) that works reliably on Windows 10/11.
If clipboard injection fails, text is saved to recovery_notes.txt as fallback.
"""

import ctypes
import ctypes.wintypes
import os
import time

from logger import log
from paths import RECOVERY_PATH

_MAX_RECOVERY_SIZE = 512_000  # 500 KB max before rotation

# ── Win32 clipboard constants & functions ─────────────────────────────────
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

CF_UNICODETEXT = 13

_OpenClipboard = _user32.OpenClipboard
_OpenClipboard.argtypes = [ctypes.wintypes.HWND]
_OpenClipboard.restype = ctypes.wintypes.BOOL

_CloseClipboard = _user32.CloseClipboard
_CloseClipboard.argtypes = []
_CloseClipboard.restype = ctypes.wintypes.BOOL

_EmptyClipboard = _user32.EmptyClipboard
_EmptyClipboard.argtypes = []
_EmptyClipboard.restype = ctypes.wintypes.BOOL

_SetClipboardData = _user32.SetClipboardData
_SetClipboardData.argtypes = [ctypes.wintypes.UINT, ctypes.wintypes.HANDLE]
_SetClipboardData.restype = ctypes.wintypes.HANDLE

_GetClipboardData = _user32.GetClipboardData
_GetClipboardData.argtypes = [ctypes.wintypes.UINT]
_GetClipboardData.restype = ctypes.wintypes.HANDLE

_GlobalAlloc = _kernel32.GlobalAlloc
_GlobalAlloc.argtypes = [ctypes.wintypes.UINT, ctypes.c_size_t]
_GlobalAlloc.restype = ctypes.wintypes.HANDLE

_GlobalLock = _kernel32.GlobalLock
_GlobalLock.argtypes = [ctypes.wintypes.HANDLE]
_GlobalLock.restype = ctypes.c_void_p

_GlobalUnlock = _kernel32.GlobalUnlock
_GlobalUnlock.argtypes = [ctypes.wintypes.HANDLE]
_GlobalUnlock.restype = ctypes.wintypes.BOOL

GMEM_MOVEABLE = 0x0002

_MAX_RETRIES = 5
_RETRY_DELAY = 0.02  # seconds


# ── Clipboard helpers ─────────────────────────────────────────────────────


def _open_clipboard() -> bool:
    """Try to open the clipboard with retries (another app may hold it)."""
    for _ in range(_MAX_RETRIES):
        if _OpenClipboard(None):
            return True
        time.sleep(_RETRY_DELAY)
    return False


def _get_clipboard_text() -> str:
    """Return current clipboard text, or empty string on failure."""
    if not _open_clipboard():
        log.warning("Cannot open clipboard for reading")
        return ""
    try:
        handle = _GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = _GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            _GlobalUnlock(handle)
    finally:
        _CloseClipboard()


def _set_clipboard_text(text: str) -> bool:
    """Write *text* to the clipboard. Returns True on success."""
    if not _open_clipboard():
        log.warning("Cannot open clipboard for writing")
        return False
    try:
        _EmptyClipboard()
        encoded = text.encode("utf-16-le") + b"\x00\x00"
        h_mem = _GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h_mem:
            return False
        ptr = _GlobalLock(h_mem)
        if not ptr:
            return False
        ctypes.memmove(ptr, encoded, len(encoded))
        _GlobalUnlock(h_mem)
        _SetClipboardData(CF_UNICODETEXT, h_mem)
        return True
    finally:
        _CloseClipboard()


# ── Recovery file ─────────────────────────────────────────────────────────


def _save_recovery(text: str):
    """Append text to recovery_notes.txt. Rotates when file exceeds 500 KB.

    On Windows, the first time the file is created we attempt to restrict
    its ACL to the current user only (strip inherited ACLs, grant current
    user full control). Subsequent appends skip the icacls call — it's
    a heavyweight subprocess and not needed on every dictation.
    """
    try:
        # Rotate if too large
        if os.path.exists(RECOVERY_PATH):
            if os.path.getsize(RECOVERY_PATH) > _MAX_RECOVERY_SIZE:
                backup = RECOVERY_PATH + ".1"
                if os.path.exists(backup):
                    os.remove(backup)
                os.rename(RECOVERY_PATH, backup)

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        is_new_file = not os.path.exists(RECOVERY_PATH)
        with open(RECOVERY_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {text}\n")

        # Best-effort ACL hardening on first creation. We only do this
        # once per file to avoid a subprocess call on every dictation.
        if is_new_file and os.name == "nt":
            try:
                import subprocess
                user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
                if user:
                    subprocess.run(
                        [
                            "icacls", RECOVERY_PATH,
                            "/inheritance:r",
                            "/grant:r", f"{user}:F",
                        ],
                        check=False,
                        capture_output=True,
                        timeout=2,
                    )
            except Exception:
                # Non-fatal: file is still saved, just not ACL-hardened.
                pass
    except Exception as exc:
        log.error("Failed to save recovery text: %s", exc)


# ── Win32 Ctrl+V via keybd_event + hardware scan codes ────────────────────
# Proven method: same approach as boppreh/keyboard library (4k+ stars on GitHub).
# keybd_event with proper hardware scan codes bypasses the issue we saw with
# pynput (which lost the Ctrl state) and with our previous SendInput attempt
# (which was timing-dependent on focus).
#
# Scan codes are hardware-level key identifiers (PS/2 Set 1). They work
# reliably across UIPI on the same integrity level. Reference: Win32 docs.

# Hardware scan codes (PS/2 Set 1, used by Windows)
SCAN_CTRL = 0x1D
SCAN_V    = 0x2F

# Virtual key codes (also needed alongside scan codes)
VK_CONTROL = 0x11
VK_V       = 0x56

# Flags for keybd_event
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP       = 0x0002
KEYEVENTF_SCANCODE    = 0x0008  # Use the bScan parameter as a scan code

# Focus-restoring constants
SW_SHOWNOACTIVATE = 4
SW_RESTORE        = 9

_SetForegroundWindow = _user32.SetForegroundWindow
_SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]
_SetForegroundWindow.restype = ctypes.wintypes.BOOL

_ShowWindow = _user32.ShowWindow
_ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
_ShowWindow.restype = ctypes.wintypes.BOOL

_IsIconic = _user32.IsIconic
_IsIconic.argtypes = [ctypes.wintypes.HWND]
_IsIconic.restype = ctypes.wintypes.BOOL


def _send_ctrl_v(target_hwnd=None):
    """Simulate Ctrl+V via keybd_event with hardware scan codes.

    This is the proven approach used by the boppreh/keyboard library
    (https://github.com/boppreh/keyboard). It works reliably because:
    - Hardware scan codes bypass synthetic-input filtering on Windows 10/11
    - keybd_event runs from any thread without UIPI issues at the same IL
    - Setting the foreground window first ensures the right window gets focus
    """
    # 1. Restore the saved target window (if given) so it receives the keys.
    #    If the window is minimised, restore it without activating.
    if target_hwnd:
        try:
            if _IsIconic(target_hwnd):
                _ShowWindow(target_hwnd, SW_RESTORE)
        except Exception:
            pass
        try:
            # Don't force foreground — that would steal focus from user.
            # The saved window is the one we want to receive input.
            _SetForegroundWindow(target_hwnd)
        except Exception:
            pass

    # 2. Send Ctrl down, V down, V up, Ctrl up — with scan codes set in dwFlags.
    #    keybd_event takes (bVk, bScan, dwFlags, dwExtraInfo).
    #    When KEYEVENTF_SCANCODE is set, bVk is ignored and bScan is used.
    try:
        _user32.keybd_event(0, SCAN_CTRL, KEYEVENTF_SCANCODE, 0)
        _user32.keybd_event(0, SCAN_V,    KEYEVENTF_SCANCODE, 0)
        _user32.keybd_event(0, SCAN_V,    KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0)
        _user32.keybd_event(0, SCAN_CTRL, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0)
    except Exception as exc:
        log.error("keybd_event failed: %s", exc)


# ── Public API ────────────────────────────────────────────────────────────


def inject(text: str, target_hwnd=None):
    """Paste *text* into the target window (or the foreground window).

    Every transcription is saved to recovery_notes.txt as a safety net,
    so dictated content is never lost even if the paste target ignores Ctrl+V.

    Args:
        text: Transcribed text to paste.
        target_hwnd: Window handle to restore and receive Ctrl+V. If None,
                     the current foreground window is used.
    """
    if not text:
        return

    log.info("INJECT: text length=%d, hwnd=%s, first_50=%r", len(text), target_hwnd, text[:50])
    # Always save to recovery file — paste target may silently ignore Ctrl+V
    _save_recovery(text)

    try:
        if not _set_clipboard_text(text):
            log.error("Failed to set clipboard text (already saved to recovery)")
            return
        # Brief pause so the clipboard is committed before we synthesise keys
        time.sleep(0.05)

        # Simulate Ctrl+V using hardware scan codes (proven, see module docstring)
        _send_ctrl_v(target_hwnd)

        # Keep the new text in clipboard — user can Ctrl+V manually if auto-paste fails
    except Exception as exc:
        log.error("Injection error: %s", exc)
        # Keep clipboard content on error — user can Ctrl+V manually
