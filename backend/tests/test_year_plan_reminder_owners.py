# -*- coding: utf-8 -*-
"""Напоминание по годовому плану доходит ОБОИМ владельцам строки.

Прибор появился 21.09.2026 вместе с разделением осей владения — и появился потому,
что разделение само по себе тихо отобрало письма у половины адресатов.

КАК ЭТО ВЫГЛЯДЕЛО БЫ. Правило «месяц запланирован, а сделок в ячейке нет» берёт
адресата из `line.sales_rep_id`. До разделения там сидел СОЗДАТЕЛЬ строки, то есть
чаще всего аккаунт, который план и ведёт, — письмо приходило ему. После разделения
там продавец, и аккаунт перестал бы получать письма, которые получал вчера. Ни
ошибки, ни пустого журнала: письмо уходит, просто не тому. Заметить это можно было
бы только по жалобе «мне перестали приходить напоминания», через недели.

У сделок в проекте так уже принято: резолвер `responsible` берёт и сейлза, и
аккаунта. Прибор требует того же от годового плана и проверяет обе половины —
и что резолвер понимает список, и что правило этот список кладёт в контекст.
"""
import pytest

from app.database import SessionLocal
from app.models import User
from app.notify.recipients import year_plan_owner
from app.sales.models import SalesRep


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def two_reps(db):
    """Два профиля на двух живых учётках — иначе адресатов не с кем сравнивать."""
    users = db.query(User).filter(User.is_active == 1).order_by(User.id).limit(2).all()
    if len(users) < 2:
        pytest.skip("нужны две живые учётки")
    made = [SalesRep(name="ТЕСТ адресат %d" % u.id, user_id=u.id) for u in users]
    db.add_all(made)
    db.flush()
    return made, [u.id for u in users]


def test_both_owners_get_the_letter(db, two_reps):
    """Список из двух владельцев → обе учётки в адресатах."""
    reps, user_ids = two_reps
    got = year_plan_owner(db, {"rep_id": [reps[0].id, reps[1].id]})
    assert set(got) == set(user_ids)


def test_single_id_still_works(db, two_reps):
    """Одно число резолвер обязан понимать по-прежнему.

    Контракт `RESOLVER_CTX` читают и другие правила, и старые записи событий; сломай
    одиночную форму — и письма пропадут там, где про список никто не знает.
    """
    reps, user_ids = two_reps
    assert year_plan_owner(db, {"rep_id": reps[0].id}) == [user_ids[0]]


def test_none_inside_the_list_is_not_an_address(db, two_reps):
    """У строки может быть только один владелец — второй приезжает как None.

    Без отсева пустого резолвер ушёл бы искать профиль с id None и вернул бы либо
    пусто, либо случайную строку — то есть письмо потерялось бы ровно в том случае,
    ради которого список и заведён.
    """
    reps, user_ids = two_reps
    assert year_plan_owner(db, {"rep_id": [reps[0].id, None]}) == [user_ids[0]]
    assert year_plan_owner(db, {"rep_id": [None, None]}) == []


def test_the_rule_passes_both_owners(db):
    """Само правило кладёт в контекст ОБЕ оси, а не одну.

    Читаем исходник, а не поведение: чтобы правило сработало данными, нужен
    запланированный месяц с суммой и без сделок — подбирать такой стенд дороже и
    ненадёжнее, чем прочитать сам вызов. Тот же приём, что в test_notify_ctx.py.
    """
    import inspect

    from app.notify import scanner
    src = inspect.getsource(scanner.rule_plan_month_empty)
    assert '"rep_id": [line.sales_rep_id, line.account_manager_id]' in src, (
        "правило адресует напоминание одной оси владения — вторая останется без писем")
    assert "account_manager_id.isnot(None)" in src, (
        "в выборку не попадают строки, у которых есть только ведущий аккаунт")
