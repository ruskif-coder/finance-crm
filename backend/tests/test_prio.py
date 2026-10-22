# -*- coding: utf-8 -*-
"""Приоритезация (19.10.2026): сборка → площадка → запуск → статистика. Сделка стенда, транзакция откатывается; API
системы приоритезации подменён — со стенда в боевую систему ничего не уходит."""
from datetime import date

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.prio import launch as L
from app.prio import models as M
from app.prio import service as S
from app.prio import stats as ST


class _U:
    id = None
    name = "тест"


class FakeApi:
    """Подмена API: заводит РК в памяти, отдаёт её по camp_id, считает вызовы create."""
    def __init__(self):
        self.camps, self.created, self.updates = {}, 0, []

    def create(self, body):
        self.created += 1
        cid = 900 + self.created
        self.camps[cid] = {**body, "camp_id": cid, "imp_token_search": f"https://t/imp?adid={cid}"}
        return self.camps[cid]

    def update(self, cid, fields):
        self.updates.append((cid, fields))
        self.camps[cid].update(fields)
        return {"ok": True}

    def campaigns(self, **f):
        if f.get("camp_id"):
            return [self.camps[f["camp_id"]]] if f["camp_id"] in self.camps else []
        return list(self.camps.values())

    def stats(self, a, b):
        return {"ok": True, "stats": [{"camp_id": cid, "impressions": 1000 + len(self.updates), "clicks": 7} for cid in self.camps]}


@pytest.fixture
def env(monkeypatch):
    import app.notify.bus as bus
    monkeypatch.setattr(bus, "emit", lambda *a, **k: None)
    from app.database import SessionLocal
    from app.sales.models import SalesDeal
    db = SessionLocal()
    did = db.execute(text("""SELECT d.id FROM sales_deals d JOIN sales_services s ON s.id = d.service_id
                              WHERE s.name = 'Приоритезация' AND d.period_from IS NOT NULL ORDER BY d.id LIMIT 1""")).scalar()
    if not did:
        pytest.skip("на стенде нет сделки Приоритезации")
    pubs = [r[0] for r in db.execute(text("SELECT id FROM sales_publishers WHERE is_active ORDER BY id LIMIT 2"))]
    db.execute(text("UPDATE sales_publishers SET prio_site_id = 7000 + id WHERE id = ANY(:p)"), {"p": pubs})
    try:
        yield db, db.get(SalesDeal, did), pubs
    finally:
        db.rollback()
        db.close()


def _ready(db, d, pub):
    S.save_common(db, d, {"product_name": "Аллервэй 5мг", "target_competitors": "Ксизал,  Эльцет, Ксизал",
                          "target_mnn": "левоцетиризин", "target_meta": "от аллергии\nот зуда"}, _U())
    p = S.add_placement(db, d, pub, _U())
    return p


def test_lists_are_normalised_for_api(env):
    db, d, pubs = env
    _ready(db, d, pubs[0])
    r = S.request_of(db, d)
    assert r.target_competitors == "Ксизал, Эльцет", "через запятую и пробел, без повторов"
    assert r.target_meta == "от аллергии, от зуда"


def test_send_needs_site_erid_landing(env):
    db, d, pubs = env
    p = _ready(db, d, pubs[0])
    with pytest.raises(S.PrioError) as e:
        S.send(db, d, p.id, _U())
    assert "ЕРИД" in e.value.message and "посадочной" in e.value.message
    with pytest.raises(S.PrioError):
        S.edit_placement(db, d, p.id, {"product_url": "javascript:alert(1)"})
    S.edit_placement(db, d, p.id, {"erid": "2SDnjcpKqT9", "product_url": "https://maksavit.ru/p/1"})
    assert S.send(db, d, p.id, _U()).status == M.AT_SITE
    assert S.view(db, d)["pipeline"][1] == {"status": M.AT_SITE, "count": 1}


def _sent(db, d, pub):
    p = _ready(db, d, pub)
    S.edit_placement(db, d, p.id, {"erid": "2SDnjcpKqT9", "product_url": "https://maksavit.ru/p/1"})
    return S.send(db, d, p.id, _U())


