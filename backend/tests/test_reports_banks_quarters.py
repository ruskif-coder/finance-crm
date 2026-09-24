# -*- coding: utf-8 -*-
"""Баланс и ДДС: кварталы и фильтр банка (аудит 23.09.2026, этап 8.2 и 8.3).

8.2. `/balance?date_to=2026-08` сравнивал период строкой: «Q3 2026» > «2026-08»
(буква больше цифры), и ВСЕ квартальные операции выпадали из остатка, едва выбрана
дата. На проде таких операций 122. Квартал раскладывается на три равных месяца — как
в /dds, /pl и /plan-fact.

8.3. `/dds?bank=…` брал стартовый остаток ВСЕХ банков: накопительный остаток одного
банка начинался с суммы четырёх.

Проверки на стенде: своя операция в транзакции, откат в конце — стенд не меняется.
"""
from datetime import date

import pytest
from sqlalchemy import text

import app.main  # noqa: F401 — все модели
from app.database import SessionLocal
from app.models import Operation, User
from app.routers import reports

BANK = "АльфаБанк"


@pytest.fixture
def ctx():
    db = SessionLocal()
    user = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
    yield db, user
    db.rollback()
    db.close()


def _alfa(out):
    return next(b for b in out["banks"] if b["bank"] == BANK)["balance"]


def test_a_quarter_counts_by_its_months_up_to_the_date(ctx):
    db, user = ctx
    before = _alfa(reports.get_balance(date_to="2026-08", db=db, current_user=user))
    before_q = _alfa(reports.get_balance(date_to="2026-09", db=db, current_user=user))
    db.add(Operation(date=date(2026, 7, 1), status="ОПЛАЧЕНО", income=300000, expense=0,
                     bank=BANK, period="Q3 2026", description="[тест] квартал"))
    db.flush()
    after = _alfa(reports.get_balance(date_to="2026-08", db=db, current_user=user))
    # июль и август — две трети квартала
    assert after - before == pytest.approx(200000), "квартал выпал из баланса по дату"
    whole = _alfa(reports.get_balance(date_to="2026-09", db=db, current_user=user))
    assert whole - before_q == pytest.approx(300000)


def test_one_bank_starts_from_its_own_opening(ctx):
    db, user = ctx
    opening = dict(db.execute(text("SELECT bank, opening_balance FROM bank_balances")).fetchall())
    if len([v for v in opening.values() if v]) < 2:
        pytest.skip("на стенде остаток задан меньше чем у двух банков")
    out = reports.get_dds(bank=BANK, group_by="period", db=db, current_user=user)
    first = out["periods"][0]
    assert first["cumulative"] - first["net"] == pytest.approx(opening.get(BANK) or 0), (
        "накопительный остаток банка начался не с его стартового остатка")


@pytest.mark.parametrize("group_by", ["period", "date"])
def test_a_range_starts_from_what_was_there_before_it(ctx, group_by):
    """Накопительный остаток с `date_from` начинается с остатка НА НАЧАЛО диапазона, а не
    со стартового: экран ДДС всегда шлёт `date_from`, и движение до него терялось
    (ревью этапа 8, 24.09.2026)."""
    db, user = ctx
    full = reports.get_dds(bank=BANK, group_by=group_by, db=db, current_user=user)["periods"]
    if len(full) < 3:
        pytest.skip("мало периодов на стенде")
    mid = full[len(full) // 2]
    prev = full[len(full) // 2 - 1]
    part = reports.get_dds(bank=BANK, group_by=group_by, date_from=mid["period"],
                           db=db, current_user=user)["periods"]
    assert part[0]["cumulative"] == pytest.approx(mid["cumulative"]), (
        "остаток на начало диапазона потерял движение до него")
    assert part[0]["cumulative"] - part[0]["net"] == pytest.approx(prev["cumulative"])
