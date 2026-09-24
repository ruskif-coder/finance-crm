# -*- coding: utf-8 -*-
"""Реестр и выгрузка операций читают статью и контрагента НЕ на каждую строку
(аудит 23.09.2026, этап 8.6; известно с ревью 03.08.2026).

Каждая строка дочитывала `op.article` и `op.counterparty` отдельным запросом: страница
в 300 операций — до 600 лишних запросов. Проверка: число запросов на странице из 100
строк и из 10 строк одинаково. Читающая, на данных стенда.
"""
import pytest
from sqlalchemy import event

import app.main  # noqa: F401 — все модели
from app.database import SessionLocal, engine
from app.models import User
from app.routers import operations as ops


def _count(fn):
    seen = []

    def on(conn, cursor, statement, params, context, executemany):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", on)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", on)
    return len(seen)


def _page(db, user, limit):
    return ops.get_operations(skip=0, limit=limit, status=None, bank=None, date_from=None,
                              date_to=None, article_id=None, counterparty_id=None,
                              period=None, op_type=None, gaps=None, ids=None,
                              sort_col="date", sort_dir="desc", db=db, current_user=user)


def test_the_page_does_not_grow_queries_with_rows():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
        if _page(db, user, 100)["total"] < 100:
            pytest.skip("на стенде меньше 100 операций")
        db.expire_all()
        small = _count(lambda: _page(db, user, 10))
        db.expire_all()
        big = _count(lambda: _page(db, user, 100))
        assert big == small, f"10 строк — {small} запросов, 100 строк — {big}"
    finally:
        db.close()
