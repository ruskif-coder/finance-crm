# -*- coding: utf-8 -*-
"""Приоритезация по шагам (владелец 19.10.2026: «проверь сборку, согласование и закрытие по шагам»).

Реальные сделки стенда, весь путь: сборка → отправка → ответы площадок → запуск → стоп/старт → статистика за дни → итоговая
сверка → закрытие (ДС через мастер-сделку или «без документов» у бонусной). Транзакция откатывается; API системы
приоритезации подменён (со стенда наружу ничего не уходит); уведомления подменены. Каждый шаг печатает, что получилось."""
from datetime import timedelta

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.final_recon import closing as CL
from app.final_recon import no_docs as ND
from app.master_deal import layout as LY
from app.master_deal import package as PK
from app.master_deal import service as MS
from app.master_deal import to_annex as TA
from app.master_deal.models import MasterDeal
from app.prio import launch as L
from app.prio import models as M
from app.prio import service as S
from app.prio import stats as ST
from tests.test_closing_path_by_service import _contract_with_template
from tests.test_prio import FakeApi


class _U:
    id = None
    name = "тест"


@pytest.fixture
def db(monkeypatch):
    import app.notify.bus as bus
    monkeypatch.setattr(bus, "emit", lambda *a, **k: None)
    from app.database import SessionLocal
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


