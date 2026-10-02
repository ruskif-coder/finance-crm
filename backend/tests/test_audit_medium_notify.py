# -*- coding: utf-8 -*-
"""Средние находки аудита 01.10.2026, группа «уведомления» (С-4, С-5, С-6, С-13)."""
import inspect
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.main  # noqa: F401
from app.database import SessionLocal


def test_c4_traffic_silence_skips_withdrawn_pairs():
    """«Трафик не проверил» не напоминает про отозванную пару — как и соседнее правило
    про молчание площадки."""
    from app.notify import scanner
    src = inspect.getsource(scanner.rule_traffic_silence)
    assert "withdrawn_at.is_(None)" in src


def test_c5_erid_letter_once_per_publisher(monkeypatch):
    """Площадка с web и app получала два одинаковых письма «ЕРИД выпущен»."""
    from app.routers import launch_prep as lp
    from app.notify import outward
    sent = []
    monkeypatch.setattr(outward, "notify_publisher", lambda db, kind, pid, **kw: sent.append(pid))
    monkeypatch.setattr(lp, "_deal_brand_name", lambda db, d: "Бренд")
    monkeypatch.setattr(lp, "deal_period_text", lambda d: "10.2026")
    pub = SimpleNamespace(id=7, domain="site.ru", name="site")
    rows = [(pub, SimpleNamespace(id=1)), (pub, SimpleNamespace(id=2)),
            (SimpleNamespace(id=8, domain="b.ru", name="b"), SimpleNamespace(id=3))]

    class Q:
        def __getattr__(self, n):
            return lambda *a, **k: self

        def all(self):
            return rows
    lp._tell_publisher_erid(SimpleNamespace(query=lambda *a: Q()), SimpleNamespace(id=1, no=1, erid="E"),
                            SimpleNamespace())
    assert sorted(sent) == [7, 8]


def test_c6_queued_letter_to_a_dropped_contact_is_not_sent(monkeypatch):
    """Письмо, отложенное на тихие часы, не уходит, если за это время контакт снял отметку
    «получает уведомления», удалён или кабинет приостановлен."""
    from app.mail import flush as F
    from app.mail.models import MailLog
    from app.mail import client as mail
    db = SessionLocal()
    row = MailLog(to_email="nobody-c6@test.invalid", subject="т", body="т", kind="pub_notify",
                  status="queued", send_after=text("now() - interval '1 minute'"))
    db.add(row)
    db.commit()
    rid = row.id
    sent = []
    monkeypatch.setattr(mail, "configured", lambda: True)
    monkeypatch.setattr(mail, "send", lambda **kw: sent.append(kw) or "mid")
    try:
        F.flush()
        st = db.execute(text("SELECT status FROM mail_log WHERE id = :i"), {"i": rid}).scalar()
        assert not sent and st == "suppressed"
    finally:
        db.execute(text("DELETE FROM mail_log WHERE id = :i"), {"i": rid})
        db.commit()
        db.close()


def test_c13_urllib_is_guarded_too():
    """Бот Telegram ходит через urllib — защита тестов от сети обязана ловить и его."""
    import urllib.request
    from tests.conftest import NetworkInTest
    with pytest.raises(NetworkInTest):
        urllib.request.urlopen("https://api.telegram.org/bot0/getMe", timeout=1)


def test_v8_archived_publisher_gets_nothing(monkeypatch):
    """Аудит 01.10.2026, В-8: площадке в архиве не уходит ничего ни в один канал."""
    from app.notify.outward import send
    called = []
    monkeypatch.setattr(send, "_enabled", lambda db, k: True)
    monkeypatch.setattr(send, "_to_panel", lambda *a, **k: called.append("panel"))
    monkeypatch.setattr(send, "_to_bot", lambda *a, **k: called.append("tg"))
    monkeypatch.setattr(send, "_is_archived", lambda db, pid: True)
    from app.notify.outward import kinds
    out = send.notify_publisher(None, next(k for k in kinds.KINDS if k.built).key, 1, title="т")
    assert out["status"] == "off" and not called


def test_v8_cabinet_counters_skip_archived():
    from app.cabinet import overview as O
    for fn in (O.creatives_pending, O.campaigns_live, O.recons_open):
        assert "АРХИВ" in inspect.getsource(fn), fn.__name__



def test_c6_same_email_at_another_publisher_does_not_unlock_the_letter():
    """Адрес — живой контакт площадки Б, а письмо адресовано площадке А, где он отписан:
    письмо А не уходит (С-6, колонка mail_log.publisher_id, 02.10.2026)."""
    from app.mail import flush as F
    db = SessionLocal()
    try:
        r = db.execute(text("""SELECT c.email, c.publisher_id FROM sales_publisher_contacts c
              JOIN sales_publishers p ON p.id = c.publisher_id
             WHERE c.notify AND coalesce(c.email,'') <> '' AND p.status <> 'АРХИВ' LIMIT 1""")).first()
        if not r:
            pytest.skip("нет живого контакта на стенде")
        other = db.execute(text("SELECT id FROM sales_publishers WHERE id <> :p LIMIT 1"),
                           {"p": r[1]}).scalar()
        assert F._still_wanted(db, r[0], r[1]) is True
        assert F._still_wanted(db, r[0], other) is False
        assert F._still_wanted(db, r[0], None) is True, "старые строки — по адресу"
    finally:
        db.close()
