# -*- coding: utf-8 -*-
"""Будильник в «Статусах продаж» (владелец 23.10.2026): на строку рекламодателя или бренда человек ставит себе дату — в
09:00 МСК этого дня (сканер уведомлений) напоминание уходит в Telegram и на почту, один раз; новая дата — снова.
Один будильник на строку у каждого. Свои строки тест убирает."""
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.routers import sales_status as SS


@pytest.fixture
def env():
    from app.models import Role, User
    db = SessionLocal()
    users = (db.query(User).join(Role, Role.id == User.role_id).filter(Role.key == "admin", User.is_active == 1)
             .order_by(User.id).limit(1).all())
    other = db.query(User).filter(User.is_active == 1).order_by(User.id.desc()).first()
    row = db.execute(text("SELECT a.id, b.id FROM sales_advertisers a JOIN sales_brands b ON b.advertiser_id = a.id "
                          "ORDER BY a.id LIMIT 1")).first()
    if not users or not row or not other or other.id == users[0].id:
        db.close()
        pytest.skip("на стенде не хватает людей или брендов")
    me = users[0]
    try:
        yield db, me, other, row[0], row[1]
    finally:
        db.rollback()
        db.execute(text("DELETE FROM sales_status_reminders WHERE note LIKE 'тест будильника%'"))
        db.execute(text("DELETE FROM audit_log WHERE action LIKE 'status_reminder%' AND details LIKE '%тест будильника%'"))
        db.commit()
        db.close()


def _set(db, user, adv, brand, on, note="тест будильника"):
    return SS.set_reminder(SS.ReminderIn(advertiser_id=adv, brand_id=brand, remind_on=on, note=note), db, user)


def test_one_reminder_per_row_and_new_date_rearms_it(env):
    db, me, _, adv, brand = env
    a = _set(db, me, adv, brand, date.today() + timedelta(days=3))
    db.execute(text("UPDATE sales_status_reminders SET sent_at = now() WHERE id = :i"), {"i": a["id"]})
    db.commit()
    b = _set(db, me, adv, brand, date.today() + timedelta(days=5), "тест будильника 2")
    assert a["id"] == b["id"]
    n, sent = db.execute(text("SELECT count(*), max(sent_at) FROM sales_status_reminders WHERE user_id = :u AND brand_id = :b"),
                         {"u": me.id, "b": brand}).first()
    assert n == 1 and sent is None


def test_past_date_and_foreign_brand_are_refused(env):
    db, me, _, adv, brand = env
    with pytest.raises(HTTPException):
        _set(db, me, adv, brand, date.today() - timedelta(days=1))
    other_adv = db.execute(text("SELECT id FROM sales_advertisers WHERE id <> :a ORDER BY id LIMIT 1"), {"a": adv}).scalar()
    with pytest.raises(HTTPException):
        _set(db, me, other_adv, brand, date.today())


def test_someone_elses_reminder_is_not_removable(env):
    db, me, other, adv, brand = env
    r = _set(db, other, adv, brand, date.today() + timedelta(days=1))
    with pytest.raises(HTTPException) as e:
        SS.delete_reminder(r["id"], db, me)
    assert e.value.status_code == 404
    SS.delete_reminder(r["id"], db, other)
    assert db.execute(text("SELECT count(*) FROM sales_status_reminders WHERE id = :i"), {"i": r["id"]}).scalar() == 0


def test_scanner_sends_due_once_to_its_owner(env):
    from app.notify import recipients, registry, scanner
    db, me, _, adv, brand = env
    due = _set(db, me, adv, brand, date.today())
    later = _set(db, me, adv, None, date.today() + timedelta(days=2))
    ev = registry.get("sales_status_reminder")
    assert ev and ev.channels.get("tg") and ev.channels.get("mail")
    hits = {h.entity_id: h for h in scanner.RULES["sales_status_reminder"](db, ev)}
    assert due["id"] in hits and later["id"] not in hits
    h = hits[due["id"]]
    assert recipients.resolve(db, ev.recipients, h.ctx) == [me.id]
    assert "/sales/status" in h.link
    scanner.AFTER_SEND["sales_status_reminder"](db, h, datetime.utcnow())
    db.commit()
    assert due["id"] not in {x.entity_id for x in scanner.RULES["sales_status_reminder"](db, ev)}


def test_matrix_shows_reminders_with_mine_flag(env):
    db, me, other, adv, brand = env
    _set(db, me, adv, brand, date.today() + timedelta(days=1))
    _set(db, other, adv, brand, date.today() + timedelta(days=2))
    m = date.today().strftime("%Y-%m")
    got = [r for r in SS.matrix(m, m, db, me)["reminders"] if r["brand_id"] == brand and (r["note"] or "").startswith("тест будильника")]
    assert sorted(r["mine"] for r in got) == [False, True]


def test_rearmed_same_day_reminder_is_a_new_stage(env):
    """Ревью 23.10: будильник на тот же день, переставленный после отправки, должен уйти снова, а не через 10 дней повтора."""
    from app.notify import registry, scanner
    db, me, _, adv, brand = env
    r = _set(db, me, adv, brand, date.today())
    ev = registry.get("sales_status_reminder")
    first = next(h for h in scanner.RULES["sales_status_reminder"](db, ev) if h.entity_id == r["id"])
    scanner.AFTER_SEND["sales_status_reminder"](db, first, datetime.utcnow())
    db.commit()
    import time
    time.sleep(1.1)
    _set(db, me, adv, brand, date.today(), "тест будильника — переставлен")
    again = next(h for h in scanner.RULES["sales_status_reminder"](db, ev) if h.entity_id == r["id"])
    assert again.stage != first.stage


def test_unknown_advertiser_and_long_client_name_are_400_not_500(env):
    db, me, _, adv, brand = env
    with pytest.raises(HTTPException) as e:
        _set(db, me, 987654321, None, date.today())
    assert e.value.status_code == 400
    r = SS.set_reminder(SS.ReminderIn(client_name="Клиент " * 80, remind_on=date.today(), note="тест будильника длинный"), db, me)
    assert r["id"]
