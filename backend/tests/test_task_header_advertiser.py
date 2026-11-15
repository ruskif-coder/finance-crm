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
    # 15.11.2026: тест может завести свою РК — всё, что он пишет, живёт в этой транзакции и откатывается; коммит,
    # если его сделает код под тестом, превращается во flush, чтобы синтетическая РК не осела на стенде.
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _deal_with_contract(db):
    from app.ord.models import OrdInitialContract
    from app.sales.models import SalesDeal
    d = (db.query(SalesDeal).join(OrdInitialContract, OrdInitialContract.id == SalesDeal.ord_initial_contract_id)
         .filter(OrdInitialContract.advertiser_inn.isnot(None), OrdInitialContract.advertiser_name.isnot(None))
         .order_by(SalesDeal.id).first())
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
    from app.ord.models import OrdInitialContract
    from app.sales.models import SalesDeal
    # 15.11.2026: РК тест берёт у сделки с изначальным договором, у которой она есть (порядок явный), а нет такой —
    # заводит пустую РК первой такой сделке в транзакции фикстуры (откат). Раньше брал первую сделку с договором без
    # сортировки, у неё РК не было — тест пропускался всегда. Упадёт, если окно РК в кабинете трафика перестанет
    # отдавать `advertiser_label` или начнёт считать его не той функцией, что метка креатива в DSP.
    with_contract = (db.query(SalesDeal)
                     .join(OrdInitialContract, OrdInitialContract.id == SalesDeal.ord_initial_contract_id)
                     .filter(OrdInitialContract.advertiser_inn.isnot(None), OrdInitialContract.advertiser_name.isnot(None)))
    d = with_contract.join(AdCampaign, AdCampaign.deal_id == SalesDeal.id).order_by(SalesDeal.id).first()
    if d is None:
        d = _deal_with_contract(db)
        db.add(AdCampaign(deal_id=d.id, status="ожидает сборки"))
        db.flush()
    camp = db.query(AdCampaign).filter(AdCampaign.deal_id == d.id).first()
    admin = SimpleNamespace(role=SimpleNamespace(key="admin"), id=None, name="тест")
    out = td.campaign(camp.id, db, admin)
    inn, name = AL.advertiser_label(db, d.id)
    assert out["advertiser_label"] == {"name": name, "inn": inn}
