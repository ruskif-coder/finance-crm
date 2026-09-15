# -*- coding: utf-8 -*-
"""Канал `app`: уведомление как СОСТОЯНИЕ объекта, а не след события.

Три правила из спеки хендоффа 14.09.2026, и каждое закрывает свой способ сделать панель
бесполезной:

· без схлопывания сканер копит строки ежедневно, и панель перестают открывать;
· без ухудшения тона он же каждые сутки поднимает одно и то же непрочитанным, и метка
  перестаёт что-либо значить;
· без гашения панель показывает разобранное, и отличить сделанное от несделанного в ней
  нельзя.
"""
import pytest
from datetime import datetime

from app.database import SessionLocal
from app.models import Notification, User
from app.notify import registry
from app.notify.bus import dedup_key, emit


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def user(db):
    u = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
    if u is None:
        pytest.skip("на стенде нет админской учётки")
    yield u
    # Свои следы убираем: ручка пишет и коммитит, откат фикстуры их не уносит.
    db.rollback()
    db.query(Notification).filter(
        Notification.user_id == u.id,
        Notification.dedup_key.like("backlog_created:test_panel:%")).delete(
            synchronize_session=False)
    db.commit()


EV = "backlog_created"          # событие с адресатом «админ» — доходит без резолверов
ENT = "test_panel"


def _emit(db, u, title, tone, eid=777):
    emit(db, EV, title=title, body=None, link="/settings/backlog",
         entity_type=ENT, entity_id=eid, user_ids=[u.id], tone=tone)
    db.commit()
    return (db.query(Notification)
            .filter(Notification.user_id == u.id,
                    Notification.dedup_key == dedup_key(EV, ENT, eid))
            .order_by(Notification.id.desc()).all())


def test_key_needs_an_object():
    """Событие без объекта не схлопывается: у «конвейер создал сделки» нет одного
    предмета, и склеивать два прогона в одну строку значит потерять второй."""
    assert dedup_key("x", None, None) == ""
    assert dedup_key("x", "deal", None) == ""
    assert dedup_key("x", "deal", 5) == "x:deal:5"


def test_repeat_updates_the_row_instead_of_adding_one(db, user):
    """Повторная сработка обновляет строку, а не плодит новые."""
    rows = _emit(db, user, "Первый раз", "warn")
    assert len(rows) == 1
    rows = _emit(db, user, "Второй раз", "warn")
    assert len(rows) == 1, "повтор завёл вторую строку"
    assert rows[0].title == "Второй раз", "строка не обновилась"


def test_only_worsening_makes_it_unread_again(db, user):
    """Тот же тон читанную строку не поднимает; ухудшение — поднимает."""
    _emit(db, user, "Заведено", "warn")
    rows = db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.dedup_key == dedup_key(EV, ENT, 777)).all()
    rows[0].is_read = True
    db.commit()

    rows = _emit(db, user, "Всё ещё висит", "warn")
    assert rows[0].is_read is True, "повтор того же тона снова поднял строку наверх"

    rows = _emit(db, user, "Стало хуже", "bad")
    assert rows[0].is_read is False, "ухудшение тона не вернуло непрочитанность"
    assert rows[0].tone == "bad"


def test_resolved_rows_leave_the_panel(db, user):
    """Погашенная строка не попадает в выдачу, но из базы не исчезает."""
    from app.routers import notifications as api

    _emit(db, user, "Живое", "warn")
    shown = api.list_notifications(db=db, current_user=user)
    assert any(i["title"] == "Живое" for i in shown["items"])

    db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.dedup_key == dedup_key(EV, ENT, 777)).update(
            {Notification.resolved_at: datetime.utcnow()}, synchronize_session=False)
    db.commit()
    shown = api.list_notifications(db=db, current_user=user)
    assert not any(i["title"] == "Живое" for i in shown["items"]), (
        "погашенная строка осталась в панели")
    assert db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.dedup_key == dedup_key(EV, ENT, 777)).count() == 1, (
        "гашение УДАЛИЛО запись — история события потеряна")


def test_scanner_stage_maps_to_a_tone():
    """Соответствие срочности тону одно на систему: очередь «Что делать» и панель
    строятся из одних правил, и разный цвет у одного состояния читался бы как разные."""
    from app.notify.scanner import STAGE_TONE
    from app.sales.urgency import OVERDUE, SOON, TODAY

    assert STAGE_TONE[OVERDUE] == "bad"
    assert STAGE_TONE[TODAY] == "warn" and STAGE_TONE[SOON] == "warn"


def test_registry_tone_is_the_fallback():
    """Событие без своей срочности берёт тон реестра — иначе строка остаётся бесцветной."""
    ev = registry.get(EV)
    assert ev is not None and ev.tone
