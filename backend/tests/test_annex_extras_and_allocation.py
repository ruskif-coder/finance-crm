# -*- coding: utf-8 -*-
"""Прибор: приложение к договору = весь медиаплан, и разнесение идёт за суммой.

  · 3.H1 — таблица и сумма ДС собирались только из строк РАЗМЕЩЕНИЯ, доп. услуги плана не
    попадали никуда. План 500 000 + 50 000 доп. услуг при 22 % давал ДС на 610 000 вместо
    671 000 — подписываемый документ занижал сумму и НДС. Сверка «сумма не сходится с
    медиапланом» при этом молчала: сумму подменяли итогом той же неполной таблицы;
  · 2.M6 — правка черновика меняла сумму приложения, а разнесение по сделкам оставалось
    прежним: доли в карточке сделки переставали складываться в сумму документа.

Всё — на живой базе в транзакции с откатом.
"""
from datetime import date

import pytest

import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.notify.models       # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.models import Contract, User
from app.routers import annexes as ax
from app.sales import annex as annex_build
from app.sales import mp_row
from app.sales.models import (SalesDeal, SalesDealAnnexAllocation, SalesMediaPlan,
                              SalesMediaPlanExtra, SalesMediaPlanRow)

RATE = 22.0


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def setup(db):
    contract = db.query(Contract).first()
    deal = db.query(SalesDeal).first()
    admin = db.query(User).filter(User.is_active == 1, User.role.has(key="admin")).first()
    if not (contract and deal and admin):
        pytest.skip("нужны договор, сделка и админ")
    plan = SalesMediaPlan(deal_id=deal.id, version=99999, status="draft", title="прибор ДС",
                          date_from=date(2099, 1, 1), date_to=date(2099, 1, 31))
    db.add(plan)
    db.flush()
    plan.group_id = plan.id
    # CPM: 1 000 000 показов × 500 ₽ за тысячу = 500 000 без НДС.
    db.add(SalesMediaPlanRow(plan_id=plan.id, sort_order=0, position="прибор", format="banners",
                             model="CPM", inventory="web", volume=1_000_000, unit_price=500,
                             discount=0))
    db.add(SalesMediaPlanExtra(plan_id=plan.id, sort_order=0, name="Отчёт верификатора",
                               period="январь", mode="фикс", price=50_000, total=50_000))
    db.flush()
    return contract, deal, admin


def test_annex_table_and_total_include_extra_services(db, setup):
    contract, deal, _ = setup
    data = annex_build.build(db, contract, period_from=date(2099, 1, 1),
                             period_to=date(2099, 1, 31), amount=0, vat_rate=RATE,
                             deal_ids=[deal.id])
    net = mp_row.row_net("CPM", 1_000_000, 500, 0) + 50_000
    assert data["plan_total"] == round(net * (100 + RATE) / 100, 2) == 671_000
    names = [r.get("position") for r in data["rows"]]
    assert "Отчёт верификатора" in names, names
    assert round(sum(r["vat"] or 0 for r in data["rows"]), 2) == 121_000


def test_editing_a_draft_reallocates_its_amount(db, setup):
    contract, deal, admin = setup
    out = ax.create_annex(ax.AnnexIn(contract_id=contract.id, deal_ids=[deal.id],
                                     period_from=date(2099, 1, 1), period_to=date(2099, 1, 31),
                                     total_amount=1.0, vat_rate=RATE), db=db, user=admin)
    alloc = lambda: [a.amount for a in db.query(SalesDealAnnexAllocation)  # noqa: E731
                     .filter(SalesDealAnnexAllocation.annex_id == out["id"]).all()]
    assert sum(alloc()) == out["total_amount"] == 671_000

    # Доп. услугу убрали из плана — черновик пересобрали, разнесение обязано поехать следом.
    db.query(SalesMediaPlanExtra).filter(SalesMediaPlanExtra.name == "Отчёт верификатора").delete()
    db.flush()
    edited = ax.edit_annex(out["id"], ax.AnnexIn(contract_id=contract.id, deal_ids=[deal.id],
                                                 period_from=date(2099, 1, 1),
                                                 period_to=date(2099, 1, 31),
                                                 total_amount=1.0, vat_rate=RATE),
                           db=db, user=admin)
    db.expire_all()
    assert edited["total_amount"] == 610_000
    assert round(sum(alloc()), 2) == 610_000


