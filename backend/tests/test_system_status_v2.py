"""«Статус системы» v2 (хендофф 16.11.2026): серия «с какого момента», история за 14 дней, оповещения при СМЕНЕ
состояния, прогноз диска, ручной запуск заданий без параллели.

Пишет в базу стенда только под ключами `t_v2_*` и убирает за собой.
"""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.system import alerts, disk, history, jobs

KEY = "t_v2_check"


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.execute(text("DELETE FROM system_check_state WHERE check_key LIKE 't_v2_%'"))
    s.execute(text("DELETE FROM system_check_day WHERE check_key LIKE 't_v2_%'"))
    s.execute(text("DELETE FROM system_job_run WHERE job_key LIKE 't_v2_%'"))
    s.commit()
    s.close()


def chk(tone, key=KEY, group="Фоновые задания", **kw):
    return {"key": key, "group": group, "title": "Тестовая проверка", "tone": tone, "value": "v",
            "note": kw.get("note"), "consequence": kw.get("consequence"), "keys": None, "action": None}


# ── серия и переходы ──────────────────────────────────────────────────────────

def test_series_starts_at_first_failure_and_restarts_on_first_ok(db):
    """Поломка: `since` переписывается каждым прогоном → «с какого момента» всегда «только что»."""
    t0 = datetime(2026, 11, 14, 2, 0)
    history.record(db, [chk("bad")], now=t0)
    history.record(db, [chk("bad")], now=t0 + timedelta(days=1))
    history.record(db, [chk("bad")], now=t0 + timedelta(days=2))
    since = db.execute(text("SELECT since FROM system_check_state WHERE check_key = :k"), {"k": KEY}).scalar()
    assert since == t0
    history.record(db, [chk("ok")], now=t0 + timedelta(days=3))
    since = db.execute(text("SELECT since FROM system_check_state WHERE check_key = :k"), {"k": KEY}).scalar()
    assert since == t0 + timedelta(days=3)


def test_alert_goes_on_change_not_on_every_run(db):
    """Три ночи подряд упавшая проверка — ОДНО сообщение об отказе и одно о восстановлении (README хендоффа)."""
    t0 = datetime(2026, 11, 14, 2, 0)
    got = []
    got += history.record(db, [chk("ok")], now=t0)
    got += history.record(db, [chk("bad")], now=t0 + timedelta(days=1))
    got += history.record(db, [chk("bad")], now=t0 + timedelta(days=2))
    got += history.record(db, [chk("bad")], now=t0 + timedelta(days=3))
    got += history.record(db, [chk("ok")], now=t0 + timedelta(days=4))
    kinds = [(t["from"], t["to"]) for t in got]
    assert kinds == [("ok", "bad"), ("bad", "ok")]
    assert got[1]["down_since"] == t0 + timedelta(days=1)


def test_day_keeps_the_worst_tone(db):
    t0 = datetime(2026, 11, 14, 6, 0)            # 09:00 МСК
    history.record(db, [chk("ok")], now=t0)
    history.record(db, [chk("bad")], now=t0 + timedelta(hours=1))
    history.record(db, [chk("ok")], now=t0 + timedelta(hours=2))
    tone = db.execute(text("SELECT tone FROM system_check_day WHERE check_key = :k"), {"k": KEY}).scalar()
    assert tone == "bad"


def test_read_gives_fourteen_days_oldest_first(db):
    t0 = datetime(2026, 11, 16, 6, 0)
    history.record(db, [chk("bad")], now=t0 - timedelta(days=2))
    history.record(db, [chk("ok")], now=t0)
    h = history.read(db, [KEY], now=t0)[KEY]
    assert len(h["hist"]) == 14
    assert h["hist"][-1] == {"day": "2026-11-16", "tone": "ok"}
    assert h["hist"][-3] == {"day": "2026-11-14", "tone": "bad"}
    assert h["hist"][0]["tone"] is None          # данных нет — не «норма»
    assert "14.11" in h["last_failure"]


