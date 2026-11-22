# -*- coding: utf-8 -*-
"""Комплект закрывающих — под КАЖДУЮ услугу отдельно, и web/app одной услуги — разные услуги (владелец 28.10.2026: на проде у
Сандоза пакет M-0001 «еФарм WEB» + «еФарм APP» при «УПД по услугам» дал одну УПД «еФарм»). Площадка строки МП (`device`) — часть
услуги в разбиении; решение 30.09.2026: web и app одной услуги — разные сделки."""
from types import SimpleNamespace

from app.master_deal import layout as L


def test_surface_is_part_of_the_service():
    assert L.service_label("еФарм", "WEB") == "еФарм · WEB"
    assert L.service_label("еФарм", "APP") == "еФарм · APP"
    assert L.service_label("Медиапакет", None) == "Медиапакет"
    assert L.service_label("Медиапакет", "") == "Медиапакет"


def _row(deal, device, net):
    return {"deal_id": deal, "deal": f"D{deal}", "brand": "Бронхо-мунал", "service": L.service_label("еФарм", device), "sk_pct": 0,
            "id": f"b:{deal}:0", "kind": "base", "position": f"еФарм · {device}", "model": "CPM", "volume": 1, "unit_price": 1,
            "net": net, "src": {}}


def _layout(monkeypatch, **st):
    m = SimpleNamespace(start_no=44, period="2026-10", **{k: None for k in L.KEYS})
    rows = [_row(1, "WEB", 1648437.5), _row(2, "APP", 351562.5)]
    monkeypatch.setattr(L, "lines", lambda db, m_: rows)
    monkeypatch.setattr(L, "_vat", lambda db, m_, ls: 22.0)
    base = {"addons_mode": "together", "bonus_addons": "zero", "ds_by_brand": False, "ds_by_service": False,
            "upd_by_brand": False, "upd_by_service": False, "moved": []}
    return L.layout(None, m, {**base, **st})


def _extra(deal, net, model="CPM", unit_price=0):
    return {"deal_id": deal, "deal": f"D{deal}", "brand": "Бронхо-мунал", "service": "еФарм", "sk_pct": 0,
            "id": f"e:{deal}:0", "kind": "extra", "position": "Доп", "model": model, "volume": None,
            "unit_price": unit_price, "net": net, "src": {}}


def test_fold_keeps_price_inflates_volume_cpm(monkeypatch):
    rows = [{"deal_id": 1, "deal": "D1", "brand": "Б", "service": "еФарм", "sk_pct": 0, "id": "b:1:0",
             "kind": "base", "position": "еФарм", "model": "CPM", "volume": 1000, "unit_price": 500, "net": 500, "src": {}},
            _extra(1, 200)]
    monkeypatch.setattr(L, "lines", lambda db, m_: rows)
    monkeypatch.setattr(L, "_vat", lambda db, m_, ls: 22.0)
    lay = L.layout(None, SimpleNamespace(start_no=0, period="2026-10", **{k: None for k in L.KEYS}), {"addons_mode": "fold"})
    r = lay["ds"][0]["groups"][0]["rows"]
    assert len(r) == 1 and r[0]["kind"] == "base"
    assert r[0]["net"] == 700 and r[0]["unit_price"] == 500 and r[0]["volume"] == 1400
    assert lay["total_net"] == 700 and lay["ds"][0]["kind"] == "main"


def test_fold_cpc_volume_and_no_price_change(monkeypatch):
    rows = [{"deal_id": 1, "deal": "D1", "brand": "Б", "service": "еФарм", "sk_pct": 0, "id": "b:1:0",
             "kind": "base", "position": "еФарм", "model": "CPC", "volume": 10, "unit_price": 10, "net": 100, "src": {}},
            _extra(1, 50, model="CPC")]
    monkeypatch.setattr(L, "lines", lambda db, m_: rows)
    monkeypatch.setattr(L, "_vat", lambda db, m_, ls: 22.0)
    lay = L.layout(None, SimpleNamespace(start_no=0, period="2026-10", **{k: None for k in L.KEYS}), {"addons_mode": "fold"})
    r = lay["ds"][0]["groups"][0]["rows"][0]
    assert r["net"] == 150 and r["unit_price"] == 10 and r["volume"] == 15


