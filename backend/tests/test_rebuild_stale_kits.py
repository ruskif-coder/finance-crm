# -*- coding: utf-8 -*-
"""Пересборка устаревших комплектов УПД у бухгалтерии (`scripts/rebuild_stale_kits_2026_11_06.py`, владелец 06.11.2026).

Поломки, которые ловит:
- пакет, собранный до v2.7.14 (одна УПД «еФарм» на WEB и APP), не находится — у бухгалтера одна заявка вместо двух;
- пересобирается пакет, по которому бухгалтер уже начал работу (черновик, номера 1С) — потеряли бы внесённое.
Живой пакет стенда M-0001 приводится к прод-состоянию в транзакции, транзакция откатывается."""
import pytest

import app.model_registry  # noqa: F401


@pytest.fixture
def stale():
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal, MasterDealUpd
    db = SessionLocal()
    m = db.query(MasterDeal).filter_by(code="M-0001").first()
    if m is None or not m.upd_by_service:
        db.close()
        pytest.skip("нужен M-0001 с «УПД по услугам»")
    m.status = "ждём 1С"
    kits = db.query(MasterDealUpd).filter_by(master_deal_id=m.id).all()
    annex_id = kits[0].annex_id
    for k in kits:
        db.delete(k)
    db.flush()
    db.add(MasterDealUpd(master_deal_id=m.id, upd_no=1, annex_id=annex_id, brand=None, service="еФарм",
                         net=2000000.0, vat=440000.0, gross=2440000.0))        # как записано на проде 27.10
    db.flush()
    try:
        yield db, m
    finally:
        db.rollback()
        db.close()


def test_stale_package_is_found_and_split_by_device(stale):
    db, m = stale
    from scripts import rebuild_stale_kits_2026_11_06 as S
    it = next(x for x in S.check(db) if x["m"].id == m.id)
    assert not it["blocked"]
    S.rebuild(db, it)
    from app.master_deal.models import MasterDealUpd
    got = [(k.service, round(k.gross, 2)) for k in db.query(MasterDealUpd).filter_by(master_deal_id=m.id).order_by(MasterDealUpd.upd_no)]
    assert got == [("еФарм · WEB", 2011093.75), ("еФарм · APP", 428906.25)]
    assert not any(x["m"].id == m.id for x in S.check(db)), "после пересборки расхождения нет"


def test_started_package_is_not_rebuilt(stale):
    db, m = stale
    from app.master_deal.models import MasterDealUpd
    from scripts import rebuild_stale_kits_2026_11_06 as S
    db.query(MasterDealUpd).filter_by(master_deal_id=m.id).first().onec_draft = {"invNo": "1"}
    db.flush()
    it = next(x for x in S.check(db) if x["m"].id == m.id)
    assert it["blocked"], "бухгалтер начал — только руками"
