"""Тесты бэклога отладки (app/routers/backlog.py, правило в app/notify/scanner.py).

Проверяется то, что ломается молча и обесценивает раздел целиком:
запись, закрытая без объяснения; статус, разъехавшийся с resolved_at; и сканер,
который либо спамит каждый прогон, либо будит по давно закрытым записям.
"""
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.backlog_models import CLOSED_STATUSES, SEVERITIES, STATUSES, BacklogItem
from app.notify import registry
from app.notify.scanner import backlog_overdue_hits
from app.routers.backlog import _validate, apply_status_change, is_overdue


class FakeUser:
    def __init__(self, uid=7, name="Тестировщик"):
        self.id, self.name = uid, name


def item(**kw) -> BacklogItem:
    base = dict(id=1, title="Проверить навигацию", status="наблюдаем",
                severity="средняя", resolution=None, watch_until=None,
                overdue_notified_at=None, context=None, signal_bad=None)
    base.update(kw)
    return BacklogItem(**base)


# ---- закрытие требует объяснения ----

@pytest.mark.parametrize("status", sorted(CLOSED_STATUSES))
def test_cannot_close_without_resolution(status):
    it = item()
    with pytest.raises(HTTPException) as e:
        apply_status_change(it, status, FakeUser())
    assert e.value.status_code == 400
    assert it.status == "наблюдаем", "статус не должен меняться при отказе"


def test_close_with_resolution_ok():
    it = item(resolution="Не воспроизвелось за две недели")
    apply_status_change(it, "закрыто", FakeUser())
    assert it.status == "закрыто"
    assert it.resolved_at is not None
    assert it.resolved_by == 7


def test_confirmed_does_not_require_resolution():
    """«Подтвердилось» — не закрытие: работа только начинается, требовать итог рано.
    Но исход зафиксировать надо, поэтому resolved_at проставляется."""
    it = item()
    apply_status_change(it, "подтвердилось", FakeUser())
    assert it.status == "подтвердилось"
    assert it.resolved_at is not None


# ---- возврат под наблюдение чистит исход ----

def test_reopen_clears_resolution_stamps():
    it = item(resolution="закрыли зря")
    apply_status_change(it, "закрыто", FakeUser())
    assert it.resolved_at is not None
    it.overdue_notified_at = datetime.utcnow()
    apply_status_change(it, "наблюдаем", FakeUser())
    assert it.resolved_at is None and it.resolved_by is None
    # Отметку о напоминании тоже сбрасываем: срок наблюдения начинается заново.
    assert it.overdue_notified_at is None


# ---- валидация справочных значений ----

def test_validate_rejects_unknown_values():
    with pytest.raises(HTTPException) as e:
        _validate("критическая", None)
    assert e.value.status_code == 400
    with pytest.raises(HTTPException):
        _validate(None, "в работе")


def test_validate_accepts_all_registered_values():
    for s in SEVERITIES:
        _validate(s, None)
    for s in STATUSES:
        _validate(None, s)


# ---- признак просрочки ----

def test_is_overdue_only_for_open_items():
    today = date(2026, 8, 16)
    past = date(2026, 8, 1)
    assert is_overdue(item(watch_until=past), today)
    assert not is_overdue(item(watch_until=date(2026, 9, 1)), today)
    assert not is_overdue(item(watch_until=past, status="закрыто"), today)
    assert not is_overdue(item(watch_until=None), today)


# ---- правило сканера ----

TODAY = date(2026, 8, 16)
NOW = datetime(2026, 8, 16, 10, 0)


def test_rule_skips_closed_items():
    items = [item(id=i, status=st, watch_until=date(2026, 8, 1))
             for i, st in enumerate(sorted(CLOSED_STATUSES), start=1)]
    assert backlog_overdue_hits(items, TODAY, NOW) == []


def test_rule_hits_open_overdue_item():
    hits = backlog_overdue_hits([item(watch_until=date(2026, 8, 1))], TODAY, NOW)
    assert len(hits) == 1
    assert hits[0].entity_type == "backlog"
    assert hits[0].stage == "overdue"
    assert hits[0].payload["days"] == 15


def test_rule_ignores_future_watch_until():
    assert backlog_overdue_hits([item(watch_until=date(2026, 9, 1))], TODAY, NOW) == []


def test_rule_does_not_remind_more_often_than_once_a_week():
    fresh = item(watch_until=date(2026, 8, 1),
                 overdue_notified_at=NOW - timedelta(days=3))
    assert backlog_overdue_hits([fresh], TODAY, NOW) == []

    stale = item(watch_until=date(2026, 8, 1),
                 overdue_notified_at=NOW - timedelta(days=8))
    assert len(backlog_overdue_hits([stale], TODAY, NOW)) == 1

    # Граница ровно в repeat_days считается наступившей: сутки плавают, повтор не теряем.
    edge = item(watch_until=date(2026, 8, 1),
                overdue_notified_at=NOW - timedelta(days=7))
    assert len(backlog_overdue_hits([edge], TODAY, NOW)) == 1


# ---- события реестра ----

def test_backlog_events_registered_app_only():
    """Каналы по умолчанию — только «в приложении»: обработчика дайджеста нет,
    и событие, отправленное туда, никому не покажется (см. bus.LIVE_CHANNELS)."""
    for key in ("backlog_created", "backlog_confirmed", "backlog_overdue"):
        ev = registry.get(key)
        assert ev is not None, key
        assert ev.channels == {"app": True}, key
    assert registry.get("backlog_overdue").scan is True
