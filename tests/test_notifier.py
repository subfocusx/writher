"""Tests for notifier.py — toast notifications and reminder/appointment scheduler."""
import types
import threading
import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# _ps_escape
# ═══════════════════════════════════════════════════════════════════════════════

def test_ps_escape_plain():
    from notifier import _ps_escape
    assert _ps_escape("hello world") == "hello world"


def test_ps_escape_double_quote():
    from notifier import _ps_escape
    assert _ps_escape('say "hi"') == 'say `"hi`"'


def test_ps_escape_single_quote():
    from notifier import _ps_escape
    assert _ps_escape("it's") == "it`'s"


def test_ps_escape_newline():
    from notifier import _ps_escape
    assert _ps_escape("line1\nline2") == "line1 line2"


def test_ps_escape_empty():
    from notifier import _ps_escape
    assert _ps_escape("") == ""


def test_ps_escape_all_special():
    from notifier import _ps_escape
    assert _ps_escape('a"b\nc') == 'a`"b c'


# ═══════════════════════════════════════════════════════════════════════════════
# ReminderScheduler
# ═══════════════════════════════════════════════════════════════════════════════

class TestReminderScheduler:

    def test_init(self):
        from notifier import ReminderScheduler
        s = ReminderScheduler()
        assert s._stop is not None
        assert isinstance(s._stop, threading.Event)
        assert s._thread is None

    def test_stop_sets_event(self):
        from notifier import ReminderScheduler
        s = ReminderScheduler()
        s.stop()
        assert s._stop.is_set()

    def test_start_creates_daemon_thread(self):
        from notifier import ReminderScheduler
        s = ReminderScheduler()
        s.start()
        assert s._thread is not None
        assert s._thread.is_alive()
        assert s._thread.daemon is True
        s.stop()
        s._thread.join(timeout=2)

    def test_loop_calls_check_reminders_and_check_appointments(self, monkeypatch):
        from notifier import ReminderScheduler
        s = ReminderScheduler()
        calls = []
        call_count = [0]
        def fake_reminders():
            calls.append("reminders")
        def fake_appointments():
            calls.append("appointments")
            call_count[0] += 1
            if call_count[0] >= 1:
                s._stop.set()
        monkeypatch.setattr(s, "_check_reminders", fake_reminders)
        monkeypatch.setattr(s, "_check_appointments", fake_appointments)
        s._loop()
        assert "reminders" in calls
        assert "appointments" in calls


# ═══════════════════════════════════════════════════════════════════════════════
# _check_reminders
# ═══════════════════════════════════════════════════════════════════════════════

def test_check_reminders_notifies_pending(monkeypatch):
    import notifier
    from notifier import ReminderScheduler

    notified_ids = []
    toasts = []
    monkeypatch.setattr(notifier, "_send_toast",
                        lambda title, msg: toasts.append((title, msg)))
    monkeypatch.setattr(notifier.db, "get_pending_reminders",
                        lambda: [{"id": 1, "message": "Test reminder"}])
    monkeypatch.setattr(notifier.db, "mark_reminder_notified",
                        lambda rid: notified_ids.append(rid))
    monkeypatch.setattr(notifier.locales, "get",
                        lambda key, **kw: key)

    s = ReminderScheduler()
    s._check_reminders()

    assert len(toasts) == 1
    assert notified_ids == [1]


def test_check_reminders_empty(monkeypatch):
    import notifier
    from notifier import ReminderScheduler

    toasts = []
    monkeypatch.setattr(notifier, "_send_toast",
                        lambda title, msg: toasts.append((title, msg)))
    monkeypatch.setattr(notifier.db, "get_pending_reminders", lambda: [])
    monkeypatch.setattr(notifier.locales, "get",
                        lambda key, **kw: key)

    s = ReminderScheduler()
    s._check_reminders()
    assert len(toasts) == 0


def test_check_reminders_handles_db_error(monkeypatch):
    import notifier
    from notifier import ReminderScheduler

    def bad_get():
        raise RuntimeError("DB error")

    monkeypatch.setattr(notifier.db, "get_pending_reminders", bad_get)

    s = ReminderScheduler()
    s._check_reminders()  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# _check_appointments
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_config_attr():
    """Ensure APPOINTMENT_REMIND_MINUTES exists on config for monkeypatching."""
    import config
    if not hasattr(config, "APPOINTMENT_REMIND_MINUTES"):
        setattr(config, "APPOINTMENT_REMIND_MINUTES", 15)


def test_check_appointments_notifies_upcoming(monkeypatch):
    import notifier
    from notifier import ReminderScheduler
    from datetime import datetime, timedelta
    _ensure_config_attr()

    toasts = []
    notified_ids = []
    future = datetime.now() + timedelta(minutes=10)
    monkeypatch.setattr(notifier, "_send_toast",
                        lambda title, msg: toasts.append((title, msg)))
    monkeypatch.setattr(notifier.config, "APPOINTMENT_REMIND_MINUTES", 15)
    monkeypatch.setattr(notifier.db, "get_upcoming_appointments",
                        lambda within_minutes=15: [
                            {"id": 42, "title": "Meeting", "dt": future.isoformat()}
                        ])
    monkeypatch.setattr(notifier.db, "mark_appointment_notified",
                        lambda aid: notified_ids.append(aid))
    monkeypatch.setattr(notifier.locales, "get",
                        lambda key, **kw: kw.get("title", key))

    s = ReminderScheduler()
    s._check_appointments()

    assert len(toasts) == 1
    assert notified_ids == [42]


