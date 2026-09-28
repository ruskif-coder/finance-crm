# -*- coding: utf-8 -*-
"""Жизненный цикл уведомлений: гашение, срок жизни, крестик (владелец 27.09.2026).

Удаление необратимо, поэтому приборы держат именно границы: что уходит по сроку, а что
остаётся (непрочитанное младше 90 дней, очередь дайджеста), и что задача гаснет только
когда работа сделана.
"""
import time
from datetime import datetime, timedelta

import pytest

import app.main  # noqa: F401 — все модели в реестре SQLAlchemy, иначе FK сделки не находят таблиц

from app.database import SessionLocal
from app.launch_prep.models import LaunchPrepCreativeSet, LaunchPrepReview
from app.models import Notification, User
from app.notify import lifecycle
from app.notify.models import NotificationAlertState, NotificationDelivery
from app.sales.models import SalesDeal, SalesStage

NOW = datetime(2026, 10, 1, 12, 0)


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def uid(db):
    return db.query(User.id).order_by(User.id).first()[0]


def _deal(db, stage_id=None):
    n = time.time_ns()
    d = SalesDeal(bitrix_id=f"notif-life-{n}", code=format(n % 36 ** 6, "X")[-6:].rjust(6, "Z"),
                  title="Пзкт уведомления", our_stage_id=stage_id)
    db.add(d)
    db.flush()
    return d


def _note(db, uid, kind="deal_booked", **kw):
    n = Notification(user_id=uid, kind=kind, title="тест жизненного цикла", **kw)
    db.add(n)
    db.flush()
    return n


def _alive(db, nid):
    """По id, а не по объекту: удалённая строка после expire_all не читается вовсе."""
    db.expire_all()
    return db.query(Notification.id).filter(Notification.id == nid).first() is not None


# ── срок жизни ──────────────────────────────────────────────────────────────────

def test_purge_edges(db, uid):
    read_old = _note(db, uid, is_read=True, created_at=NOW - timedelta(days=31))
    read_new = _note(db, uid, is_read=True, created_at=NOW - timedelta(days=29))
    unread_60 = _note(db, uid, is_read=False, created_at=NOW - timedelta(days=60))
    unread_91 = _note(db, uid, is_read=False, created_at=NOW - timedelta(days=91))
    resolved_old = _note(db, uid, created_at=NOW - timedelta(days=5),
                         resolved_at=NOW - timedelta(days=31))
    resolved_new = _note(db, uid, created_at=NOW - timedelta(days=90),
                         resolved_at=NOW - timedelta(days=2))
    ids = {k: v.id for k, v in dict(read_old=read_old, read_new=read_new, unread_60=unread_60,
                                    unread_91=unread_91, resolved_old=resolved_old,
                                    resolved_new=resolved_new).items()}
    lifecycle.purge(db, NOW)
    assert not _alive(db, ids["read_old"])
    assert _alive(db, ids["read_new"])
    assert _alive(db, ids["unread_60"]), "непрочитанное младше 90 дней удалено"
    assert not _alive(db, ids["unread_91"])
    assert not _alive(db, ids["resolved_old"])
    assert _alive(db, ids["resolved_new"]), "погашенное вчера удалено по дате создания"


def test_purge_keeps_digest_queue(db, uid):
    old = NOW - timedelta(days=200)
    sent = NotificationDelivery(event_key="deal_booked", user_id=uid, channel="mail",
                                status="sent", created_at=old)
    queued = NotificationDelivery(event_key="deal_booked", user_id=uid, channel="digest",
                                  status="queued", created_at=old)
    db.add_all([sent, queued])
    db.flush()
    sent_id, queued_id = sent.id, queued.id
    lifecycle.purge(db, NOW)
    db.expire_all()
    ids = {i for (i,) in db.query(NotificationDelivery.id)
           .filter(NotificationDelivery.id.in_([sent_id, queued_id])).all()}
    assert ids == {queued_id}, "очередь дайджеста удалена или журнал не почищен"


def test_dry_run_deletes_nothing(db, uid):
    n = _note(db, uid, is_read=True, created_at=NOW - timedelta(days=100))
    out = lifecycle.purge(db, NOW, dry_run=True)
    assert out["notifications"] >= 1
    assert _alive(db, n.id)


# ── задачи гаснут, когда работа сделана ─────────────────────────────────────────

def _set(db, deal, no=1, sent_at=None):
    s = LaunchPrepCreativeSet(deal_id=deal.id, no=9000 + no, erid_source="наш", sent_at=sent_at)
    db.add(s)
    db.flush()
    return s


def test_new_work_lives_while_traffic_has_not_answered(db, uid):
    d = _deal(db)
    s = _set(db, d)
    r = LaunchPrepReview(set_id=s.id, kind="трафики", source="трафики")
    db.add(r)
    n = _note(db, uid, kind="traffic_new_work", entity_type="sales_deal", entity_id=d.id)
    lifecycle.resolve_actions(db, NOW)
    assert n.resolved_at is None, "погасло, хотя трафик не ответил"
    r.verdict, r.decided_at = "ок", NOW
    db.flush()
    lifecycle.resolve_actions(db, NOW)
    assert n.resolved_at == NOW


