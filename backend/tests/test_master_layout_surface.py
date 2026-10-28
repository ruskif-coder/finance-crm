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
    base = {"addons_separate": False, "bonus_addons": "zero", "ds_by_brand": False, "ds_by_service": False,
            "upd_by_brand": False, "upd_by_service": False, "moved": []}
    return L.layout(None, m, {**base, **st})


def test_upd_by_service_splits_web_and_app(monkeypatch):
    lay = _layout(monkeypatch, upd_by_service=True)
    kits = lay["ds"][0]["upds"]
    assert sorted(k["service"] for k in kits) == ["еФарм · APP", "еФарм · WEB"]
    assert lay["upd_count"] == 2


def test_ds_by_service_splits_groups_and_no_split_keeps_one_kit(monkeypatch):
    assert len(_layout(monkeypatch, ds_by_service=True)["ds"][0]["groups"]) == 2
    assert _layout(monkeypatch)["upd_count"] == 1
