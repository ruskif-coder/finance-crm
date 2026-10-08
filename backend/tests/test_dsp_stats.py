# -*- coding: utf-8 -*-
"""Съём статистики DSP: разбор ответа, окно дней, сшивка по площадкам, повтор без удвоения.

Проект — `docs/ПРОЕКТ_сбор_статистики_DSP.md`. Главные приборы — сквозной прогон на двух
живых базах стенда с поддельным DSP: два прогона подряд дают те же числа, прежний хеш
креатива (перевыгрузка) не теряет показы, чужой креатив ложится остатком без площадки,
а кампания, не вернувшаяся в ответе, не сдвигает курсор.
"""
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.dsp import stat_store as store
from app.dsp import stats as S
from app.dsp.client import PROD, MsClient, _redact

CAMP = "TESTSTATCAMP0001"
CR1, CR1_OLD, CR2 = "TESTSTATCR000001", "TESTSTATCROLD001", "TESTSTATCR000002"
PARTNER = "TESTSTATPARTNER1"
D0 = date(2026, 9, 20)
TODAY = D0 + timedelta(days=4)


# ── разбор ответа ──────────────────────────────────────────────────────────
def test_parse_missing_is_not_zero_and_total_ignored():
    res = {"total": {"show": 999},
           "aaaa000000000001": {"show": 12, "click": 1, "spent": 4.8999999999999995}}
    got, miss = S.parse(res, ["AAAA000000000001", "BBBB000000000002"])
    assert got == {"AAAA000000000001": S.Numbers(12, 1, Decimal("4.90"))}
    assert miss == ["BBBB000000000002"], "спрошенный и не пришедший хеш — «нет данных»"


def test_parse_reads_offered_traffic_and_keeps_none_when_absent():
    res = {"aaaa000000000001": {"show": 12, "click": 1, "spent": 1, "bid_statistic": 13950},
           "aaaa000000000002": {"show": 0, "click": 0, "spent": 0, "bid_statistic": 0},
           "aaaa000000000003": {"show": 5, "click": 0, "spent": 0}}
    got, _ = S.parse(res, ["AAAA000000000001", "AAAA000000000002", "AAAA000000000003"])
    assert got["AAAA000000000001"].offered == 13950
    assert got["AAAA000000000002"].offered == 0, "предложено ноль — это значение, а не «нет данных»"
    assert got["AAAA000000000003"].offered is None


class _Batches:
    contour, partner_xxhash = PROD, PARTNER

    def __init__(self):
        self.calls = []

    def statistic_get_period(self, hashes, a, b):
        self.calls.append((list(hashes), a, b))
        return {h: {"show": 1, "click": 0, "spent": 0} for h in hashes}


def test_campaigns_never_share_a_call_with_creatives():
    """Замер 27.09.2026: кампании в одном вызове с креативами молча выпадают."""
    c = _Batches()
    crs = [f"C{i:015d}" for i in range(7)]
    pull = S.pull_day(c, D0, crs, ["K000000000000001"], batch=3)
    assert [len(x[0]) for x in c.calls] == [3, 3, 1, 1]
    assert c.calls[-1][0] == ["K000000000000001"]
    assert all(a == b == D0 for _, a, b in c.calls), "сутки — это from = to"
    assert len(pull.creatives) == 7 and len(pull.campaigns) == 1


# ── окно дней ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("start,end,today,cursor,expect", [
    (D0, D0 + timedelta(10), D0, None, None),                             # ещё не стартовала
    (D0, D0 + timedelta(10), D0 + timedelta(1), None, (D0, D0)),          # вчера — первый день
    (D0, D0 + timedelta(10), D0 + timedelta(6), D0 + timedelta(4),        # перезабор 3 суток
     (D0 + timedelta(3), D0 + timedelta(5))),
    (D0, D0 + timedelta(10), D0 + timedelta(8), D0 + timedelta(1),        # догон по курсору
     (D0 + timedelta(2), D0 + timedelta(7))),
    (D0, D0 + timedelta(2), D0 + timedelta(5), D0 + timedelta(2),         # после конца — досчёт
     (D0, D0 + timedelta(2))),
    (D0, D0 + timedelta(2), D0 + timedelta(7), D0 + timedelta(2), None),  # вышла из сбора
])
def test_window(start, end, today, cursor, expect):
    assert store.window_for(start, end, today, cursor) == expect


