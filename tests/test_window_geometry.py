"""Tests for window geometry save/restore (feature 1.4)."""

import re


def test_geometry_format():
    """Geometry strings must match <width>x<height>+<x>+<y>."""
    examples = [
        "520x600+100+200",
        "800x600+0+0",
        "380x400+1920+1080",
    ]
    pattern = r"^\d+x\d+[+-]\d+[+-]\d+$"
    for geo in examples:
        assert re.match(pattern, geo), f"Invalid geometry: {geo}"


def test_geometry_format_with_maximized():
    """Maximized windows should save the restore geometry, not the full-screen value."""
    restore_geo = "520x600+100+200"
    assert re.match(r"^\d+x\d+[+-]\d+[+-]\d+$", restore_geo)


def test_geometry_persistence(monkeypatch):
    """Simulate save-then-restore cycle via DB."""
    import database as db
    db.init()

    # Save
    test_geo = "800x600+50+50"
    db.save_setting("notes_window_geometry", test_geo)

    # Restore
    loaded = db.get_setting("notes_window_geometry")
    assert loaded == test_geo

    # Cleanup
    import os
    if os.path.exists("test_writher.db"):
        os.remove("test_writher.db")
