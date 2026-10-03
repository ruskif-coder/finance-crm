# -*- coding: utf-8 -*-
"""Автовыпуск ЕРИД по порогу 20 % и опрос статуса (владелец 27.09.2026).

Запись в ЕРИР необратима, поэтому приборы держат именно решения прогона: когда выпуск
случается, когда нет, и что без цепочки или ККТУ он молчит в реестр, а не пробует. Сеть и
ОРД подменены: проверяется решение, а не обмен.
"""
import time
from types import SimpleNamespace

import pytest

from app.database import SessionLocal
from app.launch_prep import erid_auto
from app.launch_prep.models import LaunchPrepCreativeSet
from app.routers import launch_prep as lp
from app.sales.models import SalesDeal


from app.launch_prep import erid_service as svc  # noqa: E402

def _patch(mp, name, value):
    """Подмена в роутере и в сервисе ЕРИД: функции выпуска живут в
    `app.launch_prep.erid_service` (02.10.2026), роутер держит их же имена."""
    mp.setattr(lp, name, value)
    if hasattr(svc, name):
        mp.setattr(svc, name, value)

@pytest.fixture
def db():
    """Сессия без коммитов. Откат внутри прогона — пустой: на проде каждый комплект
    коммитится отдельно, и откат после сбоя снимает только его; здесь же коммит подменён
    сбросом, и настоящий откат стёр бы все тестовые строки разом. Настоящий — на выходе."""
    s = SessionLocal()
    real_rollback = s.rollback
    s.commit = s.flush
    s.rollback = lambda: None
    try:
        yield s
    finally:
        real_rollback()
        s.close()


def test_auto_need_is_twenty_percent_up_min_one():
    assert lp.ERID_THRESHOLD_DEFAULT == 0.20
    assert [lp.auto_need(n, 0.2) for n in (1, 3, 5, 6, 10, 11, 15, 16)] == [1, 1, 1, 2, 2, 3, 3, 4]
    assert lp.auto_need(0, 0.2) == 0


def _pairs(sent, agreed):
    return [SimpleNamespace(agreed_at=(1 if i < agreed else None)) for i in range(sent)]


@pytest.fixture
def world(db, monkeypatch):
    """Сделка и комплекты; что у комплекта «отправлено/согласовано» — задаёт тест."""
    n = time.time_ns()
    deal = SalesDeal(bitrix_id=f"erid-auto-{n}", code=format(n % 36 ** 6, "X")[-6:].rjust(6, "Y"),
                     title="Пзкт автоЕРИД")
    db.add(deal)
    db.flush()
    plan = {}          # set_id -> (sent, agreed)
    calls = {"issue": [], "refresh": []}

    def make(sent, agreed, **kw):
        s = LaunchPrepCreativeSet(deal_id=deal.id, no=len(plan) + 1, erid_source="наш", **kw)
        db.add(s)
        db.flush()
        plan[s.id] = (sent, agreed)
        return s

    _patch(monkeypatch, "active_pairs",
                        lambda db_, set_id: _pairs(*plan[set_id]) if set_id in plan else [])
    monkeypatch.setattr(erid_auto, "_blockers", lambda db_, d: [])
    _patch(monkeypatch, "erid_threshold", lambda db_: 0.20)
    monkeypatch.setattr("app.ord.client.env", lambda: "prod")

    def issue(db_, s, d, actor):
        calls["issue"].append(s.id)
        assert actor is None, "автовыпуск — действие системы"
        return {"erid": f"E{s.id}", "status": "Created"}
    _patch(monkeypatch, "issue_marker_for_set", issue)
    return SimpleNamespace(deal=deal, make=make, calls=calls, plan=plan)


def _mine(res, w, key):
    return [x["set_id"] for x in res[key] if x["set_id"] in w.plan]


def test_issues_when_twenty_percent_agreed(db, world):
    a = world.make(5, 1)       # 1 из 5 — порог (1)
    b = world.make(5, 0)       # никто
    c = world.make(11, 2)      # нужно 3
    d = world.make(11, 3)
    res = erid_auto.issue_due(db)
    assert sorted(_mine(res, world, "issued")) == sorted([a.id, d.id])
    assert b.id not in world.calls["issue"] and c.id not in world.calls["issue"]


