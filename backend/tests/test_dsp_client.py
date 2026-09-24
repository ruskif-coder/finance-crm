"""Контур «DSP-коннектор», этап 2b: клиент МС + заведение РК + журнал — без сети.

Транспорт подменный; журнал и хеш проверяются на РЕАЛЬНЫХ локальных базах (аналит. dsp_analytics
и основная finance) с уборкой/откатом. Живой МС не трогаем: токена в окружении нет и не должно
быть в тестах.
"""
import os
from datetime import date, timedelta

import pytest
from sqlalchemy import text

import app.models  # noqa: F401
import app.launch_prep.models  # noqa: F401
from app.ad.models import AdCampaign
from app.database import SessionLocal
from app.dsp.campaigns import build_campaign_params, campaign_title, ensure_campaign
from app.dsp.client import MsClient, MsError
from app.sales.models import SalesDeal

XX = "ABCDEF0123456789"
TEST_PARTNER = "TESTPARTNER00001"   # НЕ реальный partner_xxhash — по нему же и убираем журнал
HAS_DSP = bool(os.getenv("DSP_DATABASE_URL"))


class FakeTransport:
    """Подменный МС: отдаёт заготовленные ответы, помнит тела запросов."""
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    def __call__(self, method, body):
        self.calls.append((method, body))
        r = self.responses[method]
        return r(body) if callable(r) else r


def _client(responses, journal=True):
    eng = None
    if journal and HAS_DSP:
        from app.dsp.db import dsp_engine
        eng = dsp_engine()
    t = FakeTransport(responses)
    c = MsClient(url="https://example.invalid/api/v2/", token="t", partner_xxhash=TEST_PARTNER,
                 transport=t, journal_engine=eng, journal=bool(journal and HAS_DSP))
    return c, t


def _cleanup_journal(local_ref=None):
    """Убираем ВСЁ, что породили тесты: по тестовому партнёру в теле запроса, по TEST-ref
    и по конкретному ref (у списка/таргетинга local_ref может быть не наш id)."""
    if not HAS_DSP:
        return
    from app.dsp.db import dsp_engine
    with dsp_engine().begin() as c:
        c.execute(text("DELETE FROM dsp_send_log WHERE request->'params'->>'partner_xxhash' = :tp "
                       "OR local_ref = :tp OR local_ref LIKE 'TEST-%' OR local_ref = :lr"),
                  {"tp": TEST_PARTNER, "lr": (str(local_ref) if local_ref is not None else "")})


@pytest.fixture(autouse=True)
def _journal_hygiene():
    _cleanup_journal()
    yield
    _cleanup_journal()


# ── клиент ────────────────────────────────────────────────────────────────

def test_call_envelope_and_result_is_plain_xxhash():
    c, t = _client({"Campaign.add": {"jsonrpc": "2.0", "result": XX.lower(), "id": 1}}, journal=False)
    got = c.campaign_add({"title": "x"}, local_ref="TEST-env")
    assert got == XX  # нормализуем к верхнему регистру
    method, body = t.calls[0]
    assert method == "Campaign.add"
    assert body["jsonrpc"] == "2.0" and body["method"] == "Campaign.add" and body["id"] == 1
    assert body["params"]["partner_xxhash"] == TEST_PARTNER  # партнёр подставлен клиентом


def test_jsonrpc_error_raises_and_no_xxhash_on_garbage():
    c, _ = _client({"Campaign.add": {"jsonrpc": "2.0", "error": {"code": -1, "message": "bad"}, "id": 1}},
                   journal=False)
    with pytest.raises(MsError):
        c.campaign_add({"title": "x"})
    c2, _ = _client({"Campaign.add": {"jsonrpc": "2.0", "result": {"ok": True}, "id": 1}}, journal=False)
    with pytest.raises(MsError):  # result без xxhash — не считаем успехом
        c2.campaign_add({"title": "x"})


def test_set_status_validates_enum():
    c, _ = _client({}, journal=False)
    with pytest.raises(MsError):
        c.campaign_set_status(XX, "PAUSED")  # такого статуса у МС нет


@pytest.mark.skipif(not HAS_DSP, reason="нет DSP_DATABASE_URL — аналит. база не подключена")
def test_journal_row_written_with_xxhash():
    ref = "TEST-journal-1"
    _cleanup_journal(ref)
    try:
        c, _ = _client({"Campaign.add": {"jsonrpc": "2.0", "result": XX, "id": 1}})
        c.campaign_add({"title": "j"}, local_ref=ref)
        from app.dsp.db import dsp_engine
        with dsp_engine().connect() as conn:
            row = conn.execute(text(
                "SELECT method, entity_type, ok, ms_xxhash, request->'params'->>'title' AS t, "
                "response->>'result' AS r FROM dsp_send_log WHERE local_ref=:lr ORDER BY ts DESC LIMIT 1"),
                {"lr": ref}).mappings().one()
        assert row["method"] == "Campaign.add" and row["entity_type"] == "campaign"
        assert row["ok"] is True and row["ms_xxhash"] == XX and row["t"] == "j" and row["r"] == XX
        assert c.last_ok_xxhash("Campaign.add", "campaign", ref) == XX
    finally:
        _cleanup_journal(ref)


