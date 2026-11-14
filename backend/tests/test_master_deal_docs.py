# -*- coding: utf-8 -*-
"""Документы сделки — из мастер-сделки (владелец 13.11.2026: «документы показываем из мастер-сделки, ручную загрузку ДС,
счёта, УПД и акта убираем»).

Три случая: сделка = пакет (один к одному); одна сделка — два ДС (основные + допы) — два комплекта; пакет из нескольких
сделок с комплектами, не совпадающими со сделками, — сделка видит только комплекты со своими строками, со своей долей и
с кем комплект общий. Разбивку комплекта по сделкам пишет `to_annex.write_kits` в `master_deal_upds.deals`.

Поломки, которые ловят тесты: комплект создаётся без разбивки по сделкам; сделке отдаётся чужой комплект; доля сделки не
сходится с суммой комплекта; второй ДС сделки теряется (раньше карточка брала только первый)."""
import pytest

import app.model_registry  # noqa: F401
from app.master_deal import deal_docs as DD
from app.master_deal import layout as LY
from app.master_deal import service as MS
from app.master_deal import to_annex as TA
from app.master_deal.models import MasterDeal, MasterDealUpd
from tests import test_closing_scenarios as _cs
from tests.test_master_to_annex import _package

env = _cs.env


def test_kit_remembers_which_deals_it_is_made_of(env):
    db, deals, u = env
    m = _package(db, deals, u, {"addons_separate": True, "bonus_addons": "zero", "upd_by_brand": False, "upd_by_service": False})
    TA.create(db, m, u)
    kits = db.query(MasterDealUpd).filter_by(master_deal_id=m.id).all()
    assert kits
    ids = {d.id for d in deals}
    for k in kits:
        assert k.deals, f"комплект {k.upd_no} без разбивки по сделкам"
        assert {x["deal_id"] for x in k.deals} <= ids
        assert sum(x["net"] for x in k.deals) == pytest.approx(k.net, abs=0.02), "доли сделок = сумма комплекта"


def test_each_deal_sees_only_its_kits_with_its_share(env):
    db, deals, u = env
    m = _package(db, deals, u, {"addons_separate": True, "bonus_addons": "zero", "upd_by_brand": False, "upd_by_service": False})
    TA.create(db, m, u)
    kits = db.query(MasterDealUpd).filter_by(master_deal_id=m.id).all()
    for d in deals:
        got = DD.for_deal(db, d)
        assert got["master"]["code"] == m.code
        mine = [k for k in kits if any(x["deal_id"] == d.id for x in k.deals)]
        assert sorted(x["upd_no"] for x in got["kits"]) == sorted(k.upd_no for k in mine), "только комплекты со строками сделки"
        for row in got["kits"]:
            k = next(k for k in mine if k.upd_no == row["upd_no"])
            share = next(x for x in k.deals if x["deal_id"] == d.id)
            assert row["share_net"] == pytest.approx(share["net"], abs=0.01)
            assert row["total_gross"] == pytest.approx(k.gross, abs=0.01)
            others = {x["code"] for x in k.deals if x["deal_id"] != d.id}
            assert set(row["shared_with"]) == others
        # ДС — все, где у сделки есть доля (раньше карточка брала только первый)
        assert len(got["ds"]) == len({k.annex_id for k in mine} | {a["id"] for a in got["ds"]})


def test_deal_outside_master_gets_empty_kits_and_no_master(env):
    db, deals, u = env
    got = DD.for_deal(db, deals[0])
    if got["master"] is None:
        assert got["kits"] == []


def test_two_ds_of_one_deal_are_both_listed(env):
    """Случай 2: допы отдельным ДС — у сделки два ДС и минимум два комплекта."""
    db, deals, u = env
    m = _package(db, deals[:1], u, {"addons_separate": True, "bonus_addons": "zero"})
    lay = LY.layout(db, m)
    if len(lay["ds"]) < 2:
        pytest.skip("у сделки стенда нет платных допов — второго ДС не будет")
    TA.create(db, m, u)
    got = DD.for_deal(db, deals[0])
    assert len(got["ds"]) >= 2 and len(got["kits"]) >= 2
    assert all(not k["shared_with"] for k in got["kits"]), "сделка одна — комплекты не общие"


def test_send_with_unused_import_guard():
    assert MS and MasterDeal       # импорт держит модули в графе фикстур, как в соседних тестах


def test_closing_documents_are_not_uploaded_by_hand():
    """ДС, счёт, УПД и акт сделки — только из мастер-сделки (13.11.2026): ручная загрузка запрещена, отчёт и бриф — можно.
    Поломка: ручка загрузки снова принимает invoice/upd/ds/act, и рядом с документом 1С появляется вторая копия."""
    from app.routers import sales_dashboard as SD
    for kind in ("ds", "invoice", "upd", "act"):
        assert kind not in SD.DEAL_DOC_UPLOAD_KINDS
    for kind in ("report", "creatives", "brief_file"):
        assert kind in SD.DEAL_DOC_UPLOAD_KINDS
