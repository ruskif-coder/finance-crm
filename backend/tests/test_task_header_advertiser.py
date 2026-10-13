# -*- coding: utf-8 -*-
"""Шапка «Задач РК» в кабинете трафика: юр. лицо и ИНН по изначальному договору (владелец 13.10.2026).

Один расчёт на рекламную метку креатива и на шапку окна — `app/ord/advertiser_label.py`: метка в
DSP и то, что читает трафик, обязаны говорить то же, что ЕРИР.
"""
import pytest

from app.ord import advertiser_label as AL


@pytest.fixture()
def db():
    import app.main  # noqa: F401
    from app.database import SessionLocal
    s = SessionLocal()
    yield s
    s.close()


def _deal_with_contract(db):
    from app.ord.models import OrdInitialContract
    from app.sales.models import SalesDeal
    d = (db.query(SalesDeal).join(OrdInitialContract, OrdInitialContract.id == SalesDeal.ord_initial_contract_id)
         .filter(OrdInitialContract.advertiser_inn.isnot(None), OrdInitialContract.advertiser_name.isnot(None))
         .first())
    if d is None:
        pytest.skip("на стенде нет сделки с изначальным договором ОРД")
    return d


def test_label_comes_from_initial_contract(db):
    from app.ord.models import OrdInitialContract
    d = _deal_with_contract(db)
    ic = db.get(OrdInitialContract, d.ord_initial_contract_id)
    inn, name = AL.advertiser_label(db, d.id)
    assert inn == "".join(ch for ch in ic.advertiser_inn if ch.isdigit()) and name == ic.advertiser_name.strip()


def test_label_is_none_without_a_contract(db):
    assert AL.advertiser_label(db, -1) is None


def test_dsp_and_the_task_header_use_the_same_function():
    from app.dsp import provision
    assert provision.ad_label is AL.advertiser_label


def test_campaign_payload_carries_the_label(db):
    from types import SimpleNamespace
    from app.ad.models import AdCampaign
    from app.routers import traffic_dashboard as td
    d = _deal_with_contract(db)
    camp = db.query(AdCampaign).filter(AdCampaign.deal_id == d.id).first()
    if camp is None:
        pytest.skip("у сделки с договором нет РК на стенде")
    admin = SimpleNamespace(role=SimpleNamespace(key="admin"), id=None, name="тест")
    out = td.campaign(camp.id, db, admin)
    inn, name = AL.advertiser_label(db, d.id)
    assert out["advertiser_label"] == {"name": name, "inn": inn}
