# -*- coding: utf-8 -*-
"""Путь «итоговая сверка → ДС» по КАЖДОЙ услуге (владелец 19.10.2026: «по каждой услуге пройди путь до ДС»).

Одна реальная сделка стенда на услугу, весь путь, как его проходит аккаунт:
  контур аккаунта — ввод факта по полям строки (90 % плана) и себестоимости; полный цикл — пин по факту или «Под МП», если факта нет;
  → «Подтвердить сверку» → «Собрать ДС» (своё ДС, новая мастер-сделка) → раскладка → «В конструктор ДС» → документ ДС.
Проверяется, что каждый шаг проходит и что сумма ДС = сумме «к закрытию» сделки. Транзакция откатывается: на стенде следов нет;
уведомления подменены; DSP не вызывается."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.annex_tpl import document as tpl_doc
from app.final_recon import closing as CL
from app.final_recon import flow as FLOW
from app.master_deal import layout as LY
from app.master_deal import package as PK
from app.master_deal import service as MS
from app.master_deal import to_annex as TA
from app.master_deal.models import MasterDeal

SERVICES = ["еФарм", "eFMCG", "Приоритезация", "Клик-аут", "Альфарм-Таргет", "Polza", "OLV"]


@pytest.fixture
def env(monkeypatch):
    import app.notify.bus as bus
    monkeypatch.setattr(bus, "emit", lambda *a, **k: None)
    from app.database import SessionLocal
    from app.models import User
    db = SessionLocal()
    admin = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
    try:
        yield db, admin
    finally:
        db.rollback()
        db.close()


def _deal_of(db, service):
    from app.sales.models import SalesDeal
    row = db.execute(text("""
        SELECT d.id FROM sales_deals d
          JOIN sales_services s ON s.id = d.service_id AND s.name = :s
          JOIN sales_media_plans mp ON mp.deal_id = d.id AND mp.status <> 'rejected'
          JOIN sales_media_plan_rows r ON r.plan_id = mp.id AND r.unit_price > 0 AND r.volume > 0
         WHERE NOT EXISTS (SELECT 1 FROM master_deal_items i WHERE i.deal_id = d.id)
           AND NOT EXISTS (SELECT 1 FROM final_recon_deals f WHERE f.deal_id = d.id AND f.sent_at IS NOT NULL)
         GROUP BY d.id ORDER BY d.period_from DESC NULLS LAST, d.id DESC LIMIT 1"""), {"s": service}).first()
    if not row:
        pytest.skip(f"на стенде нет сделки «{service}» с медиапланом")
    return db.get(SalesDeal, row[0])


def _contract_with_template(db):
    from app.models import Contract
    for c in db.query(Contract).order_by(Contract.id):
        if tpl_doc.resolve(db, c)[0] is not None:
            return c
    pytest.skip("на стенде нет договора с шаблоном ДС")


def _fill_fact(db, d, u):
    """Контур аккаунта: факт по полям строки — 90 % плана, клики, досмотры, показы справочно; себестоимость."""
    rows = CL.compute(db, d)["fact_entry"]["rows"]
    assert rows, "у сделки контура аккаунта нет строк для ввода факта"
    vals = {}
    for r in rows:
        fact = round(r["volume"] * 0.9, 2) if r["kind"] != "fix" else r["volume"]
        vals[r["row_id"]] = {"fact": fact, "clicks": 1000 if r["kind"] in ("cpm", "video") else None,
                             "completed": round(fact * 0.7) if r["kind"] == "video" else None,
                             "reference_shows": 800000 if r["kind"] == "fix" else None}
    CL.save_fact(db, d, vals, "тест: отчёт платформы", u)
    CL.save_cost(db, d, 1000, u)
    st = CL.compute(db, d)
    assert st["fact_source"] == "entered" and st["fact_shows"] is not None, "введённый факт не стал фактом сделки"
    return st


@pytest.mark.parametrize("service", SERVICES)
def test_path_to_ds(env, service):
    db, u = env
    from app.sales.models import SalesAnnex
    d = _deal_of(db, service)
    c = _contract_with_template(db)
    d.ord_final_contract_id = c.id
    if not d.period_from:
        pytest.skip(f"{d.code}: у сделки нет периода")
    d.our_stage_id = db.execute(text("SELECT id FROM sales_stages WHERE name = 'Итоговая сверка'")).scalar()
    db.flush()

    account = FLOW.is_account(db, d)
    st = _fill_fact(db, d, u) if account else CL.compute(db, d)
    mode = "fact" if st["fact_shows"] is not None else "plan"
    CL.set_mode(db, d, mode, None, u, privileged=True)
    CL.confirm(db, d, True, u)
    st = CL.compute(db, d)
    assert st["confirmed"] and st["total_net"] is not None, f"{d.code}: сверка не подтвердилась"

    out = MS.send_with(db, d, [], u, target="new")
    m = db.get(MasterDeal, out["master"]["id"])
    assert CL.compute(db, d)["frozen"], f"{d.code}: «Собрать ДС» не заморозил сверку"
    last = max((x["no"] for x in PK.issued(db, m.contract_id)), default=0)
    PK.set_start_no(db, m, last, u)

    lay = LY.layout(db, m)
    assert lay["ds"], f"{d.code}: раскладка пустая"
    made = TA.create(db, m, u)
    assert made, f"{d.code}: конструктор ДС ничего не создал"
    total = 0.0
    for x in made:
        a = db.get(SalesAnnex, x["id"])
        model = tpl_doc.live(db, c, tpl_doc.resolve(db, c)[0], a, [d.id])
        assert model["consistency"]["ok"], f"{d.code} {x['number']}: {model['consistency']['details']}"
        total += float(model["table"]["totals"]["net"])
    assert total == pytest.approx(st["total_net"], abs=0.05), f"{d.code}: сумма ДС {total} ≠ к закрытию {st['total_net']}"
    print(f"[путь] {service}: {d.code} · {'контур аккаунта' if account else 'полный цикл'} · пин {mode} · факт {st['fact_shows']} "
          f"· к закрытию {st['total_net']} · {m.code} · ДС: " + ", ".join(f"{x['number']} ({x.get('kind', '')})" for x in made) + f" · сумма ДС {round(total, 2)}")


def _inject_fact(db, d, pct):
    """Полный цикл с фактом (владелец 19.10: «просто подставь данные»): РК сделки (нет — заводим), план из МП, строка статистики DSP
    на `pct` % плана. Всё в той же транзакции — откатывается вместе с тестом."""
    from app.ad.models import AdCampaign
    from app.sales import mp_row
    from app.sales.annex import plan_rows
    plan = sum(float(r["volume"] or 0) for r in plan_rows(db, [d.id]) if r.get("kind") != "extra" and mp_row.is_cpm(r.get("model")))
    plan = plan or sum(float(r["volume"] or 0) for r in plan_rows(db, [d.id]) if r.get("kind") != "extra")
    camp = db.query(AdCampaign).filter(AdCampaign.deal_id == d.id).first()
    if camp is None:
        camp = AdCampaign(deal_id=d.id, status="запущена", date_start=d.period_from, date_end=d.period_to or d.period_from)
        db.add(camp)
    camp.plan_show = int(plan)
    db.flush()
    db.execute(text("INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks, source) "
                    "VALUES (:c, NULL, :d, :s, 0, 'dsp')"),
               {"c": camp.id, "d": camp.date_start or d.period_from, "s": int(plan * pct / 100)})
    db.flush()
    return plan


@pytest.mark.parametrize("service,pct", [("еФарм", 90), ("еФарм", 100), ("еФарм", 110), ("Приоритезация", 90), ("Клик-аут", 95)])
def test_full_cycle_with_fact_to_ds(env, service, pct):
    """Полный цикл с фактом из статистики: недокрут / в плане / перекрут → «По факту» (не больше плана) → ДС."""
    db, u = env
    from app.sales.models import SalesAnnex
    d = _deal_of(db, service)
    if FLOW.is_account(db, d):
        pytest.skip(f"{d.code}: сделка в контуре аккаунта по своей воронке")
    c = _contract_with_template(db)
    d.ord_final_contract_id = c.id
    d.our_stage_id = db.execute(text("SELECT id FROM sales_stages WHERE name = 'Итоговая сверка'")).scalar()
    db.flush()
    plan = _inject_fact(db, d, pct)
    st = CL.compute(db, d)
    assert st["fact_source"] == "stats" and st["fact_shows"] == int(plan * pct / 100), f"{d.code}: подставленный факт не виден сверке"
    want = {90: "under", 100: "ok", 110: "over"}.get(pct)
    if want == "under":
        assert st["verdict"]["code"] == "under"
    CL.set_mode(db, d, "fact", None, u, privileged=True)
    CL.confirm(db, d, True, u)
    st = CL.compute(db, d)
    by_fact = round(min(st["fact_shows"], st["plan_shows"]) / st["plan_shows"] * st["base_plan_net"], 2)
    assert st["base_ds_net"] == pytest.approx(by_fact, abs=0.05), "«По факту» — факт, но не больше плана"
    m = db.get(MasterDeal, MS.send_with(db, d, [], u, target="new")["master"]["id"])
    PK.set_start_no(db, m, max((x["no"] for x in PK.issued(db, m.contract_id)), default=0), u)
    made = TA.create(db, m, u)
    total = sum(float(tpl_doc.live(db, c, tpl_doc.resolve(db, c)[0], db.get(SalesAnnex, x["id"]), [d.id])["table"]["totals"]["net"]) for x in made)
    assert total == pytest.approx(st["total_net"], abs=0.05)
    print(f"[факт] {service} {pct} %: {d.code} · план {int(plan)} · факт {st['fact_shows']} · {st['verdict']['text']} · "
          f"по факту {st['base_ds_net']} из {st['base_plan_net']} · ДС {', '.join(x['number'] for x in made)} на {round(total, 2)}")
