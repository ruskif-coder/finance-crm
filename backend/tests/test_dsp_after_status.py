# -*- coding: utf-8 -*-
"""После нажатия статуса: лимиты при запуске сразу, статусы перечитываются из DSP
(владелец 30.09.2026). Сбой сверки — отчёт, а не отказ: статус DSP уже принял."""
from types import SimpleNamespace

from app.dsp import campaigns as dc


class Ms:
    def __init__(self, camp="LAUNCHED", cr=None, boom=False):
        self.camp, self.cr, self.boom = camp, cr or {}, boom

    def campaign_get_info(self, xx):
        if self.boom:
            raise RuntimeError("обрыв")
        return {"status": self.camp}

    def creative_get_info(self, xx):
        return {"status": self.cr.get(xx)}


CAMP = SimpleNamespace(id=1, ms_campaign_xxhash="C1")


def _no_limits(monkeypatch, got=None):
    import app.dsp.limits as L
    monkeypatch.setattr(L, "sync_limits", lambda db, camp, c: got or {"updated": 2, "failed": []})


def test_launch_syncs_limits_and_all_matches(monkeypatch):
    _no_limits(monkeypatch)
    r = dc.after_status(None, CAMP, "LAUNCHED", {"A": "LAUNCHED", "B": "STOPPED"},
                        Ms(cr={"A": "LAUNCHED", "B": "STOPPED"}))
    assert r["limits"]["updated"] == 2 and r["mismatch"] == [] and r["error"] is None


def test_mismatch_is_reported(monkeypatch):
    _no_limits(monkeypatch)
    r = dc.after_status(None, CAMP, "LAUNCHED", {"A": "LAUNCHED"},
                        Ms(camp="STOPPED", cr={"A": "STOPPED"}))
    assert {m["what"] for m in r["mismatch"]} == {"кампания", "креатив A"}


def test_stop_does_not_touch_limits(monkeypatch):
    import app.dsp.limits as L
    monkeypatch.setattr(L, "sync_limits", lambda *a: (_ for _ in ()).throw(AssertionError("не звать")))
    r = dc.after_status(None, CAMP, "STOPPED", {}, Ms(camp="STOPPED"))
    assert r["limits"] is None and r["mismatch"] == []


def test_check_failure_is_a_report_not_a_refusal(monkeypatch):
    _no_limits(monkeypatch)
    r = dc.after_status(None, CAMP, "LAUNCHED", {}, Ms(boom=True))
    assert "сверка с DSP не прошла" in r["error"]
