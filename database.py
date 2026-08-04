"""SQLite storage for notes, appointments and reminders."""

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from paths import DB_PATH

_lock = threading.Lock()


class _ConnCM:
    """Context manager that guarantees sqlite3.Connection.close().

    sqlite3's Connection.__exit__ only handles transactions, not closing,
    so wrapping it in a tiny CM ensures c.close() runs even on exceptions.
    """

    def __init__(self) -> None:
        self.c = _conn()

    def __enter__(self) -> sqlite3.Connection:
        return self.c

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self.c.commit()
        finally:
            self.c.close()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init():
    """Create tables if they don't exist and run safe migrations."""
    with _lock, _ConnCM() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS notes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT NOT NULL DEFAULT '',
                content    TEXT NOT NULL DEFAULT '',
                category   TEXT NOT NULL DEFAULT 'general',
                note_type  TEXT NOT NULL DEFAULT 'text',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS appointments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                dt          TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                notified    INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                message    TEXT NOT NULL,
                remind_at  TEXT NOT NULL,
                notified   INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
        """)
        # Safe migration: add notified column to appointments if missing
        cols = [row[1] for row in c.execute("PRAGMA table_info(appointments)")]
        if "notified" not in cols:
            c.execute("ALTER TABLE appointments ADD COLUMN notified INTEGER NOT NULL DEFAULT 0")

        # Custom words dictionary for dynamic prompt
        c.execute("""
            CREATE TABLE IF NOT EXISTS custom_words (
                word   TEXT PRIMARY KEY,
                weight REAL NOT NULL DEFAULT 1.0
            )
        """)

        # Settings key/value store
        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)



def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── Notes ─────────────────────────────────────────────────────────────────

def save_note(content: str, category: str = "general", title: str = "") -> int:
    """Save a free-text note. Returns the new note id."""
    now = _now()
    with _lock, _ConnCM() as c:
        cur = c.execute(
            "INSERT INTO notes (title,content,category,note_type,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?)",
            (title, content, category, "text", now, now),
        )
        nid = cur.lastrowid
    return nid


def save_list(title: str, items: list[str], category: str = "general") -> int:
    """Save a list note (shopping, todo …). Returns the new note id."""
    now = _now()
    data = json.dumps([{"item": it, "checked": False} for it in items],
                      ensure_ascii=False)
    with _lock, _ConnCM() as c:
        cur = c.execute(
            "INSERT INTO notes (title,content,category,note_type,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?)",
            (title, data, category, "list", now, now),
        )
        nid = cur.lastrowid
    return nid


def add_to_list(note_id: int, items: list[str]) -> bool:
    """Append items to an existing list note."""
    with _lock, _ConnCM() as c:
        row = c.execute("SELECT content, note_type FROM notes WHERE id=?",
                        (note_id,)).fetchone()
        if not row or row["note_type"] != "list":
            return False
        current = json.loads(row["content"])
        current.extend({"item": it, "checked": False} for it in items)
        c.execute("UPDATE notes SET content=?, updated_at=? WHERE id=?",
                  (json.dumps(current, ensure_ascii=False), _now(), note_id))
    return True


def check_item(note_id: int, item_text: str) -> bool:
    """Toggle checked state for an item in a list note (fuzzy match)."""
    with _lock, _ConnCM() as c:
        row = c.execute("SELECT content, note_type FROM notes WHERE id=?",
                        (note_id,)).fetchone()
        if not row or row["note_type"] != "list":
            return False
        current = json.loads(row["content"])
        target = item_text.strip().lower()
        found = False
        for entry in current:
            if entry["item"].strip().lower() == target:
                entry["checked"] = not entry["checked"]
                found = True
                break
        if found:
            c.execute("UPDATE notes SET content=?, updated_at=? WHERE id=?",
                      (json.dumps(current, ensure_ascii=False), _now(), note_id))
    return found


def find_list_by_title(title: str) -> dict | None:
    """Find a list note by fuzzy title match. Returns dict or None."""
    with _lock, _ConnCM() as c:
        rows = c.execute(
            "SELECT * FROM notes WHERE note_type='list' ORDER BY updated_at DESC"
        ).fetchall()
    target = title.strip().lower()
    for r in rows:
        if target in r["title"].strip().lower():
            return dict(r)
    return None


def get_all_notes() -> list[dict]:
    with _lock, _ConnCM() as c:
        rows = c.execute("SELECT * FROM notes ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete_note(note_id: int):
    with _lock, _ConnCM() as c:
        c.execute("DELETE FROM notes WHERE id=?", (note_id,))


# ── Appointments ──────────────────────────────────────────────────────────

def create_appointment(title: str, dt: str, description: str = "") -> int:
    """Create a calendar appointment. *dt* is ISO datetime string."""
    with _lock, _ConnCM() as c:
        cur = c.execute(
            "INSERT INTO appointments (title,dt,description,created_at)"
            " VALUES (?,?,?,?)",
            (title, dt, description, _now()),
        )
        aid = cur.lastrowid
    return aid


def get_appointments(from_dt: str | None = None, to_dt: str | None = None) -> list[dict]:
    """Return appointments optionally filtered by date range."""
    with _lock, _ConnCM() as c:
        q = "SELECT * FROM appointments"
        params: list = []
        clauses = []
        if from_dt:
            clauses.append("dt >= ?")
            params.append(from_dt)
        if to_dt:
            clauses.append("dt <= ?")
            params.append(to_dt)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY dt ASC"
        rows = c.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def delete_appointment(aid: int):
    with _lock, _ConnCM() as c:
        c.execute("DELETE FROM appointments WHERE id=?", (aid,))


def get_upcoming_appointments(within_minutes: int) -> list[dict]:
    """Return appointments due within *within_minutes* that haven't been notified yet."""
    now = datetime.now()
    cutoff = (now + timedelta(minutes=within_minutes)).isoformat(timespec="seconds")
    now_str = now.isoformat(timespec="seconds")
    with _lock, _ConnCM() as c:
        rows = c.execute(
            "SELECT * FROM appointments WHERE notified=0 AND dt<=? AND dt>=?"
            " ORDER BY dt ASC",
            (cutoff, now_str),
        ).fetchall()
    return [dict(r) for r in rows]


