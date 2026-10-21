# -*- coding: utf-8 -*-
"""«Вашу сделку забрали в пакет» (владелец 16.10.2026): сделку добавил в мастер-сделку не её аккаунт —
аккаунту и мастерам аккаунтов, каналом «дайджест»."""
import app.model_registry  # noqa: F401
from app.notify import master_deal as N
from app.notify import registry


class _Deal:
    id, code, account_manager_id = 10, "TEST01", 7


class _M:
    id, code = 1, "M-0999"


class _U:
    def __init__(self, uid, name="Анна Ким"):
        self.id, self.name = uid, name


def test_event_registered_for_account_and_masters_by_digest():
    ev = registry.get("deal_taken_into_master")
    assert ev is not None
    assert ev.channels.get("digest") and not ev.channels.get("tg")
    assert {r["value"] for r in ev.recipients} >= {"account_manager", "account_masters"}


def test_foreign_user_triggers_notice(monkeypatch):
    sent = []
    monkeypatch.setattr(N, "_owner_user_id", lambda db, deal: 22)
    monkeypatch.setattr(N, "_emit", lambda db, deal, m, user: sent.append((deal.code, m.code, user.id)))
    N.deal_taken(None, _Deal(), _M(), _U(20))
    assert sent == [("TEST01", "M-0999", 20)]


def test_own_account_adding_own_deal_is_silent(monkeypatch):
    sent = []
    monkeypatch.setattr(N, "_owner_user_id", lambda db, deal: 22)
    monkeypatch.setattr(N, "_emit", lambda *a: sent.append(a))
    N.deal_taken(None, _Deal(), _M(), _U(22))
    assert sent == []


def test_both_places_that_add_a_deal_notify():
    import inspect

    from app.master_deal import service
    src = inspect.getsource(service)
    import re
    assert src.count("MasterDealItem(") == len(re.findall(r"^\s+_taken\(db, deal, m, user\)", src, re.M))
