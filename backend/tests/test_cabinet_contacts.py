# -*- coding: utf-8 -*-
"""Правка контактов и учёток кабинета: что ломается молча.

Три правила, каждое из которых до первой поломки проверяется глазами:

  · **правка контакта ЧАСТИЧНАЯ.** Прежняя редакция `update_contact` присваивала все
    восемь полей из тела, поэтому вызов с двумя полями стирал телеграм, телефон и
    заметку. Ничего не падает — данные просто исчезают, и заметить это можно только
    открыв карточку паблишера;
  · **главное контактное лицо у площадки ОДНО.** Зелёный квадрат на трёх строках не
    значит ничего, а назначение без снятия прежнего именно это и даёт;
  · **два входа выдачи доступа не взаимозаменяемы.** В кабинет площадки человек
    приходит из реестра, в служебный — заводится на месте. Перепутать их значит либо
    завести вторую запись о том же человеке, либо приписать нашего сотрудника к чужой
    площадке.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from types import SimpleNamespace

from app.cabinet import overview
from app.database import SessionLocal
from app.routers.cabinets import AccessIn, AccountPatch, grant_access, update_account
from app.routers.publishers import ContactIn, update_contact
from app.sales.models import SalesPublisher  # noqa: F401  — см. test_cabinet_scope

ADMIN = SimpleNamespace(role=SimpleNamespace(key='admin'), id=None, name='прибор')


@pytest.fixture
def stand():
    """Площадка в кабинете и два её контакта — со всеми заполненными полями."""
    db = SessionLocal()
    pub = db.execute(text(
        "SELECT publisher_id FROM cabinet_publisher LIMIT 1")).scalar()
    if pub is None:
        db.close()
        pytest.skip('нужна площадка, прикреплённая к кабинету')
    made = []
    for i in (1, 2):
        cid = db.execute(text(
            "INSERT INTO sales_publisher_contacts "
            "  (publisher_id, name, email, telegram, phone, role, note, is_primary) "
            "VALUES (:p, :n, :e, '@tg', '+70000000000', 'аккаунт', 'заметка', :pr) "
            "RETURNING id"),
            {"p": pub, "n": f'__проба {i}__', "e": f'probe{i}@lk.local',
             "pr": i == 1}).scalar()
        made.append(cid)
    db.commit()
    yield SimpleNamespace(db=db, pub=pub, ids=made)

    db.rollback()
    # Строки журнала снимаются ЗДЕСЬ, а не в одном из тестов: выдача доступа пишет их
    # почти в каждом, и уборка, оставленная в последнем по файлу, держится на порядке
    # запуска — то есть работает случайно.
    db.execute(text("DELETE FROM cabinet_log WHERE actor_name = :n"), {"n": ADMIN.name})
    db.execute(text("DELETE FROM cabinet_account WHERE contact_id = ANY(:i)"),
               {"i": made})
    db.execute(text("DELETE FROM sales_publisher_contacts WHERE id = ANY(:i)"),
               {"i": made})
    db.commit()
    db.close()


def test_partial_edit_does_not_blank_untouched_fields(stand):
    """Правка двух полей не стирает остальные шесть."""
    db, cid = stand.db, stand.ids[0]
    update_contact(stand.pub, cid, ContactIn(name='__проба 1 новое__'), db, ADMIN)
    row = db.execute(text(
        "SELECT name, email, telegram, phone, role, note "
        "  FROM sales_publisher_contacts WHERE id = :i"), {"i": cid}).first()
    assert row.name == '__проба 1 новое__'
    assert row.telegram == '@tg' and row.phone == '+70000000000'
    assert row.role == 'аккаунт' and row.note == 'заметка'
    assert row.email == 'probe1@lk.local'


def test_primary_is_exclusive_within_the_publisher(stand):
    """Назначение главного снимает пометку с остальных — тем же запросом."""
    db, first, second = stand.db, stand.ids[0], stand.ids[1]
    update_contact(stand.pub, second, ContactIn(is_primary=True), db, ADMIN)
    flags = dict(db.execute(text(
        "SELECT id, is_primary FROM sales_publisher_contacts WHERE id = ANY(:i)"),
        {"i": [first, second]}).all())
    assert flags[second] is True
    assert flags[first] is False, 'у площадки осталось два главных лица'


def test_clearing_primary_leaves_publisher_without_one(stand):
    """Снять пометку можно: «главного нет» — допустимое состояние, а не ошибка."""
    db, first = stand.db, stand.ids[0]
    update_contact(stand.pub, first, ContactIn(is_primary=False), db, ADMIN)
    assert db.execute(text(
        "SELECT count(*) FROM sales_publisher_contacts "
        " WHERE publisher_id = :p AND is_primary"), {"p": stand.pub}).scalar() == 0


def test_contact_email_and_login_are_separate(stand):
    """Почта контакта и почта входа расходятся, и сводка показывает обе.

    Учётка копирует адрес при заведении. Дальше это два разных значения, и молча
    сводить их нельзя: смена логина при правке визитки обнаруживается только на входе.
    """
    db, cid = stand.db, stand.ids[0]
    cab = db.execute(text(
        "SELECT cabinet_id FROM cabinet_publisher WHERE publisher_id = :p"),
        {"p": stand.pub}).scalar()
    grant_access(cab, AccessIn(contact_id=cid), db, ADMIN)

    update_contact(stand.pub, cid, ContactIn(email='moved@lk.local'), db, ADMIN)
    row = next(r for r in overview.contacts_of(db, [stand.pub]) if r["contact_id"] == cid)
    assert row["email"] == 'moved@lk.local'
    assert row["login_email"] == 'probe1@lk.local', 'логин уехал вместе с визиткой'


def test_login_can_be_moved_deliberately(stand):
    """…и переносится отдельным действием, когда этого действительно хотят."""
    db, cid = stand.db, stand.ids[0]
    cab = db.execute(text(
        "SELECT cabinet_id FROM cabinet_publisher WHERE publisher_id = :p"),
        {"p": stand.pub}).scalar()
    out = grant_access(cab, AccessIn(contact_id=cid), db, ADMIN)
    update_account(out["id"], AccountPatch(email='MOVED@lk.local'), db, ADMIN)
    assert db.execute(text("SELECT email FROM cabinet_account WHERE id = :i"),
                      {"i": out["id"]}).scalar() == 'moved@lk.local'


def test_login_must_stay_unique(stand):
    """Занятый адрес не отбирается у другой учётки: по нему входят."""
    db = stand.db
    cab = db.execute(text(
        "SELECT cabinet_id FROM cabinet_publisher WHERE publisher_id = :p"),
        {"p": stand.pub}).scalar()
    a1 = grant_access(cab, AccessIn(contact_id=stand.ids[0]), db, ADMIN)
    grant_access(cab, AccessIn(contact_id=stand.ids[1]), db, ADMIN)
    with pytest.raises(HTTPException) as e:
        update_account(a1["id"], AccountPatch(email='probe2@lk.local'), db, ADMIN)
    assert e.value.status_code == 400


# ── два входа выдачи доступа ────────────────────────────────────────────────
def test_service_cabinet_takes_a_person_not_a_contact(stand):
    db = stand.db
    cab = db.execute(text("SELECT id FROM cabinet WHERE kind = 'служебный'")).scalar()
    if cab is None:
        pytest.skip('нет служебного кабинета')
    try:
        out = grant_access(cab, AccessIn(name='__наш человек__',
                                         email='OUR@lk.local'), db, ADMIN)
        row = db.execute(text(
            "SELECT contact_id, email FROM cabinet_account WHERE id = :i"),
            {"i": out["id"]}).first()
        assert row.contact_id is None, 'служебной учётке контакт площадки не нужен'
        assert row.email == 'our@lk.local', 'адрес входа хранится в нижнем регистре'

        with pytest.raises(HTTPException) as e:
            grant_access(cab, AccessIn(contact_id=stand.ids[0]), db, ADMIN)
        assert 'нашему человеку' in e.value.detail
    finally:
        db.rollback()
        db.execute(text("DELETE FROM cabinet_account WHERE email = 'our@lk.local'"))
        db.commit()


def test_publisher_cabinet_refuses_a_typed_in_person(stand):
    """В кабинет площадки человека не набирают руками — иначе о нём будет две записи."""
    db = stand.db
    cab = db.execute(text(
        "SELECT cabinet_id FROM cabinet_publisher WHERE publisher_id = :p"),
        {"p": stand.pub}).scalar()
    with pytest.raises(HTTPException) as e:
        grant_access(cab, AccessIn(name='кто-то', email='someone@lk.local'), db, ADMIN)
    assert 'контакту площадки' in e.value.detail
