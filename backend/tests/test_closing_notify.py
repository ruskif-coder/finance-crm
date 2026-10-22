# -*- coding: utf-8 -*-
"""Уведомления контура закрытия (владелец 21.10.2026): кому и когда. Отправка подменена — проверяем, ЧТО уходит."""
from types import SimpleNamespace

import pytest

from app.master_deal import status as ST
from app.notify import closing as CN
from app.notify import registry
from app.notify.recipients import RESOLVERS, master_collector


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(CN, "_emit", lambda db, key, **kw: out.append((key, kw)))
    return out


def _m(status, **kw):
    return SimpleNamespace(id=1, code="M-0001", status=status, created_by=7, **kw)


def test_all_events_registered_and_two_overdues_go_to_telegram():
    keys = ("recon_arrived", "recon_overdue", "deal_sent_to_do", "master_deal_ready", "master_ds_created",
            "master_wait_1c", "master_closed", "master_scans_overdue")
    for k in keys:
        assert registry.get(k) is not None, k
    tg = {k for k in keys if registry.get(k).channels.get("tg")}
    assert tg == {"recon_overdue", "master_scans_overdue"}


def test_ready_goes_only_when_whole_package_is_sent(sent, monkeypatch):
    from app.master_deal import service as MS
    monkeypatch.setattr(MS, "gate", lambda db, m: {"ok": False, "wait": [{"code": "X"}]})
    CN.ready_check(None, _m(ST.DRAFT))
    assert not sent
    monkeypatch.setattr(MS, "gate", lambda db, m: {"ok": True, "wait": []})
    CN.ready_check(None, _m(ST.AGREE))                  # ДС уже созданы — «собрана» не повторяем
    assert not sent
    CN.ready_check(None, _m(ST.DRAFT))
    assert sent[0][0] == "master_deal_ready" and "собрана, ждёт дальнейших действий" in sent[0][1]["title"]
    assert sent[0][1]["actor"] is None                  # последней кнопкой мог нажать сам собирающий — он всё равно получает


@pytest.mark.parametrize("was,now,key", [
    (ST.AGREE, ST.WAIT_1C, "master_wait_1c"),
    (ST.WAIT_PAY, ST.WAIT_SCANS, "master_closed"),
    (ST.WAIT_PAY, ST.ARCHIVE, "master_closed"),
    (ST.WAIT_SCANS, ST.ARCHIVE, "master_closed"),
    (ST.WAIT_1C, ST.ISSUE, None),
    (ST.WAIT_PAY, ST.ISSUE, None),                       # откат — тишина
])
def test_status_events(sent, was, now, key):
    CN.status_changed(None, _m(now), was, None)
    assert [k for k, _ in sent] == ([key] if key else [])


def test_collector_resolver(monkeypatch):
    import app.notify.recipients as R
    monkeypatch.setattr(R, "_active", lambda db, ids: list(ids))
    assert RESOLVERS["master_collector"] is master_collector
    assert master_collector(None, {"master": _m(ST.DRAFT)}) == [7]
    assert master_collector(None, {}) == []


def test_notification_failure_does_not_break_the_action(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("шина легла")
    monkeypatch.setattr(CN, "_emit", boom)
    CN.status_changed(None, _m(ST.WAIT_1C), ST.AGREE, None)       # не бросает


def test_ready_fires_once_after_send_with_whole_batch(monkeypatch):
    """«Отправить в ДО» пакетом (ручка зовёт `send_with`): «собрана» — после всех доп. сделок, а не никогда (ревью 21.10.2026)."""
    from app.master_deal import service as MS
    calls = []
    monkeypatch.setattr(MS, "send", lambda db, d, u, **kw: {"master": {"id": 1, "code": "M-1"}, "first_send": True})
    monkeypatch.setattr(MS, "siblings", lambda db, d, *a: [])
    monkeypatch.setattr(CN, "ready_check", lambda db, m: calls.append(m))

    class Db:
        def get(self, model, i):
            return _m(ST.DRAFT)
    MS.send_with(Db(), SimpleNamespace(id=1), [], None, target="new")
    assert len(calls) == 1


def test_resend_of_already_sent_deal_does_not_fire_ready(monkeypatch):
    from app.master_deal import service as MS
    calls = []
    monkeypatch.setattr(MS, "send", lambda db, d, u, **kw: {"master": {"id": 1, "code": "M-1"}, "first_send": False})
    monkeypatch.setattr(MS, "siblings", lambda db, d, *a: [])
    monkeypatch.setattr(CN, "ready_check", lambda db, m: calls.append(m))

    class Db:
        def get(self, model, i):
            return _m(ST.DRAFT)
    MS.send_with(Db(), SimpleNamespace(id=1), [], None, target="existing")
    assert calls == []
