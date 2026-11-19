# -*- coding: utf-8 -*-
"""Пиксель Weborama и выгрузка в DSP — сами (трафики 19.11.2026, `app/ad/auto_external`).

Поломки, которые ловит набор:
- автоматика работает при выключенной настройке или при EXTERNAL_WRITES=off (стенд пишет в боевые кабинеты);
- DSP идёт раньше Weborama — креатив уезжает без пикселя, и завести его заново нечем;
- запрет «объёмы больше плана», стоящий на кнопке «В DSP», обходится автоматикой;
- «нет ЕРИД» (площадка просто ждёт маркер) считается сбоем — колокольчик трафика звонит раз в 5 минут;
- тот же отказ уведомляется на каждом прогоне, а не раз в сутки.
Внешние вызовы подменены; запись в базу откатывается в конце."""
import pytest
from sqlalchemy.orm import Session

import app.model_registry  # noqa: F401
from app.ad import auto_external as AE
from app.ad.models import AdCampaign
from app.models import AuditLog
from app.database import SessionLocal
from app.dsp import provision as dsp
from app.launch_prep import volumes
from app.weborama import provision as wb


@pytest.fixture
def env(monkeypatch):
    s = SessionLocal()
    camp = s.query(AdCampaign).order_by(AdCampaign.id).first()
    if camp is None:
        s.close()
        pytest.skip("на стенде нет ни одной РК")
    calls, sent = [], []
    # без коммитов: всё, что пишет проход, откатывается в конце теста
    monkeypatch.setattr(s, "commit", s.flush)
    monkeypatch.setattr(s, "rollback", lambda: None)

    def fake_log(db, user, action, entity_type=None, entity_id=None, details=None):
        db.add(AuditLog(action=action, entity_type=entity_type, entity_id=entity_id, details=details))
        db.flush()

    monkeypatch.setattr(AE, "log_action", fake_log)
    monkeypatch.setattr(AE, "_label", lambda db, c: f"РК {c.id}")
    monkeypatch.setattr(AE, "enabled", lambda db: True)
    monkeypatch.setattr(AE.external_writes, "allowed", lambda: True)
    monkeypatch.setattr(AE, "candidates", lambda db, deal_ids=None: [camp.id])
    from app.notify import bus
    monkeypatch.setattr(bus, "emit", lambda db, key, **kw: sent.append((key, kw["body"])) or [1])
    monkeypatch.setattr(wb, "default_landing", lambda db, c: "https://example.test/")
    monkeypatch.setattr(wb, "plan", lambda db, c: {"todo": 1})
    monkeypatch.setattr(wb, "provision", lambda db, c, landing, user_id=None: calls.append("wb") or {"done": [1], "failed": []})
    monkeypatch.setattr(dsp, "plan", lambda db, c: {"todo": 1})
    monkeypatch.setattr(dsp, "provision", lambda db, c, user_id=None: calls.append("dsp") or {"done": [1], "failed": []})
    monkeypatch.setattr(volumes, "check", lambda db, d: {"blocked": False, "message": None})
    yield s, camp, calls, sent
    Session.rollback(s)
    s.close()


def test_pixel_goes_before_dsp_and_both_are_logged_as_automatic(env):
    s, camp, calls, sent = env
    out = AE.run(s)
    assert calls == ["wb", "dsp"]
    assert out["campaigns"][0]["weborama"] == 1 and out["campaigns"][0]["dsp"] == 1 and not sent
    rows = s.query(AuditLog).filter(AuditLog.entity_id == camp.deal_id, AuditLog.details.like("%автоматически%")).all()
    assert sorted(r.action for r in rows) == ["dsp_provision", "weborama_provision"]


def test_switched_off_or_external_writes_off_does_nothing(env, monkeypatch):
    s, camp, calls, sent = env
    monkeypatch.setattr(AE, "enabled", lambda db: False)
    assert AE.run(s)["skipped"] == "выключено в настройках трафика"
    monkeypatch.setattr(AE, "enabled", lambda db: True)
    monkeypatch.setattr(AE.external_writes, "allowed", lambda: False)
    assert "EXTERNAL_WRITES" in AE.run(s)["skipped"]
    assert calls == [] and sent == []


def test_volumes_over_plan_stop_dsp_like_the_button(env, monkeypatch):
    s, camp, calls, sent = env
    monkeypatch.setattr(volumes, "check", lambda db, d: {"blocked": True, "message": "Объёмы больше плана РК"})
    out = AE.run(s)
    assert calls == ["wb"]
    assert out["campaigns"][0]["failed"] == ["DSP: Объёмы больше плана РК"] and len(sent) == 1


def test_waiting_for_erid_is_not_a_failure(env, monkeypatch):
    s, camp, calls, sent = env
    monkeypatch.setattr(wb, "provision", lambda db, c, landing, user_id=None: {
        "done": [], "failed": [{"placement_id": 1, "name": "площадка", "error": wb.NO_ERID}]})
    out = AE.run(s)
    assert out["campaigns"] == [] or not out["campaigns"][0]["failed"]
    assert sent == []


def test_same_failure_is_notified_once_a_day(env, monkeypatch):
    s, camp, calls, sent = env
    monkeypatch.setattr(dsp, "provision", lambda db, c, user_id=None: {
        "done": [], "failed": [{"creative_id": 7, "name": "креатив", "error": "DSP отказала"}]})
    AE.run(s)
    AE.run(s)
    assert [k for k, _ in sent] == ["traffic_auto_external_failed"]
    assert "креатив: DSP отказала" in sent[0][1]


def test_failure_shows_in_rk_pult_until_a_clean_pass(env, monkeypatch):
    """Владелец 19.11.2026: отказ автоматики — алертом в пульте раскрытой РК. Поломка: алерт не появляется, не гаснет после
    чистого прохода или остаётся висеть, когда автоматику выключили."""
    s, camp, calls, sent = env
    monkeypatch.setattr(volumes, "check", lambda db, d: {"blocked": True, "message": "Объёмы больше плана РК"})
    AE.run(s)
    assert AE.alerts(s)[camp.id] == "DSP: Объёмы больше плана РК"
    monkeypatch.setattr(volumes, "check", lambda db, d: {"blocked": False, "message": None})
    AE.run(s)
    assert camp.id not in AE.alerts(s)
    monkeypatch.setattr(volumes, "check", lambda db, d: {"blocked": True, "message": "Объёмы больше плана РК"})
    AE.run(s)
    monkeypatch.setattr(AE, "enabled", lambda db: False)
    AE.run(s)
    assert AE.alerts(s) == {}


def test_overlay_paints_only_setup_step_red():
    base = {"worst": "green", "all_ok": True, "groups": [
        {"key": "setup", "title": "Заведение", "level": "green", "text": "ок", "action": None},
        {"key": "collect", "title": "Сбор", "level": "green", "text": "ок", "action": None}]}
    out = AE.overlay(base, "DSP: Объёмы больше плана РК")
    assert out["worst"] == "red" and out["all_ok"] is False
    assert out["groups"][0]["level"] == "red" and out["groups"][0]["text"] == "Автоматика: DSP: Объёмы больше плана РК"
    assert out["groups"][0]["action"]["target"] == "dsp" and out["groups"][1]["level"] == "green"
    assert base["groups"][0]["level"] == "green"          # исходная сводка не тронута
