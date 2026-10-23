# -*- coding: utf-8 -*-
"""«Статусы продаж»: опоздание старта и темп к закрытию (владелец 23.10.2026).

· Реальный старт: полный цикл — первый день с показами в боевой статистике РК; контур аккаунта (внешние услуги) —
  кнопка «Запустить», то есть вход на «В размещении». Его дата — в подсказке пина.
· Сделка на «Готовятся к старту» / «В размещении» без реального старта: 7 дней после планового — жёлтый «!», 14 — красный.
· Темп: сумма сделки × доля прогноза открутки (факт ÷ отчитанные дни × длина флайта, не больше плана) для полного цикла;
  внешние услуги и РК без прогноза — 100 %."""
from datetime import date

import pytest

from app.sales import status_launch as L


@pytest.mark.parametrize("stage,plan,real,today,want", [
    ("launch_prep", date(2026, 10, 1), None, date(2026, 10, 7), None),
    ("launch_prep", date(2026, 10, 1), None, date(2026, 10, 8), "warn"),
    ("launch", date(2026, 10, 1), None, date(2026, 10, 15), "bad"),
    ("launch", date(2026, 10, 1), date(2026, 10, 3), date(2026, 10, 30), None),
    ("closing", date(2026, 10, 1), None, date(2026, 10, 30), None),
    ("booking", date(2026, 10, 1), None, date(2026, 10, 30), None),
    ("launch_prep", None, None, date(2026, 10, 30), None),
])
def test_late_start_levels(stage, plan, real, today, want):
    assert L.late(stage, plan, real, today)[0] == want


def test_late_days_counted_from_plan():
    assert L.late("launch", date(2026, 10, 1), None, date(2026, 10, 15)) == ("bad", 14)


@pytest.mark.parametrize("full,plan,fact,start,end,today,want", [
    (True, 1000, 300, date(2026, 10, 1), date(2026, 10, 30), date(2026, 10, 15), 0.6),    # 300/15×30 = 600 из 1000
    (True, 1000, 900, date(2026, 10, 1), date(2026, 10, 30), date(2026, 10, 15), 1.0),    # перекрут — не больше плана
    (True, 1000, None, date(2026, 10, 1), date(2026, 10, 30), date(2026, 10, 15), 1.0),   # прогноза нет — 100 %
    (True, None, 300, date(2026, 10, 1), date(2026, 10, 30), date(2026, 10, 15), 1.0),
    (False, 1000, 100, date(2026, 10, 1), date(2026, 10, 30), date(2026, 10, 15), 1.0),  # внешняя услуга — всегда 100 %
])
def test_pace_ratio(full, plan, fact, start, end, today, want):
    assert L.pace_ratio(full, plan, fact, start, end, today) == pytest.approx(want)


def test_collect_on_stand_data_does_not_fail():
    """Сборка по живым сделкам стенда: у каждой — плановая дата или None, доля темпа в [0, 1]."""
    import app.model_registry  # noqa: F401
    from sqlalchemy import text
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        rows = db.execute(text("""SELECT d.id, s.stage_key, d.period_from, d.realization_pipeline_id, d.service_id
                                    FROM sales_deals d LEFT JOIN sales_stages s ON s.id = d.our_stage_id
                                   WHERE s.stage_key IN ('launch_prep', 'launch') LIMIT 50""")).all()
        if not rows:
            pytest.skip("на стенде нет сделок на старте")
        out = L.collect(db, rows, date(2026, 10, 23))
        assert set(out) == {r.id for r in rows}
        assert all(0 <= v["pace"] <= 1 for v in out.values())
    finally:
        db.close()


def test_matrix_deals_carry_start_and_pace():
    import app.model_registry  # noqa: F401
    from app.database import SessionLocal
    from app.models import Role, User
    from app.routers import sales_status as SS
    db = SessionLocal()
    try:
        u = db.query(User).join(Role, Role.id == User.role_id).filter(Role.key == "admin").first()
        deals = SS.matrix("2026-07", "2026-12", db, u)["deals"]
        if not deals:
            pytest.skip("нет сделок в окне")
        assert all({"real_start", "plan_start", "late", "pace"} <= set(d) for d in deals)
    finally:
        db.close()
