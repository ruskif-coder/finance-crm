# -*- coding: utf-8 -*-
"""Запуск приоритезации с дашборда и автодозапуск (владелец 16.11.2026): чек-лист готовых площадок, «Запустить», плашка
«есть незапущенные площадки» и «дозапускать сам», пока РК идёт. Сделка стенда, транзакция откатывается: commit подменён
на flush, API приоритезации и письмо площадке — подделки, наружу ничего не уходит."""
import pytest

import app.model_registry  # noqa: F401
from app.prio import autolaunch as A
from app.prio import launch as L
from app.prio import models as M
from app.sales import account_turn as AT
from app.sales import queue_state as qs
from tests.test_prio import FakeApi, _approved, env  # noqa: F401 — фикстура стенда


@pytest.fixture
def quiet(env, monkeypatch):  # noqa: F811
    """Автозапуск коммитит сам (он идёт фоном и кроном) — в тесте коммит = flush, откат фикстуры уберёт всё."""
    db, d, pubs = env
    monkeypatch.setattr(db, "commit", db.flush)
    from app.notify import prio as N
    sent = []
    monkeypatch.setattr(N, "live_to_site", lambda db_, deal, p, on, reason="": sent.append((p.id, on)))
    monkeypatch.setattr(N, "auto_launched", lambda db_, deal, p: sent.append((p.id, "auto")))
    import app.prio.erid as E
    monkeypatch.setattr(E, "_deal_is_closed", lambda db_, deal: False)
    return db, d, pubs, sent


def test_ready_placement_starts_itself_once_campaign_runs(quiet):
    """РК уже идёт на одной площадке → вторая, согласовав и получив ЕРИД, стартует сама; аккаунту и площадке — сообщения.
    Уронит: автозапуск не взводится от идущей площадки / не зовёт тот же launch."""
    db, d, pubs, sent = quiet
    api = FakeApi()
    p1, p2 = _approved(db, d, pubs[0]), _approved(db, d, pubs[1])
    L.launch(db, d, p1.id, client=api)
    assert A.try_one(db, d, p2, client=api) is True
    assert p2.status == M.LIVE and p2.camp_id and api.created == 2
    assert (p2.id, "auto") in sent and (p2.id, True) in sent


def test_first_launch_is_never_automatic(quiet):
    """Ничего ещё не запущено — первый запуск только руками аккаунта, даже с включённым флагом."""
    db, d, pubs, _ = quiet
    api = FakeApi()
    p1 = _approved(db, d, pubs[0])
    assert A.try_one(db, d, p1, client=api) is False
    assert p1.status == M.APPROVED and api.created == 0


def test_switched_off_means_manual(quiet):
    """«Дозапускать сам» выключен — готовая площадка ждёт кнопки, РК не заводится."""
    db, d, pubs, _ = quiet
    api = FakeApi()
    p1, p2 = _approved(db, d, pubs[0]), _approved(db, d, pubs[1])
    L.launch(db, d, p1.id, client=api)
    db.get(M.PrioRequest, p2.request_id).auto_launch_more = False
    db.flush()
    assert A.try_one(db, d, p2, client=api) is False and p2.status == M.APPROVED and api.created == 1


def test_queue_counts_ready_total_live_draft(quiet):
    db, d, pubs, _ = quiet
    api = FakeApi()
    p1, _p2 = _approved(db, d, pubs[0]), _approved(db, d, pubs[1])
    assert qs.prio_counts(db, [d.id])[d.id] == (2, 2, 0, 0)
    L.launch(db, d, p1.id, client=api)
    assert qs.prio_counts(db, [d.id])[d.id] == (1, 2, 1, 0)


def _b(slot, prio, **kw):
    return qs.Bundle(slot=slot, code="X", flow="приоритезация", prio=prio, **kw)


@pytest.mark.parametrize("prio,label,mine", [
    ((2, 3, 0, 0), "Запустить · 2", True),        # готовы — запуск с дашборда
    ((0, 3, 0, 1), "Запрос площадкам", True),     # черновики — отправить
    ((0, 3, 0, 0), None, False),                  # ждём площадки и ЕРИД — не наш ход
])
def test_row_before_start(prio, label, mine):
    b = _b("prep", prio)
    st = qs.row_state(b)
    assert (st["action"] or {}).get("label") == label
    assert AT.turn(b, st["action"])["mine"] is mine


def test_row_live_shows_unlaunched_sites():
    """«В размещении»: готовые, но не запущенные площадки → плашка, «Дозапустить», ход аккаунта. Без них — крутят площадки."""
    b = _b("live", (1, 3, 2, 0))
    st = qs.row_state(b)
    assert st["action"]["label"] == "Дозапустить"
    assert any(x.get("v") == "есть незапущенные площадки: 1" for x in st["state"])
    assert AT.turn(b, st["action"])["mine"] is True
    calm = _b("live", (0, 3, 3, 0))
    assert AT.turn(calm, qs.row_state(calm)["action"])["mine"] is False
