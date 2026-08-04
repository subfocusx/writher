"""Tests for notes_window.py — logic methods (non-GUI)."""
import types
import sys
import os
import json
import pytest

project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _make_notes_window(monkeypatch, tmp_path):
    """Create a NotesWindow with all GUI dependencies stubbed."""
    fake_ctk = types.ModuleType("customtkinter")

    def make_fake_frame(**extra):
        children = []
        frame = types.SimpleNamespace(
            pack=lambda **kw: None,
            pack_propagate=lambda v: None,
            configure=lambda **kw: None,
            destroy=lambda: None,
            winfo_children=lambda: children,
            place=lambda **kw: None,
            bind=lambda e, c=None: None,
            _children=children,
            **extra,
        )
        return frame

    fake_ctk.CTkToplevel = lambda root: types.SimpleNamespace(
        winfo_exists=lambda: True,
        attributes=lambda *a: None,
        lift=lambda: None,
        focus_force=lambda: None,
        geometry=lambda g: None,
        destroy=lambda: None,
        configure=lambda **kw: None,
        winfo_x=lambda: 0,
        winfo_y=lambda: 0,
        winfo_width=lambda: 520,
        winfo_height=lambda: 600,
        winfo_screenwidth=lambda: 1920,
        winfo_screenheight=lambda: 1080,
        minsize=lambda *a: None,
        overrideredirect=lambda v: None,
        wm_attributes=lambda *a: None,
        withdraw=lambda: None,
        tk=types.SimpleNamespace(call=lambda *a: 96 / 72),
        pack=lambda **kw: None,
        pack_propagate=lambda v: None,
    )
    fake_ctk.CTkFrame = lambda *a, **kw: make_fake_frame()
    fake_ctk.CTkLabel = lambda *a, **kw: types.SimpleNamespace(
        pack=lambda **kw: None,
        configure=lambda **kw: None,
        place=lambda **kw: None,
        bind=lambda e, c=None: None,
    )
    fake_ctk.CTkButton = lambda *a, **kw: types.SimpleNamespace(
        pack=lambda **kw: None,
        configure=lambda **kw: None,
    )
    fake_ctk.CTkScrollableFrame = lambda *a, **kw: types.SimpleNamespace(
        pack=lambda **kw: None,
        winfo_children=lambda: [],
    )
    fake_ctk.CTkCheckBox = lambda *a, **kw: types.SimpleNamespace(
        pack=lambda **kw: None,
        select=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "customtkinter", fake_ctk)

    fake_pil = types.ModuleType("PIL")
    _fake_image_cls = type("Image", (), {})
    _fake_image_mod = types.ModuleType("PIL.Image")
    _fake_image_mod.Image = _fake_image_cls
    _fake_image_mod.new = lambda *a, **kw: types.SimpleNamespace(
        load=lambda: {}, resize=lambda s, m: types.SimpleNamespace(
            mode="RGB", size=s, load=lambda: {}
        ), convert=lambda m: types.SimpleNamespace(mode=m),
    )
    _fake_image_mod.LANCZOS = 1
    _fake_draw_mod = types.ModuleType("PIL.ImageDraw")
    _fake_draw_mod.Draw = lambda img: types.SimpleNamespace(
        rounded_rectangle=lambda *a, **kw: None,
        ellipse=lambda *a, **kw: None,
        line=lambda *a, **kw: None,
        arc=lambda *a, **kw: None,
        polygon=lambda *a, **kw: None,
    )
    _fake_filter_mod = types.ModuleType("PIL.ImageFilter")
    _fake_filter_mod.GaussianBlur = lambda radius=0: None
    fake_pil.Image = _fake_image_mod
    fake_pil.ImageDraw = _fake_draw_mod
    fake_pil.ImageFilter = _fake_filter_mod
    fake_pil_imagetk = types.ModuleType("PIL.ImageTk")
    fake_pil_imagetk.PhotoImage = lambda img: None
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", _fake_image_mod)
    monkeypatch.setitem(sys.modules, "PIL.ImageDraw", _fake_draw_mod)
    monkeypatch.setitem(sys.modules, "PIL.ImageFilter", _fake_filter_mod)
    monkeypatch.setitem(sys.modules, "PIL.ImageTk", fake_pil_imagetk)

    if project not in sys.path:
        sys.path.insert(0, project)

    import database as _real_db
    monkeypatch.setitem(sys.modules, "database", _real_db)

    if "notes_window" in sys.modules:
        del sys.modules["notes_window"]

    from notes_window import NotesWindow
    root = types.SimpleNamespace(
        after=lambda ms, fn: fn(),
    )
    nw = NotesWindow(root)
    return nw


