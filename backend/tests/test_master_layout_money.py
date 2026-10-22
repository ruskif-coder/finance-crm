# -*- coding: utf-8 -*-
"""Раскладка мастер-сделки на денежных правилах `final_recon.money` (аудит 2.7.0, пп. 2.3–2.4; владелец 22.10.2026 — НДС по строкам):
строки базовой услуги сделки складываются ровно в сумму её сверки, НДС ДС и комплекта — сумма НДС строк, итог пакета — сумма ДС.
Только чтение: раскладка — расчёт, ничего не пишет."""
from decimal import Decimal

import pytest

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.final_recon import closing as CL
from app.final_recon import money as M
from app.master_deal import layout as L
from app.master_deal.models import MasterDeal


@pytest.fixture
def packages():
    db = SessionLocal()
    ms = db.query(MasterDeal).order_by(MasterDeal.id).all()
    if not ms:
        db.close()
        pytest.skip("на стенде нет мастер-сделок")
    try:
        yield db, ms
    finally:
        db.rollback()
        db.close()


def _d(v):
    return Decimal(str(v))


def test_base_lines_sum_exactly_to_reconciled_sum(packages):
    from app.sales.models import SalesDeal
    db, ms = packages
    for m in ms:
        by_deal = {}
        for x in L.lines(db, m):
            if x["kind"] == "base":
                by_deal[x["deal_id"]] = by_deal.get(x["deal_id"], Decimal(0)) + _d(x["net"])
        for deal_id, got in by_deal.items():
            want = CL.compute(db, db.get(SalesDeal, deal_id))["base_ds_net"] or 0
            assert got == _d(want), (m.code, deal_id)


def test_ds_and_kit_vat_is_sum_of_line_vats(packages):
    db, ms = packages
    for m in ms:
        lay = L.layout(db, m)
        rate = lay["vat_rate"]
        for ds in lay["ds"]:
            nets = [r["net"] for g in ds["groups"] for r in g["rows"]]
            assert _d(ds["vat"]) == _d(M.doc_vat(nets, rate)), (m.code, ds["no"])
            assert _d(ds["gross"]) == _d(ds["net"]) + _d(ds["vat"])
            line_net = {r["id"]: r["net"] for g in ds["groups"] for r in g["rows"]}
            for k in ds["upds"]:
                assert _d(k["vat"]) == _d(M.doc_vat([line_net[i] for i in k["lines"]], rate)), (m.code, k["upd_no"])
                assert _d(k["gross"]) == _d(k["net"]) + _d(k["vat"])
        assert _d(lay["total_gross"]) == sum((_d(ds["gross"]) for ds in lay["ds"]), Decimal(0))


def test_package_total_equals_sum_of_deal_reconciliations(packages):
    """Решение владельца 22.10.2026: сверка сверяется с документом — итог пакета (без НДС и с НДС) равен сумме сверок его сделок."""
    from app.master_deal.models import MasterDealItem
    from app.sales.models import SalesDeal
    db, ms = packages
    for m in ms:
        lay = L.layout(db, m)
        sts = [CL.compute(db, db.get(SalesDeal, i.deal_id))
               for i in db.query(MasterDealItem).filter(MasterDealItem.master_deal_id == m.id)]
        if any(s["total_net"] is None for s in sts):
            continue
        assert sum((_d(s["total_net"]) for s in sts), Decimal(0)) == _d(lay["total_net"]), m.code
        assert sum((_d(s["total_gross"]) for s in sts), Decimal(0)) == _d(lay["total_gross"]), m.code
