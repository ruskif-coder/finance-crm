# -*- coding: utf-8 -*-
"""Пиксель Weborama — только после ЕРИД (владелец 30.09.2026).

Случай с прода: 54ZYCH / Максавит — пиксель выдан в 10:44, ЕРИД выпущен автоматикой в
11:00; по журналу так же ещё 8 размещений в 5 сделках. Вставка в их кабинете не удаляется,
поэтому запирать надо ДО вызова: размещение без согласованного креатива с ЕРИД в заведение
не идёт.
"""
import pytest
from sqlalchemy import text

import app.main  # noqa: F401 — все модели в реестре SQLAlchemy
from app.database import SessionLocal
from app.weborama import provision as prov


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _placement_with_erid(db):
    row = db.execute(text("""
        SELECT cr.placement_id, cr.id FROM ad_campaign_creative cr
         WHERE cr.erid IS NOT NULL AND cr.status = ANY(:ok)
           AND NOT EXISTS (SELECT 1 FROM ad_campaign_creative o
                            WHERE o.placement_id = cr.placement_id AND o.id <> cr.id)
         LIMIT 1"""), {"ok": list(prov.ERID_CREATIVE_OK)}).first()
    if not row:
        pytest.skip("нет размещения с единственным согласованным креативом с ЕРИД")
    return row


def test_placement_with_agreed_erid_creative_is_ready(db):
    pid, _ = _placement_with_erid(db)
    assert pid in prov.erid_ready(db, [pid])


def test_placement_without_erid_is_not_ready(db):
    pid, cid = _placement_with_erid(db)
    db.execute(text("UPDATE ad_campaign_creative SET erid = NULL WHERE id = :c"), {"c": cid})
    assert pid not in prov.erid_ready(db, [pid]), "пиксель без ЕРИД — так быть не должно"


def test_erid_on_unagreed_creative_does_not_count(db):
    pid, cid = _placement_with_erid(db)
    db.execute(text("UPDATE ad_campaign_creative SET status = 'у площадки' WHERE id = :c"), {"c": cid})
    assert pid not in prov.erid_ready(db, [pid])