# ── подпись «с какого момента» ────────────────────────────────────────────────

NOW = datetime(2026, 11, 16, 17, 0)               # 20:00 МСК


def test_since_label_counts_days_inclusive():
    assert history.since_label("bad", "jobs", datetime(2026, 11, 14, 2, 0), NOW) == "с 14.11 · 3 дня"


def test_since_label_today_shows_time_msk():
    assert history.since_label("bad", "jobs", datetime(2026, 11, 16, 11, 5), NOW) == "с 14:05"


def test_since_label_for_keys_is_yellow_since():
    assert history.since_label("warn", "keys", datetime(2026, 11, 7, 6, 0), NOW) == "жёлтый с 07.11"


def test_since_label_none_when_ok():
    assert history.since_label("ok", "jobs", datetime(2026, 11, 1), NOW) is None


# ── прогноз диска ─────────────────────────────────────────────────────────────

GB = 2 ** 30


def test_forecast_linear_growth_to_yellow_threshold():
    """79 ГБ, занято 41, рост ровно 1 ГБ в неделю. Жёлтый — свободно 20 %, т.е. занято 63,2 ГБ: 22,2 недели."""
    d0 = date(2026, 10, 19)
    samples = [(d0 + timedelta(days=i), int((41 - 4 + i / 7) * GB), 79 * GB) for i in range(29)]
    f = disk.forecast(samples)
    assert round(f["growth_gb_week"], 2) == 1.0
    assert round(f["weeks_to_warn"], 1) == 22.2


def test_forecast_flat_growth_says_not_noticeable():
    d0 = date(2026, 10, 19)
    f = disk.forecast([(d0 + timedelta(days=i), 41 * GB, 79 * GB) for i in range(29)])
    assert f["flat"] is True and f["weeks_to_warn"] is None


def test_forecast_needs_a_week_of_samples():
    d0 = date(2026, 11, 14)
    assert disk.forecast([(d0 + timedelta(days=i), 41 * GB, 79 * GB) for i in range(3)]) is None


# ── оповещения ────────────────────────────────────────────────────────────────

def test_alert_settings_gate_each_kind():
    tr = [{"key": "a", "from": "ok", "to": "bad"}, {"key": "b", "from": "bad", "to": "ok"}]
    assert [e for e, _ in alerts.plan(tr, {"bad": True, "ok": False, "tg": True, "mail": False})] == ["system_check_failed"]
    assert [e for e, _ in alerts.plan(tr, {"bad": True, "ok": True, "tg": False, "mail": False})] == []   # нет каналов


def test_warn_to_ok_is_not_a_recovery_alert():
    """«Вернулось в норму» — после ОТКАЗА; снятое предупреждение уходит сводкой, а не тревогой."""
    tr = [{"key": "b", "from": "warn", "to": "ok"}]
    assert alerts.plan(tr, {"bad": True, "ok": True, "tg": True, "mail": True}) == []


# ── ручной запуск ─────────────────────────────────────────────────────────────

def test_second_run_of_the_same_job_is_refused(db):
    jobs.start(db, "t_v2_job", None, spawn=False)
    with pytest.raises(jobs.AlreadyRunning):
        jobs.start(db, "t_v2_job", None, spawn=False)


def test_stale_run_does_not_block_forever(db):
    """Бэкенд перезапустился посреди задания — строка не закрылась. Через 3 часа она не мешает запуску."""
    db.execute(text("INSERT INTO system_job_run (job_key, started_at) VALUES ('t_v2_job', now() - interval '4 hours')"))
    db.commit()
    jobs.start(db, "t_v2_job", None, spawn=False)
    rows = db.execute(text("SELECT finished_at IS NULL, ok, error FROM system_job_run WHERE job_key='t_v2_job' "
                           "ORDER BY started_at")).all()
    assert len(rows) == 2
    assert rows[0][0] is False and rows[0][1] is False and "оборвался" in rows[0][2]   # зависший закрыт
    assert rows[1][0] is True                                                         # новый идёт