# ═══════════════════════════════════════════════════════════════════════════════
# Init
# ═══════════════════════════════════════════════════════════════════════════════

def test_notes_window_init():
    assert os.path.isfile(os.path.join(project, "notes_window.py"))


# ═══════════════════════════════════════════════════════════════════════════════
# _close
# ═══════════════════════════════════════════════════════════════════════════════

def test_close_saves_geometry_and_destroys(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    import database
    monkeypatch.setattr(database, "save_setting", lambda k, v: None)
    destroyed = []
    nw._win = types.SimpleNamespace(
        geometry=lambda: "520x600+100+100",
        destroy=lambda: destroyed.append(True),
    )
    nw._maximized = False
    nw._close()
    assert destroyed
    assert nw._win is None


def test_close_when_maximized(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    import database
    monkeypatch.setattr(database, "save_setting", lambda k, v: None)
    destroyed = []
    nw._win = types.SimpleNamespace(
        geometry=lambda: "1920x1080+0+0",
        destroy=lambda: destroyed.append(True),
    )
    nw._maximized = True
    nw._restore_geo = "800x600+200+200"
    nw._close()
    assert destroyed
    assert nw._maximized is False


def test_close_noop_when_no_win(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._win = None
    nw._close()  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# _switch_tab
# ═══════════════════════════════════════════════════════════════════════════════

def test_switch_tab_notes(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._tab_buttons = {
        "notes": types.SimpleNamespace(configure=lambda **kw: None),
        "appointments": types.SimpleNamespace(configure=lambda **kw: None),
        "reminders": types.SimpleNamespace(configure=lambda **kw: None),
    }
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    import database
    monkeypatch.setattr(database, "get_all_notes", lambda **kw: [])
    monkeypatch.setattr(database, "get_appointments", lambda: [])
    monkeypatch.setattr(database, "get_all_reminders", lambda **kw: [])
    nw._switch_tab("notes")
    assert nw._current_tab == "notes"


def test_switch_tab_appointments(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._tab_buttons = {
        "notes": types.SimpleNamespace(configure=lambda **kw: None),
        "appointments": types.SimpleNamespace(configure=lambda **kw: None),
        "reminders": types.SimpleNamespace(configure=lambda **kw: None),
    }
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    import database
    monkeypatch.setattr(database, "get_all_notes", lambda **kw: [])
    monkeypatch.setattr(database, "get_appointments", lambda: [])
    monkeypatch.setattr(database, "get_all_reminders", lambda **kw: [])
    nw._switch_tab("appointments")
    assert nw._current_tab == "appointments"


def test_switch_tab_reminders(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._tab_buttons = {
        "notes": types.SimpleNamespace(configure=lambda **kw: None),
        "appointments": types.SimpleNamespace(configure=lambda **kw: None),
        "reminders": types.SimpleNamespace(configure=lambda **kw: None),
    }
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    import database
    monkeypatch.setattr(database, "get_all_notes", lambda **kw: [])
    monkeypatch.setattr(database, "get_appointments", lambda: [])
    monkeypatch.setattr(database, "get_all_reminders", lambda **kw: [])
    nw._switch_tab("reminders")
    assert nw._current_tab == "reminders"


# ═══════════════════════════════════════════════════════════════════════════════
# _refresh
# ═══════════════════════════════════════════════════════════════════════════════

def test_refresh_notes_empty(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    nw._current_tab = "notes"
    import database
    monkeypatch.setattr(database, "get_all_notes", lambda **kw: [])
    nw._refresh()


def test_refresh_appointments_empty(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    nw._current_tab = "appointments"
    import database
    monkeypatch.setattr(database, "get_appointments", lambda: [])
    nw._refresh()


def test_refresh_reminders_empty(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    nw._current_tab = "reminders"
    import database
    monkeypatch.setattr(database, "get_all_reminders", lambda **kw: [])
    nw._refresh()


# ═══════════════════════════════════════════════════════════════════════════════
# _populate_notes
# ═══════════════════════════════════════════════════════════════════════════════

def test_populate_notes_with_items(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    import database
    notes = [
        {
            "id": 1,
            "title": "Test Note",
            "content": "Hello world",
            "note_type": "text",
            "category": "general",
            "updated_at": "2025-01-15T10:30:00",
        },
    ]
    monkeypatch.setattr(database, "get_all_notes", lambda **kw: notes)
    nw._populate_notes()


def test_populate_notes_list_type(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    import database
    notes = [
        {
            "id": 2,
            "title": "Shopping List",
            "content": json.dumps([
                {"item": "Milk", "checked": False},
                {"item": "Bread", "checked": True},
            ]),
            "note_type": "list",
            "category": "shopping",
            "updated_at": "2025-01-15T10:30:00",
        },
    ]
    monkeypatch.setattr(database, "get_all_notes", lambda **kw: notes)
    nw._populate_notes()


def test_populate_notes_no_title_text(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    import database
    notes = [
        {
            "id": 3,
            "title": None,
            "content": "Content",
            "note_type": "text",
            "category": "",
            "updated_at": "invalid-date",
        },
    ]
    monkeypatch.setattr(database, "get_all_notes", lambda **kw: notes)
    nw._populate_notes()


def test_populate_notes_no_title_list(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    import database
    notes = [
        {
            "id": 4,
            "title": None,
            "content": "[]",
            "note_type": "list",
            "category": "",
            "updated_at": "2025-01-15T10:30:00",
        },
    ]
    monkeypatch.setattr(database, "get_all_notes", lambda **kw: notes)
    nw._populate_notes()


def test_populate_notes_bad_json(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    import database
    notes = [
        {
            "id": 5,
            "title": "Bad List",
            "content": "not-json",
            "note_type": "list",
            "category": "",
            "updated_at": "2025-01-15T10:30:00",
        },
    ]
    monkeypatch.setattr(database, "get_all_notes", lambda **kw: notes)
    nw._populate_notes()


# ═══════════════════════════════════════════════════════════════════════════════
# _populate_appointments
# ═══════════════════════════════════════════════════════════════════════════════

def test_populate_appointments_with_items(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    import database
    appts = [
        {
            "id": 1,
            "title": "Meeting",
            "dt": "2025-01-20T14:00:00",
            "description": "Team sync",
        },
    ]
    monkeypatch.setattr(database, "get_appointments", lambda: appts)
    nw._populate_appointments()


def test_populate_appointments_no_desc(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    import database
    appts = [
        {
            "id": 2,
            "title": "Lunch",
            "dt": "invalid-date",
            "description": None,
        },
    ]
    monkeypatch.setattr(database, "get_appointments", lambda: appts)
    nw._populate_appointments()


# ═══════════════════════════════════════════════════════════════════════════════
# _populate_reminders
# ═══════════════════════════════════════════════════════════════════════════════

def test_populate_reminders_with_items(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    import database
    rems = [
        {
            "id": 1,
            "message": "Call mom",
            "remind_at": "2025-01-20T10:00:00",
            "notified": False,
        },
        {
            "id": 2,
            "message": "Done task",
            "remind_at": "2025-01-15T10:00:00",
            "notified": True,
        },
    ]
    monkeypatch.setattr(database, "get_all_reminders", lambda **kw: rems)
    nw._populate_reminders()


def test_populate_reminders_bad_date(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    import database
    rems = [
        {
            "id": 3,
            "message": "Test",
            "remind_at": "not-a-date",
            "notified": False,
        },
    ]
    monkeypatch.setattr(database, "get_all_reminders", lambda **kw: rems)
    nw._populate_reminders()


# ═══════════════════════════════════════════════════════════════════════════════
# _toggle_maximize
# ═══════════════════════════════════════════════════════════════════════════════

def test_toggle_maximize_no_win(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._win = None
    nw._toggle_maximize()  # Should not raise


def test_toggle_maximize_restore(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    geo = []
    nw._win = types.SimpleNamespace(
        geometry=lambda g=None: geo.append(g) if g else "800x600+100+100",
    )
    nw._max_btn = types.SimpleNamespace(configure=lambda **kw: None)
    nw._maximized = True
    nw._restore_geo = "800x600+100+100"
    nw._toggle_maximize()
    assert nw._maximized is False


def test_toggle_maximize_fullscreen(monkeypatch, tmp_path):
    import ctypes
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._win = types.SimpleNamespace(
        geometry=lambda g=None: "520x600+200+200",
        tk=types.SimpleNamespace(call=lambda *a: 96 / 72),
    )
    nw._max_btn = types.SimpleNamespace(configure=lambda **kw: None)
    nw._maximized = False
    # Mock SystemParametersInfoW
    fake_user32 = types.SimpleNamespace(
        SystemParametersInfoW=lambda *a: None,
    )
    orig_windll = getattr(ctypes, "windll", None)
    ctypes.windll = types.SimpleNamespace(user32=fake_user32)
    try:
        nw._toggle_maximize()
        assert nw._maximized is True
        assert nw._restore_geo == "520x600+200+200"
    finally:
        if orig_windll is not None:
            ctypes.windll = orig_windll


# ═══════════════════════════════════════════════════════════════════════════════
# _start_drag / _on_drag
# ═══════════════════════════════════════════════════════════════════════════════

def test_start_drag(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._maximized = False
    event = types.SimpleNamespace(x=50, y=60)
    nw._start_drag(event)
    assert nw._drag_x == 50
    assert nw._drag_y == 60


def test_start_drag_maximized(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._maximized = True
    event = types.SimpleNamespace(x=50, y=60)
    nw._start_drag(event)
    assert nw._drag_x == 0
    assert nw._drag_y == 0


def test_on_drag(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    geo = []
    nw._win = types.SimpleNamespace(
        winfo_x=lambda: 100,
        winfo_y=lambda: 200,
        geometry=lambda g: geo.append(g),
    )
    nw._maximized = False
    nw._drag_x = 10
    nw._drag_y = 15
    event = types.SimpleNamespace(x=30, y=45)
    nw._on_drag(event)
    assert geo == ["+120+230"]


def test_on_drag_maximized(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._maximized = True
    nw._win = types.SimpleNamespace()
    event = types.SimpleNamespace(x=30, y=45)
    nw._on_drag(event)  # Should return early


def test_on_drag_no_win(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._maximized = False
    nw._win = None
    event = types.SimpleNamespace(x=30, y=45)
    nw._on_drag(event)  # Should return early


# ═══════════════════════════════════════════════════════════════════════════════
# _start_resize / _on_resize
# ═══════════════════════════════════════════════════════════════════════════════

def test_start_resize(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._maximized = False
    nw._win = types.SimpleNamespace(
        winfo_width=lambda: 520,
        winfo_height=lambda: 600,
    )
    event = types.SimpleNamespace(x_root=100, y_root=200)
    nw._start_resize(event)
    assert nw._resize_x == 100
    assert nw._resize_y == 200
    assert nw._resize_w == 520
    assert nw._resize_h == 600


def test_start_resize_maximized(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._maximized = True
    event = types.SimpleNamespace(x_root=100, y_root=200)
    nw._start_resize(event)  # Should return early


def test_on_resize(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._maximized = False
    geo = []
    nw._win = types.SimpleNamespace(
        geometry=lambda g: geo.append(g),
    )
    nw._resize_x = 100
    nw._resize_y = 200
    nw._resize_w = 520
    nw._resize_h = 600
    event = types.SimpleNamespace(x_root=150, y_root=300)
    nw._on_resize(event)
    assert len(geo) == 1


def test_on_resize_maximized(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._maximized = True
    event = types.SimpleNamespace(x_root=150, y_root=300)
    nw._on_resize(event)  # Should return early


def test_on_resize_no_win(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._maximized = False
    nw._win = None
    event = types.SimpleNamespace(x_root=150, y_root=300)
    nw._on_resize(event)  # Should return early


# ═══════════════════════════════════════════════════════════════════════════════
# _delete_note / _delete_appt / _delete_rem / _toggle_item
# ═══════════════════════════════════════════════════════════════════════════════

def test_delete_note(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    deleted = []
    import database
    monkeypatch.setattr(database, "delete_note", lambda nid: deleted.append(nid))
    monkeypatch.setattr(database, "get_all_notes", lambda **kw: [])
    monkeypatch.setattr(database, "get_appointments", lambda: [])
    monkeypatch.setattr(database, "get_all_reminders", lambda **kw: [])
    nw._scroll_frame = types.SimpleNamespace(winfo_children=lambda: [])
    nw._current_tab = "notes"
    nw._tab_buttons = {}
    nw._delete_note(1)
    assert 1 in deleted


def test_delete_appt(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    deleted = []
    import database
    monkeypatch.setattr(database, "delete_appointment", lambda aid: deleted.append(aid))
    monkeypatch.setattr(database, "get_all_notes", lambda **kw: [])
    monkeypatch.setattr(database, "get_appointments", lambda: [])
    monkeypatch.setattr(database, "get_all_reminders", lambda **kw: [])
    nw._scroll_frame = types.SimpleNamespace(winfo_children=lambda: [])
    nw._current_tab = "appointments"
    nw._tab_buttons = {}
    nw._delete_appt(2)
    assert 2 in deleted


def test_delete_rem(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    deleted = []
    import database
    monkeypatch.setattr(database, "delete_reminder", lambda rid: deleted.append(rid))
    monkeypatch.setattr(database, "get_all_notes", lambda **kw: [])
    monkeypatch.setattr(database, "get_appointments", lambda: [])
    monkeypatch.setattr(database, "get_all_reminders", lambda **kw: [])
    nw._scroll_frame = types.SimpleNamespace(winfo_children=lambda: [])
    nw._current_tab = "reminders"
    nw._tab_buttons = {}
    nw._delete_rem(3)
    assert 3 in deleted


def test_toggle_item(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    toggled = []
    import database
    monkeypatch.setattr(database, "check_item", lambda nid, txt: toggled.append((nid, txt)))
    monkeypatch.setattr(database, "get_all_notes", lambda **kw: [])
    monkeypatch.setattr(database, "get_appointments", lambda: [])
    monkeypatch.setattr(database, "get_all_reminders", lambda **kw: [])
    nw._scroll_frame = types.SimpleNamespace(winfo_children=lambda: [])
    nw._current_tab = "notes"
    nw._tab_buttons = {}
    nw._toggle_item(1, "Milk")
    assert (1, "Milk") in toggled


# ═══════════════════════════════════════════════════════════════════════════════
# show (with existing window)
# ═══════════════════════════════════════════════════════════════════════════════

def test_show_existing_window(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._win = types.SimpleNamespace(
        winfo_exists=lambda: True,
        attributes=lambda *a: None,
        lift=lambda: None,
        focus_force=lambda: None,
        after=lambda ms, fn: None,
    )
    nw._tab_buttons = {
        "notes": types.SimpleNamespace(configure=lambda **kw: None),
        "appointments": types.SimpleNamespace(configure=lambda **kw: None),
        "reminders": types.SimpleNamespace(configure=lambda **kw: None),
    }
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    import database
    monkeypatch.setattr(database, "get_all_notes", lambda **kw: [])
    monkeypatch.setattr(database, "get_appointments", lambda: [])
    monkeypatch.setattr(database, "get_all_reminders", lambda **kw: [])
    nw.show("notes")


# ═══════════════════════════════════════════════════════════════════════════════
# _make_card / _make_delete_btn / _empty_label
# ═══════════════════════════════════════════════════════════════════════════════

def test_make_card(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    card = nw._make_card()
    assert card is not None


def test_make_delete_btn(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    called = []
    btn = nw._make_delete_btn(
        types.SimpleNamespace(pack=lambda **kw: None),
        lambda: called.append(True),
    )
    assert btn is not None


def test_empty_label(monkeypatch, tmp_path):
    nw = _make_notes_window(monkeypatch, tmp_path)
    nw._scroll_frame = types.SimpleNamespace(
        winfo_children=lambda: [],
    )
    nw._empty_label("No items")