class DayApi(FakeApi):
    """Статистика по дням: показы на день задаются тестом; повторный запрос того же дня может «дорасти»."""
    def __init__(self):
        super().__init__()
        self.daily = {}

    def stats(self, a, b):
        return {"ok": True, "stats": [{"camp_id": cid, "search": {"imp": v, "clk": v // 100}, "catalog": {"imp": 0, "clk": 0}}
                                      for cid, v in self.daily.get(a, {}).items()]}


def _deal(db, code):
    from app.sales.models import SalesDeal
    d = db.query(SalesDeal).filter_by(code=code).first()
    if d is None:
        pytest.skip(f"на стенде нет сделки {code}")
    return d


def _step(n, what, detail):
    print(f"[шаг {n}] {what}: {detail}")


def _assemble_and_approve(db, d, pubs, indexes):
    """Шаги 1–3: сборка, отправка, ответы площадок. Первая площадка согласует, вторая вернёт → ответ → согласует, третья откажет."""
    c = S.save_common(db, d, {"product_name": "Тест-препарат 5 мг", "target_competitors": "Ксизал, Эльцет, Цетрин",
                              "target_mnn": "левоцетиризин", "target_meta": "от аллергии, от зуда, капли от насморка"}, _U())
    _step(1, "сборка · общая часть", f"«{c.product_name}», период {c.date_start}–{c.date_end}, конкурентов 3, МНН 1, ключевых 3")
    db.execute(text("UPDATE sales_publishers SET prio_site_id = 8000 + id WHERE id = ANY(:p)"), {"p": pubs})
    pls = []
    for pub, ix in zip(pubs, indexes):
        db.execute(text("DELETE FROM publisher_balance_index WHERE publisher_id = :p"), {"p": pub})
        db.execute(text("INSERT INTO publisher_balance_index (publisher_id, scope, index_auto) VALUES (:p, 'web', :v)"), {"p": pub, "v": ix})
    for pub in pubs:
        p = S.add_placement(db, d, pub, _U())
        miss = S.view(db, d)["placements"][-1]["missing"]
        S.edit_placement(db, d, p.id, {"erid": f"2SDtest{pub}", "product_url": f"https://apteka{pub}.example/p/1"})
        pls.append(p)
        _step(1, f"сборка · площадка {pub}", f"до посадочной и ЕРИД не хватало: {', '.join(miss)}")
    v = S.view(db, d)
    _step(1, "раскладка цели по индексу", f"объём {v['plan_volume']}: " + ", ".join(
        f"{x['publisher_id']} — индекс {x['index']}, вес {x['weight_pct']} %, цель {x['goal_imp']}" for x in v["placements"])
        + f"; сумма целей {sum(x['goal_imp'] or 0 for x in v['placements'])}")
    _step(2, "к отправке", f"готовых черновиков {v['ready_to_send']}")
    for p in pls:
        S.send(db, d, p.id, _U())
    _step(2, "отправлено", " / ".join(f"{p.publisher_id}: {p.status}" for p in pls))
    a, b, rej = pls[0], pls[1], (pls[2] if len(pls) > 2 else None)
    S.set_sku(db, a, "1234567")
    S.verdict(db, a, "ок", None)
    S.verdict(db, b, "вернуть", "SKU не тот: это 10 мг")
    _step(3, "ответы площадок", f"{a.publisher_id}: SKU {a.product_id} → {a.status}; {b.publisher_id}: {b.status} — «{b.comment}»")
    S.reply(db, d, b.id, "поправили на 5 мг", _U())
    S.set_sku(db, b, "7654321")
    S.verdict(db, b, "ок", None)
    _step(3, "ответ аккаунта → повторно", f"{b.publisher_id}: «{b.comment}» → {b.status}")
    if rej:
        S.verdict(db, rej, "отказ", "товара нет в ассортименте")
        _step(3, "отказ", f"{rej.publisher_id}: {rej.status} — «{rej.comment}»")
    v = S.view(db, d)
    _step(3, "после отказа — цели", ", ".join(f"{x['publisher_id']}: {x['goal_imp']}" for x in v["placements"]) if False else
          ", ".join(f"{x['publisher_id']}: {x['goal_imp']}" for x in S.view(db, d)["placements"]))
    _step(3, "конвейер", ", ".join(f"{x['status']} {x['count']}" for x in v["pipeline"]) + f"; к запуску {v['ready_to_launch']}")
    return [a, b]


def _launch_and_collect(db, d, live, api, days, per_day):
    for p in live:
        L.launch(db, d, p.id, client=api)
    _step(4, "запуск", " / ".join(f"{p.publisher_id}: camp {p.camp_id} {p.status}, autostart {api.camps[p.camp_id]['autostart']}" for p in live))
    L.toggle(db, d, live[0].id, False, client=api)
    s1 = live[0].status
    L.toggle(db, d, live[0].id, True, client=api)
    _step(5, "стоп / старт", f"{live[0].publisher_id}: {s1} → {live[0].status}; в системе toggle_on={api.camps[live[0].camp_id]['toggle_on']}")
    for day in days:
        api.daily[day.isoformat()] = {p.camp_id: per_day[i] for i, p in enumerate(live)}
    o = ST.pull(db, api, days, commit=False)
    api.daily[days[-1].isoformat()] = {p.camp_id: per_day[i] + 500 for i, p in enumerate(live)}   # последний день дорос
    o2 = ST.pull(db, api, [days[-1]], commit=False)
    deltas = [r.delta_shows for r in db.query(M.PrioStatRaw).filter_by(day=days[-1]).order_by(M.PrioStatRaw.id) if r.delta_shows is not None]
    _step(6, "статистика", f"суток {o['days']}, снимков {o['snapshots']}, строк факта {o['written']}; перезабор последнего дня — "
                           f"снимков {o2['snapshots']}, дельты {deltas}")
    return o


def test_paid_prioritization_to_ds(db):
    """Платная (3VBNTL): сборка → площадки → запуск → статистика → сверка по факту → ДС."""
    d = _deal(db, "3VBNTL")
    pubs = [r[0] for r in db.execute(text("SELECT id FROM sales_publishers WHERE is_active ORDER BY id LIMIT 3"))]
    live = _assemble_and_approve(db, d, pubs, [3.0, 1.0, 1.0])
    assert all(p.status == M.APPROVED for p in live)
    v = S.view(db, d)
    assert sum(x["goal_imp"] or 0 for x in v["placements"]) == v["plan_volume"], "цели не складываются в объём"
    g = {x["publisher_id"]: x["goal_imp"] for x in v["placements"]}
    assert abs(g[pubs[0]] - v["plan_volume"] * 3 / 4) <= 1 and g[pubs[2]] == 0, "после отказа доля перешла по индексу 3:1"
    api = DayApi()
    start = S.request_of(db, d).date_start
    days = [start + timedelta(days=i) for i in range(5)]
    o = _launch_and_collect(db, d, live, api, days, [20000, 9000])
    assert o["written"] == 5, "строка факта — одна на сутки: площадки без своей строки РК складываются"
    # итоговая сверка: факт — из статистики приоритезации (источник prio), как у полного цикла
    d.our_stage_id = db.execute(text("SELECT id FROM sales_stages WHERE name = 'Итоговая сверка'")).scalar()
    c = _contract_with_template(db)
    d.ord_final_contract_id = c.id
    db.flush()
    st = CL.compute(db, d)
    fact = sum(r[0] for r in db.execute(text("""SELECT shows FROM ad_campaign_stat s JOIN ad_campaign a ON a.id = s.campaign_id
                                                 WHERE a.deal_id = :d AND s.source = 'prio'"""), {"d": d.id}))
    _step(7, "итоговая сверка", f"план {st['plan_shows']}, факт {st['fact_shows']} (источник: {st['fact_source']}), "
                                f"{st['verdict']['text']}, по факту {st['amounts']['fact']} из {st['base_plan_net']}")
    assert st["fact_source"] == "stats" and st["fact_shows"] == fact, "факт приоритезации не дошёл до сверки"
    want = 5 * (20000 + 9000) + 2 * 500                     # все площадки, все дни, последний день дорос у обеих
    assert fact == want, f"факт {fact} ≠ {want}: показы площадок затирают друг друга"
    CL.set_mode(db, d, "fact", None, _U(), privileged=True)
    CL.confirm(db, d, True, _U())
    m = db.get(MasterDeal, MS.send_with(db, d, [], _U(), target="new")["master"]["id"])
    PK.set_start_no(db, m, max((x["no"] for x in PK.issued(db, m.contract_id)), default=0), _U())
    lay = LY.layout(db, m)
    made = TA.create(db, m, _U())
    st = CL.compute(db, d)
    _step(8, "закрытие", f"{m.code}: ДС {', '.join(x['number'] for x in made)}, к закрытию {st['total_net']} до НДС / "
                         f"{st['total_gross']} с НДС, УПД в раскладке {lay['upd_count']}")
    assert made and st["frozen"]


def test_bonus_prioritization_closes_without_documents(db):
    """Бонусная (Q7UM3A, скидка 100 %): всё то же до статистики → «Закрыть без документов» → архив, без ДС."""
    d = _deal(db, "Q7UM3A")
    pubs = [r[0] for r in db.execute(text("SELECT id FROM sales_publishers WHERE is_active ORDER BY id DESC LIMIT 2"))]
    live = _assemble_and_approve(db, d, pubs, [2.0, 1.0])
    api = DayApi()
    start = S.request_of(db, d).date_start
    _launch_and_collect(db, d, live, api, [start + timedelta(days=i) for i in range(3)], [30000, 15000])
    d.our_stage_id = db.execute(text("SELECT id FROM sales_stages WHERE name = 'Итоговая сверка'")).scalar()
    db.flush()
    st = CL.compute(db, d)
    _step(7, "итоговая сверка", f"план {st['plan_shows']}, факт {st['fact_shows']}, сумма МП {st['base_plan_net']}, "
                                f"бонусное размещение: {st['no_docs']['eligible']}")
    assert st["no_docs"]["eligible"]
    out = ND.close(db, d, _U())
    _step(8, "закрытие без документов", f"стадия «{out['moved_to']}», заморожено {out['frozen']}, мастер-сделки нет: "
          f"{not db.execute(text('SELECT 1 FROM master_deal_items WHERE deal_id = :d'), {'d': d.id}).first()}")
    assert out["moved_to"] == "Архив успешных сделок"
