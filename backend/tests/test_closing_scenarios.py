# -*- coding: utf-8 -*-
"""Сценарный прогон контура закрытия (владелец 15.10.2026): итоговая сверка во всех вариантах → «Собрать ДС» → раскладка
мастер-сделки при всех сочетаниях настроек. Проверяется, что ничего не падает и что держатся инварианты:
сумма пакета = сумме сделок «к закрытию», № УПД сквозной с 1, комплект только из позиций со стоимостью,
ДС допов только при платных строках, у заблокированных путей — понятный отказ (4xx), а не исключение.

Сделки — со стенда (ничего не пишется: транзакция откатывается; уведомления подменены; DSP не вызывается)."""
import itertools

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.final_recon import closing as CL
from app.final_recon import sk as SK
from app.master_deal import layout as LY
from app.master_deal import package as PK
from app.master_deal import service as MS
from app.master_deal.models import MasterDeal

BONUSES = [(None, None), ("pct", 10), ("qty", 150_000), ("rub", 40_000), ("pct", 300)]
SKS = [(None, None), ("скидка в счёт", 10), ("постоплата", 5), ("скидка в счёт", 0)]


class _U:
    id = None


@pytest.fixture
def env(monkeypatch):
    import app.notify.bus as bus
    monkeypatch.setattr(bus, "emit", lambda *a, **k: None)
    from app.database import SessionLocal
    from app.models import User
    from app.sales.models import SalesDeal
    db = SessionLocal()
    # Разные сделки ПО КАТЕГОРИЯМ (первая версия набора брала шесть одинаковых — с фактом, без платных допов, — и половина
    # путей не проверялась): с фактом РК · без РК (нет факта) · с платным допом · с бонусным допом.
    base = """
        SELECT d.id FROM sales_deals d
          JOIN sales_media_plans mp ON mp.deal_id = d.id AND mp.status <> 'rejected'
          JOIN sales_media_plan_rows r ON r.plan_id = mp.id AND r.unit_price > 0 AND r.volume > 0
         WHERE d.ord_final_contract_id IS NOT NULL AND d.period_from IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM master_deal_items i WHERE i.deal_id = d.id) AND {cond}
         GROUP BY d.id ORDER BY d.id DESC LIMIT {n}"""
    cats = {
        "fact": "EXISTS (SELECT 1 FROM ad_campaign c JOIN ad_campaign_stat t ON t.campaign_id = c.id WHERE c.deal_id = d.id)",
        "nofact": "NOT EXISTS (SELECT 1 FROM ad_campaign c WHERE c.deal_id = d.id)",
        "paid": "EXISTS (SELECT 1 FROM sales_media_plan_extras e WHERE e.plan_id = mp.id AND e.total > 0)",
        "bonus": "EXISTS (SELECT 1 FROM sales_media_plan_extras e WHERE e.plan_id = mp.id AND coalesce(e.total, 0) = 0)",
    }
    ids = []
    for k, cond in cats.items():
        for (i,) in db.execute(text(base.format(cond=cond, n=2))).fetchall():
            if i not in ids:
                ids.append(i)
    rows = [(i,) for i in ids]
    recon = db.execute(text("SELECT id FROM sales_stages WHERE name = 'Итоговая сверка'")).scalar()
    deals = []
    for r in rows:
        d = db.get(SalesDeal, r[0])
        d.our_stage_id = recon
        deals.append(d)
    for d in deals[1:]:                      # один договор и месяц — чтобы собирать пакеты
        d.ord_final_contract_id, d.period_from = deals[0].ord_final_contract_id, deals[0].period_from
    db.flush()
    admin = db.query(User).filter(User.is_active == 1).first()
    try:
        yield db, deals, admin
    finally:
        db.rollback()
        db.close()


def _ready(db, d, mode="plan"):
    CL.set_mode(db, d, mode, None, None, privileged=True)
    CL.confirm(db, d, True, None)


# ── итоговая сверка: все пины × бонусы × СК — расчёт не падает и сходится сам с собой ──────────────────────