def test_publisher_answers(env):
    db, d, pubs = env
    p = _sent(db, d, pubs[0])
    with pytest.raises(S.PrioError):
        S.verdict(db, p, "ок", None)                       # без SKU — нельзя
    for bad in ("12a4", "123", ""):
        with pytest.raises(S.PrioError):
            S.set_sku(db, p, bad)
    S.verdict(db, p, "вернуть", "SKU не тот")
    assert p.status == M.REWORK and p.comment == "SKU не тот"
    S.reply(db, d, p.id, "поправили", _U())
    assert p.status == M.AT_SITE
    S.set_sku(db, p, "1234567")
    assert S.verdict(db, p, "ок", None).status == M.APPROVED


def test_reject_is_final(env):
    db, d, pubs = env
    p = _sent(db, d, pubs[0])
    with pytest.raises(S.PrioError):
        S.verdict(db, p, "отказ", "")
    S.verdict(db, p, "отказ", "не наш товар")
    assert p.status == M.REJECTED and p.rejected_at
    with pytest.raises(S.PrioError):
        S.verdict(db, p, "ок", None)


def _approved(db, d, pub):
    p = _sent(db, d, pub)
    S.set_sku(db, p, "1234567")
    return S.verdict(db, p, "ок", None)


def test_launch_stop_start_and_no_duplicate(env):
    db, d, pubs = env
    api = FakeApi()
    # обе площадки — до запуска: запущенная держит свою цель, и площадке, добавленной позже, объёма уже не останется
    p = _approved(db, d, pubs[0])
    p2 = _approved(db, d, pubs[1])
    L.launch(db, d, p.id, client=api)
    assert p.status == M.LIVE and p.camp_id and p.tracker and api.created == 1
    sent = api.camps[p.camp_id]
    assert sent["autostart"] is True and sent["target_competitors"] == "Ксизал, Эльцет" and sent["site_id"] == 7000 + pubs[0]
    L.toggle(db, d, p.id, False, client=api)
    assert p.status == M.STOPPED and api.camps[p.camp_id]["toggle_on"] is False
    L.toggle(db, d, p.id, True, client=api)
    assert p.status == M.LIVE
    # оборванный POST: у нас статус ещё «согласовано», а РК в системе уже есть — второй не заводим
    api.create({**L.payload(db, d, p2)})                    # «первая попытка», ответ потерян
    L.launch(db, d, p2.id, client=api)
    assert api.created == 2, "повтор запуска завёл дубль"


def test_stats_snapshots_with_delta_and_fact(env):
    db, d, pubs = env
    api = FakeApi()
    p = _approved(db, d, pubs[0])
    L.launch(db, d, p.id, client=api)
    camp = db.execute(text("SELECT id FROM ad_campaign WHERE deal_id = :d ORDER BY id LIMIT 1"), {"d": d.id}).scalar()
    day = date(2026, 10, 15)
    o1 = ST.pull(db, api, [day], commit=False)
    api.updates.append("дорос")                              # день дорос при перезаборе
    o2 = ST.pull(db, api, [day], commit=False)
    snaps = db.query(M.PrioStatRaw).filter_by(camp_id=p.camp_id, day=day).order_by(M.PrioStatRaw.id).all()
    assert [s.delta_shows for s in snaps] == [None, 1] and o1["snapshots"] == o2["snapshots"] == 1
    if camp:
        f = db.execute(text("SELECT sum(shows) FROM ad_campaign_stat WHERE campaign_id = :c AND date = :d AND source = 'prio'"),
                       {"c": camp, "d": day}).scalar()
        assert f == snaps[-1].shows, "в факт — последний снимок, а не сумма снимков"


@pytest.mark.parametrize("body,want", [
    ({"ok": True, "stats": [{"camp_id": 5, "impressions": 10, "clicks": 2}]}, {5: (10, 2)}),
    ([{"camp_id": "6", "imp": 3, "clk": 1}], {6: (3, 1)}),
    ({"ok": True, "stats": [{"camp_id": 7, "search": {"imp": 4, "clk": 1}, "catalog": {"imp": 6, "clk": 0}}]}, {7: (10, 1)}),
])
def test_parse_is_tolerant(body, want):
    got = ST.parse(body)
    assert {k: (v["shows"], v["clicks"]) for k, v in got.items()} == want


