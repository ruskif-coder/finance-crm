# -*- coding: utf-8 -*-
"""Ранний выпуск ЕРИД — только с явным подтверждением (владелец 28.09.2026, вариант 2).

Случай, из-за которого правило появилось: на проде маркер выпустили кнопкой через десять
секунд после отправки комплекта, площадка ещё ничего не согласовала. Кнопку порог не
запирает (решение 27.09: человек вправе выпустить раньше), но выпуск до порога
автовыпуска теперь требует подтверждения — и не только на экране: ручка отказывает сама,
иначе любой другой вызов прошёл бы мимо окна. Запись в ЕРИР необратима.

Крон автовыпуска зовёт `issue_marker_for_set` напрямую и этой проверки не касается: он
выпускает только при взятом пороге.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.ord import client as ord_client
from app.routers import launch_prep as lp


class _Db:
    def __init__(self, s):
        self.s = s

    def query(self, model):
        s = self.s
        return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: s))

    def commit(self):
        pass


def _pairs(agreed, total):
    return [SimpleNamespace(agreed_at="2026-09-28" if i < agreed else None) for i in range(total)]


@pytest.fixture
def wired(monkeypatch):
    cset = SimpleNamespace(id=1, no=1, deal_id=1, erid=None, ord_creative_id=None,
                           ord_env=None, erid_source="наш")
    seen = {"issued": 0, "logged": []}
    state = {"pairs": _pairs(0, 5)}
    monkeypatch.setattr(lp, "_deal", lambda db, deal_id, user: SimpleNamespace(id=1, code="ABC123"))
    monkeypatch.setattr(lp, "active_pairs", lambda db, set_id: state["pairs"])
    monkeypatch.setattr(lp, "erid_threshold", lambda db: 0.2)
    monkeypatch.setattr(lp, "issue_marker_for_set",
                        lambda db, s, deal, actor: seen.__setitem__("issued", seen["issued"] + 1) or {"erid": "X"})
    monkeypatch.setattr(lp, "log_action", lambda db, u, action, *a, **kw: seen["logged"].append(action))
    monkeypatch.setattr(ord_client, "env", lambda: "prod")
    return SimpleNamespace(db=_Db(cset), set=cset, seen=seen, state=state, user=SimpleNamespace(id=1))


def test_before_threshold_refuses_without_confirmation(wired):
    with pytest.raises(HTTPException) as e:
        lp.issue_erid(1, wired.db, wired.user)
    assert e.value.status_code == 409
    assert "0 из 5" in e.value.detail and "нужно 1" in e.value.detail
    assert wired.seen["issued"] == 0, "маркер ушёл в ЕРИР без подтверждения"


def test_confirmed_early_issue_goes_and_is_logged(wired):
    lp.issue_erid(1, wired.db, wired.user, lp.EridIssueIn(early_ok=True))
    assert wired.seen["issued"] == 1
    assert "issue_erid_early" in wired.seen["logged"], "ранний выпуск не оставил следа в журнале"


def test_threshold_reached_needs_no_confirmation(wired):
    wired.state["pairs"] = _pairs(1, 5)          # 20 % от пяти — одно согласование
    lp.issue_erid(1, wired.db, wired.user)
    assert wired.seen["issued"] == 1
    assert "issue_erid_early" not in wired.seen["logged"]


def test_already_registered_poll_is_not_asked_again(wired):
    """Регистрация на этом контуре уже состоялась — повторное нажатие лишь забирает
    маркер. Спрашивать «выпустить раньше?» второй раз незачем: выпуск уже случился."""
    wired.set.ord_creative_id, wired.set.ord_env = "CR-1", "prod"
    lp.issue_erid(1, wired.db, wired.user)
    assert wired.seen["issued"] == 1


def test_readiness_reports_early_state():
    assert lp.early_state({"sent": 5, "agreed": 0}, 0.2) == {"need_auto": 1, "early": True}
    assert lp.early_state({"sent": 5, "agreed": 1}, 0.2) == {"need_auto": 1, "early": False}
    assert lp.early_state({"sent": 11, "agreed": 2}, 0.2) == {"need_auto": 3, "early": True}