# ── параметры РК ──────────────────────────────────────────────────────────

def _camp(deal_id=1, **kw):
    c = AdCampaign(deal_id=deal_id, month=date(2026, 9, 1), date_start=date(2026, 9, 1),
                   date_end=date(2026, 9, 30), plan_show=120000.7, plan_click=1500, plan_budget=250000)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_build_params_plan_total_uniform_pro_no_day_hour():
    deal = SalesDeal(id=1, code="HCLA6E", title="Тестовая сделка")
    p = build_campaign_params(_camp(), deal)
    assert p["status"] == "STOPPED"                                    # запуск — отдельным событием
    assert p["limits"]["traffic_distribution"] == "uniform_pro"       # ЯВНО, default API — accelerated
    assert p["limits"]["show"] == {"total": 120001, "day": 0, "hour": 0}   # план целиком, без day/hour
    assert p["limits"]["click"]["total"] == 1500 and p["limits"]["budget"]["total"] == 250000
    assert p["date_start"] == "2026-09-01" and p["date_end"] == "2026-09-30"
    assert p["title"] == "HCLA6E · Тестовая сделка · 2026-09"


def test_build_params_requires_dates_and_order():
    deal = SalesDeal(id=1, code="X")
    with pytest.raises(MsError):
        build_campaign_params(_camp(date_end=None), deal)
    with pytest.raises(MsError):
        build_campaign_params(_camp(date_start=date(2026, 9, 30), date_end=date(2026, 9, 1)), deal)


def test_title_truncated_to_ms_limit():
    deal = SalesDeal(id=1, code="X", title="Д" * 500)
    assert len(campaign_title(_camp(), deal)) <= 254


# ── заведение РК: хеш ложится в ad_campaign, дубли не плодятся ────────────

def _free_deal(db):
    """Сделка без РК (deal_id в ad_campaign UNIQUE)."""
    used = {r[0] for r in db.query(AdCampaign.deal_id).all()}
    for d in db.query(SalesDeal).order_by(SalesDeal.id).limit(200).all():
        if d.id not in used:
            return d
    pytest.skip("нет свободной сделки для РК")


def test_ensure_campaign_persists_xxhash_and_calls_add_once():
    db = SessionLocal()
    ref = None
    try:
        deal = _free_deal(db)
        camp = _camp(deal_id=deal.id)
        db.add(camp)
        db.flush()
        ref = camp.id
        _cleanup_journal(ref)
        c, t = _client({"Campaign.getListByPartner": {"jsonrpc": "2.0", "result": [], "id": 1},
                        "Campaign.add": {"jsonrpc": "2.0", "result": XX, "id": 2}})
        got = ensure_campaign(db, camp, c, commit=False)
        assert got == XX and camp.ms_campaign_xxhash == XX and camp.ms_synced_at is not None
        assert [m for m, _ in t.calls] == ["Campaign.getListByPartner", "Campaign.add"]
        # второй вызов — хеш уже есть, в МС не ходим
        assert ensure_campaign(db, camp, c, commit=False) == XX
        assert len(t.calls) == 2
    finally:
        db.rollback()
        db.close()
        if ref is not None:
            _cleanup_journal(ref)


def test_ensure_campaign_reuses_title_match_instead_of_add():
    db = SessionLocal()
    ref = None
    try:
        deal = _free_deal(db)
        camp = _camp(deal_id=deal.id)
        db.add(camp)
        db.flush()
        ref = camp.id
        _cleanup_journal(ref)
        title = campaign_title(camp, deal)
        c, t = _client({"Campaign.getListByPartner": {"jsonrpc": "2.0", "result":
                        [{"title": title, "xxhash": "1111222233334444", "status": "STOPPED"}], "id": 1}})
        assert ensure_campaign(db, camp, c, commit=False) == "1111222233334444"
        assert [m for m, _ in t.calls] == ["Campaign.getListByPartner"]  # add не звали
    finally:
        db.rollback()
        db.close()
        if ref is not None:
            _cleanup_journal(ref)


@pytest.mark.skipif(not HAS_DSP, reason="нет DSP_DATABASE_URL")
def test_ensure_campaign_reuses_journal_when_our_commit_was_lost():
    db = SessionLocal()
    ref = None
    try:
        deal = _free_deal(db)
        camp = _camp(deal_id=deal.id)
        db.add(camp)
        db.flush()
        ref = camp.id
        _cleanup_journal(ref)
        from app.dsp.db import dsp_engine
        with dsp_engine().begin() as conn:  # «МС создал, наш коммит не дошёл»
            conn.execute(text("INSERT INTO dsp_send_log (method, entity_type, local_ref, ms_xxhash, ok) "
                              "VALUES ('Campaign.add','campaign',:lr,:xx,true)"), {"lr": str(ref), "xx": XX})
        c, t = _client({})
        assert ensure_campaign(db, camp, c, commit=False) == XX
        assert t.calls == []  # ни списка, ни add — хеш взят из журнала
    finally:
        db.rollback()
        db.close()
        if ref is not None:
            _cleanup_journal(ref)