def test_today_is_never_collected():
    for cur in (None, D0 + timedelta(5)):
        w = store.window_for(D0, D0 + timedelta(30), D0 + timedelta(6), cur)
        assert w[1] == D0 + timedelta(5)


# ── токены не попадают в журнал ────────────────────────────────────────────
def test_redact_strips_tokens_deep_and_keeps_original():
    resp = {"result": {"user": {"auth_token": "SECRET", "name": "x"},
                       "list": [{"access_token": "S2"}], "refresh_token": ""}}
    red = _redact(resp)
    assert "SECRET" not in str(red) and "S2" not in str(red)
    assert red["result"]["user"]["name"] == "x"
    assert resp["result"]["user"]["auth_token"] == "SECRET", "ответ вызывающему не трогается"


class _Eng:
    def __init__(self):
        self.rows = []

    @contextmanager
    def begin(self):
        eng = self

        class _C:
            def execute(self, _sql, params=None):
                eng.rows.append(params)
        yield _C()


def test_journal_row_has_no_token():
    eng = _Eng()
    c = MsClient(url="http://x", token="t", partner_xxhash=PARTNER, journal_engine=eng,
                 transport=lambda m, b: {"result": {"auth_token": "LEAK", "methods": []}})
    assert c.call("User.getInfo", {})["auth_token"] == "LEAK"
    assert eng.rows and "LEAK" not in str(eng.rows[0]["rs"])


# ── сквозной прогон на базах стенда ────────────────────────────────────────
class FakeDsp:
    contour, partner_xxhash = PROD, PARTNER

    def __init__(self, data):
        self.data = data            # {день: {хеш: показы}}

    def statistic_get_period(self, hashes, a, b):
        day = self.data.get(a, {})
        return {h: {"show": day[h], "click": 0, "spent": day[h] / 10}
                for h in hashes if h in day}


def _dsp():
    from app.dsp.db import DspSessionLocal, dsp_engine
    try:
        dsp_engine()
    except Exception:
        pytest.skip("аналитическая база недоступна")
    return DspSessionLocal()


