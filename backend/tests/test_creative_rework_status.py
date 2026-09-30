# -*- coding: utf-8 -*-
"""Креатив, возвращённый на переделку, — «отклонён», а не «у трафика» (30.09.2026).

Случай с прода: 20 креативов (AFKJMM, DLMBGB, YRPB7W) стояли на дашборде трафика
«у трафика», хотя трафик уже вынес «на переделку» и в конвейере их, правильно, не было.
Синк креативов понимал только вердикт «ок», любой другой читал как «ещё не ответили».
Мяч после переделки у аккаунта: новый комплект даст новый креатив, а этот не крутится.
"""
import pytest
from sqlalchemy import text

import app.main  # noqa: F401 — все модели в реестре SQLAlchemy
from app.ad import build
from app.ad.models import AdCampaign, AdCampaignCreative
from app.database import SessionLocal


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _rework_creative(db, kind):
    row = db.execute(text("""
        SELECT cr.id, cr.campaign_id FROM ad_campaign_creative cr
          JOIN launch_prep_pair pr ON pr.id = cr.pair_id
          JOIN launch_prep_review rv ON rv.pair_id = pr.id AND rv.kind = :k
          JOIN launch_prep_target t ON t.id = pr.target_id
         WHERE rv.verdict IS NOT NULL AND rv.verdict <> 'ок'
           AND cr.status NOT IN ('запущен', 'пауза') AND pr.withdrawn_at IS NULL
           -- без комплекта-замены: иначе «отклонён» дала бы уже старая ветка «заменён»
           AND NOT EXISTS (SELECT 1 FROM launch_prep_creative_set n
                            WHERE n.replaces_set_id = pr.set_id AND n.publisher_id = t.publisher_id)
         LIMIT 1"""), {"k": kind}).first()
    return row


def _pick_any_pair_creative(db):
    row = db.execute(text("""
        SELECT cr.id, cr.campaign_id, cr.pair_id FROM ad_campaign_creative cr
          JOIN launch_prep_review rv ON rv.pair_id = cr.pair_id AND rv.kind = 'трафики'
         WHERE cr.status NOT IN ('запущен', 'пауза') LIMIT 1""")).first()
    if not row:
        pytest.skip("нет креатива с проверкой трафика")
    return row


@pytest.mark.parametrize("kind", ["трафики", "площадка"])
def test_rework_verdict_makes_creative_rejected(db, kind):
    row = _rework_creative(db, kind)
    if not row:
        cid, camp_id, pair_id = _pick_any_pair_creative(db)
        db.execute(text("UPDATE launch_prep_review SET verdict = 'ок' WHERE pair_id = :p"),
                   {"p": pair_id})
        db.execute(text("""UPDATE launch_prep_review SET verdict = 'на переделку'
                            WHERE pair_id = :p AND kind = :k"""), {"p": pair_id, "k": kind})
        if kind == "площадка" and not db.execute(text(
                "SELECT 1 FROM launch_prep_review WHERE pair_id = :p AND kind = 'площадка'"),
                {"p": pair_id}).first():
            pytest.skip("у пары нет строки площадки")
    else:
        cid, camp_id = row
    db.execute(text("UPDATE ad_campaign_creative SET status = 'у трафика' WHERE id = :c"), {"c": cid})
    build.sync_creatives(db, db.query(AdCampaign).get(camp_id), commit=False)
    db.flush()
    assert db.query(AdCampaignCreative).get(cid).status == "отклонён"
