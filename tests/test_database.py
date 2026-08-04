"""Unit tests for database.py — covers all CRUD + settings + migrations."""
import os
import sqlite3
import tempfile
import types
import pytest

import database as db


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    """Each test gets a fresh SQLite database in tmp_path."""
    test_db = tmp_path / "test_writher.db"
    monkeypatch.setattr(db, "DB_PATH", str(test_db))
    db.init()
    yield str(test_db)
    # cleanup automatic via tmp_path


# ── init() / migrations ───────────────────────────────────────────────────


def test_init_creates_tables(isolated_db):
    conn = sqlite3.connect(isolated_db)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = [r[0] for r in rows]
    assert "notes" in names
    assert "appointments" in names
    assert "reminders" in names
    assert "settings" in names
    conn.close()


def test_init_adds_notified_column_via_migration(isolated_db, monkeypatch):
    """Verify the safe-migration path for notified column on appointments."""
    # Drop and recreate without notified
    conn = sqlite3.connect(isolated_db)
    conn.executescript("""
        DROP TABLE appointments;
        CREATE TABLE appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            dt TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
    """)
    conn.close()
    # Now run init again — it should add the column
    db.init()
    conn = sqlite3.connect(isolated_db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(appointments)")]
    assert "notified" in cols
    conn.close()


# ── notes ─────────────────────────────────────────────────────────────────


def test_save_note_returns_id(isolated_db):
    nid = db.save_note(content="hello", category="work", title="Hi")
    assert isinstance(nid, int) and nid > 0


def test_save_list_creates_checkable_items(isolated_db):
    nid = db.save_list(title="Shopping", items=["milk", "bread"])
    notes = db.get_all_notes()
    target = [n for n in notes if n["id"] == nid][0]
    import json
    data = json.loads(target["content"])
    assert len(data) == 2
    assert data[0]["item"] == "milk"
    assert data[0]["checked"] is False


def test_add_to_list_appends_items(isolated_db):
    nid = db.save_list(title="Todo", items=["a", "b"])
    assert db.add_to_list(nid, ["c", "d"])
    import json
    notes = db.get_all_notes()
    target = [n for n in notes if n["id"] == nid][0]
    data = json.loads(target["content"])
    assert [e["item"] for e in data] == ["a", "b", "c", "d"]


def test_add_to_list_rejects_non_list_note(isolated_db):
    nid = db.save_note(content="text only")
    assert db.add_to_list(nid, ["x"]) is False


def test_check_item_toggles_state(isolated_db):
    nid = db.save_list(title="L", items=["apple"])
    assert db.check_item(nid, "apple")
    # check again toggles off
    assert db.check_item(nid, "apple")
    # different item not found
    assert not db.check_item(nid, "banana")


def test_check_item_on_non_list_returns_false(isolated_db):
    nid = db.save_note(content="just text")
    assert not db.check_item(nid, "anything")


def test_find_list_by_title_fuzzy_match(isolated_db):
    db.save_list(title="Shopping List", items=["x"])
    db.save_list(title="Work Tasks", items=["y"])
    result = db.find_list_by_title("shop")
    assert result is not None
    assert "Shop" in result["title"]
    # No match
    assert db.find_list_by_title("nonexistent") is None


def test_get_all_notes_returns_sorted(isolated_db):
    db.save_note(content="first", title="A")
    db.save_note(content="second", title="B")
    notes = db.get_all_notes()
    assert len(notes) >= 2
    # updated_at DESC: most recent first
    assert notes[0]["title"] in ("B", "A")


def test_delete_note_removes(isolated_db):
    nid = db.save_note(content="delete me")
    db.delete_note(nid)
    assert all(n["id"] != nid for n in db.get_all_notes())


# ── appointments ─────────────────────────────────────────────────────────


def test_create_appointment(isolated_db):
    aid = db.create_appointment(title="Dentist", dt="2026-12-01T10:00", description="clean")
    assert aid > 0


def test_get_appointments_filters_by_range(isolated_db):
    db.create_appointment(title="Past", dt="2020-01-01T10:00")
    db.create_appointment(title="Future", dt="2099-01-01T10:00")
    rows = db.get_appointments(from_dt="2025-01-01T00:00")
    titles = [r["title"] for r in rows]
    assert "Future" in titles
    assert "Past" not in titles


def test_get_upcoming_appointments_within_window(isolated_db):
    from datetime import datetime, timedelta
    soon = (datetime.now() + timedelta(minutes=5)).isoformat(timespec="seconds")
    later = (datetime.now() + timedelta(hours=2)).isoformat(timespec="seconds")
    db.create_appointment(title="Soon", dt=soon)
    db.create_appointment(title="Way later", dt=later)
    upcoming = db.get_upcoming_appointments(within_minutes=10)
    assert any(a["title"] == "Soon" for a in upcoming)
    assert not any(a["title"] == "Way later" for a in upcoming)


def test_get_past_unnotified_appointments(isolated_db):
    from datetime import datetime, timedelta
    past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
    db.create_appointment(title="Already past", dt=past)
    rows = db.get_past_unnotified_appointments()
    assert any(a["title"] == "Already past" for a in rows)


def test_mark_appointment_notified(isolated_db):
    aid = db.create_appointment(title="X", dt="2099-01-01T10:00")
    db.mark_appointment_notified(aid)
    # Should not appear in upcoming
    assert not any(a["id"] == aid for a in db.get_upcoming_appointments(60))


def test_delete_appointment(isolated_db):
    aid = db.create_appointment(title="X", dt="2099-01-01T10:00")
    db.delete_appointment(aid)
    assert all(a["id"] != aid for a in db.get_appointments())


# ── reminders ────────────────────────────────────────────────────────────


def test_set_reminder(isolated_db):
    rid = db.set_reminder(message="call mom", remind_at="2099-01-01T10:00")
    assert rid > 0


def test_get_pending_reminders_returns_due(isolated_db):
    past = "2020-01-01T10:00:00"
    db.set_reminder(message="old", remind_at=past)
    pending = db.get_pending_reminders()
    assert any(r["message"] == "old" for r in pending)


def test_mark_reminder_notified(isolated_db):
    rid = db.set_reminder(message="done", remind_at="2020-01-01T10:00:00")
    db.mark_reminder_notified(rid)
    assert not any(r["id"] == rid for r in db.get_pending_reminders())


def test_get_all_reminders_includes_notified(isolated_db):
    rid = db.set_reminder(message="notified", remind_at="2020-01-01T10:00:00")
    db.mark_reminder_notified(rid)
    all_rem = db.get_all_reminders(include_notified=True)
    only_pending = db.get_all_reminders(include_notified=False)
    assert any(r["id"] == rid for r in all_rem)
    assert not any(r["id"] == rid for r in only_pending)


def test_delete_reminder(isolated_db):
    rid = db.set_reminder(message="x", remind_at="2099-01-01T10:00:00")
    db.delete_reminder(rid)
    assert all(r["id"] != rid for r in db.get_all_reminders())


# ── settings ─────────────────────────────────────────────────────────────


def test_get_setting_default_when_missing(isolated_db):
    assert db.get_setting("doesnt_exist", default="fallback") == "fallback"
    assert db.get_setting("doesnt_exist") == ""


def test_save_and_get_setting(isolated_db):
    db.save_setting("theme", "dark")
    assert db.get_setting("theme") == "dark"


def test_save_setting_overwrites(isolated_db):
    db.save_setting("k", "v1")
    db.save_setting("k", "v2")
    assert db.get_setting("k") == "v2"


# ── custom_words ─────────────────────────────────────────────────────────


def test_add_custom_word(isolated_db):
    db.add_custom_word("проект")
    words = db.get_custom_words()
    assert "проект" in words


def test_add_custom_word_normalises_case(isolated_db):
    db.add_custom_word("Проект")
    words = db.get_custom_words()
    assert "проект" in words


def test_add_custom_word_updates_existing(isolated_db):
    db.add_custom_word("тест", weight=0.5)
    db.add_custom_word("тест", weight=2.0)
    words = db.get_custom_words()
    assert "тест" in words


def test_delete_custom_word(isolated_db):
    db.add_custom_word("удалить")
    db.delete_custom_word("удалить")
    assert "удалить" not in db.get_custom_words()


def test_get_custom_words_ordered_by_weight(isolated_db):
    db.add_custom_word("a", weight=1.0)
    db.add_custom_word("b", weight=3.0)
    db.add_custom_word("c", weight=2.0)
    words = db.get_custom_words()
    assert words == ["b", "c", "a"]  # highest weight first


def test_get_keywords_from_notes_returns_top_words(isolated_db):
    db.save_note(content="Надо купить проект сервер и архитектуру")
    db.save_note(content="проект сервер микросервис архитектура")
    keywords = db.get_keywords_from_notes(max_words=5)
    assert "проект" in keywords
    assert "сервер" in keywords
    assert len(keywords) <= 5


# ═══════════════════════════════════════════════════════════════════════════════
# Context manager hardening (1.1.0 audit fix)
# ═══════════════════════════════════════════════════════════════════════════════

def test_conn_cm_closes_on_exception(isolated_db, monkeypatch):
    """_ConnCM guarantees close() even if the wrapped block raises.

    The fix replaces 20 hand-rolled `c = _conn(); ...; c.close()` blocks
    with `with _ConnCM() as c:`. Without this, an exception inside the
    block would leak the sqlite3.Connection.
    """
    from database import _ConnCM

    raised = False
    try:
        with _ConnCM() as c:
            # Force an exception in the middle of the block.
            raise RuntimeError("simulated failure")
    except RuntimeError:
        raised = True
    assert raised, "Exception should have propagated"

    # After the exception, we should still be able to open a new conn
    # (i.e. the broken one was closed, not leaked).
    with _ConnCM() as c:
        c.execute("SELECT 1").fetchone()


def test_conn_cm_commits_on_success(isolated_db):
    """_ConnCM commits the transaction on a clean exit."""
    from database import _ConnCM

    with _ConnCM() as c:
        c.execute(
            "INSERT INTO notes (title, content, category, note_type, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ("test", "content", "general", "text", "2024-01-01T00:00:00", "2024-01-01T00:00:00"),
        )
    # After exiting the with-block, the row must be visible from a new conn.
    notes = db.get_all_notes()
    assert any(n["title"] == "test" for n in notes)