@pytest.fixture()
def world():
    import app.main  # noqa: F401 — реестр моделей целиком, иначе FK на sales_deals не найдётся
    from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement
    from app.database import SessionLocal
    dsp_db = _dsp()
    db = SessionLocal()
    deal_id = db.execute(text(
        "SELECT d.id FROM sales_deals d LEFT JOIN ad_campaign c ON c.deal_id = d.id "
        "WHERE c.id IS NULL ORDER BY d.id LIMIT 1")).scalar()
    pubs = db.execute(text("SELECT id FROM sales_publishers ORDER BY id LIMIT 2")).scalars().all()
    if not deal_id or len(pubs) < 2:
        pytest.skip("нет свободной сделки или двух площадок")
    c = AdCampaign(deal_id=deal_id, status="запущена", plan_show=1000, date_start=D0,
                   date_end=D0 + timedelta(days=2), ms_campaign_xxhash=CAMP)
    db.add(c)
    db.flush()
    pls = []
    for pub in pubs:
        pl = AdCampaignPlacement(campaign_id=c.id, publisher_id=pub, weight=1,
                                 status="запущена", plan_show=500)
        db.add(pl)
        db.flush()
        pls.append(pl)
    cr1 = AdCampaignCreative(campaign_id=c.id, placement_id=pls[0].id, creative_no=1,
                             status="согласован", ms_creative_xxhash=CR1)
    cr2 = AdCampaignCreative(campaign_id=c.id, placement_id=pls[1].id, creative_no=1,
                             status="согласован", ms_creative_xxhash=CR2)
    db.add_all([cr1, cr2])
    db.commit()
    cid = c.id
    # Прежний хеш первого креатива — до перевыгрузки. Живёт только в журнале.
    dsp_db.execute(text(
        "INSERT INTO dsp_send_log (contour, method, entity_type, local_ref, request, "
        "ms_xxhash, ok) VALUES ('prod', 'Creative.add', 'creative', :lr, "
        "CAST(:rq AS jsonb), :xx, true)"),
        {"lr": f"cr{cr1.id}", "xx": CR1_OLD,
         "rq": '{"params": {"partner_xxhash": "%s"}}' % PARTNER})
    dsp_db.commit()
    try:
        yield db, dsp_db, c, pls
    finally:
        # Сначала аналитическая база: её строки держат блокировки, и оборвавшаяся уборка
        # оставила бы следующий тест ждать их вечно. Журнал — по выдуманному клиенту
        # кабинета, без обращения к объектам основной базы (они уже могут быть удалены).
        dsp_db.rollback()
        dsp_db.execute(text("DELETE FROM dsp_stat_raw WHERE ms_campaign_xxhash = :h"), {"h": CAMP})
        dsp_db.execute(text("DELETE FROM dsp_sync_cursor WHERE ms_campaign_xxhash = :h"),
                       {"h": CAMP})
        dsp_db.execute(text("DELETE FROM dsp_send_log "
                            "WHERE request->'params'->>'partner_xxhash' = :px"), {"px": PARTNER})
        dsp_db.commit()
        dsp_db.close()
        db.rollback()
        db.execute(text("DELETE FROM ad_campaign WHERE id = :c"), {"c": cid})
        db.commit()
        db.close()


def _fact(db, cid):
    rows = db.execute(text(
        "SELECT placement_id, date, shows FROM ad_campaign_stat "
        "WHERE campaign_id = :c AND source = 'dsp'"), {"c": cid}).all()
    return {(p, d): s for p, d, s in rows}


def _cursor(dsp_db):
    return dsp_db.execute(text("SELECT last_pulled_ts FROM dsp_sync_cursor "
                               "WHERE ms_campaign_xxhash = :h"), {"h": CAMP}).scalar()


def test_sync_spreads_by_placement_and_repeats_without_doubling(world):
    db, dsp_db, c, (p1, p2) = world
    d1, d2 = D0 + timedelta(1), D0 + timedelta(2)
    data = {D0: {CR1: 100, CR1_OLD: 10, CR2: 50, CAMP: 180},
            d1: {CR1: 0, CR1_OLD: 0, CR2: 0, CAMP: 0},
            d2: {CR1: 5, CR1_OLD: 0, CR2: 0, CAMP: 5}}
    out = store.sync(db, dsp_db, FakeDsp(data), TODAY)
    want = {(p1.id, D0): 110, (p2.id, D0): 50, (None, D0): 20, (p1.id, d2): 5}
    assert _fact(db, c.id) == want, "прежний хеш потерян, остаток не лёг или ноль записан"
    assert out["unassigned"] == {c.id: 20}
    assert _cursor(dsp_db) is not None

    store.sync(db, dsp_db, FakeDsp(data), TODAY)
    assert _fact(db, c.id) == want, "повторный прогон изменил числа — удвоение"


def test_zero_after_recount_removes_row(world):
    db, dsp_db, c, (p1, p2) = world
    store.sync(db, dsp_db, FakeDsp({D0: {CR1: 100, CR1_OLD: 0, CR2: 50, CAMP: 170}}), TODAY)
    assert _fact(db, c.id)[(None, D0)] == 20
    store.sync(db, dsp_db, FakeDsp({D0: {CR1: 100, CR1_OLD: 0, CR2: 0, CAMP: 100}}), TODAY)
    f = _fact(db, c.id)
    assert (p2.id, D0) not in f and (None, D0) not in f, "досчёт до нуля оставил старое число"
    assert f[(p1.id, D0)] == 100


