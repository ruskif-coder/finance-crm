# -*- coding: utf-8 -*-
"""ЕРИД — свойство комплекта (владелец 30.09.2026): площадка, согласовавшая комплект, у
которого ЕРИД уже есть, сразу «ерид получен». До правки отметку ставил только сам выпуск
ЕРИД — тем, кто согласовал ДО него; на проде так застряли 68 получателей в 9 сделках.
"""
import pytest
from sqlalchemy import text

import app.main  # noqa: F401 — все модели в реестре SQLAlchemy
from app.database import SessionLocal
from app.launch_prep.models import LaunchPrepTarget
from app.routers import launch_prep as lp


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _target_agreed_on_erid_set(db):
    row = db.execute(text("""
        SELECT t.id FROM launch_prep_target t
          JOIN launch_prep_pair pr ON pr.target_id = t.id
          JOIN launch_prep_creative_set s ON s.id = pr.set_id
         WHERE pr.agreed_at IS NOT NULL AND pr.withdrawn_at IS NULL AND s.erid IS NOT NULL
         LIMIT 1""")).first()
    if not row:
        pytest.skip("нет получателя, согласовавшего комплект с ЕРИД")
    return db.query(LaunchPrepTarget).get(row[0])


def test_agree_on_set_with_erid_gives_erid_state(db):
    t = _target_agreed_on_erid_set(db)
    t.state = "согласование"
    lp._recompute_target_state(db, t)
    assert t.state == "ерид получен"


def test_agree_without_erid_stays_agreed(db):
    t = _target_agreed_on_erid_set(db)
    db.execute(text("""UPDATE launch_prep_creative_set SET erid = NULL WHERE id IN (
                         SELECT set_id FROM launch_prep_pair WHERE target_id = :t)"""), {"t": t.id})
    t.state = "согласование"
    lp._recompute_target_state(db, t)
    assert t.state == "согласован"
