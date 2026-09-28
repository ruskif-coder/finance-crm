# -*- coding: utf-8 -*-
"""«Внешняя оценка» в балансировщике (владелец 28.09.2026).

Держим три обещания: оценка сохраняется и читается обратно; она справочная — индекс и
доли от неё не меняются; загрузка старого файла без этой колонки оценки не стирает.
"""
import io

import pytest
from fastapi import UploadFile

import app.main  # noqa: F401 — все модели в реестре SQLAlchemy
from app.ad import balance
from app.database import SessionLocal
from app.models import User
from app.routers import traffic_balancer as tb


@pytest.fixture
def db(monkeypatch):
    s = SessionLocal()
    s.commit = s.flush
    # Пересчёт РК после правки — не предмет этих тестов и ходит по всем сделкам.
    monkeypatch.setattr(tb, "_push_to_campaigns", lambda db_: True)
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def user(db):
    return db.query(User).filter(User.is_active == 1).order_by(User.id).first()


@pytest.fixture
def row(db):
    rows = balance.rows(db)
    if not rows:
        pytest.skip("в балансировщике нет ни одной строки")
    return rows[0]


def _find(rows, r):
    return next(x for x in rows if x["publisher_id"] == r["publisher_id"] and x["scope"] == r["scope"])


def _save(db, user, r, **kw):
    body = dict(volume=r["volume"], depth=r["depth"], requests=r["requests"],
                index_manual=r["index_manual"], is_locked=r["is_locked"], note=r["note"],
                external_score=r.get("external_score"))
    body.update(kw)
    return tb.balancer_save_row(r["publisher_id"], r["scope"], tb.BalanceRowIn(**body),
                                db=db, user=user)


def test_saved_and_read_back(db, user, row):
    out = _save(db, user, row, external_score=7.5)
    assert _find(out["rows"], row)["external_score"] == 7.5
    out = _save(db, user, _find(out["rows"], row), external_score=None)
    assert _find(out["rows"], row)["external_score"] is None, "очистка клетки не сохранилась"


def test_does_not_touch_index(db, user, row):
    before = _find(balance.rows(db), row)
    after = _find(_save(db, user, row, external_score=123456.0)["rows"], row)
    for k in ("index_auto", "index_manual", "index_effective", "source"):
        assert after[k] == before[k], f"внешняя оценка сдвинула {k}"


def _xlsx(headers, values):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    ws.append(values)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return UploadFile(filename="b.xlsx", file=buf)


def test_import_sets_score_and_old_file_keeps_it(db, user, row):
    _save(db, user, row, external_score=4.0)
    old = _xlsx(["ID", "Поверхность (код)", "Примечание"],
                [row["publisher_id"], row["scope"], row["note"]])
    tb.balancer_import(file=old, db=db, user=user)
    assert _find(balance.rows(db), row)["external_score"] == 4.0, \
        "файл без колонки стёр внешнюю оценку"
    new = _xlsx(["ID", "Поверхность (код)", "Внешняя оценка"],
                [row["publisher_id"], row["scope"], "9,25"])
    tb.balancer_import(file=new, db=db, user=user)
    assert _find(balance.rows(db), row)["external_score"] == 9.25


def test_export_has_the_column():
    assert ("external_score", "Внешняя оценка") in tb.BALANCE_COLS
    assert "external_score" in tb.BALANCE_EDITABLE