def test_blocked_set_is_reported_not_sent(db, world, monkeypatch):
    s = world.make(5, 5)
    monkeypatch.setattr(erid_auto, "_blockers", lambda db_, d: ["не заполнен код ККТУ у бренда"])
    res = erid_auto.issue_due(db)
    assert s.id not in world.calls["issue"], "без ККТУ ушло в реестр"
    assert s.id in [b["set_id"] for b in res["blocked"]]


def test_foreign_marker_source_is_left_alone(db, world):
    s = world.make(5, 5)
    s.erid_source = "площадки"
    db.flush()
    erid_auto.issue_due(db)
    assert s.id not in world.calls["issue"]


def test_registered_on_this_contour_skips_the_threshold(db, world):
    here = world.make(5, 0, ord_creative_id="CR-1", ord_env="prod")
    sandbox = world.make(5, 0, ord_creative_id="CR-2", ord_env="demo")
    erid_auto.issue_due(db)
    assert here.id in world.calls["issue"], "зарегистрированный без маркера не опрошен"
    assert sandbox.id not in world.calls["issue"], "регистрация песочницы отменила порог"


def test_closed_deal_is_skipped(db, world, monkeypatch):
    s = world.make(5, 5)
    monkeypatch.setattr(erid_auto, "_deal_is_closed", lambda db_, d: True)
    erid_auto.issue_due(db)
    assert s.id not in world.calls["issue"]


def test_one_failure_does_not_stop_the_rest(db, world, monkeypatch):
    from fastapi import HTTPException
    a = world.make(5, 5)
    b = world.make(5, 5)

    def issue(db_, s, d, actor):
        world.calls["issue"].append(s.id)
        if s.id == a.id:
            raise HTTPException(400, "ОРД отказал")
        return {"erid": "E", "status": "Created"}
    _patch(monkeypatch, "issue_marker_for_set", issue)
    res = erid_auto.issue_due(db)
    assert a.id in [f["set_id"] for f in res["failed"]]
    assert b.id in _mine(res, world, "issued")


def test_dry_run_sends_nothing(db, world):
    world.make(5, 5)
    erid_auto.issue_due(db, dry_run=True)
    assert world.calls["issue"] == []


def test_refresh_only_own_contour_and_unfinished(db, world, monkeypatch):
    live = world.make(1, 1, erid="EA", ord_env="prod", ord_status="Registering")
    done = world.make(1, 1, erid="EB", ord_env="prod", ord_status="Active")
    other = world.make(1, 1, erid="EC", ord_env="demo", ord_status="Registering")
    seen = []

    def refresh(db_, s):
        seen.append(s.id)
        return {"status": "Active"}
    monkeypatch.setattr("app.ord.submit.refresh_creative_status", refresh)
    res = erid_auto.refresh_statuses(db)
    assert live.id in seen
    assert done.id not in seen and other.id not in seen
    assert live.id in [c["set_id"] for c in res["changed"]]


# ── общая функция кнопки и автовыпуска: поздний маркер объявляется ─────────────────

def test_marker_that_arrives_on_poll_is_announced(monkeypatch):
    """Маркер пришёл при опросе — получатели, РК и уведомления, как при выпуске сразу."""
    s = SimpleNamespace(id=1, no=1, erid=None, ord_creative_id="CR-1", ord_env="prod")
    deal = SimpleNamespace(id=1, code="ABC123", brand_id=None)
    seen = []
    _patch(monkeypatch, "active_pairs", lambda db_, set_id: [1])
    _patch(monkeypatch, "_ord_chain", lambda db_, d: ("F-1", None))
    _patch(monkeypatch, "_files_with_content", lambda db_, set_id: [])
    _patch(monkeypatch, "_target_urls", lambda db_, set_id: [])
    # Настоящий issue_marker пишет маркер и статус в комплект; объявляется только ГОТОВЫЙ
    # (Active/Registering — `app.ord.readiness`, 02.10.2026), Created ждёт опроса.
    def issue(db_, cset, *a, **k):
        cset.erid, cset.ord_status = "E1", "Registering"
        return {"erid": "E1", "status": "Registering"}
    monkeypatch.setattr("app.ord.submit.issue_marker", issue)
    _patch(monkeypatch, "announce_marker", lambda db_, s_, d, actor, out: seen.append(out["erid"]))
    lp.issue_marker_for_set(SimpleNamespace(commit=lambda: None), s, deal, None)
    assert seen == ["E1"]


