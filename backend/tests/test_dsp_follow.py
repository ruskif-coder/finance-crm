# -*- coding: utf-8 -*-
"""Снимок и откат статусов РК при отказе DSP (аудит 13.11.2026, `app/ad/dsp_follow.py`). На настоящей РК стенда, всё в
транзакции с откатом (запись — flush, коммит подменён).

Поломки, которые ловят: откат не возвращает статус РК или площадок; откат затирает то, что после нас поменял другой."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.ad import dsp_follow as F


@pytest.fixture
def env():
    from app.database import SessionLocal
    from app.ad.models import AdCampaign, AdCampaignPlacement
    db = SessionLocal()
    db.commit = db.flush
    cid = db.execute(text("""SELECT c.id FROM ad_campaign c
                              WHERE (SELECT count(*) FROM ad_campaign_placement p WHERE p.campaign_id = c.id) >= 2
                              ORDER BY c.id DESC LIMIT 1""")).scalar()
    if cid is None:
        db.close()
        pytest.skip("на стенде нет РК с двумя площадками")
    c = db.get(AdCampaign, cid)
    pls = db.query(AdCampaignPlacement).filter_by(campaign_id=cid).order_by(AdCampaignPlacement.id).all()
    try:
        yield db, c, pls
    finally:
        db.rollback()
        db.close()


def test_restore_returns_campaign_and_placements(env):
    db, c, pls = env
    snap = F.take(db, c)
    was_c, was_p = c.status, [p.status for p in pls]
    c.status = "пауза" if c.status != "пауза" else "остановлена"
    pls[0].status = "пауза" if pls[0].status != "пауза" else "завершена"
    db.flush()
    F.mark_written(db, snap, c)
    assert F.restore(db, snap) == []
    db.refresh(c)
    for p in pls:
        db.refresh(p)
    assert c.status == was_c and [p.status for p in pls] == was_p


def test_restore_keeps_what_someone_else_changed_after_us(env):
    """Между нашим коммитом и отказом DSP другой запрос изменил площадку — откат её не трогает и называет."""
    db, c, pls = env
    snap = F.take(db, c)
    was0 = pls[0].status
    pls[0].status = "пауза" if was0 != "пауза" else "завершена"
    db.flush()
    F.mark_written(db, snap, c)
    pls[0].status = "запущен" if pls[0].status != "запущен" else "отключена"      # чужая правка после нас
    theirs = pls[0].status
    db.flush()
    skipped = F.restore(db, snap)
    db.refresh(pls[0])
    assert pls[0].status == theirs and any(f"#{pls[0].id}" in s for s in skipped), skipped


def test_refused_dsp_commits_then_restores(env, monkeypatch):
    """Порядок: наше — коммит, потом DSP; отказ DSP — откат по снимку и исключение ручки."""
    from app.dsp.client import MsError
    db, c, pls = env
    snap = F.take(db, c)
    was = c.status
    c.status = "пауза" if was != "пауза" else "остановлена"
    order = []
    monkeypatch.setattr(db, "commit", lambda: (order.append("commit"), db.flush())[1])
    # Настоящий откат транзакции здесь вернул бы всё и без снимка (коммит подменён flush) — гасим его, чтобы проверить
    # именно возврат по снимку.
    monkeypatch.setattr(db, "rollback", lambda: order.append("rollback"))

    def dsp():
        order.append("dsp")
        raise MsError("DSP: обрыв")

    with pytest.raises(RuntimeError):
        F.run(db, c, snap, dsp, lock_shares=lambda: order.append("lock"),
              on_refused=lambda e, sk: RuntimeError(f"отказ: {e}"))
    assert order[:2] == ["commit", "dsp"] and "lock" in order
    db.refresh(c)
    assert c.status == was
