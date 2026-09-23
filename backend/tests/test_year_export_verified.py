# -*- coding: utf-8 -*-
"""Прибор: годовая выгрузка берёт проверенные медиапланы и считает их со скидкой (3.M5).

  · «проверен» искался в журнале по действию `verify_media_plan`, которое с 13.09.2026 не
    пишет никто: выгрузка молча считала всё по годовому плану, а не по реальным планам;
  · для тех планов, что всё же подхватывались, стоимость считалась `объём × цена ÷ 1000`
    без скидки — то есть завышенной.
"""
import pytest

import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.notify.models       # noqa: F401
import app.ord.models          # noqa: F401
from app import year_mp_export as ye
from app.database import SessionLocal
from app.sales import mp_row
from app.sales.catalog import Catalog
from app.sales.models import SalesDeal, SalesMediaPlan, SalesMediaPlanRow, SalesYearPlanLine


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush       # проверяемый код коммитить не должен, но если начнёт — не в стенд
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def cell(db):
    line = db.query(SalesYearPlanLine).first()
    if line is None:
        pytest.skip("на стенде нет строк годового плана")
    deal = db.query(SalesDeal).first()
    deal.year_plan_line_id, deal.plan_month, deal.plan_deal_idx = line.id, 0, 0
    plan = SalesMediaPlan(deal_id=deal.id, version=99999, status="draft", title="прибор")
    db.add(plan)
    db.flush()
    db.add(SalesMediaPlanRow(plan_id=plan.id, sort_order=0, position="прибор", model="CPM",
                             inventory="web", volume=1_000_000, unit_price=500, discount=0.1))
    db.flush()
    return line, deal


# Правило владельца 23.09.2026: до «Сборки» сделка повторяет годовой план (конвейер
# обновляет её из плана, если на месяце нет замочка), со «Сборки» её медиаплан
# зафиксирован. Поэтому в выгрузку медиаплан сделки идёт ТОЛЬКО со «Сборки» — денежный слой
# «реализуемые» и дальше. Сорвавшаяся сделка денежного слоя не имеет и не идёт вовсе.
# До этого признаком было «ушла с первой стадии», и план сделки на «МП Отправлено» или
# сорвавшейся подменял цифры годового плана.

def _stage(db, key=None, lost=False):
    from app.sales.models import SalesStage
    q = db.query(SalesStage)
    st = q.filter(SalesStage.is_lost.is_(True)).first() if lost else q.filter(
        SalesStage.stage_key == key).first()
    if st is None:
        pytest.skip(f"в каталоге нет стадии {key or 'срыва'}")
    return st


def test_plan_of_a_deal_in_assembly_counts_as_verified(db, cell):
    line, deal = cell
    deal.our_stage_id = _stage(db, "launch_prep").id
    db.flush()
    got = ye.verified_parts(db, [line])
    rows, _ = got[(line.id, 0)][0]
    assert any(r.get("position") == "прибор" for r in rows)


@pytest.mark.parametrize("where", ["sent", "booking", "lost"])
def test_plan_before_assembly_or_of_a_lost_deal_is_not_verified(db, cell, where):
    line, deal = cell
    cat = Catalog(db)
    deal.our_stage_id = {"sent": lambda: cat.next_of(cat.first().id).id,
                         "booking": lambda: _stage(db, "booking").id,
                         "lost": lambda: _stage(db, lost=True).id}[where]()
    db.flush()
    assert (line.id, 0) not in ye.verified_parts(db, [line])


def test_plan_still_on_the_first_stage_is_not_verified(db, cell):
    line, deal = cell
    deal.our_stage_id = Catalog(db).first().id
    db.flush()
    assert (line.id, 0) not in ye.verified_parts(db, [line])


def test_row_cost_uses_the_discount():
    r = {"model": "CPM", "volume": 1_000_000, "unit_price": 500, "discount": 0.1}
    assert ye.row_cost(r) == mp_row.row_net("CPM", 1_000_000, 500, 0.1) == 450_000


# ── Ставка НДС листов (ревью 23.09.2026) ────────────────────────────────────────

def test_year_rate_is_the_law_rate_for_past_years(db):
    from app import vat
    assert vat.for_year(db, 2025) == 20
    assert vat.for_year(db, 2026) == vat.current(db)


def test_every_sheet_is_built_at_the_rate_of_the_export(db, monkeypatch):
    """Шапка листа месяца и «Годового МП» несёт ставку выгрузки. Без неё лист считался по
    ставке по умолчанию (22 %), а «Сводная» того же файла — по ставке года."""
    import os
    from types import SimpleNamespace

    from app.routers import media_plans as yp
    from app.sales.models import SalesAddonService, SalesService
    seen = []
    monkeypatch.setattr(ye, "_render_plain", lambda ws, full, *a, **k: seen.append(full["vat_rate"]))
    monkeypatch.setattr(ye, "_render_with_metrics",
                        lambda ws, full, *a, **k: seen.append(full["vat_rate"]))
    svc = {s.id: s for s in db.query(SalesService).all()}
    add = {a.id: a for a in db.query(SalesAddonService).all()}
    names, tpl = yp._names(db), os.path.abspath(yp.TEMPLATE_PATH)
    for line in db.query(SalesYearPlanLine).order_by(SalesYearPlanLine.id).all():
        plan = SimpleNamespace(id=line.advertiser_id, year=2025,
                               advertiser_id=line.advertiser_id, title="прибор")
        _, data = ye.build_workbook(db, plan, [line], svc, add, names, tpl, 0.20)
        if data["months"]:
            break
    else:
        pytest.skip("на стенде нет строки годового плана с закупкой")
    assert seen and all(v == pytest.approx(20) for v in seen)