def test_report_names_the_skipped():
    out = {"dry_run": False,
           "issue": {"share": 0.2, "issued": [], "pending": [], "waiting": 2,
                     "blocked": [{"set_id": 7, "deal": "ABC123", "why": ["не заполнен код ККТУ у бренда"]}],
                     "failed": []},
           "refresh": {"checked": 1, "changed": [], "failed": []}}
    text = erid_auto._report(out)
    assert "порог 20 %" in text and "ABC123" in text and "ККТУ" in text


# ── строка «Автовыпуск ЕРИД» на экране «Статус системы» ───────────────────────────

def _last(db, **kw):
    import json
    from datetime import datetime, timedelta
    from sqlalchemy import text
    base = {"at": (datetime.utcnow() - timedelta(minutes=kw.pop("ago_min", 10)))
            .isoformat(timespec="seconds"), "issued": 1, "pending": 0,
            "blocked": [], "failed": [], "refresh_failed": 0}
    base.update(kw)
    db.execute(text("INSERT INTO company_settings (key, value) VALUES ('erid_auto_last', :v) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
               {"v": json.dumps(base, ensure_ascii=False)})
    db.flush()


def test_status_row_tones(db):
    from app.system.status import check_erid_auto
    _last(db)
    assert check_erid_auto(db)["tone"] == "ok"
    _last(db, ago_min=180)
    c = check_erid_auto(db)
    assert c["tone"] == "bad" and c["consequence"], "мёртвый крон без последствия словами"
    _last(db, failed=["ABC123: ОРД отказал"])
    c = check_erid_auto(db)
    assert c["tone"] == "bad" and "ОРД отказал" in c["note"] and c["consequence"]
    _last(db, blocked=["ABC123: не заполнен код ККТУ у бренда"])
    c = check_erid_auto(db)
    assert c["tone"] == "warn" and "ККТУ" in c["note"]


def test_status_row_is_on_the_board():
    import inspect
    from app.system import status
    assert "check_erid_auto" in inspect.getsource(status.collect)


def test_live_run_is_recorded_dry_run_is_not(monkeypatch):
    calls = []
    monkeypatch.setattr(erid_auto, "issue_due", lambda db_, dry_run=False: {
        "share": 0.2, "issued": [], "pending": [], "waiting": 0, "blocked": [], "failed": []})
    monkeypatch.setattr(erid_auto, "refresh_statuses", lambda db_, dry_run=False: {
        "checked": 0, "changed": [], "failed": []})
    monkeypatch.setattr(erid_auto, "record", lambda db_, out: calls.append(out["dry_run"]))
    # Догон объявлений пишет площадкам — в тесте его нет (реальные уведомления запрещены).
    monkeypatch.setattr(erid_auto, "catch_up", lambda db_, dry_run=False: [])
    erid_auto.run(dry_run=True)
    erid_auto.run(dry_run=False)
    assert calls == [False]


# ── тревога администратору: падает / молчит ──────────────────────────────────────

def test_alert_events_go_to_admin_by_telegram_and_mail():
    from app.notify import registry
    for key in ("cron_erid_auto_failed", "cron_erid_auto_stale"):
        ev = registry.get(key)
        assert ev.recipients == [{"type": "role", "value": "admin"}], key
        assert ev.channels.get("tg") and ev.channels.get("mail"), f"{key}: не срочно"
        assert ev.locked, f"{key}: тревогу о поломке можно выключить"


def _out(failed=0, refresh_failed=0):
    return {"issue": {"failed": [{"deal": "A", "error": "x"}] * failed},
            "refresh": {"failed": [{"set_id": 1}] * refresh_failed}}


def test_alert_fires_on_transition_only():
    assert erid_auto.should_alert(None, _out(failed=1))
    assert erid_auto.should_alert({"failed": [], "refresh_failed": 0}, _out(refresh_failed=1))
    assert not erid_auto.should_alert({"failed": ["A: x"]}, _out(failed=1)), "спам каждые полчаса"
    assert not erid_auto.should_alert(None, _out())


def test_stale_cron_is_caught_by_the_scanner():
    from datetime import datetime, timedelta
    from app.notify import scanner
    now = datetime(2026, 10, 1, 12, 0)
    assert scanner.erid_auto_stale_hits(None, now) == [], "на стенде крона нет — это норма"
    assert scanner.erid_auto_stale_hits(now - timedelta(minutes=40), now) == []
    hits = scanner.erid_auto_stale_hits(now - timedelta(hours=3), now)
    assert len(hits) == 1 and hits[0].stage == "stale"
    assert "cron_erid_auto_stale" in scanner.RULES, "правило не подключено к сканеру"
