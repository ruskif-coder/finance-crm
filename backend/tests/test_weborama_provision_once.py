# -*- coding: utf-8 -*-
"""Weborama: недошедший ответ и двойной клик не дают второй вставки (аудит 23.09.2026).

4.H3 — таймаут закрывал попытку как «отказ» и разрешал повтор, хотя POST мог пройти.
4.H4 — два одновременных нажатия упирались в уникальность реестра только ПОСЛЕ внешнего
       вызова: в кабинете две вставки, у нас 500.
4.M6 — съём статистики читал аккаунт из переменной окружения, а заводили вставки по
       настройке: разойдись они — «легло 0», и никто не видит почему.

Вставку у Weborama не удалить и не переименовать по API: второй счётчик делит показы
одной площадки, и оба числа неверны. Поэтому проверяется число СОЗДАЮЩИХ вызовов.
"""
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import text

import app.models  # noqa: F401 — пользователи для внешнего ключа журнала
from app.database import SessionLocal, engine
from app.weborama import client as wclient
from app.weborama import provision as prov
from app.weborama.models import KIND_INSERTION, WeboramaRef, WeboramaSubmission

ACC = "TESTACC_A4"
LOCAL = 999440


@pytest.fixture
def db():
    s = SessionLocal()
    _purge(s)
    yield s
    _purge(s)
    s.close()


def _purge(s):
    s.rollback()
    s.query(WeboramaRef).filter(WeboramaRef.account_id == ACC).delete()
    s.query(WeboramaSubmission).filter(WeboramaSubmission.account_id == ACC).delete()
    s.commit()


def _client(monkeypatch, answer):
    """Настоящий клиент, подменён только сетевой вызов — чтобы проверялся и разбор
    сетевой ошибки внутри клиента, а не только реакция на готовое исключение."""
    sent = {"n": 0}

    def request(method, url, **kw):
        sent["n"] += 1
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(wclient.httpx, "request", request)
    c = wclient.WcmClient(ACC, email="a@b.c", password="x")
    c._token = "JWT"
    return c, sent


def _ensure(db, c):
    return prov._ensure(db, c, ACC, KIND_INSERTION, LOCAL, "ТЕСТ · вставка",
                        "/advertiser/insertions/placements/json", {"campaign_id": "1"}, None)


def _open(db):
    return db.execute(text(
        "SELECT count(*) FROM weborama_submissions WHERE account_id = :a "
        "AND local_id = :l AND finished_at IS NULL"), {"a": ACC, "l": LOCAL}).scalar()


# ── 4.H3: исход неизвестен — повтор запрещён ────────────────────────────────

@pytest.mark.parametrize("answer", [
    httpx.ReadTimeout("timed out"),
    httpx.Response(502, text="Bad Gateway"),
    httpx.Response(200, json={"status": "ok"}),       # успех без идентификатора
], ids=["таймаут", "502", "200 без id"])
def test_unknown_outcome_keeps_the_attempt_open(db, monkeypatch, answer):
    c, sent = _client(monkeypatch, answer)
    with pytest.raises(prov.ProvisionError):
        _ensure(db, c)
    assert _open(db) == 1, "попытка закрыта — повтор разрешён, а вставка могла создаться"

    with pytest.raises(prov.ProvisionError) as e:
        _ensure(db, c)
    assert sent["n"] == 1, "повтор ушёл в Weborama"
    assert "кабинет" in str(e.value)


def test_their_refusal_closes_the_attempt_and_allows_retry(db, monkeypatch):
    """Отказ — это ответ: вставка точно не создана, повтор разрешён."""
    c, sent = _client(monkeypatch, httpx.Response(400, json={"error": "bad label"}))
    with pytest.raises(prov.ProvisionError):
        _ensure(db, c)
    assert _open(db) == 0
    with pytest.raises(prov.ProvisionError):
        _ensure(db, c)
    assert sent["n"] == 2