def test_test_leaves_nothing_on_stand():
    """Сбор статистики коммитит (это крон) — тест обязан звать его с commit=False, иначе строки остаются на стенде (19.10)."""
    import inspect
    src = inspect.getsource(test_stats_snapshots_with_delta_and_fact)
    assert src.count("commit=False") == src.count("ST.pull(")


def test_routes_need_edit_for_writes():
    import inspect

    from app.routers import prio as R
    src = inspect.getsource(R)
    for fn in ("prio_save_common", "prio_add", "prio_remove", "prio_edit", "prio_action", "prio_bulk"):
        assert "Depends(EDIT)" in inspect.getsource(getattr(R, fn)), fn
    assert "_deal(db, deal_id, user)" in src, "область видимости сделки"


# ── раскладка цели по расчётному индексу площадки (владелец 19.10.2026: «вес учитывай по площадкам — индекс расчётный») ──
def _set_index(db, pub, value):
    db.execute(text("""INSERT INTO publisher_balance_index (publisher_id, scope, index_auto) VALUES (:p, 'web', :v)
                       ON CONFLICT (publisher_id, scope) DO UPDATE SET index_auto = EXCLUDED.index_auto"""), {"p": pub, "v": value})
    db.execute(text("DELETE FROM publisher_balance_index WHERE publisher_id = :p AND scope <> 'web'"), {"p": pub})


def test_goals_follow_index_and_sum_to_plan(env):
    db, d, pubs = env
    third = db.execute(text("SELECT id FROM sales_publishers WHERE is_active AND id <> ALL(:p) ORDER BY id LIMIT 1"), {"p": pubs}).scalar()
    for pub, idx in zip(pubs + [third], (3.0, 1.0, 0.0)):
        _set_index(db, pub, idx)
    S.save_common(db, d, {"product_name": "Т"}, _U())
    for pub in pubs + [third]:
        S.add_placement(db, d, pub, _U())
    v = S.view(db, d)
    plan = v["plan_volume"]
    goals = {x["publisher_id"]: x["goal_imp"] for x in v["placements"]}
    assert sum(goals.values()) == plan, "цели не складываются в объём МП"
    assert goals[pubs[0]] == round(plan * 3 / 4) or abs(goals[pubs[0]] - plan * 3 / 4) <= 1
    assert goals[third] == 0, "нулевой индекс — нулевая цель"
    assert {x["publisher_id"]: x["weight_pct"] for x in v["placements"]}[pubs[0]] == 75.0


def test_rejected_share_goes_to_others_launched_keep_goal(env):
    db, d, pubs = env
    _set_index(db, pubs[0], 1.0)
    _set_index(db, pubs[1], 1.0)
    S.save_common(db, d, {"product_name": "Т"}, _U())
    a = S.add_placement(db, d, pubs[0], _U())
    b = S.add_placement(db, d, pubs[1], _U())
    plan = S.view(db, d)["plan_volume"]
    for p in (a, b):
        S.edit_placement(db, d, p.id, {"erid": "E", "product_url": "https://x.example/p"})
        S.send(db, d, p.id, _U())
    S.verdict(db, b, "отказ", "нет товара")
    assert a.goal_imp == plan and b.goal_imp in (0, None), "доля отказавшей площадки не перешла"


def test_late_placement_gets_nothing_after_launch(env):
    """Запущенная держит цель: площадка, добавленная после запуска, получает остаток — здесь ноль, и отправить её нельзя."""
    db, d, pubs = env
    p = _approved(db, d, pubs[0])
    L.launch(db, d, p.id, client=FakeApi())
    late = S.add_placement(db, d, pubs[1], _U())
    assert p.goal_imp == S.view(db, d)["plan_volume"] and late.goal_imp == 0


def test_goal_is_not_edited_by_hand(env):
    db, d, pubs = env
    S.save_common(db, d, {"product_name": "Т"}, _U())
    p = S.add_placement(db, d, pubs[0], _U())
    with pytest.raises(S.PrioError):
        S.edit_placement(db, d, p.id, {"goal_imp": 5})