def test_check_appointments_now(monkeypatch):
    import notifier
    from notifier import ReminderScheduler
    from datetime import datetime
    _ensure_config_attr()

    toasts = []
    monkeypatch.setattr(notifier, "_send_toast",
                        lambda title, msg: toasts.append((title, msg)))
    monkeypatch.setattr(notifier.config, "APPOINTMENT_REMIND_MINUTES", 15)
    monkeypatch.setattr(notifier.db, "get_upcoming_appointments",
                        lambda within_minutes=15: [
                            {"id": 1, "title": "Now event", "dt": datetime.now().isoformat()}
                        ])
    monkeypatch.setattr(notifier.db, "mark_appointment_notified", lambda aid: None)
    monkeypatch.setattr(notifier.locales, "get",
                        lambda key, **kw: key)

    s = ReminderScheduler()
    s._check_appointments()
    assert len(toasts) == 1


def test_check_appointments_invalid_dt(monkeypatch):
    import notifier
    from notifier import ReminderScheduler
    _ensure_config_attr()

    toasts = []
    monkeypatch.setattr(notifier, "_send_toast",
                        lambda title, msg: toasts.append((title, msg)))
    monkeypatch.setattr(notifier.config, "APPOINTMENT_REMIND_MINUTES", 15)
    monkeypatch.setattr(notifier.db, "get_upcoming_appointments",
                        lambda within_minutes=15: [
                            {"id": 2, "title": "Bad dt", "dt": "not-a-date"}
                        ])
    monkeypatch.setattr(notifier.db, "mark_appointment_notified", lambda aid: None)
    monkeypatch.setattr(notifier.locales, "get",
                        lambda key, **kw: key)

    s = ReminderScheduler()
    s._check_appointments()
    assert len(toasts) == 1


def test_check_appointments_handles_db_error(monkeypatch):
    import notifier
    from notifier import ReminderScheduler
    _ensure_config_attr()

    def bad_get(within_minutes=15):
        raise RuntimeError("DB error")

    monkeypatch.setattr(notifier.db, "get_upcoming_appointments", bad_get)

    s = ReminderScheduler()
    s._check_appointments()  # Should not raise


def test_check_appointments_empty(monkeypatch):
    import notifier
    from notifier import ReminderScheduler
    _ensure_config_attr()

    toasts = []
    monkeypatch.setattr(notifier, "_send_toast",
                        lambda title, msg: toasts.append((title, msg)))
    monkeypatch.setattr(notifier.config, "APPOINTMENT_REMIND_MINUTES", 15)
    monkeypatch.setattr(notifier.db, "get_upcoming_appointments",
                        lambda within_minutes=15: [])
    monkeypatch.setattr(notifier.locales, "get",
                        lambda key, **kw: key)

    s = ReminderScheduler()
    s._check_appointments()
    assert len(toasts) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# _send_toast
# ═══════════════════════════════════════════════════════════════════════════════

def test_send_toast_no_backend(monkeypatch):
    import notifier
    monkeypatch.setattr(notifier, "_backend", None)
    monkeypatch.setattr(notifier, "subprocess", types.SimpleNamespace(
        Popen=lambda *a, **kw: None
    ))
    notifier._send_toast("Title", "Message")


def test_send_toast_winotify_success(monkeypatch):
    import notifier
    fake_toast = types.SimpleNamespace(show=lambda: None)
    monkeypatch.setattr(notifier, "_backend", "winotify")
    monkeypatch.setattr(notifier, "_WinotifyNotification",
                        lambda **kw: fake_toast)
    monkeypatch.setattr(notifier, "get_notification_icon_path",
                        lambda: "icon.ico")
    notifier._send_toast("T", "M")


def test_send_toast_winotify_failure(monkeypatch):
    import notifier
    monkeypatch.setattr(notifier, "_backend", "winotify")
    monkeypatch.setattr(notifier, "_WinotifyNotification",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("fail")))
    monkeypatch.setattr(notifier, "get_notification_icon_path",
                        lambda: "icon.ico")
    monkeypatch.setattr(notifier, "subprocess", types.SimpleNamespace(
        Popen=lambda *a, **kw: None
    ))
    notifier._send_toast("T", "M")


def test_send_toast_plyer_success(monkeypatch):
    import notifier
    called = []
    monkeypatch.setattr(notifier, "_backend", "plyer")
    monkeypatch.setattr(notifier, "_WinotifyNotification", None)
    notifier._plyer = types.SimpleNamespace(notify=lambda **kw: called.append(kw))
    monkeypatch.setattr(notifier, "get_notification_icon_path",
                        lambda: "icon.ico")
    notifier._send_toast("T", "M")
    assert len(called) == 1


def test_send_toast_plyer_failure(monkeypatch):
    import notifier
    monkeypatch.setattr(notifier, "_backend", "plyer")
    monkeypatch.setattr(notifier, "_WinotifyNotification", None)
    notifier._plyer = types.SimpleNamespace(
        notify=lambda **kw: (_ for _ in ()).throw(RuntimeError("fail")))
    monkeypatch.setattr(notifier, "get_notification_icon_path",
                        lambda: "icon.ico")
    monkeypatch.setattr(notifier, "subprocess", types.SimpleNamespace(
        Popen=lambda *a, **kw: None
    ))
    notifier._send_toast("T", "M")