def test_source_key_setting_single_point():
    from app.dsp.sources import DEFAULT_SOURCE_KEYS, source_key
    db = SessionLocal()
    try:
        assert source_key(db, "web") == "x-simb-web"
        assert source_key(db, "app") in ("x-simb", "xoalt_simb")  # значение — решение владельца
        assert DEFAULT_SOURCE_KEYS["app"] == "x-simb"
    finally:
        db.close()


def test_plan_total_is_never_a_remainder():
    """Правило: на edit шлём ПОЛНЫЙ total, не остаток — params не зависят от факта открутки."""
    deal = SalesDeal(id=1, code="X")
    camp = _camp()
    a = build_campaign_params(camp, deal)["limits"]["show"]["total"]
    camp.date_start = date.today() - timedelta(days=10)  # РК уже «крутится» — total тот же
    camp.date_end = date.today() + timedelta(days=10)
    assert build_campaign_params(camp, deal)["limits"]["show"]["total"] == a


def test_a_definite_refusal_is_journaled_with_an_answer():
    """Ревью 23.09.2026. Строка журнала без ответа значит «ушло, исход неизвестен», и
    повтор создающего вызова по ней запирается. HTTP 4xx — это ответ: DSP отказал, объект
    не создан. Без тела в журнале отказ выглядел бы неизвестностью и запирал зря."""
    import httpx

    from app.dsp.client import MsClient, MsError

    seen = []

    def refuse(method, body):
        req = httpx.Request("POST", "https://dsp.test/")
        raise httpx.HTTPStatusError("400", request=req,
                                    response=httpx.Response(400, request=req, text="bad"))

    def timeout(method, body):
        raise httpx.ReadTimeout("timed out")

    for transport, answered in ((refuse, True), (timeout, False)):
        c = MsClient(url="https://dsp.test/", token="t", partner_xxhash="0" * 16,
                     transport=transport, journal=False)
        c._journal = lambda *a: seen.append(a)
        with pytest.raises(MsError):
            c.call("Campaign.add", {}, entity_type="campaign", local_ref=1)
        resp = seen[-1][4]
        assert (resp is not None) == answered, (transport.__name__, resp)


@pytest.mark.skipif(not HAS_DSP, reason="нет DSP_DATABASE_URL — аналит. база не подключена")
def test_unknown_outcome_reads_the_real_journal():
    """Запрос `unknown_outcome` — по настоящему журналу, а не по подделке: таймаут и
    «успех без хеша» запирают повтор, отказ с ответом и последующий успех — нет."""
    import httpx

    ref = "TEST-unknown-1"
    _cleanup_journal(ref)
    try:
        def timeout(method, body):
            raise httpx.ReadTimeout("timed out")

        c, _ = _client({})
        c._transport = timeout
        with pytest.raises(MsError):
            c.campaign_add({"title": "u"}, local_ref=ref)
        assert c.unknown_outcome("Campaign.add", "campaign", ref) is True

        ok, _ = _client({"Campaign.add": {"jsonrpc": "2.0", "result": XX, "id": 1}})
        ok.campaign_add({"title": "u"}, local_ref=ref)
        assert ok.unknown_outcome("Campaign.add", "campaign", ref) is False

        nohash, _ = _client({"Campaign.add": {"jsonrpc": "2.0", "result": {"x": 1}, "id": 1}})
        with pytest.raises(MsError):
            nohash.campaign_add({"title": "u"}, local_ref=ref)
        assert nohash.unknown_outcome("Campaign.add", "campaign", ref) is True
    finally:
        _cleanup_journal(ref)


@pytest.mark.skipif(not HAS_DSP, reason="нет DSP_DATABASE_URL — аналит. база не подключена")
def test_a_resolution_mark_resets_the_unknown_on_the_real_journal():
    """Отметка «в кабинете нет» — точка сброса: после неё повтор снова разрешён, а
    пакетный поиск для экрана видит то же, что поиск перед вызовом."""
    import httpx

    ref = "TEST-unknown-2"
    _cleanup_journal(ref)
    try:
        def timeout(method, body):
            raise httpx.ReadTimeout("timed out")

        c, _ = _client({})
        c._transport = timeout
        with pytest.raises(MsError):
            c.creative_add("C" * 16, {"title": "u"}, local_ref=ref)
        assert c.unknown_refs("Creative.add", "creative", [ref, "TEST-other"]) == {ref}

        c.journal_raw("Creative.add", "creative", ref, {"resolved_by": "тест"},
                      {"resolved": "not_found"}, None, False, "сверено вручную")
        assert c.unknown_outcome("Creative.add", "creative", ref) is False
        assert c.unknown_refs("Creative.add", "creative", [ref]) == set()
    finally:
        _cleanup_journal(ref)
