# -*- coding: utf-8 -*-
"""Доступность сайтов площадок (владелец 30.09.2026): решение по одной проверке, адрес из
домена, тревога только на СМЕНЕ состояния, антибот — без тревоги. Сеть подменена."""
import pytest
from sqlalchemy import text

import app.main  # noqa: F401 — все модели в реестре SQLAlchemy
from app.database import SessionLocal
from app.traffic import site_monitor as sm


def http_code(code):
    return lambda url: {"http_status": code, "final_url": url}


def http_fail(url):
    raise OSError("connection refused")


def browser_code(code):
    return lambda url: {"status": code, "final_url": url, "title": ""}


def test_ok_by_plain_request_does_not_touch_browser():
    def no_browser(url):
        raise AssertionError("браузер звать не нужно")
    r = sm.check("https://a.ru", "http", http=http_code(200), browser=no_browser)
    assert r["status"] == sm.OK and r["method"] == "http"


def test_server_error_is_down_without_browser():
    r = sm.check("https://a.ru", "http", http=http_code(502), browser=browser_code(200))
    assert r["status"] == sm.DOWN


def test_403_goes_to_browser_and_is_antibot_if_browser_passes():
    r = sm.check("https://a.ru", "http", http=http_code(403), browser=browser_code(200))
    assert r["status"] == sm.ANTIBOT and r["method"] == "browser"


def test_browser_mode_ok_is_ok_not_antibot():
    r = sm.check("https://a.ru", "browser", http=http_code(200), browser=browser_code(200))
    assert r["status"] == sm.OK


def test_browser_401_is_antibot_not_down():
    r = sm.check("https://a.ru", "browser", http=http_code(200), browser=browser_code(401))
    assert r["status"] == sm.ANTIBOT, "антибот — отметка, а не ложная тревога"


def test_network_failure_then_browser_failure_is_down():
    r = sm.check("https://a.ru", "http", http=http_fail,
                 browser=lambda u: {"status": None, "error": "ERR_CONNECTION_REFUSED"})
    assert r["status"] == sm.DOWN and "REFUSED" in r["message"]


def test_site_url_handles_cyrillic_and_scheme():
    assert sm.site_url("009.рф") == "https://009.xn--p1ai"
    assert sm.site_url("https://Maksavit.ru/catalog") == "https://maksavit.ru"
    assert sm.site_url("") is None


@pytest.fixture
def db(monkeypatch):
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def test_alert_only_on_change(db, monkeypatch):
    sent = []
    import app.notify.bus as bus
    monkeypatch.setattr(bus, "emit", lambda db_, key, **kw: sent.append(key) or [])
    t = sm.targets(db)
    if not t:
        pytest.skip("нет сайтов для проверки")
    url = t[0]["url"]
    db.execute(text("DELETE FROM site_checks WHERE url = :u"), {"u": url})
    sm.run(db, only_url=url, http=http_code(502), browser=browser_code(502))
    sm.run(db, only_url=url, http=http_code(502), browser=browser_code(502))
    assert sent == ["site_down"], "вторая неудача подряд тревогу не повторяет"
    sm.run(db, only_url=url, http=http_code(200), browser=browser_code(200))
    assert sent == ["site_down", "site_recovered"]
    sm.run(db, only_url=url, http=http_code(403), browser=browser_code(200))
    assert sent == ["site_down", "site_recovered"], "антибот — без тревоги"


def test_down_publishers_feeds_queue_alert(db, monkeypatch):
    import app.notify.bus as bus
    monkeypatch.setattr(bus, "emit", lambda *a, **k: [])
    t = [x for x in sm.targets(db) if x.get("publisher_id")]
    if not t:
        pytest.skip("нет площадок реестра в проверке")
    sm.run(db, only_url=t[0]["url"], http=http_code(503), browser=browser_code(503))
    assert t[0]["publisher_id"] in sm.down_publishers(db)


def test_dsp_missing_alerts_on_change_and_respects_exclusions(db, monkeypatch):
    from datetime import date, timedelta
    sent = []
    import app.notify.bus as bus
    monkeypatch.setattr(bus, "emit", lambda db_, key, **kw: sent.append(kw["title"]) or [])
    db.execute(text("DELETE FROM company_settings WHERE key = :k"), {"k": sm.SETTING_DSP_STATE})
    db.execute(text("INSERT INTO company_settings (key, value) VALUES (:k, 'adfox.ru') "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
               {"k": sm.SETTING_DSP_EXCLUDE})
    y = date.today() - timedelta(days=1)
    data = {y: {"a.ru", "b.ru", "https://adfox.ru"}, date.today(): {"a.ru"}}
    r = sm.dsp_missing(db, fetch=lambda d: data[d])
    assert r["missing"] == ["b.ru"], "adfox.ru в исключениях"
    sm.dsp_missing(db, fetch=lambda d: data[d])
    assert len(sent) == 1, "тот же список — без повтора"
    data[date.today()] = {"a.ru", "b.ru"}
    sm.dsp_missing(db, fetch=lambda d: data[d])
    assert len(sent) == 2 and "восстановились" in sent[-1]


def test_dsp_not_configured_says_so(monkeypatch, db):
    for k in sm.DSP_ENV:
        monkeypatch.delenv(k, raising=False)
    assert sm.dsp_missing(db) == {"configured": False}
