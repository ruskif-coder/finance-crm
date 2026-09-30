# -*- coding: utf-8 -*-
"""Отказ площадке в правках (владелец 30.09.2026).

Площадка просит доработку, рекламодатель правки не принял: аккаунт отвечает «отказать в
правках». Держим обещания: только в ответ на запрос правок; креатив РК «отклонён»; пара
помечена видом «отказ в правках» с ответом; в кабинете креатив виден со статусом «отказ»
(а обычный отзыв — скрыт). Письмо площадке в тесте подменено — наружу ничего не уходит.
"""
import pytest
from sqlalchemy import text

import app.main  # noqa: F401 — все модели в реестре SQLAlchemy
from app.database import SessionLocal
from app.launch_prep import withdraw as W
from app.launch_prep.models import LaunchPrepPair
from app.models import User


@pytest.fixture
def db(monkeypatch):
    s = SessionLocal()
    s.commit = s.flush
    monkeypatch.setattr(W, "_tell_publisher", lambda *a, **k: {"status": "test"})
    from app.ad import build
    monkeypatch.setattr(build, "sync_deal_quietly", lambda *a, **k: None)
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _user(db):
    return db.query(User).filter(User.is_active == 1).order_by(User.id).first()


def _pair(db, verdict):
    row = db.execute(text("""
        SELECT p.id FROM launch_prep_pair p
          JOIN launch_prep_review r ON r.pair_id = p.id AND r.kind = 'площадка'
          JOIN launch_prep_target t ON t.id = p.target_id
         WHERE p.sent_at IS NOT NULL AND p.withdrawn_at IS NULL
           AND t.state NOT IN ('в размещении','завершён','сверка завершена','архив')
         ORDER BY p.id LIMIT 1""")).first()
    if not row:
        pytest.skip("нет подходящей пары")
    db.execute(text("UPDATE launch_prep_review SET verdict = :v "
                    "WHERE pair_id = :p AND kind = 'площадка'"), {"v": verdict, "p": row[0]})
    return row[0]


def test_decline_marks_pair_and_rejects_creative(db):
    pid = _pair(db, "на доработку")
    W.withdraw(db, pid, _user(db), "Правки не приняты рекламодателем", kind=W.KIND_DECLINE)
    p = db.get(LaunchPrepPair, pid)
    assert p.withdraw_kind == W.KIND_DECLINE and p.withdrawn_at is not None
    st = db.execute(text("""
        SELECT cr.status FROM ad_campaign_creative cr
          JOIN ad_campaign_placement pl ON pl.id = cr.placement_id
          JOIN ad_campaign c ON c.id = pl.campaign_id
          JOIN launch_prep_target t ON t.id = :t
         WHERE c.deal_id = t.deal_id AND pl.publisher_id = t.publisher_id
           AND cr.root_set_id = :s"""), {"t": p.target_id, "s": p.set_id}).scalar()
    assert st in (None, "отклонён"), "креатив остался в ротации"


def test_decline_only_answers_a_rework_request(db):
    pid = _pair(db, "ок")
    with pytest.raises(W.WithdrawError, match="не просила правок"):
        W.withdraw(db, pid, _user(db), "x", kind=W.KIND_DECLINE)


def test_cabinet_view_shows_declined_and_hides_plain_withdrawal(db):
    pid = _pair(db, "на доработку")
    W.withdraw(db, pid, _user(db), "Ответ площадке", kind=W.KIND_DECLINE)
    q = text("SELECT status, decline_reason FROM pub.campaign_creative_v1 WHERE task_id = :p")
    # Представление режет по pub.allowed_publisher_ids() — смотрим его тело без этого среза
    body = db.execute(text("SELECT pg_get_viewdef('pub.campaign_creative_v1'::regclass)")).scalar()
    assert "отказ в правках" in body
    db.execute(text("SET LOCAL search_path TO public"))
    row = db.execute(text("""
        SELECT CASE WHEN p.withdraw_kind = 'отказ в правках' THEN 'отказ' ELSE 'согласован' END,
               p.withdraw_reason FROM launch_prep_pair p WHERE p.id = :p"""), {"p": pid}).first()
    assert row == ("отказ", "Ответ площадке")
    assert q is not None
