# -*- coding: utf-8 -*-
"""Проверка баннера после заливки в DSP (владелец 15.11.2026): очередь, слова проблем, уведомление трафику.

Браузер (сайдкар) и DSP подменяются: здесь проверяется решение «прошёл / нет», а не рендер."""
import pytest

from app.dsp import banner_check as bc

GOOD = {"plaque": True, "n_btns": 1, "styled": 1, "plaque_on_top": True, "erid_shown": True,
        "plaque_click_navigates": False, "center_ok": True}
ONE = '<head><script src="https://s.dsp.example/engine/viewability.js"></script></head><body>x</body>'


def test_all_good_is_ok():
    assert bc.problems_of({"300x600": GOOD, "970x250": GOOD}, ONE) == {}


@pytest.mark.parametrize("raw, word", [
    ({"plaque": False}, "нет плашки «Реклама»"),
    ({**GOOD, "plaque_on_top": False, "cover": "DIV.bg", "erid_shown": None}, "плашка «Реклама» перекрыта (DIV.bg)"),
    ({**GOOD, "erid_shown": False}, "клик по плашке не раскрывает ЕРИД"),
    ({**GOOD, "plaque_click_navigates": True}, "клик по плашке уводит на посадочную"),
    ({**GOOD, "center_ok": False}, "клик по баннеру не ведёт на посадочную"),
    ({"error": "Timeout 45000ms"}, "не отрисовался: Timeout 45000ms"),
])
def test_each_failure_has_its_word(raw, word):
    assert word in bc.problems_of({"300x600": raw}, ONE)["300x600"]


def test_viewability_count_is_checked_on_the_markup():
    two = ONE.replace("</head>", '<script src="https://s.dsp.example/engine/viewability.js"></script></head>')
    assert bc.problems_of({"300x600": GOOD}, two) == {"разметка": ["скриптов видимости 2, нужен один"]}
    assert bc.problems_of({"300x600": GOOD}, "<body>x</body>") == {"разметка": ["нет скрипта видимости"]}


def test_request_rules_come_from_settings_not_code():
    opts = bc.request_rules("https://static.dsp.example/engine/viewability.js",
                            ['<script src="https://counter.example/afcar/qq.js"></script>', ""])
    assert opts == {"allow_urls": ["https://static.dsp.example/engine/viewability.js"], "block_domain": "dsp.example",
                    "block_hosts": ["counter.example"]}


# --- очередь и прогон -------------------------------------------------------------------------------------------

class FakeDsp:
    def __init__(self, html):
        self.html = html

    def creative_get_info(self, xx):
        return {"data": {"html_code": self.html}}


@pytest.fixture
def creative(db):
    """Креатив стенда; его строку проверки тест пишет по-настоящему (run коммитит) — после теста возвращаем как было."""
    from sqlalchemy import text
    cid = db.execute(text("SELECT id FROM ad_campaign_creative WHERE coalesce(ms_creative_xxhash,'') <> '' "
                          "ORDER BY id LIMIT 1")).scalar()
    if cid is None:
        pytest.skip("в базе нет креатива, заведённого в DSP")
    keep = db.execute(text("SELECT html_hash, checked_at, ok, problems::text FROM dsp_banner_check WHERE creative_id = :c"),
                      {"c": cid}).first()
    yield cid
    db.rollback()
    db.execute(text("DELETE FROM dsp_banner_check WHERE creative_id = :c"), {"c": cid})
    if keep:
        db.execute(text("INSERT INTO dsp_banner_check (creative_id, html_hash, checked_at, ok, problems) "
                        "VALUES (:c, :h, :t, :o, CAST(:p AS jsonb))"),
                   {"c": cid, "h": keep[0], "t": keep[1], "o": keep[2], "p": keep[3]})
    db.commit()


def test_enqueue_then_run_stores_result_and_notifies_on_failure(db, creative, monkeypatch):
    from app.dsp.banner_check_models import DspBannerCheck
    sent = []
    monkeypatch.setattr(bc, "_notify", lambda db, row, problems: sent.append(problems))
    monkeypatch.setattr(bc, "render", lambda html, erid, opts: {"300x600": {**GOOD, "center_ok": False}})
    bc.enqueue(db, creative)
    row = db.query(DspBannerCheck).filter_by(creative_id=creative).one()
    assert row.checked_at is None and row.ok is None
    rep = bc.run(db, client=FakeDsp(ONE), limit=50, only=[creative])
    db.refresh(row)
    assert rep["checked"] == 1 and row.ok is False and row.checked_at is not None
    assert row.problems == {"300x600": ["клик по баннеру не ведёт на посадочную"]}
    assert row.html_hash == bc.html_hash(ONE)
    assert sent == [row.problems]
    # повторная заливка возвращает креатив в очередь; исправный — без уведомления
    bc.enqueue(db, creative)
    monkeypatch.setattr(bc, "render", lambda html, erid, opts: {"300x600": GOOD})
    bc.run(db, client=FakeDsp(ONE), limit=50, only=[creative])
    db.refresh(row)
    assert row.ok is True and row.problems is None and len(sent) == 1


def test_sidecar_failure_keeps_the_creative_in_queue(db, creative, monkeypatch):
    from app.dsp.banner_check_models import DspBannerCheck

    def boom(html, erid, opts):
        raise bc.BannerCheckError("сайдкар не ответил")
    monkeypatch.setattr(bc, "render", boom)
    bc.enqueue(db, creative)
    rep = bc.run(db, client=FakeDsp(ONE), limit=50, only=[creative])
    row = db.query(DspBannerCheck).filter_by(creative_id=creative).one()
    assert rep["failed"] == 1 and row.checked_at is None


def test_empty_markup_is_a_problem_not_a_crash(db, creative, monkeypatch):
    from app.dsp.banner_check_models import DspBannerCheck
    monkeypatch.setattr(bc, "_notify", lambda *a: None)
    bc.enqueue(db, creative)
    bc.run(db, client=FakeDsp(""), limit=50, only=[creative])
    row = db.query(DspBannerCheck).filter_by(creative_id=creative).one()
    assert row.ok is False and row.problems == {"разметка": ["пустая разметка в DSP"]}


def test_sdk_deeplink_is_a_valid_click_link():
    """16.11.2026: у app-площадок в режиме «sdk» ссылка клика — диплинк SDK с {LINK_ESC} (подставляется вторым шагом
    выгрузки), клик ведёт в приложение. Альфазокс 5T7LXJ × aptekabv/apteka25/minicen/newapteka ложно краснел."""
    sdk = ("deeplink+://navigate?primaryUrl=aHR0cHM6Ly9hcHRla2Fidi5ydS90b3Zhci83NDMxMTI=&primaryTrackingUrl={LINK_ESC}")
    assert bc.problems_of({"300x600": {**GOOD, "center_ok": False, "center_href": sdk}}, ONE) == {}


def test_other_links_at_the_center_are_still_a_problem():
    for href in (None, "https://other.example/", "deeplink+://navigate?primaryUrl=x"):    # без макроса — клик не посчитается
        p = bc.problems_of({"300x600": {**GOOD, "center_ok": False, "center_href": href}}, ONE)
        assert p == {"300x600": ["клик по баннеру не ведёт на посадочную"]}, href