def test_closing_every_pin_bonus_sk_combination(env):
    db, deals, u = env
    kinds = {CL.compute(db, d)["fact_shows"] is None for d in deals}
    assert kinds == {True, False}, "набор обязан содержать сделки и с фактом, и без"
    for d in deals:
        for (bm, bv), (sm, sp) in itertools.product(BONUSES, SKS):
            d.bonus_traffic_mode, d.bonus_traffic_value = bm, bv
            SK.set_deal(db, d, sm, sp, u)
            db.flush()
            for mode in ("fact", "plan", "manual"):
                st = CL.compute(db, d)
                if mode == "fact" and st["fact_shows"] is None:
                    out = CL.set_mode(db, d, "fact", None, None, privileged=True)
                    assert out["base_ds_net"] is None and out["total_net"] is None, "нет факта — суммы нет, но и не падаем"
                    with pytest.raises(CL.ClosingError):
                        CL.confirm(db, d, True, None)
                    continue
                if mode == "manual":
                    out = CL.set_mode(db, d, "manual", max(st["base_plan_net"] / 3, 0.01), None, privileged=True, manual_volume=1000)
                else:
                    out = CL.set_mode(db, d, mode, None, None, privileged=True)
                assert out["base_ds_net"] is not None and out["base_ds_net"] <= out["base_plan_net"] + 0.01, "в ДС не больше МП"
                disc = out["sk"]["amount_net"] if out["sk"]["mode"] == "скидка в счёт" else 0
                assert out["total_net"] == pytest.approx(out["base_ds_net"] + out["paid_extras_net"] - disc, abs=0.02)
                assert out["total_gross"] >= out["total_net"]
                assert out["verdict"]["code"] in ("under", "in_plan", "over", "no_fact", "no_plan")
                assert not out["confirmed"], "смена режима снимает подтверждение"


def test_manual_guards(env):
    db, deals, u = env
    d = deals[0]
    mp = CL.compute(db, d)["base_plan_net"]
    for bad in (0, -5, mp + 100):
        with pytest.raises(CL.ClosingError):
            CL.set_mode(db, d, "manual", bad, None, privileged=True)
    with pytest.raises(CL.ClosingError) as e:
        CL.set_mode(db, d, "manual", mp / 2, None, privileged=False)
    assert e.value.status == 403
    with pytest.raises(CL.ClosingError):
        CL.set_mode(db, d, "что-то", None, None, privileged=True)


# ── «Собрать ДС»: своё ДС, в пакет, с соседями в разных состояниях, повтор, отказы ─────────────────────────

def test_send_variants_and_refusals(env):
    db, deals, u = env
    d1, d2, d3 = deals[:3]
    with pytest.raises(MS.MasterError):                      # без подтверждения
        MS.send(db, d1, u, target="new")
    _ready(db, d1)
    with pytest.raises(MS.MasterError):                      # непонятная цель
        MS.send(db, d1, u, target="куда-то")
    _ready(db, d2)                                           # d2 готова, d3 — РК не завершена
    d3.our_stage_id = db.execute(text("SELECT id FROM sales_stages WHERE name = 'В размещении'")).scalar()
    db.flush()
    sib = {x["id"]: x for x in MS.siblings(db, d1)}
    assert sib[d2.id]["state"] == "ready" and sib[d3.id]["state"] == "rk"
    out = MS.send_with(db, d1, [d2, d3], u, target="new")
    m = db.get(MasterDeal, out["master"]["id"])
    assert sorted(out["added"]) == sorted([d2.code, d3.code])
    g = MS.gate(db, m)
    assert not g["ok"] and [w["code"] for w in g["wait"]] == [d3.code]
    # повторная отправка той же сделки — уже в пакете, ничего не ломает
    again = MS.send(db, d1, u, target="new")
    assert again["master"]["id"] == m.id and again["moved_to"] is None
    # чужая сделка (другой договор) в пакет не входит
    if len(deals) > 3:
        x = deals[3]
        x.ord_final_contract_id = None
        db.flush()
        with pytest.raises(MS.MasterError):
            PK.add_deal(db, m, x, u)


