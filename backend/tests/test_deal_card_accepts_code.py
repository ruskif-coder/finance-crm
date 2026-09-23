# -*- coding: utf-8 -*-
"""Ручки карточки сделки принимают НАШУ МЕТКУ, а не только числовой id.

ЧТО СЛУЧИЛОСЬ (22.09.2026). Карточка сделки живёт по адресу `/deals/{code}` — в
ссылках и в интерфейсе стоит наша шестизначная метка, а не внутренний id. Ручка
`move-preview` была объявлена с `deal_id: int`, поэтому FastAPI отказывал ещё до
входа в тело: 422 на путь `/sales/deals/N3A4D6/move-preview`.

Заметить это было почти нечем. Карточка глотает отказ намеренно — «список
требований не обязателен», — поэтому полоса «что нужно для перехода» просто не
появлялась. Не пустая, не с ошибкой: её не было, и выглядело это как «так и
задумано». Нашлось по жалобе владельца и по 422 в консоли браузера.

Прибор держит два утверждения:

  1. `move-preview` отвечает и на метку, и на число — одно и то же;
  2. ВСЕ ручки, которые зовёт карточка своим адресным параметром, объявлены
     строкой. Это структурная проверка: перепиши кто-нибудь параметр обратно в
     `int`, и карточка снова потеряет кусок молча. Подписи читаем у самих
     функций, а не повторяем список путей.
"""
import inspect

import pytest

from app.database import SessionLocal
from app.routers.sales_dashboard import (deal_history, get_deal, move_preview,
                                         _deal_by_ref)
from app.sales.models import SalesDeal

# Ровно те ручки, которые страница /sales/deals/[id] зовёт параметром из адреса.
CARD_HANDLERS = (get_deal, deal_history, move_preview)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def admin(db):
    from app.models import User
    u = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
    if u is None:
        pytest.skip("нужна живая учётка")
    return u


@pytest.fixture
def deal_with_code(db):
    d = (db.query(SalesDeal).filter(SalesDeal.code.isnot(None))
         .order_by(SalesDeal.id).first())
    if d is None:
        pytest.skip("нужна сделка с меткой")
    return d


@pytest.mark.parametrize("fn", CARD_HANDLERS, ids=lambda f: f.__name__)
def test_card_handlers_take_a_string_key(fn):
    """`deal_id` объявлен строкой — иначе метка не пройдёт разбор пути."""
    ann = inspect.signature(fn).parameters["deal_id"].annotation
    assert ann is str, (
        "%s объявлен с %r: карточка зовёт его меткой, и FastAPI ответит 422 ещё до "
        "тела функции" % (fn.__name__, ann))


def test_resolver_finds_the_same_deal_by_code_and_by_id(db, deal_with_code):
    """Метка и число ведут к ОДНОЙ сделке. Регистр метки значения не имеет."""
    d = deal_with_code
    assert _deal_by_ref(db, str(d.id)).id == d.id
    assert _deal_by_ref(db, d.code).id == d.id
    assert _deal_by_ref(db, d.code.lower()).id == d.id


def test_move_preview_answers_the_same_for_code_and_id(db, admin, deal_with_code):
    """Та самая ручка: ответ по метке совпадает с ответом по числу."""
    d = deal_with_code
    by_id = move_preview(deal_id=str(d.id), to_stage_id=None,
                         realization_pipeline_id=None, db=db, current_user=admin)
    by_code = move_preview(deal_id=d.code, to_stage_id=None,
                           realization_pipeline_id=None, db=db, current_user=admin)
    assert by_id == by_code


def test_unknown_key_is_not_found_not_a_crash(db, admin):
    """Несуществующая метка — «не найдена», а не отказ разбора и не падение.

    Отдельная проверка, потому что переход на строку снимает разбор типа: теперь в
    ручку доедет любой мусор, и отвечать на него она должна осмысленно.
    """
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        move_preview(deal_id="ZZZZZZ", to_stage_id=None,
                     realization_pipeline_id=None, db=db, current_user=admin)
    assert e.value.status_code == 404
