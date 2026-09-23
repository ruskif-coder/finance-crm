# -*- coding: utf-8 -*-
"""Прибор: маржа на дашборде руководителя = сводка финотчёта (аудит 23.09.2026, 2.M7).

Докстрока дашборда обещала «те же числа, что P&L», а расчёт брал все статусы, суммы с НДС
и одну сторону строки (возвраты терялись). На одном месяце дашборд, P&L и финотчёт
показывали три разные маржи. Теперь дашборд считается финотчётом (по начислению, без
НДС, нетто по знаку строки).

Сверяется ПУБЛИЧНЫЙ ответ ручки `/exec/overview` с ПУБЛИЧНЫМ итогом финотчёта. До ревью
23.09.2026 тест звал внутреннюю `_pl_by_month`, которая сама вызывает финотчёт, — сверка
выходила почти с самим собой, и ручка, переставшая звать `_pl_by_month`, прошла бы.
"""
import pytest

import app.notify.models  # noqa: F401
from app.database import SessionLocal
from app.models import User
from app.routers import exec_dashboard as ex
from app.routers import finreport as fr


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def test_exec_margin_equals_finreport_summary(db):
    admin = db.query(User).filter(User.is_active == 1, User.role.has(key="admin")).first()
    if admin is None:
        pytest.skip("нужна учётка админа")
    rep = fr.build_report(db, "accrual", "net", "2025-01", "2026-12")
    months = [p for p in rep["base_periods"] if rep["summary"][p]["revenue"]]
    if not months:
        pytest.skip("на стенде нет месяцев с выручкой — сверять нечего")
    for mo in months[-3:]:
        m = ex.overview(scale="month", anchor=mo, db=db, user=admin)["margin"]
        s = rep["summary"][mo]
        for k_ex, k_fr in (("revenue", "revenue"), ("cogs", "cogs"),
                           ("gross", "gross_profit"), ("opex", "opex"),
                           ("marketing", "marketing")):
            assert abs(m[k_ex] - s[k_fr]) < 0.01, (mo, k_ex, m[k_ex], s[k_fr])
