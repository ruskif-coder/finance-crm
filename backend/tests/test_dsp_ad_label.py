"""`self_inn` / `self_name` креатива — рекламная метка (владелец 28.09.2026: слать всегда).

У боевого клиента DSP включена самостоятельная маркировка, и без этих полей кабинет
отказывает КАЖДОМУ креативу (28.09.2026, DLMBGB — все восемь). Данные — из изначального
договора ОРД сделки: с ним маркер зарегистрирован в ЕРИР, метка обязана говорить то же.
"""
from types import SimpleNamespace

import pytest

from app.dsp import creatives as cr
from app.dsp import provision as prov


def test_params_carry_inn_and_name():
    p = cr.build_creative_params(title="t", link="https://a.ru/", erid="E",
                                 self_inn="7700000000", self_name="ООО Тест")
    assert p["self_inn"] == "7700000000" and p["self_name"] == "ООО Тест"


def test_no_initial_contract_refuses_before_any_dsp_call(monkeypatch):
    """Без договора — отказ ДО кампании и загрузок: иначе в кабинете остались бы пустые
    кампания и архивы, а все креативы получили бы отказ."""
    calls = []
    monkeypatch.setattr(prov, "ad_label", lambda db, deal_id: None)
    monkeypatch.setattr(prov, "pixel_setup",
                        lambda db, deal_id: {"needed": False, "mode": None, "tag": None})
    row = {"creative": SimpleNamespace(id=1, ms_creative_xxhash=None, erid="E", ms_title="t"),
           "placement": SimpleNamespace(id=1, weborama_pixel=None, is_direct=False,
                                        status="готова к запуску", publisher_id=1),
           "publisher": SimpleNamespace(domain="a.ru", name="a", our_code=True),
           "file": SimpleNamespace(is_archive=True, original_name="a.zip", path="x"),
           "target": SimpleNamespace(advertiser_url="https://a.ru/")}
    monkeypatch.setattr(prov, "_rows", lambda db, camp: [row])
    monkeypatch.setattr(prov, "_blocker", lambda *a, **k: None)
    monkeypatch.setattr(prov, "ensure_campaign", lambda *a, **k: calls.append("campaign"))
    with pytest.raises(prov.DspProvisionError) as e:
        prov._provision(SimpleNamespace(), SimpleNamespace(id=1, deal_id=1, ms_campaign_xxhash=None),
                        SimpleNamespace())
    assert "договор ОРД" in str(e.value)
    assert calls == [], "кампания заведена, хотя креативы заведомо получат отказ"


def test_label_is_read_from_initial_contract():
    """На данных стенда: у сделки с изначальным договором метка берётся из него."""
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.ord.models import OrdInitialContract
    from app.sales.models import SalesDeal
    db = SessionLocal()
    try:
        d = (db.query(SalesDeal).join(OrdInitialContract,
                                      OrdInitialContract.id == SalesDeal.ord_initial_contract_id)
             .filter(OrdInitialContract.advertiser_inn.isnot(None),
                     OrdInitialContract.advertiser_name.isnot(None)).first())
        if d is None:
            pytest.skip("на стенде нет сделки с изначальным договором ОРД")
        ic = db.get(OrdInitialContract, d.ord_initial_contract_id)
        inn, name = prov.ad_label(db, d.id)
        assert inn == "".join(ch for ch in ic.advertiser_inn if ch.isdigit())
        assert name == ic.advertiser_name.strip()
        assert prov.ad_label(db, -1) is None
    finally:
        db.close()


def test_cyrillic_landing_gets_our_site_as_adomain():
    """DSP не принимает домен .рф в `adomain` ни в какой записи (демо 28.09.2026, восемь
    вариантов) — тогда `adomain` наш сайт; ссылка перехода остаётся посадочной целиком."""
    assert cr.landing_domain("https://009.xn--p1ai/search/x?region=false") == "https://simb-ad.com/"
    assert cr.landing_domain("https://120на80.рф/catalog") == "https://simb-ad.com/"
    assert cr.landing_domain("https://farmakopeika.ru/tovar/1") == "https://farmakopeika.ru/"
    assert cr.landing_domain("not a url") is None
