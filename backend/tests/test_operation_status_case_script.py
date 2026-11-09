# -*- coding: utf-8 -*-
"""Скрипт 2026-11-09_operation_status_case: «план поступлений» строчными (так писал мост, прод 21 операция) → «ПЛАН ПОСТУПЛЕНИЙ»;
незнакомый статус не трогает, только называет; сухой прогон ничего не пишет. Транзакция откатывается."""
import importlib

import pytest
from sqlalchemy import text

S = importlib.import_module("scripts.2026-11-09_operation_status_case")


@pytest.fixture
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    ids = [s.execute(text("INSERT INTO operations (status, income, expense, period) VALUES (:st, 100, 0, '2026-10') RETURNING id"),
                     {"st": st}).scalar() for st in ("план поступлений", "Оплачено", "черновик")]
    try:
        yield s, ids
    finally:
        s.rollback()
        s.close()


def _status(s, i):
    return s.execute(text("SELECT status FROM operations WHERE id = :i"), {"i": i}).scalar()


def test_dry_run_lists_and_changes_nothing(db):
    s, (low, mixed, odd) = db
    rep = S.run(s)
    assert {x["id"] for x in rep["fix"]} >= {low, mixed} and odd in {x["id"] for x in rep["other"]}
    assert _status(s, low) == "план поступлений"


def test_apply_fixes_case_only_and_is_idempotent(db):
    s, (low, mixed, odd) = db
    S.run(s, apply=True)
    assert (_status(s, low), _status(s, mixed), _status(s, odd)) == ("ПЛАН ПОСТУПЛЕНИЙ", "ОПЛАЧЕНО", "черновик")
    assert not [x for x in S.run(s)["fix"] if x["id"] in (low, mixed)]
