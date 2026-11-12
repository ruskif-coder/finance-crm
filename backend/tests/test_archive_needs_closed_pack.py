# -*- coding: utf-8 -*-
"""В «Архив успешных сделок» руками — только с закрытым пакетом (владелец 12.11.2026: «вообще не давать по всей системе уходить
в терминальную стадию без сканов»; для ЭДО достаточно отметки подписи; правило для всех сделок, в том числе заведённых задним
числом; бонусное «Закрыть без документов» — исключение, оно идёт своей ручкой мимо ручного перевода).

Поломки: сделка без пакета или с неподписанным пакетом уходит в архив руками; пакет в «архиве» не пускает свою сделку."""
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.sales import stage_move as SM
from app.sales.catalog import Catalog

ACC = SimpleNamespace(role=SimpleNamespace(key="account", is_master=False))


@pytest.fixture
def env():
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal
    from app.sales.models import SalesDeal
    db = SessionLocal()
    row = db.execute(text("""SELECT i.deal_id, i.master_deal_id FROM master_deal_items i JOIN master_deals m ON m.id = i.master_deal_id
                              WHERE m.status <> 'архив' ORDER BY i.id DESC LIMIT 1""")).first()
    if row is None:
        db.close()
        pytest.skip("на стенде нет сделки в пакете")
    cat = Catalog(db)
    arch = next(s for s in cat.by_id.values() if s.name == "Архив успешных сделок")
    pay = next(s for s in cat.by_id.values() if s.name == "Оплата")
    d = db.get(SalesDeal, row[0])
    d.our_stage_id = pay.id
    db.flush()
    try:
        yield db, cat, arch, d, db.get(MasterDeal, row[1])
    finally:
        db.rollback()
        db.close()


def test_open_pack_blocks_manual_archive(env):
    db, cat, arch, d, m = env
    g = SM.manual_guard(db, d, arch, ACC, cat)
    assert g and m.code in g


def test_closed_pack_lets_the_deal_into_archive(env):
    db, cat, arch, d, m = env
    m.status = "архив"
    db.flush()
    assert SM.manual_guard(db, d, arch, ACC, cat) is None


def test_deal_without_pack_cannot_go_to_archive_by_hand(env):
    db, cat, arch, d, m = env
    db.execute(text("DELETE FROM master_deal_items WHERE deal_id = :d"), {"d": d.id})
    db.flush()
    g = SM.manual_guard(db, d, arch, ACC, cat)
    assert g and "мастер-сделк" in g
