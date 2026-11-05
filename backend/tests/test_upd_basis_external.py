# -*- coding: utf-8 -*-
"""Основание УПД у ДС, подписанного вне системы (владелец 05.11.2026): «генерим по шаблону наиболее близкому — если есть
прикреплённый к бренду — или исторически который был». Своей модели у внешнего ДС нет (его текст — чужой файл), поэтому
основание собирается по шаблону той же цепочкой, что в конструкторе: память бренда → основной договора → базовый формата.

Поломка, которую ловит: у внешнего ДС основание пустое — бухгалтеру нечего вписать в УПД (на проде 05.11: M-0011, M-0019, M-0020).
Живой пакет стенда, только чтение."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401


@pytest.fixture
def kit():
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal, MasterDealUpd
    db = SessionLocal()
    row = db.execute(text("""SELECT k.id FROM master_deal_upds k JOIN sales_annexes a ON a.id = k.annex_id
                              WHERE a.origin = 'загружен' AND k.basis_text IS NULL ORDER BY k.id LIMIT 1""")).first()
    if row is None:
        db.close()
        pytest.skip("на стенде нет внешних ДС в пакетах")
    k = db.get(MasterDealUpd, row[0])
    try:
        yield db, db.get(MasterDeal, k.master_deal_id), k
    finally:
        db.rollback()
        db.close()


def test_external_annex_kit_gets_basis_from_nearest_template(kit):
    db, m, k = kit
    from app.master_deal import to_annex as TA
    u = next(x for x in TA.upds_of(db, m) if x["upd_no"] == k.upd_no)
    assert u["basis"].strip(), "основание внешнего ДС — по шаблону, не пустое"
    from app.sales.models import SalesAnnex
    a = db.get(SalesAnnex, k.annex_id)
    assert str(a.no) in u["basis"], "в основании — номер самого внешнего ДС"
