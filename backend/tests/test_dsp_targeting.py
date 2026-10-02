"""Таргетинги DSP: тела запросов сверены с каталогами боевого кабинета (чтение 28.09.2026).

Главная ловушка — соцдем: в документе «таргеты симбад» нумерация возрастов сдвинута на
один (`age2` там 25–30), а в кабинете `age2` — 18–24. Взять ключи из документа значило бы
показывать рекламу 18–50 вместо 25–55, молча.
"""
from app.dsp import targeting as tg


def test_socdem_25_55_is_age3_to_age8_by_cabinet_catalog():
    assert tg.socdem_keys(25, 55) == ["man", "woman", "age3", "age4", "age5", "age6", "age7", "age8"]
    items = tg.socdem_items()
    assert "age2" not in items and "age9" not in items
    assert items["age3"] == {"is_checked": True, "bid_rate": 1}


def test_frequency_from_media_plan():
    assert tg.frequency_keys(4) == ["1", "2", "3", "4"]
    assert tg.frequency_keys(None) == ["1", "2", "3", "4", "5"], "пусто — по умолчанию 5"
    assert tg.frequency_keys("") == ["1", "2", "3", "4", "5"]
    # Больше пяти — ещё 6–10 (владелец 28.09.2026), и не дальше.
    assert tg.frequency_keys(8) == ["1", "2", "3", "4", "5", "6p"]
    assert tg.frequency_keys(25) == ["1", "2", "3", "4", "5", "6p"]


def test_audience_from_media_plan():
    assert tg.parse_audience(["Ж/М 30–60"]) == {"age_from": 30, "age_to": 60,
                                                "sexes": ("man", "woman")}
    a = tg.parse_audience(["Ж 25-45"])
    assert a["sexes"] == ("woman",) and (a["age_from"], a["age_to"]) == (25, 45)
    assert tg.parse_audience(["М 18+"])["age_to"] == 200
    assert tg.parse_audience(["до 45"])["sexes"] == ("man", "woman"), "пол не упомянут — оба"
    assert tg.parse_audience(["медицина и здоровье"]) is None, "не разобралось — умолчание"
    assert tg.parse_audience(None) is None
    # «30–60» по середине группы: 25–30 не входит, 56–60 входит, 60+ нет.
    assert tg.socdem_keys(30, 60) == ["man", "woman", "age4", "age5", "age6", "age7", "age8", "age9"]


def test_geo_default_is_russia_plus_crimea():
    assert tg.geo_items() == {
        "2017370": {"is_checked": True, "bid_rate": 1, "name": "Россия"},
        "68681200": {"is_checked": True, "bid_rate": 1, "name": "Республика Крым"},
    }


def test_source_carries_bid_rate_1_and_bid_start():
    """Правка DSP 02.10.2026: без `bid_rate` DSP читает его как 0 — источник отдаёт
    `bid_rate: 1`, как все остальные таргетинги, а ставку по-прежнему в `bid_start`."""
    assert tg.source_items(["x-simb-web", "xoalt_simb", "x-simb-web"], 100) == {
        "x-simb-web": {"is_checked": True, "bid_rate": 1, "bid_start": 100},
        "xoalt_simb": {"is_checked": True, "bid_rate": 1, "bid_start": 100},
    }


def test_placement_whitelist_and_body_shape():
    body = tg.data(tg.placement_items(["36783", " 37406 ", ""]))
    assert body == {"is_invert_mode": False, "items": {
        "36783": {"is_checked": True, "bid_rate": 1},
        "37406": {"is_checked": True, "bid_rate": 1}}}


def test_apply_sets_campaign_and_only_hashed_creatives():
    calls = []

    class C:
        def targeting_set(self, xx, key, items, invert):
            calls.append((xx, key))

    plan = {"campaign": {"source": tg.data({"x": {}}), "geo_id": tg.data({})},
            "creatives": {1: {"placement": tg.data({"b": {}})},
                          2: {"placement": tg.data({"c": {}})}}}
    out = tg.apply(C(), plan, "CAMP", {1: "CR1"})
    assert ("CAMP", "source") in calls and ("CAMP", "geo_id") in calls
    assert ("CR1", "placement") in calls
    assert all(xx != "CR2" for xx, _ in calls), "креатив без хеша таргетировать нечем"
    assert not out["failed"]


def test_apply_one_failure_does_not_stop_the_rest():
    from app.dsp.client import MsError

    class C:
        def targeting_set(self, xx, key, items, invert):
            if key == "geo_id":
                raise MsError("отказ")

    plan = {"campaign": {"source": tg.data({}), "geo_id": tg.data({}), "socdem": tg.data({})},
            "creatives": {}}
    out = tg.apply(C(), plan, "CAMP", {})
    assert len(out["done"]) == 2 and out["failed"][0]["what"] == "кампания: geo_id"


def test_plan_on_stand_data():
    """На данных стенда: план собирается, креатив без блоков называется, а не теряется."""
    import app.main  # noqa: F401
    from app.ad.models import AdCampaign
    from app.database import SessionLocal
    from app.dsp.provision import _rows
    db = SessionLocal()
    try:
        camp = db.query(AdCampaign).order_by(AdCampaign.id).first()
        if camp is None:
            import pytest
            pytest.skip("на стенде нет РК")
        p = tg.plan_for(db, camp, _rows(db, camp))
        assert set(p["campaign"]) == {"source", "geo_id", "uniq_show_creative", "socdem"}
        s = p["summary"]
        assert s["creatives_with_blocks"] + len(s["creatives_without_blocks"]) == len(_rows(db, camp))
        assert p["enabled"] in (True, False)
    finally:
        db.close()
