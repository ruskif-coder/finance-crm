# -*- coding: utf-8 -*-
"""Письма площадке — только сотруднику с учёткой кабинета (владелец 29.10.2026).

Контакт, заведённый без учётки, не может войти в кабинет и снять «Письма» — значит, и писать ему нельзя: добавили
человека, и ему пошла вся почта. Учётка выключена — то же самое. Проверяется в транзакции с откатом."""
import inspect

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.mail import flush as F
from app.notify.outward import digest as D
from app.notify.outward import send as S

MAIL = "no-account-29@test.local"


@pytest.fixture
def db():
    s = SessionLocal()
    pid = s.execute(text("""
        SELECT p.id FROM sales_publishers p WHERE p.status <> 'АРХИВ' AND NOT EXISTS (
            SELECT 1 FROM cabinet_publisher cp JOIN cabinet cab ON cab.id = cp.cabinet_id
             WHERE cp.publisher_id = p.id AND cab.state = 'приостановлен') ORDER BY p.id LIMIT 1""")).scalar()
    if pid is None:
        s.close()
        pytest.skip("на стенде нет живой площадки")
    cid = s.execute(text("""INSERT INTO sales_publisher_contacts (publisher_id, name, email, notify, is_primary)
                            VALUES (:p, 'Без учётки', :e, true, false) RETURNING id"""), {"p": pid, "e": MAIL}).scalar()
    yield s, pid, cid
    s.rollback()
    s.close()


def _mailed(s, pid):
    return MAIL in [r["email"] for r in S._recipients(s, pid)]


def test_contact_without_account_gets_no_mail(db):
    s, pid, _ = db
    assert not _mailed(s, pid)
    assert F._still_wanted(s, MAIL, pid) is False


def test_contact_with_active_account_gets_mail_and_switched_off_account_does_not(db):
    s, pid, cid = db
    s.execute(text("INSERT INTO cabinet_account (email, name, contact_id, is_active) VALUES (:e, 'Т', :c, true)"),
              {"e": MAIL, "c": cid})
    assert _mailed(s, pid)
    assert F._still_wanted(s, MAIL, pid) is True
    s.execute(text("UPDATE cabinet_account SET is_active = false WHERE contact_id = :c"), {"c": cid})
    assert not _mailed(s, pid)
    assert F._still_wanted(s, MAIL, pid) is False


def test_digest_uses_the_same_rule():
    """Накопленное в дайджесте тоже не уходит контакту без учётки — одно условие на три отбора."""
    assert "{HAS_CABINET_ACCESS}" in inspect.getsource(D)
    assert "{HAS_CABINET_ACCESS}" in inspect.getsource(F._still_wanted)