# ── раскладка: все 2^4 × бонусы допов × переносы — инварианты ───────────────────────────────────────────

def _check(lay, deals_total):
    assert lay["total_net"] == pytest.approx(deals_total, abs=0.05), "сумма пакета = сумме сделок к закрытию"
    nos = [k["upd_no"] for ds in lay["ds"] for k in ds["upds"]]
    assert nos == list(range(1, len(nos) + 1)), "№ УПД сквозной с 1"
    for ds in lay["ds"]:
        assert all(k["net"] > 0 for k in ds["upds"]), "комплект только из позиций со стоимостью"
        assert ds["net"] == pytest.approx(sum(r["net"] for g in ds["groups"] for r in g["rows"]), abs=0.02)
        assert ds["no_kits"] == (not ds["upds"])
        if ds["kind"] == "addons":
            assert any(r["kind"] == "extra" for g in ds["groups"] for r in g["rows"]), "ДС допов только с платными строками"
            assert all(g["service"] is None for g in ds["groups"]), "у допов услуга не делит"


def test_layout_all_settings_combinations(env):
    db, deals, u = env
    for d in deals:
        _ready(db, d)
    SK.set_deal(db, deals[1], "скидка в счёт", 7, u)          # СК в пакете — видна в раскладке
    CL.confirm(db, deals[1], True, None)
    out = MS.send_with(db, deals[0], deals[1:], u, target="new")
    m = db.get(MasterDeal, out["master"]["id"])
    deals_total = sum(CL.compute(db, d)["total_net"] or 0 for d in deals)
    ls = LY.lines(db, m)
    paid = [x["id"] for x in ls if x["kind"] == "extra"]
    # прибор полноты: набор обязан задеть платные и бонусные допы и скидку — иначе проверка ниже ничего не доказывает
    assert paid, "в пакете нет платных допов — ДС допов и переносы не проверены"
    assert any(x["kind"] == "bonus" for x in ls), "в пакете нет бонусных допов"
    seen_addons = False
    for sep, bonus, a, b, c, e in itertools.product((True, False), ("zero", "hide"), *[(True, False)] * 4):
        for moved in ([], paid[:1], paid):
            lay = LY.layout(db, m, {"addons_separate": sep, "bonus_addons": bonus, "ds_by_brand": a, "ds_by_service": b,
                                    "upd_by_brand": c, "upd_by_service": e, "moved": moved})
            _check(lay, deals_total)
            seen_addons |= any(ds["kind"] == "addons" for ds in lay["ds"])
            assert any(r["kind"] == "discount" for ds in lay["ds"] for g in ds["groups"] for r in g["rows"]), "скидка СК видна"
    assert seen_addons, "ДС допов ни разу не построен"
    # сохранение и перечитывание — то же самое
    PK.save_settings(db, m, {"addons_separate": True, "bonus_addons": "hide", "moved": paid[:1]}, u)
    _check(LY.layout(db, m), deals_total)


def test_package_edits_and_empty_package(env):
    db, deals, u = env
    _ready(db, deals[0])
    m = db.get(MasterDeal, MS.send(db, deals[0], u, target="new")["master"]["id"])
    PK.add_deal(db, m, deals[1], u)                            # «+ сделка» — любая того же договора и месяца
    with pytest.raises(MS.MasterError):
        PK.add_deal(db, m, deals[1], u)                        # повторно — отказ
    PK.remove_deal(db, m, deals[1].id)
    PK.remove_deal(db, m, deals[0].id)                         # пакет можно опустошить до нуля
    lay = LY.layout(db, m)
    assert lay["ds"] == [] and lay["total_net"] == 0 and lay["upd_count"] == 0
    with pytest.raises(MS.MasterError):
        PK.remove_deal(db, m, deals[0].id)                     # уже не в пакете
    # номер ДС: проверка и сохранение
    for no in (0, 1, 7, 1000):
        chk = PK.check_start_no(db, m, no)
        assert "ok" in chk
        if chk["ok"]:
            PK.set_start_no(db, m, no, u)
    with pytest.raises(MS.MasterError):
        PK.set_start_no(db, m, -1, u)