def get_past_unnotified_appointments() -> list[dict]:
    """Return appointments whose time has passed but were never notified."""
    now_str = datetime.now().isoformat(timespec="seconds")
    with _lock, _ConnCM() as c:
        rows = c.execute(
            "SELECT * FROM appointments WHERE notified=0 AND dt<=?"
            " ORDER BY dt ASC",
            (now_str,),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_appointment_notified(aid: int):
    with _lock, _ConnCM() as c:
        c.execute("UPDATE appointments SET notified=1 WHERE id=?", (aid,))


# ── Reminders ─────────────────────────────────────────────────────────────

def set_reminder(message: str, remind_at: str) -> int:
    """Create a reminder. *remind_at* is ISO datetime string."""
    with _lock, _ConnCM() as c:
        cur = c.execute(
            "INSERT INTO reminders (message,remind_at,notified,created_at)"
            " VALUES (?,?,0,?)",
            (message, remind_at, _now()),
        )
        rid = cur.lastrowid
    return rid


def get_pending_reminders() -> list[dict]:
    """Return reminders that are due and not yet notified."""
    now = _now()
    with _lock, _ConnCM() as c:
        rows = c.execute(
            "SELECT * FROM reminders WHERE notified=0 AND remind_at<=?"
            " ORDER BY remind_at ASC", (now,)
        ).fetchall()
    return [dict(r) for r in rows]


def mark_reminder_notified(rid: int):
    with _lock, _ConnCM() as c:
        c.execute("UPDATE reminders SET notified=1 WHERE id=?", (rid,))


def get_all_reminders(include_notified: bool = False) -> list[dict]:
    with _lock, _ConnCM() as c:
        q = "SELECT * FROM reminders"
        if not include_notified:
            q += " WHERE notified=0"
        q += " ORDER BY remind_at ASC"
        rows = c.execute(q).fetchall()
    return [dict(r) for r in rows]


def delete_reminder(rid: int):
    with _lock, _ConnCM() as c:
        c.execute("DELETE FROM reminders WHERE id=?", (rid,))


# ── Settings ──────────────────────────────────────────────────────────────

# ── Custom words dictionary (dynamic prompt) ─────────────────────────────

def add_custom_word(word: str, weight: float = 1.0):
    with _lock, _ConnCM() as c:
        c.execute(
            "INSERT INTO custom_words (word, weight) VALUES (?, ?)"
            " ON CONFLICT(word) DO UPDATE SET weight=excluded.weight",
            (word.strip().lower(), weight),
        )


def delete_custom_word(word: str):
    with _lock, _ConnCM() as c:
        c.execute("DELETE FROM custom_words WHERE word=?", (word.strip().lower(),))


def get_custom_words() -> list[str]:
    with _lock, _ConnCM() as c:
        rows = c.execute(
            "SELECT word FROM custom_words ORDER BY weight DESC"
        ).fetchall()
    return [r["word"] for r in rows]


def get_recent_notes_text(limit: int = 10) -> str:
    with _lock, _ConnCM() as c:
        rows = c.execute(
            "SELECT content, title FROM notes WHERE note_type='text'"
            " ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    parts = []
    for r in rows:
        if r["title"]:
            parts.append(r["title"])
        parts.append(r["content"])
    return " ".join(parts)


_COMMA = ","


def get_keywords_from_notes(max_words: int = 20) -> list[str]:
    text = get_recent_notes_text()
    if not text.strip():
        return []
    import re
    tokens = re.findall(r"[а-яёА-ЯЁa-zA-Z-]{3,}", text.lower())
    freq = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    sorted_words = sorted(freq, key=freq.get, reverse=True)
    return sorted_words[:max_words]


def get_setting(key: str, default: str = "") -> str:
    """Return a setting value, or *default* if not found."""
    with _lock, _ConnCM() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def save_setting(key: str, value: str):
    """Insert or update a setting."""
    with _lock, _ConnCM() as c:
        c.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