# ── 4.H4: одновременное заведение ───────────────────────────────────────────

def test_losing_the_race_is_a_clear_refusal_not_500(db, monkeypatch):
    """Пока шёл наш вызов, параллельный запрос успел записать ту же вставку."""

    class Racing:
        def call(self, method, path, data=None, params=None):
            other = SessionLocal()
            other.add(WeboramaRef(account_id=ACC, kind=KIND_INSERTION, local_id=LOCAL,
                                  wcm_id="77", label="ТЕСТ · соседний запрос"))
            other.commit()
            other.close()
            return {"id": 78}

        def _created(self, raw, what):
            return str(raw["id"])

    with pytest.raises(prov.ProvisionError) as e:
        _ensure(db, Racing())
    assert "одновременно" in str(e.value)


def test_second_click_on_the_same_deal_is_refused_before_any_call(db):
    """Замок — по СДЕЛКЕ: проект Weborama заводится на сделку, и две РК одной сделки
    иначе завели бы два проекта."""
    from app.ext_lock import WEBORAMA_PROVISION

    camp = SimpleNamespace(id=999441, deal_id=999442)
    holder = engine.connect()
    holder.execute(text("SELECT pg_advisory_lock(:a, :b)"),
                   {"a": WEBORAMA_PROVISION, "b": camp.deal_id})
    try:
        class NoCalls:
            def call(self, *a, **kw):
                raise AssertionError("вызов ушёл, хотя заведение уже идёт")

        with pytest.raises(prov.ProvisionError) as e:
            prov.provision(db, camp, "https://simb-ad.com", client=NoCalls())
        assert "уже идёт" in str(e.value)
    finally:
        holder.execute(text("SELECT pg_advisory_unlock(:a, :b)"),
                       {"a": WEBORAMA_PROVISION, "b": camp.deal_id})
        holder.close()


# ── 4.M6: съём читает тот же аккаунт, что заведение ─────────────────────────

class _Stop(Exception):
    pass


def test_daily_pull_reads_the_account_vehicles_were_created_in(monkeypatch):
    from app.weborama import daily

    seen = {}

    def fake_client(account_id, **kw):
        seen["account"] = account_id
        raise _Stop()

    monkeypatch.setattr(prov, "account_id", lambda db: "SETTING_ACC")
    monkeypatch.setattr(daily, "WcmClient", fake_client)
    for env in ("ENV_ACC", ""):
        monkeypatch.setenv("WEBORAMA_DEMO_ACCOUNT_ID", env)
        seen.clear()
        with pytest.raises(_Stop):
            daily.run(dry_run=True)
        assert seen["account"] == "SETTING_ACC", (
            f"при переменной {env!r} съём пошёл в аккаунт {seen.get('account')!r}")


def test_stats_screen_names_the_same_account(db, monkeypatch):
    from app.weborama import state

    monkeypatch.setattr(prov, "account_id", lambda db: "SETTING_ACC")
    monkeypatch.setenv("WEBORAMA_DEMO_ACCOUNT_ID", "ENV_ACC")
    assert state.stats_state(db)["account_id"] == "SETTING_ACC"


def test_failed_login_is_not_an_unknown_outcome(db, monkeypatch):
    """Ревью 23.09.2026. Вход — тоже POST, и его таймаут стал «исходом неизвестен»:
    попытка по объекту оставалась открытой, хотя до создания дело не дошло, и сделка
    запиралась навсегда. Неудачный вход — отказ: ничего не создано, повтор разрешён."""
    c, sent = _client(monkeypatch, httpx.ReadTimeout("timed out"))
    c._token = None
    with pytest.raises(prov.ProvisionError):
        _ensure(db, c)
    assert _open(db) == 0, "неудачный вход запер повтор"
    with pytest.raises(prov.ProvisionError):
        _ensure(db, c)
    assert sent["n"] == 2
