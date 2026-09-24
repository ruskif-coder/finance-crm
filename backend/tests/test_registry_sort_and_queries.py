# -*- coding: utf-8 -*-
"""Реестр сделок: сортировка «по сумме» — по ПОКАЗАННОЙ сумме, и без запроса на строку
(аудит 23.09.2026, 3.L1 и 3.L2).

3.L1. Колонка «Сумма» показывает сумму из медиаплана, если он посчитан (`eff_net`), а
сортировка шла по полю сделки. У сделок, чей план разошёлся с полем, порядок в таблице
не совпадал с числами в столбце — на стенде таких 12 из 957.

3.L2. «Следующая стадия» считалась на каждую строку отдельно, и каждый раз заново
читалась разметка стадий по услугам: до 500 одинаковых запросов на страницу.

Читающие проверки на живых данных стенда: ничего не пишут.
"""
import pytest
from sqlalchemy import event

import app.main  # noqa: F401 — все модели
from app.database import SessionLocal, engine
from app.models import User
from app.routers import sales_dashboard as sd


def _registry(db, user, sort, direction):
    return sd.deals_registry(sort=sort, direction=direction, limit=500, offset=0,
                             db=db, current_user=user)


@pytest.fixture
def ctx():
    db = SessionLocal()
    user = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
    yield db, user
    db.rollback()
    db.close()


def _amounts(out):
    rows = out["items"]
    return [r["amount"] for r in rows]


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sorting_by_amount_follows_the_shown_amount(ctx, direction):
    db, user = ctx
    got = _amounts(_registry(db, user, "amount", direction))
    if len(got) < 2:
        pytest.skip("на стенде мало сделок")
    want = sorted(got, reverse=(direction == "desc"))
    assert got == want, "порядок строк не совпадает с числами в колонке «Сумма»"


def test_the_stage_markup_is_read_once_per_page(ctx):
    db, user = ctx
    seen = []

    def count(conn, cursor, statement, params, context, executemany):
        if "sales_stage_services" in statement:
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        _registry(db, user, "period_from", "desc")
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert len(seen) <= 1, f"разметка стадий читается {len(seen)} раз на страницу"
