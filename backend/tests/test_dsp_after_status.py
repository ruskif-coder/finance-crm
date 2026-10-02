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


def _launch(monkeypatch, reread_fails=False):
    from app.dsp.client import MsError
    _no_limits(monkeypatch)
    sent = []

    class M(Ms):
        def campaign_set_status(self, xx, st, local_ref=None):
            sent.append(("camp", st))

        def creative_set_status(self, xx, st, local_ref=None):
            if xx == "K2":
                raise MsError("Creative.setStatus: отказ")
            sent.append((xx, st))
            self.cr[xx] = st
    monkeypatch.setattr(dc, "creative_targets",
                        lambda rows, t: {"K1": "LAUNCHED", "K2": "LAUNCHED", "K3": "LAUNCHED"})
    monkeypatch.setattr(dc, "sync_campaign_plan", lambda *a, **k: None)

    class Q:
        def __getattr__(self, n):
            return lambda *a, **k: self

        def all(self):
            return []
    camp = SimpleNamespace(id=2, ms_campaign_xxhash="C2")
    ms = M(cr={"K2": "STOPPED"}, boom=reread_fails)
    assert dc.apply_status(SimpleNamespace(query=lambda *a: Q()), camp, "запущена", client=ms) == "LAUNCHED"
    return sent, camp._dsp_check


def test_one_refused_creative_does_not_undo_an_accepted_launch(monkeypatch):
    """Аудит 01.10.2026, К-6: DSP отказал на N-м креативе — раньше `apply_status` падал,
    вызывающий откатывал НАШ статус и писал «изменения не сохранены», а кампания и
    креативы 1…N−1 в DSP уже крутились."""
    sent, chk = _launch(monkeypatch)
    assert ("K1", "LAUNCHED") in sent and ("K3", "LAUNCHED") in sent, "отказ K2 не остановил K3"
    assert [m["got"] for m in chk["mismatch"] if "K2" in m["what"]] == ["STOPPED"]
    assert [r["what"] for r in chk["refused"]] == ["креатив K2"]


def test_refusal_survives_a_failed_reread(monkeypatch):
    """Обрыв связи бьёт и по отказу, и по перечитыванию — отказ всё равно в отчёте."""
    _, chk = _launch(monkeypatch, reread_fails=True)
    assert chk["error"] and [r["what"] for r in chk["refused"]] == ["креатив K2"]


def test_campaign_refusal_still_propagates(monkeypatch):
    from app.dsp.client import MsError
    import pytest

    class M(Ms):
        def campaign_set_status(self, xx, st, local_ref=None):
            raise MsError("Campaign.setStatus: отказ")
    with pytest.raises(MsError):
        dc.apply_status(None, SimpleNamespace(id=3, ms_campaign_xxhash="C3"), "остановлена", client=M())