def test_fold_total_invariant_two_lines(monkeypatch):
    rows = [{"deal_id": 1, "deal": "D1", "brand": "Б", "service": "еФарм", "sk_pct": 0, "id": "b:1:0",
             "kind": "base", "position": "a", "model": "CPM", "volume": 1000, "unit_price": 400, "net": 400, "src": {}},
            {"deal_id": 1, "deal": "D1", "brand": "Б", "service": "еФарм", "sk_pct": 0, "id": "b:1:1",
             "kind": "base", "position": "b", "model": "CPM", "volume": 1000, "unit_price": 100, "net": 100, "src": {}},
            _extra(1, 100)]
    monkeypatch.setattr(L, "lines", lambda db, m_: rows)
    monkeypatch.setattr(L, "_vat", lambda db, m_, ls: 22.0)
    lay = L.layout(None, SimpleNamespace(start_no=0, period="2026-10", **{k: None for k in L.KEYS}), {"addons_mode": "fold"})
    nets = [r["net"] for r in lay["ds"][0]["groups"][0]["rows"]]
    vols = [r["volume"] for r in lay["ds"][0]["groups"][0]["rows"]]
    assert nets == [480, 120] and vols == [1200, 1200] and lay["total_net"] == 600


def test_fold_sk_addon_not_discounted(monkeypatch):
    rows = [{"deal_id": 1, "deal": "D1", "brand": "Б", "service": "еФарм", "sk_pct": 20, "id": "b:1:0",
             "kind": "base", "position": "еФарм", "model": "CPM", "volume": 1000, "unit_price": 400, "net": 400, "src": {}},
            _extra(1, 64)]
    monkeypatch.setattr(L, "lines", lambda db, m_: rows)
    monkeypatch.setattr(L, "_vat", lambda db, m_, ls: 22.0)
    lay = L.layout(None, SimpleNamespace(start_no=0, period="2026-10", **{k: None for k in L.KEYS}), {"addons_mode": "fold"})
    r = lay["ds"][0]["groups"][0]["rows"][0]
    assert r["net"] == 384 and r["unit_price"] == 320 and r["volume"] == 1200


def test_fold_blocked_on_fix_base(monkeypatch):
    rows = [{"deal_id": 1, "deal": "D1", "brand": "Б", "service": "еФарм", "sk_pct": 0, "id": "b:1:0",
             "kind": "base", "position": "еФарм", "model": "Fix", "volume": 1, "unit_price": 400, "net": 400, "src": {}},
            _extra(1, 100, model="Fix")]
    monkeypatch.setattr(L, "lines", lambda db, m_: rows)
    monkeypatch.setattr(L, "_vat", lambda db, m_, ls: 22.0)
    lay = L.layout(None, SimpleNamespace(start_no=0, period="2026-10", **{k: None for k in L.KEYS}), {"addons_mode": "fold"})
    assert lay["addons_fold"]["ok"] is False and "Fix" in lay["addons_fold"]["reason"]


def test_fold_drops_extra_rows(monkeypatch):
    rows = [{"deal_id": 1, "deal": "D1", "brand": "Б", "service": "еФарм", "sk_pct": 0, "id": "b:1:0",
             "kind": "base", "position": "еФарм", "model": "CPM", "volume": 1000, "unit_price": 500, "net": 500, "src": {}},
            _extra(1, 200),
            {"deal_id": 1, "deal": "D1", "brand": "Б", "service": "еФарм", "sk_pct": 0, "id": "bonus:1:0",
             "kind": "bonus", "position": "Бонус", "model": "CPM", "volume": None, "unit_price": None, "net": 0, "src": {}}]
    monkeypatch.setattr(L, "lines", lambda db, m_: rows)
    monkeypatch.setattr(L, "_vat", lambda db, m_, ls: 22.0)
    lay = L.layout(None, SimpleNamespace(start_no=0, period="2026-10", **{k: None for k in L.KEYS}), {"addons_mode": "fold"})
    kinds = [r["kind"] for r in lay["ds"][0]["groups"][0]["rows"]]
    assert "extra" not in kinds and "bonus" in kinds


def test_upd_by_service_splits_web_and_app(monkeypatch):
    lay = _layout(monkeypatch, upd_by_service=True)
    kits = lay["ds"][0]["upds"]
    assert sorted(k["service"] for k in kits) == ["еФарм · APP", "еФарм · WEB"]
    assert lay["upd_count"] == 2


def test_ds_by_service_splits_groups_and_no_split_keeps_one_kit(monkeypatch):
    assert len(_layout(monkeypatch, ds_by_service=True)["ds"][0]["groups"]) == 2
    assert _layout(monkeypatch)["upd_count"] == 1
