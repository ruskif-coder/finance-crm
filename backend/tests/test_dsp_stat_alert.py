# -*- coding: utf-8 -*-
"""Тревога о поломке ночного сбора DSP (владелец 16.10.2026: «повесь уведомление в тг»)."""
from app.dsp import stat_daily as SD
from app.notify import registry


def test_event_goes_to_admin_and_traffic_masters_by_tg():
    ev = registry.get("cron_dsp_stat_failed")
    assert ev is not None and ev.channels.get("tg")
    vals = {r["value"] for r in ev.recipients}
    assert {"admin", "traffic_masters"} <= vals


def test_bad_states():
    assert SD.is_bad({}, None) is False
    assert SD.is_bad({"failed_campaigns": {"X": "2026-10-15"}}, None)
    assert SD.is_bad({"denied": ["A"]}, None)
    assert SD.is_bad({}, "токен истёк")
    assert SD.is_bad({"unassigned": {"1": 5}}, None) is False, "неразнесённое — предупреждение, не поломка"


def test_alert_only_on_transition(monkeypatch):
    sent = []
    monkeypatch.setattr(SD, "_emit", lambda title, body: sent.append(title))
    SD.alert_if_broke(prev_bad=False, out={"denied": ["A"]}, error=None)
    SD.alert_if_broke(prev_bad=True, out={"denied": ["A"]}, error=None)
    SD.alert_if_broke(prev_bad=False, out={}, error=None)
    assert len(sent) == 1