def test_annex_screen_names_a_mismatch_with_the_deal(db, setup):
    """Сумма документа ≠ сумме сделки — экран говорит об этом до подписания (3.H1)."""
    contract, deal, admin = setup
    deal.amount_with_vat = 700_000
    db.flush()
    out = ax.create_annex(ax.AnnexIn(contract_id=contract.id, deal_ids=[deal.id],
                                     period_from=date(2099, 1, 1), period_to=date(2099, 1, 31),
                                     total_amount=1.0, vat_rate=RATE), db=db, user=admin)
    got = ax.get_annex(out["id"], db=db, user=admin)
    assert got["mismatch"] and "671 000.00" in got["mismatch"] and "700 000.00" in got["mismatch"]
    deal.amount_with_vat = 671_000
    db.flush()
    assert ax.get_annex(out["id"], db=db, user=admin)["mismatch"] is None


def test_editing_a_draft_without_a_rate_keeps_its_own_rate(db, setup):
    """Черновик посчитан по 20 %. Правка, в которой ставка не прислана, пересобирает
    документ по ЕГО ставке, а не по текущей ставке юрлица: иначе итог документа молча
    переезжал с 660 000 на 671 000 (ревью 23.09.2026)."""
    contract, deal, admin = setup
    out = ax.create_annex(ax.AnnexIn(contract_id=contract.id, deal_ids=[deal.id],
                                     period_from=date(2099, 1, 1), period_to=date(2099, 1, 31),
                                     total_amount=1.0, vat_rate=20), db=db, user=admin)
    assert out["total_amount"] == 660_000
    edited = ax.edit_annex(out["id"], ax.AnnexIn(contract_id=contract.id, deal_ids=[deal.id],
                                                 period_from=date(2099, 1, 1),
                                                 period_to=date(2099, 1, 31),
                                                 total_amount=1.0),
                           db=db, user=admin)
    assert edited["vat_rate"] == 20
    assert edited["total_amount"] == 660_000


def test_mismatch_is_silent_when_a_deal_has_no_amount():
    """ДС на две сделки, у одной суммы нет: сумма сделок неизвестна, и «не совпадает»
    было бы ложной тревогой — одна известная сумма всегда меньше итога (ревью 23.09.2026)."""
    from types import SimpleNamespace
    a = SimpleNamespace(total_amount=1000.0)
    deals = [{"deal_amount_with_vat": 400.0}, {"deal_amount_with_vat": None}]
    assert ax._mismatch(a, deals) is None
    assert ax._mismatch(a, [{"deal_amount_with_vat": 400.0}, {"deal_amount_with_vat": 500.0}])


def test_annex_without_our_rate_takes_the_law_rate_not_zero(db, setup):
    """Ставка юрлица не заполнена — документ не должен выйти без НДС. Запас — ставка закона
    на период документа (`app/vat.py`), а не 0 % и не `vat_rate` контрагента: это ставка по
    ЕГО расходам, она стоит нулём (ревью 23.09.2026)."""
    from app import own_company
    contract, deal, _ = setup
    us = contract.own_company or own_company.sole(db)
    if us is None:
        pytest.skip("нет нашего юрлица")
    us.vat_rate_income = None
    db.flush()
    data = annex_build.build(db, contract, period_from=date(2099, 1, 1),
                             period_to=date(2099, 1, 31), amount=0, vat_rate=None,
                             deal_ids=[deal.id])
    net = mp_row.row_net("CPM", 1_000_000, 500, 0) + 50_000
    assert data["plan_total"] == round(net * 1.22, 2)
