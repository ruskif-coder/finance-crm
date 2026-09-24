# -*- coding: utf-8 -*-
"""Находки ревью этапа 6 (аудит 23.09.2026) — по прибору на каждую.

1. Письмо площадке, поставленное на повтор днём, роняло рассылку: срок тихих часов
   днём пуст, а ответ форматировал его как дату.
2. Сканер: сбой внутри рассылки события (или в хуке после неё) стирал отметку — и
   следующий прогон слал то же письмо тем, кому оно уже ушло.
3. Подстановка без значения оставляла висящий разделитель: «· 3 события».
4. Правка шаблона письма площадке не проходила заслон денег.
5. Досылка сотрудникам — одним прогоном за раз.
6. Письмо площадке с правкой карточки — через настоящую прослойку рассылки.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.main  # noqa: F401 — все модели
from app.database import SessionLocal, engine
from app.mail import client as mail
from app.mail import editor
from app.notify import dispatch, scanner
from app.notify.models import NotificationAlertState, NotificationScanRun
from app.notify.outward import send as osend

SETTINGS = ("mail_cards_pub",)


@pytest.fixture
def settings_snapshot():
    s = SessionLocal()
    snap = dict(s.execute(text("SELECT key, value FROM company_settings WHERE key = ANY(:k)"),
                          {"k": list(SETTINGS)}).all())
    yield s
    s.rollback()
    s.execute(text("DELETE FROM company_settings WHERE key = ANY(:k)"), {"k": list(SETTINGS)})
    for k, v in snap.items():
        s.execute(text("INSERT INTO company_settings (key, value) VALUES (:k, :v)"),
                  {"k": k, "v": v})
    s.commit()
    s.close()


def _publisher(db):
    row = db.execute(text("SELECT id FROM sales_publishers ORDER BY id LIMIT 1")).first()
    if not row:
        pytest.skip("на стенде нет площадок")
    return row[0]


def _wire_publisher_letter(monkeypatch, status="queued"):
    """Прослойка рассылки с подменённой отправкой и одним получателем."""
    sent = []
    monkeypatch.setattr(mail, "configured", lambda: True)
    monkeypatch.setattr(osend, "_to_panel", lambda *a, **kw: {"status": "ok"})
    monkeypatch.setattr(osend, "_to_bot", lambda *a, **kw: {"status": "no_channel"})
    monkeypatch.setattr(osend, "_recipients", lambda db, pid: [
        {"contact_id": None, "email": "pub@example.org", "name": "Контакт"}])
    monkeypatch.setattr(osend.prefs, "accounts_by_contact", lambda db, pid: {})
    monkeypatch.setattr(osend.prefs, "cell", lambda m, kind, ch: ch == osend.prefs.MAIL)
    from app.notify.outward import schedule
    monkeypatch.setattr(schedule, "due_at", lambda *a, **kw: None)   # день, не тихие часы

    def fake_send(db, **kw):
        sent.append(kw)
        return SimpleNamespace(status=status, id=1, error="сервер недоступен",
                               send_after=1)
    import app.mail.send as msend
    monkeypatch.setattr(msend, "send_and_log", fake_send)
    return sent


# ── 1 ────────────────────────────────────────────────────────────────────────

def test_a_daytime_retry_does_not_crash_the_mailing(settings_snapshot, monkeypatch):
    db = settings_snapshot
    _wire_publisher_letter(monkeypatch, status="queued")
    out = osend.notify_publisher(db, "новый креатив", _publisher(db), title="т", body="т")
    assert out["status"] in ("held", "retry"), out


# ── 4 и 6 ────────────────────────────────────────────────────────────────────

def test_a_card_edit_reaches_the_publisher_letter_through_the_real_path(
        settings_snapshot, monkeypatch):
    db = settings_snapshot
    editor.save_card(db, editor.PUB, "новый креатив", {"title": "Свежий материал: {площадка}"})
    db.commit()
    sent = _wire_publisher_letter(monkeypatch, status="sent")
    osend.notify_publisher(db, "новый креатив", _publisher(db), title="Код", body="т")
    assert sent and "Свежий материал:" in sent[0]["html"]


def test_money_typed_into_a_template_does_not_reach_the_publisher(
        settings_snapshot, monkeypatch):
    db = settings_snapshot
    editor.save_card(db, editor.PUB, "новый креатив",
                     {"body": "Стоимость размещения 500 000 ₽"})
    db.commit()
    sent = _wire_publisher_letter(monkeypatch, status="sent")
    osend.notify_publisher(db, "новый креатив", _publisher(db), title="т",
                           body="Текст из кода")
    assert "500 000" not in sent[0]["html"] and "500 000" not in sent[0]["body"]
    assert "Текст из кода" in sent[0]["html"], "вместо денег — текст из кода"


# ── 3 ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tpl,want", [("{площадка} · {всего}", "3 события"),
                                      ("{всего} · {темы}", "3 события"),
                                      ("{площадка} · за сутки {всего}", "за сутки 3 события")])
def test_an_empty_substitution_leaves_no_dangling_separator(tpl, want):
    assert editor.subst(tpl, {"площадка": "", "темы": "", "всего": "3 события"}) == want


# ── 2 ────────────────────────────────────────────────────────────────────────

@pytest.fixture
def scan_world(monkeypatch):
    s = SessionLocal()
    before = (s.query(NotificationScanRun.id).order_by(NotificationScanRun.id.desc())
              .first() or (0,))[0]
    sent = []
    monkeypatch.setattr(scanner.registry, "get", lambda key: SimpleNamespace(params={}))
    yield SimpleNamespace(sent=sent)
    s.query(NotificationAlertState).filter(
        NotificationAlertState.event_key.like("test_scan6%")).delete(synchronize_session=False)
    s.query(NotificationScanRun).filter(NotificationScanRun.id > before).delete()
    s.commit()
    s.close()


def test_a_failure_inside_emit_does_not_resend_next_run(scan_world, monkeypatch):
    calls = []

    def emit(db, key, **kw):
        calls.append(key)
        raise RuntimeError("сбой на втором получателе — первому уже ушло")

    monkeypatch.setattr(scanner, "RULES", {
        "test_scan6_a": lambda db, ev: [scanner.Hit("test_entity", 999611, "первая", "т")]})
    monkeypatch.setattr(scanner, "AFTER_SEND", {})
    monkeypatch.setattr(scanner, "emit", emit)
    scanner.scan()
    scanner.scan()
    assert calls.count("test_scan6_a") == 1, "повторный прогон разослал то же снова"


def test_a_failing_hook_does_not_abort_the_scan(scan_world, monkeypatch):
    sent = []

    def hook(db, hit, now):
        raise RuntimeError("хук упал")

    monkeypatch.setattr(scanner, "RULES", {
        "test_scan6_b": lambda db, ev: [scanner.Hit("test_entity", 999612, "первая", "т")]})
    monkeypatch.setattr(scanner, "AFTER_SEND", {"test_scan6_b": hook})
    monkeypatch.setattr(scanner, "emit", lambda db, key, **kw: sent.append(key) or [])
    scanner.scan()
    scanner.scan()
    assert sent.count("test_scan6_b") == 1


# ── 5 ────────────────────────────────────────────────────────────────────────

def test_overlapping_dispatch_runs_do_not_send_twice():
    from app.ext_lock import STAFF_DISPATCH

    holder = engine.connect()
    holder.execute(text("SELECT pg_advisory_lock(:a, 1)"), {"a": STAFF_DISPATCH})
    try:
        assert dispatch.flush().get("busy")
    finally:
        holder.execute(text("SELECT pg_advisory_unlock(:a, 1)"), {"a": STAFF_DISPATCH})
        holder.close()