def test_missing_campaign_does_not_move_cursor(world):
    db, dsp_db, c, _ = world
    out = store.sync(db, dsp_db, FakeDsp({D0: {CR1: 7, CR1_OLD: 0, CR2: 0}}), TODAY)
    assert out["failed_campaigns"] == {CAMP: D0.isoformat()}
    assert _cursor(dsp_db) is None, "сутки без итога кампании сочтены забранными"


# ── экран состояния ────────────────────────────────────────────────────────
@pytest.mark.parametrize("last,tone", [
    (None, "idle"),
    ({"hours": 40}, "bad"),
    ({"error": "DSP_API_URL / DSP_ACCESS_TOKEN не заданы"}, "bad"),
    ({"failed": ["TESTSTATCAMP0001 с 2026-09-20"]}, "bad"),
    ({"unassigned": {"45": 20}}, "warn"),
    ({}, "ok"),
])
def test_status_shows_the_last_run(last, tone):
    import json
    from datetime import datetime

    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.system.status import check_dsp_stats
    db = SessionLocal()
    prev = db.execute(text("SELECT value FROM company_settings WHERE key = 'dsp_stat_last'")).scalar()
    try:
        db.execute(text("DELETE FROM company_settings WHERE key = 'dsp_stat_last'"))
        if last is not None:
            at = datetime.utcnow() - timedelta(hours=last.pop("hours", 1))
            db.execute(text("INSERT INTO company_settings (key, value) VALUES ('dsp_stat_last', :v)"),
                       {"v": json.dumps({"at": at.isoformat(), "campaigns": 1, "shows": 5, **last})})
        db.commit()
        assert check_dsp_stats(db)["tone"] == tone
    finally:
        db.execute(text("DELETE FROM company_settings WHERE key = 'dsp_stat_last'"))
        if prev is not None:
            db.execute(text("INSERT INTO company_settings (key, value) VALUES ('dsp_stat_last', :v)"),
                       {"v": prev})
        db.commit()
        db.close()


# ── находки ревью 28.09.2026 ───────────────────────────────────────────────
class FlakyDsp(FakeDsp):
    """DSP отказывает на одних сутках — остальные обязаны лечь."""
    def __init__(self, data, bad_day):
        super().__init__(data)
        self.bad_day = bad_day

    def statistic_get_period(self, hashes, a, b):
        from app.dsp.client import MsError
        if a == self.bad_day:
            raise MsError("Statistic.getPeriod: timeout")
        return super().statistic_get_period(hashes, a, b)


def test_one_bad_day_does_not_sink_the_others(world):
    db, dsp_db, c, (p1, _) = world
    d2 = D0 + timedelta(2)
    data = {D0: {CR1: 9, CR1_OLD: 0, CR2: 0, CAMP: 9}, d2: {CR1: 4, CR1_OLD: 0, CR2: 0, CAMP: 4}}
    out = store.sync(db, dsp_db, FlakyDsp(data, D0 + timedelta(1)), TODAY)
    f = _fact(db, c.id)
    assert f[(p1.id, D0)] == 9 and f[(p1.id, d2)] == 4
    assert out["errors"] and CAMP in out["failed_campaigns"]
    assert _cursor(dsp_db) is None, "сутки с отказом сочтены забранными"


def test_manual_range_neither_moves_cursor_nor_takes_today(world):
    db, dsp_db, c, _ = world
    t = store.targets(db, dsp_db, D0 + timedelta(1), c.id, D0, D0 + timedelta(5))
    assert [(x.start, x.end) for x in t] == [(D0, D0)], "ручной отрезок зашёл в незакрытые сутки"
    store.sync(db, dsp_db, FakeDsp({D0: {CR1: 1, CR1_OLD: 0, CR2: 0, CAMP: 1}}), TODAY,
               campaign_id=c.id, start=D0, end=D0)
    assert _cursor(dsp_db) is None, "ручной добор сдвинул курсор — дни до него ночь не заберёт"
