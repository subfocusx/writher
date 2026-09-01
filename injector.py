"""Inject transcribed text into the active application using the clipboard.

Uses the Win32 clipboard API (via ctypes) for atomic clipboard access,
eliminating the race condition that existed with pyperclip.
Uses keybd_event with hardware scan codes to simulate Ctrl+V — the proven
method from boppreh/keyboard (4k+ stars) that works reliably on Windows 10/11.
If clipboard injection fails, text is saved to recovery_notes.txt as fallback.

The original clipboard content is saved before injection and restored afterwards,
so the user never loses what they had copied before dictation.
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
_PASTE_WAIT = 1.0  # seconds — time to wait for target app to read clipboard


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


def _clear_clipboard() -> bool:
    """Empty the clipboard. Returns True on success.

    Fallback: called only when clipboard restore fails (see inject()).
    The text is already saved to recovery_notes.txt, so nothing is lost.
    """
    if not _open_clipboard():
        log.warning("Cannot open clipboard for clearing")
        return False
    try:
        _EmptyClipboard()
        return True
    finally:
        _CloseClipboard()


# ── Recovery file ─────────────────────────────────────────────────────────


def _current_user_account() -> str:
    """Return the current user's account name (DOMAIN\\user) for ACL grants.

    Resolved from the process token rather than the USERNAME environment
    variable. The env var can name an orphaned / renamed account or simply
    be absent in odd launchers — granting to it permanently locks the file
    (the ACL bug that broke WritHer 1.1.0). The token never lies.
    """
    import ctypes as _c
    try:
        size = _c.wintypes.DWORD(256)
        buf = _c.create_unicode_buffer(size.value)
        if _c.windll.advapi32.GetUserNameW(buf, _c.byref(size)):
            return buf.value
    except Exception:
        pass
    # Fall back to the env var, but keep the raw login name only.
    return (os.environ.get("USERNAME") or os.environ.get("USER") or "")


def _safe_harden_recovery():
    """Best-effort: grant the current user FullControl on the recovery file.

    Designed so it can NEVER lock the app out of its own file:
      * the grant goes to the real process-user, not a stale env var;
      * inheritance is kept (no destructive `/inheritance:r`), so even if
        the grant is wrong the parent folder's rights still apply;
      * we verify writability afterwards and, if it broke, re-enable
        inheritance to self-heal.
    Failures are logged, never fatal — the text is already appended.
    """
    if os.name != "nt":
        return
    try:
        import subprocess
        user = _current_user_account()
        if not user:
            return
        _run_icacls(["icacls", RECOVERY_PATH, "/grant", f"{user}:F"])
        # Verify we still hold write access; if not, restore inheritance.
        try:
            with open(RECOVERY_PATH, "a", encoding="utf-8"):
                pass
        except OSError:
            _run_icacls(["icacls", RECOVERY_PATH, "/inheritance:e"])
    except Exception as exc:
        log.warning("ACL hardening skipped: %s", exc)


def _run_icacls(args: list[str]):
    import subprocess
    try:
        subprocess.run(args, check=False, capture_output=True, timeout=2)
    except Exception:
        pass


def _save_recovery(text: str):
    """Append text to recovery_notes.txt. Rotates when file exceeds 500 KB.

    On Windows we try to ensure the current user has FullControl on the
    file, hardened so it can never lock the app out (see
    ``_safe_harden_recovery``). The old ``/inheritance:r`` + env-var grant
    permanently broke the file (Permission denied on every dictation) when
    the USERNAME env var didn't match the real account — that bug is gone.
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
        first_write = not os.path.exists(RECOVERY_PATH)
        with open(RECOVERY_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {text}\n")

        # Ensure the current user can always write, once after creation.
        if first_write:
            _safe_harden_recovery()
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
    #    Small sleeps between events prevent fast machines from collapsing
    #    down/up into a single keystroke that target apps can't recognise
    #    as a Ctrl+V chord (commonly reported symptom: nothing pastes).
    try:
        _user32.keybd_event(0, SCAN_CTRL, KEYEVENTF_SCANCODE, 0)
        time.sleep(0.02)
        _user32.keybd_event(0, SCAN_V,    KEYEVENTF_SCANCODE, 0)
        time.sleep(0.02)
        _user32.keybd_event(0, SCAN_V,    KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)
        _user32.keybd_event(0, SCAN_CTRL, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0)
    except Exception as exc:
        log.error("keybd_event failed: %s", exc)


# ── Public API ────────────────────────────────────────────────────────────


def inject(text: str, target_hwnd=None):
    """Paste *text* into the target window (or the foreground window).

    Every transcription is saved to recovery_notes.txt as a safety net,
    so dictated content is never lost even if the paste target ignores Ctrl+V.

    The user's original clipboard content is saved before injection and
    restored afterwards, so nothing the user had copied is lost.

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

    # Save the user's original clipboard content so we can restore it after
    # the paste. If the clipboard contains non-text data (image, file list),
    # _get_clipboard_text returns "" which is fine — we'll restore empty.
    original_clipboard = _get_clipboard_text()

    try:
        if not _set_clipboard_text(text):
            log.error("Failed to set clipboard text (already saved to recovery)")
            return
        # Brief pause so the clipboard is committed before we synthesise keys
        time.sleep(0.05)

        # Simulate Ctrl+V using hardware scan codes (proven, see module docstring)
        _send_ctrl_v(target_hwnd)

        # Wait for the target window to actually consume the paste before we
        # restore the clipboard. Heavy editors (Word, big contenteditable,
        # Electron apps) can take 300-600+ ms to read the clipboard after
        # receiving Ctrl+V — too short and the paste silently drops, and
        # then our restore wipes the buffer ("в буфер не попадает" symptom).
        # Recovery file already has the text.
        time.sleep(_PASTE_WAIT)

        # Restore the original clipboard content so the user never loses
        # what they had copied before dictation. If restore fails, fall
        # back to clearing — the dictated text is in recovery_notes.txt.
        if original_clipboard:
            if not _set_clipboard_text(original_clipboard):
                log.warning("Could not restore original clipboard, clearing instead")
                _clear_clipboard()
        else:
            _clear_clipboard()
    except Exception as exc:
        log.error("Injection error: %s", exc)
        # On error, leave whatever's in the clipboard — better to re-paste
        # the dictated text than to lose it. The text is in recovery too.
