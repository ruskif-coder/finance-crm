# -*- coding: utf-8 -*-
"""«Отправить в ДО» и мастер-сделка (app/master_deal, владелец 15.10.2026): своё ДС заводит пакет M-xxxx, вторая сделка того же
договора и месяца видит его кандидатом, сделка уже в пакете уходит в конструктор, заморозка сверки и переход стадии; раскладка
по ДС и УПД. Всё в откатываемой транзакции; уведомления подменены — со стенда ничего не уходит."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.master_deal import layout as LY
from app.master_deal import service as MS


@pytest.fixture
def env(monkeypatch):
    import app.notify.bus as bus
    monkeypatch.setattr(bus, "emit", lambda *a, **k: None)
    from app.database import SessionLocal
    from app.models import User
    from app.sales.models import SalesDeal
    db = SessionLocal()
    rows = db.execute(text("""
        SELECT d.id FROM sales_deals d
          JOIN sales_media_plans mp ON mp.deal_id = d.id AND mp.status <> 'rejected'
          JOIN sales_media_plan_rows r ON r.plan_id = mp.id AND r.unit_price > 0
         WHERE d.ord_final_contract_id IS NOT NULL AND d.period_from IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM master_deal_items i WHERE i.deal_id = d.id)
         GROUP BY d.id ORDER BY d.id LIMIT 2""")).fetchall()
    if len(rows) < 2:
        pytest.skip("на стенде мало сделок с договором и МП")
    recon = db.execute(text("SELECT id FROM sales_stages WHERE name = 'Итоговая сверка'")).scalar()
    deals = []
    for (i,) in rows:
        d = db.get(SalesDeal, i)
        d.our_stage_id = recon
        deals.append(d)
    # обе сделки — один договор и месяц, чтобы проверить «в мастер-сделку»
    deals[1].ord_final_contract_id, deals[1].period_from = deals[0].ord_final_contract_id, deals[0].period_from
    db.flush()
    from app.final_recon import closing as CL
    for d in deals:                      # у тестовых сделок факта может не быть — сумма ДС «под МП», сверка подтверждена
        CL.set_mode(db, d, "plan", None, None, privileged=True)
        CL.confirm(db, d, True, None)
    admin = db.query(User).filter(User.is_active == 1).first()
    try:
        yield db, deals, admin
    finally:
        db.rollback()
        db.close()


def test_own_ds_creates_master_and_moves_stage(env):
    db, (d1, _), u = env
    out = MS.send(db, d1, u, target="new")
    assert out["master"]["code"].startswith("M-")
    assert out["closing"]["frozen"] is True
    assert out["moved_to"] is not None
    assert MS.fork(db, d1)["in_master"]["code"] == out["master"]["code"]


def test_second_deal_sees_open_master_and_joins(env):
    db, (d1, d2), u = env
    code = MS.send(db, d1, u, target="new")["master"]["code"]
    f = MS.fork(db, d2)
    assert [c["code"] for c in f["candidates"]] == [code]
    out = MS.send(db, d2, u, target="join", master_id=f["candidates"][0]["id"])
    assert out["master"]["code"] == code


def test_send_only_from_recon_stage(env):
    db, (d1, _), u = env
    d1.our_stage_id = db.execute(text("SELECT id FROM sales_stages WHERE name = 'В размещении'")).scalar()
    with pytest.raises(MS.MasterError) as e:
        MS.send(db, d1, u, target="new")
    assert e.value.status == 409


def test_no_contract_blocks(env):
    db, (d1, _), u = env
    d1.ord_final_contract_id = None
    with pytest.raises(MS.MasterError) as e:
        MS.send(db, d1, u, target="new")
    assert e.value.status == 409


def test_layout_sum_equals_deals_and_upd_numbers_run_through(env):
    db, (d1, d2), u = env
    m_id = MS.send(db, d1, u, target="new")["master"]["id"]
    MS.send(db, d2, u, target="join", master_id=m_id)
    from app.final_recon import closing as CL
    from app.master_deal.models import MasterDeal
    m = db.get(MasterDeal, m_id)
    lay = LY.layout(db, m)
    deals_sum = sum((CL.compute(db, d)["base_ds_net"] or 0) + CL.compute(db, d)["paid_extras_net"] for d in (d1, d2))
    assert lay["total_net"] == pytest.approx(deals_sum, abs=0.05)
    nos = [x["upd_no"] for ds in lay["ds"] for x in ds["upds"]]
    assert nos == list(range(1, len(nos) + 1)), "№ УПД — сквозной в рамках пакета"
    m.addons_separate = False
    kinds = [ds["kind"] for ds in LY.layout(db, m)["ds"]]
    assert len(kinds) == 1 and kinds[0] in ("all", "main"), "допы строками — один ДС"


def test_addons_ds_only_with_paid_rows_and_moved_line_goes_to_main(env):
    """ТЗ §4–5: ДС допов только при платных строках; перенесённый платный доп — в основном ДС; № УПД сквозной; сумма не меняется."""
    db, (d1, d2), u = env
    m_id = MS.send(db, d1, u, target="new")["master"]["id"]
    MS.send(db, d2, u, target="join", master_id=m_id)
    from app.master_deal.models import MasterDeal
    m = db.get(MasterDeal, m_id)
    lay = LY.layout(db, m)
    paid = [x for x in LY.lines(db, m) if x["kind"] == "extra"]
    if not paid:
        assert [ds["kind"] for ds in lay["ds"]] == ["main"]
        return
    assert [ds["kind"] for ds in lay["ds"]] == ["main", "addons"]
    moved = LY.layout(db, m, {"moved": [x["id"] for x in paid]})
    assert [ds["kind"] for ds in moved["ds"]] == ["all"], "все платные допы перенесены — ДС допов не создаётся"
    assert moved["total_net"] == lay["total_net"]
    for ds in lay["ds"]:
        for k in ds["upds"]:
            assert k["net"] > 0, "комплект только из позиций со стоимостью"


def test_start_no_below_issued_is_refused(env):
    from app.master_deal import package as PK
    db, (d1, _), u = env
    m_id = MS.send(db, d1, u, target="new")["master"]["id"]
    from app.master_deal.models import MasterDeal
    m = db.get(MasterDeal, m_id)
    last = max((x["no"] for x in PK.issued(db, m.contract_id)), default=None)
    if last is None or last < 1:
        PK.set_start_no(db, m, 4, u)
        assert LY.layout(db, m)["ds"][0]["no"] == "5"
        return
    with pytest.raises(MS.MasterError):
        PK.set_start_no(db, m, last - 1, u)
    assert "пропущены" in PK.check_start_no(db, m, last + 3)["warn"]


def test_no_fact_with_fact_pin_cannot_be_confirmed(env):
    db, (d1, _), u = env
    from app.final_recon import closing as CL
    if CL.compute(db, d1)["fact_shows"] is not None:
        pytest.skip("у сделки есть факт")
    CL.set_mode(db, d1, "fact", None, None, privileged=True)
    with pytest.raises(CL.ClosingError) as e:
        CL.confirm(db, d1, True, None)
    assert e.value.status == 409


def test_send_with_sibling_puts_both_in_one_master(env):
    db, (d1, d2), u = env
    sib = {x["id"]: x for x in MS.siblings(db, d1)}
    assert d2.id in sib and sib[d2.id]["state"] == "ready", "по умолчанию — тот же договор и тот же месяц"
    out = MS.send_with(db, d1, [d2], u, target="new")
    assert out["added"] == [d2.code]
    assert MS.item_of(db, d2.id).master_deal_id == out["master"]["id"]
    from app.master_deal.models import MasterDeal
    assert MS.gate(db, db.get(MasterDeal, out["master"]["id"]))["ok"]


def test_sibling_with_running_rk_is_attached_and_holds_the_gate(env):
    """Владелец 15.10: взять можно и сделку с идущей РК — она прикрепляется, но пакет дальше конструктора документов не уйдёт."""
    db, (d1, d2), u = env
    d2.our_stage_id = db.execute(text("SELECT id FROM sales_stages WHERE name = 'В размещении'")).scalar()
    db.flush()
    assert {x["id"]: x for x in MS.siblings(db, d1)}[d2.id]["status"] == "РК не завершена"
    out = MS.send_with(db, d1, [d2], u, target="new")
    assert MS.item_of(db, d2.id).master_deal_id == out["master"]["id"]
    from app.master_deal.models import MasterDeal
    g = MS.gate(db, db.get(MasterDeal, out["master"]["id"]))
    assert not g["ok"] and [w["code"] for w in g["wait"]] == [d2.code]
    assert d2.our_stage_id == db.execute(text("SELECT id FROM sales_stages WHERE name = 'В размещении'")).scalar(), "прикреплённая не двигается"


def test_send_needs_confirmed_recon_and_pin_change_drops_it(env):
    """Дизайн 15.10: «Собрать ДС» — только по подтверждённой сверке; смена режима снимает подтверждение."""
    db, (d1, _), u = env
    from app.final_recon import closing as CL
    assert CL.compute(db, d1)["confirmed"]
    CL.set_mode(db, d1, "plan", None, None, privileged=True)
    assert not CL.compute(db, d1)["confirmed"]
    with pytest.raises(MS.MasterError) as e:
        MS.send(db, d1, u, target="new")
    assert e.value.status == 409


def test_sk_discount_shown_in_layout_and_sum_matches(env):
    """Владелец 15.10: скидка СК «в счёт» видна в раскладке — сумма пакета = сумме сделок к закрытию."""
    db, (d1, d2), u = env
    from app.final_recon import closing as CL
    from app.final_recon import sk as SK
    from app.master_deal.models import MasterDeal
    SK.set_deal(db, d1, "скидка в счёт", 10, u)
    CL.confirm(db, d1, True, None)
    m_id = MS.send(db, d1, u, target="new")["master"]["id"]
    MS.send(db, d2, u, target="join", master_id=m_id)
    m = db.get(MasterDeal, m_id)
    for st in ({}, {"addons_separate": False}, {"upd_by_service": True, "ds_by_service": True}):
        lay = LY.layout(db, m, st)
        rows = [r for ds in lay["ds"] for g in ds["groups"] for r in g["rows"]]
        assert any(r["kind"] == "discount" and r["deal"] == d1.code for r in rows)
        expect = sum(CL.compute(db, d)["total_net"] for d in (d1, d2))
        assert lay["total_net"] == pytest.approx(expect, abs=0.05)
        assert all(k["net"] > 0 for ds in lay["ds"] for k in ds["upds"]), "комплект из одной скидки не образуется"