def test_rework_lives_until_a_new_set_is_sent(db, uid):
    d = _deal(db)
    old = _set(db, d, 1, sent_at=NOW - timedelta(days=3))
    db.add(LaunchPrepReview(set_id=old.id, kind="трафики", source="трафики",
                            verdict="на переделку", decided_at=NOW - timedelta(days=2)))
    n = _note(db, uid, kind="traffic_rework", entity_type="sales_deal", entity_id=d.id)
    lifecycle.resolve_actions(db, NOW)
    assert n.resolved_at is None, "погасло без нового комплекта"
    _set(db, d, 2, sent_at=NOW - timedelta(days=1))
    lifecycle.resolve_actions(db, NOW)
    assert n.resolved_at == NOW


def test_closed_deal_resolves_task(db, uid):
    term = db.query(SalesStage.id).filter(SalesStage.is_terminal.is_(True)).first()[0]
    d = _deal(db, stage_id=term)
    s = _set(db, d)
    db.add(LaunchPrepReview(set_id=s.id, kind="трафики", source="трафики"))
    n = _note(db, uid, kind="traffic_new_work", entity_type="sales_deal", entity_id=d.id)
    lifecycle.resolve_actions(db, NOW)
    assert n.resolved_at == NOW, "задача по закрытой сделке висит"


def test_pixel_task_resolves_when_pixel_turned_off(db, uid):
    d = _deal(db)
    d.weborama_pixel = True
    db.flush()
    n = _note(db, uid, kind="weborama_pixel_needed", entity_type="deal", entity_id=d.id)
    lifecycle.resolve_actions(db, NOW)
    assert n.resolved_at is None, "погасло, хотя пикселя нет"
    d.weborama_pixel = False
    db.flush()
    lifecycle.resolve_actions(db, NOW)
    assert n.resolved_at == NOW


def test_fact_notifications_are_not_resolved(db, uid):
    d = _deal(db)
    n = _note(db, uid, kind="deal_booked", entity_type="sales_deal", entity_id=d.id)
    lifecycle.resolve_actions(db, NOW)
    assert n.resolved_at is None
    assert "deal_booked" not in lifecycle.ACTION_RESOLVERS


# ── строки сканера до схлопывания ────────────────────────────────────────────────

def test_legacy_scan_rows(db, uid):
    d1, d2, d3 = _deal(db), _deal(db), _deal(db)
    gone = _note(db, uid, kind="stage_stuck", entity_type="sales_deal", entity_id=d1.id)
    keyed = _note(db, uid, kind="stage_stuck", entity_type="sales_deal", entity_id=d2.id)
    db.add(NotificationAlertState(event_key="stage_stuck", entity_type="sales_deal",
                                  entity_id=d2.id, stage="overdue"))
    dup_old = _note(db, uid, kind="stage_stuck", entity_type="sales_deal", entity_id=d3.id)
    _note(db, uid, kind="stage_stuck", entity_type="sales_deal", entity_id=d3.id,
          dedup_key=f"stage_stuck:sales_deal:{d3.id}")
    db.add(NotificationAlertState(event_key="stage_stuck", entity_type="sales_deal",
                                  entity_id=d3.id, stage="overdue"))
    db.flush()
    lifecycle.resolve_legacy_scan_rows(db, NOW)
    assert gone.resolved_at == NOW, "причина снята, строка висит"
    assert keyed.resolved_at is None and keyed.dedup_key == f"stage_stuck:sales_deal:{d2.id}"
    assert dup_old.resolved_at == NOW, "две строки об одном"


def test_legacy_ignores_non_scan_events(db, uid):
    d = _deal(db)
    n = _note(db, uid, kind="deal_booked", entity_type="sales_deal", entity_id=d.id)
    lifecycle.resolve_legacy_scan_rows(db, NOW)
    assert n.resolved_at is None and n.dedup_key is None


# ── крестик ─────────────────────────────────────────────────────────────────────

def test_dismiss_own_and_foreign(db, uid):
    from fastapi import HTTPException
    from app.routers.notifications import dismiss, list_notifications
    me = db.query(User).filter(User.id == uid).first()
    other = db.query(User).filter(User.id != uid).first()
    n = _note(db, uid, is_read=False)
    dismiss(n.id, db=db, current_user=me)
    assert n.resolved_at is not None and n.is_read
    assert n.id not in [x["id"] for x in list_notifications(db=db, current_user=me, limit=100)["items"]]
    theirs = _note(db, other.id)
    with pytest.raises(HTTPException) as e:
        dismiss(theirs.id, db=db, current_user=me)
    assert e.value.status_code == 404
    assert theirs.resolved_at is None, "закрыл чужое"


def test_dismiss_route_is_mounted():
    from app.main import app
    paths = {r.path for r in app.routes}
    assert "/api/notifications/{notification_id}/dismiss" in paths


def test_resolved_rows_are_not_counted(db, uid):
    me = db.query(User).filter(User.id == uid).first()
    from app.routers.notifications import unread_count
    before = unread_count(db=db, current_user=me)["unread"]
    n = _note(db, uid, is_read=False)
    assert unread_count(db=db, current_user=me)["unread"] == before + 1
    n.resolved_at = NOW
    db.flush()
    assert unread_count(db=db, current_user=me)["unread"] == before
