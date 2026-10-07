# -*- coding: utf-8 -*-
"""Статус креатива в дашборде трафика (аудит 01.10.2026, В-3): «запущен» и «пауза» —
только согласованному; смена статуса доходит до DSP ОДНИМ вызовом по этому креативу;
отклонённый вручную креатив останавливается в DSP; архивный (отозванный) не возвращается."""
from types import SimpleNamespace as NS

import pytest
from fastapi import HTTPException

import app.main  # noqa: F401
from app.routers import traffic_dashboard as td


@pytest.fixture(autouse=True)
def _no_share_lock(monkeypatch):
    """Замок доли РК (`ext_lock.lock_campaign_shares`) ходит в настоящую базу, а здесь она подставная.
    Сам замок и порядок его взятия проверяет test_campaign_shares_lock.py (07.10.2026)."""
    monkeypatch.setattr(td, "_lock_shares", lambda db, cid: None)


class _Db:
    def __init__(self, cr, pl_status="запущен"):
        self.cr, self.pl = cr, NS(status=pl_status)

    def query(self, model):
        obj = self.pl if model is td.AdCampaignPlacement else self.cr
        return NS(get=lambda i: obj)

    def flush(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass


def _wire(monkeypatch, dsp_now="LAUNCHED", camp_status="запущена"):
    calls = []
    monkeypatch.setattr(td, "_campaign_in_scope",
                        lambda db, cid, u: (NS(id=cid, ms_campaign_xxhash="C", status=camp_status), NS()))
    monkeypatch.setattr(td, "_campaign_chain", lambda db, c: "запущена")
    monkeypatch.setattr(td.build, "recompute_shares", lambda db, cid: None)
    monkeypatch.setattr(td, "log_action", lambda *a, **k: None)

    class Ms:
        def creative_get_info(self, h):
            return {"status": dsp_now}

        def creative_set_status(self, h, st, local_ref=None):
            calls.append((h, st))
    monkeypatch.setattr(td, "MsClient", Ms)
    return calls


def _cr(status):
    return NS(id=1, campaign_id=2, placement_id=3, status=status, ms_title="t", ms_creative_xxhash="H")


@pytest.mark.parametrize("to", ["запущен", "пауза"])
def test_unapproved_creative_cannot_be_launched_or_paused(monkeypatch, to):
    _wire(monkeypatch)
    with pytest.raises(HTTPException) as e:
        td.set_creative_status(1, td.StatusIn(status=to), db=_Db(_cr("у площадки")), user=NS(id=1))
    assert e.value.status_code == 400


def test_pause_stops_only_this_creative(monkeypatch):
    calls = _wire(monkeypatch)
    out = td.set_creative_status(1, td.StatusIn(status="пауза"), db=_Db(_cr("запущен")), user=NS(id=1))
    assert calls == [("H", "STOPPED")] and out["dsp_status"] == "STOPPED"


def test_resume_launches_only_this_creative(monkeypatch):
    calls = _wire(monkeypatch, dsp_now="STOPPED")
    td.set_creative_status(1, td.StatusIn(status="запущен"), db=_Db(_cr("пауза")), user=NS(id=1))
    assert calls == [("H", "LAUNCHED")]


def test_manual_reject_stops_a_live_creative(monkeypatch):
    calls = _wire(monkeypatch)
    td.set_creative_status(1, td.StatusIn(status=td.CREATIVE_REJECTED), db=_Db(_cr("запущен")), user=NS(id=1))
    assert calls == [("H", "STOPPED")]


def test_archived_creative_is_not_touched_and_not_revived(monkeypatch):
    calls = _wire(monkeypatch, dsp_now="ARCHIVE")
    td.set_creative_status(1, td.StatusIn(status=td.CREATIVE_REJECTED), db=_Db(_cr("запущен")), user=NS(id=1))
    assert calls == []
    with pytest.raises(HTTPException) as e:
        td.set_creative_status(1, td.StatusIn(status="запущен"), db=_Db(_cr(td.CREATIVE_REJECTED)), user=NS(id=1))
    assert e.value.status_code == 400
