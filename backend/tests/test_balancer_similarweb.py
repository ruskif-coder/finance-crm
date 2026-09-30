# -*- coding: utf-8 -*-
"""SimilarWeb в балансировщике (владелец 30.09.2026; заменил «Внешнюю оценку» 28.09).

Обещания: SW visits / PpV / BR сохраняются и читаются обратно, Swtraffic считается по
формуле; SW бывает только у web; загрузка из Excel подхватывает колонки SW.
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
    rows = [r for r in balance.rows(db) if r["scope"] == "web"]
    if not rows:
        pytest.skip("в балансировщике нет web-строки")
    return rows[0]


@pytest.fixture
def app_row(db):
    rows = [r for r in balance.rows(db) if r["scope"] != "web"]
    if not rows:
        pytest.skip("в балансировщике нет app-строки")
    return rows[0]


def _find(rows, r):
    return next(x for x in rows if x["publisher_id"] == r["publisher_id"] and x["scope"] == r["scope"])


def _save(db, user, r, **kw):
    body = dict(volume=r["volume"], depth=r["depth"], requests=r["requests"],
                index_manual=r["index_manual"], is_locked=r["is_locked"], note=r["note"])
    body.update(kw)
    return tb.balancer_save_row(r["publisher_id"], r["scope"], tb.BalanceRowIn(**body),
                                db=db, user=user)


def test_sw_saved_read_back_and_swtraffic_computed(db, user, row):
    got = _find(_save(db, user, row, sw_visits=100000, sw_ppv=3.0, sw_br=40.0)["rows"], row)
    assert (got["sw_visits"], got["sw_ppv"], got["sw_br"]) == (100000, 3.0, 40.0)
    assert got["swtraffic"] == pytest.approx(180000), "100000 × 3 × 60 / 100"


def test_sw_only_for_web(db, user, app_row):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _save(db, user, app_row, sw_visits=1000)
    assert e.value.status_code == 400


def test_br_out_of_range_rejected(db, user, row):
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _save(db, user, row, sw_br=140)


def _xlsx(headers, values):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    ws.append(values)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_import_picks_up_sw_columns(db, user, row):
    f = _xlsx(["ID", "Поверхность (код)", "SW visits", "PpV", "BR"],
              [row["publisher_id"], "web", 5000, 2.0, 50])
    out = tb.balancer_import(UploadFile(filename="b.xlsx", file=f), db=db, user=user)
    got = _find(out["rows"], row)
    assert got["swtraffic"] == pytest.approx(5000), "5000 × 2 × 50 / 100"
