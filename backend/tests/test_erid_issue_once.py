# -*- coding: utf-8 -*-
"""Кнопка «выпустить ЕРИД»: маркер без маркера не объявляется (аудит 23.09.2026, 4.H5).

ОРД выдаёт идентификатор креатива сразу, а маркер — бывает, что позже. Ручка до правки
в этом случае всё равно переводила получателей в «ерид получен» и писала площадке
«ЕРИД None»: площадка ставила в эфир материал без маркировки. А второе нажатие
регистрировало креатив заново — второй в ЕРИР, не отзываемый.

Ручка проверяется на подменах: база, сделка и отправка — поддельные, проверяется только
её собственное решение «объявлять или нет» и то, что она зовёт опрос, а не регистрацию.
"""
from types import SimpleNamespace

import pytest

from app.ord import submit as ord_submit
from app.routers import launch_prep as lp


class _Db:
    def __init__(self, s):
        self.s = s

    def query(self, model):
        s = self.s
        return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: s))

    def commit(self):
        pass


@pytest.fixture
def wired(monkeypatch):
    cset = SimpleNamespace(id=1, no=1, deal_id=1, erid=None, ord_creative_id=None,
                           ord_env=None, erid_source="наш")
    deal = SimpleNamespace(id=1, code="ABC123", brand_id=None)
    seen = {"marked": 0, "told": 0, "emitted": 0, "register": 0, "refresh": 0}

    def issue(db, s, *a, **kw):
        # Поддельный ОРД: id выдан, маркера нет — ни в первый раз, ни во второй.
        if s.ord_creative_id:
            seen["refresh"] += 1
        else:
            seen["register"] += 1
            s.ord_creative_id = "CR-1"
        return {"ord_id": "CR-1", "erid": None, "status": "Registering", "env": "demo"}

    monkeypatch.setattr(lp, "_deal", lambda db, deal_id, user: deal)
    monkeypatch.setattr(lp, "active_pairs", lambda db, set_id: [1])
    monkeypatch.setattr(lp, "_ord_chain", lambda db, d: ("F-1", None))
    monkeypatch.setattr(lp, "_files_with_content", lambda db, set_id: [])
    monkeypatch.setattr(lp, "_target_urls", lambda db, set_id: [])
    monkeypatch.setattr(lp, "_mark_targets_erid",
                        lambda db, set_id: seen.__setitem__("marked", seen["marked"] + 1))
    monkeypatch.setattr(lp, "_tell_publisher_erid",
                        lambda db, s, d: seen.__setitem__("told", seen["told"] + 1))
    monkeypatch.setattr(lp, "emit",
                        lambda *a, **kw: seen.__setitem__("emitted", seen["emitted"] + 1))
    monkeypatch.setattr(lp, "log_action", lambda *a, **kw: None)
    monkeypatch.setattr("app.ad.build.sync_deal_quietly", lambda db, deal_id: None)
    monkeypatch.setattr(ord_submit, "issue_marker", issue, raising=False)
    # Ручка обязана идти через `issue_marker`: прямой вызов регистрации и есть дефект.
    monkeypatch.setattr(ord_submit, "register_creative",
                        lambda *a, **kw: pytest.fail("ручка регистрирует мимо issue_marker"))
    return SimpleNamespace(db=_Db(cset), seen=seen, user=SimpleNamespace(id=1))


def test_no_marker_means_no_recipients_moved_and_no_letter(wired):
    out = lp.issue_erid(1, wired.db, wired.user)
    assert out["erid"] is None
    assert wired.seen["marked"] == 0, "получатели переведены в «ерид получен» без маркера"
    assert wired.seen["told"] == 0, "площадке ушло письмо «ЕРИД None»"
    assert wired.seen["emitted"] == 0


def test_second_press_asks_for_status_instead_of_registering(wired):
    lp.issue_erid(1, wired.db, wired.user)
    lp.issue_erid(1, wired.db, wired.user)
    assert wired.seen["register"] == 1, "второе нажатие зарегистрировало креатив снова"
    assert wired.seen["refresh"] == 1
