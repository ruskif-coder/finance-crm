# -*- coding: utf-8 -*-
"""Демо-стенд DSP: контур, обёртка креатива, отказ без настроек.

Главное здесь — КОНТУР. Демо и бой делят один журнал, а на журнале стоит защита от
дублей: она ищет прошлый удачный хеш по нашему local_ref. Демо-прогон по той же сделке
заставил бы боевое заведение решить, что кампания уже создана, — и боевая РК не завелась
бы, молча и «успешно». Это не падает и не видно в коде.
"""
import os

import pytest

from app.dsp.client import DEMO, PROD, MsClient
from app.dsp import creatives as cr


def _client(contour, transport, ref):
    return MsClient(url="http://x/", token="t", partner_xxhash="P" * 16,
                    transport=transport, contour=contour)


def test_contours_do_not_see_each_other_in_the_journal():
    """Один и тот же local_ref в двух контурах — два разных хеша, и каждый видит свой."""
    from app.dsp.db import dsp_engine
    try:
        dsp_engine()
    except Exception:
        pytest.skip('аналитическая база недоступна')
    ref = "TEST-contour"
    demo = _client(DEMO, lambda m, b: {"jsonrpc": "2.0", "result": "D" * 16, "id": 1}, ref)
    prod = _client(PROD, lambda m, b: {"jsonrpc": "2.0", "result": "F" * 16, "id": 1}, ref)
    try:
        assert demo.campaign_add({"title": "t"}, local_ref=ref) == "D" * 16
        assert prod.campaign_add({"title": "t"}, local_ref=ref) == "F" * 16
        assert demo.last_ok_xxhash("Campaign.add", "campaign", ref) == "D" * 16
        assert prod.last_ok_xxhash("Campaign.add", "campaign", ref) == "F" * 16
    finally:
        from sqlalchemy import text
        with dsp_engine().begin() as c:
            c.execute(text("DELETE FROM dsp_send_log WHERE local_ref = :r"), {"r": ref})


def test_unknown_contour_is_refused_at_construction():
    """Опечатка в контуре не должна тихо превратиться в боевой вызов."""
    with pytest.raises(ValueError):
        MsClient(url="http://x/", token="t", partner_xxhash="P" * 16, contour="prd")


# ── конвейер креатива ────────────────────────────────────────────────────────

def test_not_a_zip_is_refused_before_the_network():
    """Загрузчик DSP на чужой файл отвечает своей страницей, а не ошибкой — и мы приняли
    бы её HTML за баннер. Молча и правдоподобно."""
    with pytest.raises(cr.CreativeError):
        cr.check_zip(b"<html>not a zip</html>", "banner.zip")
    with pytest.raises(cr.CreativeError):
        cr.check_zip(b"", "empty.zip")
    cr.check_zip(b"PK\x03\x04" + b"\0" * 10, "ok.zip")   # настоящий начинается с PK


def test_wrapper_adds_viewability_and_keeps_the_macros():
    """Макросы раскрывает сам DSP при выдаче. Развернуть их у себя значило бы прибить
    креатив к одной площадке; потерять — лишить его отслеживания и клика."""
    vsrc = "https://example.test/viewability.js"
    src = "<html><head><title>b</title></head><body>{RID} {LINK_UNESC} {PUBLISHER}</body></html>"
    out = cr.wrap_html(src, erid="ABC123", viewability_src=vsrc)
    assert vsrc in out
    assert "ABC123" in out
    assert set(cr.macros_found(out)) == {"{RID}", "{LINK_UNESC}", "{PUBLISHER}"}
    # Разметка без <head> тоже должна получить обёртку, а не остаться голой.
    bare = cr.wrap_html("<div>{RID}</div>", viewability_src=vsrc)
    assert vsrc in bare and "{RID}" in bare


def test_wrapper_without_the_setting_carries_no_viewability_and_no_hardcoded_address():
    """Адрес скрипта видимости живёт в настройке, а не в коде: в репозитории имя
    поставщика не хранится (09.09.2026). Пусто — обёртка идёт без него, молча подставить
    нечего, и потребитель обязан сказать об этом вслух."""
    out = cr.wrap_html("<div>{RID}</div>")
    assert "<script src=" not in out
    assert not hasattr(cr, "VIEWABILITY_SRC")


def test_creative_limits_are_total_only():
    """При uniform_pro день и час на креативе конфликтуют с API (готча из теста
    владельца). Значит в теле их быть не должно вовсе."""
    p = cr.build_creative_params(title="c", link="https://x.ru", total_shows=1000,
                                 total_clicks=10)
    assert p["limits"] == {"show": {"total": 1000}, "click": {"total": 10}}
    assert "description" not in p, 'description не трогаем — ломается'


def test_creative_without_link_is_refused():
    """Креатив без посадочной ссылки бессмысленен, и узнать об этом лучше до отправки."""
    with pytest.raises(cr.CreativeError):
        cr.build_creative_params(title="c", link="")
    with pytest.raises(cr.CreativeError):
        cr.build_creative_params(title="", link="https://x.ru")


# ── ручки стенда ─────────────────────────────────────────────────────────────

def test_stand_says_it_is_not_configured_instead_of_failing_later():
    """Без ЛЮБЫХ ключей шаг отвечает отказом сразу, а не роняет первую кнопку пятисоткой.

    До 09.09.2026 здесь требовались именно демо-ключи. Теперь их отсутствие — не отказ, а
    работа боевыми (демо-клиента у нас нет), поэтому снимаем и те и другие.
    """
    from fastapi import HTTPException
    from app.routers import dsp_demo as D
    keys = (D.ENV_TOKEN, D.ENV_PARTNER, "DSP_ACCESS_TOKEN", "DSP_PARTNER_XXHASH")
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        with pytest.raises(HTTPException) as e:
            D.demo_client()
        assert e.value.status_code == 400
        assert "не настроен" in str(e.value.detail)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_partner_hash_is_masked_on_screen():
    """Экран видят люди, которым доступ к кабинету DSP не выдавали."""
    from app.routers import dsp_demo as D
    # Хеш выдуман: настоящий partner_xxhash — идентификатор нашего кабинета в чужой
    # системе, и в трекаемом файле ему не место (репозиторий уезжает на GitHub).
    assert D._mask("0123456789ABCDEF") == "…CDEF"
    assert D._mask(None) is None


# ── план до конца кампании ───────────────────────────────────────────────────

def test_remaining_becomes_a_full_total_not_a_remainder():
    """ГЛАВНАЯ ловушка DSP: `total` — лимит за ВЕСЬ срок, а не остаток.

    Человек думает остатком («до конца надо ещё 200 000»), и прислать это число напрямую
    значит сказать МС, что весь план равен остатку: он засчитает уже открученное и
    остановит кампанию раньше срока. Поэтому total = откручено + остаток.
    """
    from app.dsp.campaigns import plan_total
    assert plan_total(300000, 200000) == 500000
    # Остаток ноль — план равен открученному, кампания встанет. Это законный способ
    # остановить открутку планом, и он не должен превращаться во что-то другое.
    assert plan_total(300000, 0) == 300000
    # Мусор не должен уезжать в DSP отрицательным числом.
    assert plan_total(-5, -5) == 0
    assert plan_total(None, 1000) == 1000


def test_plan_body_carries_no_day_or_hour_limits():
    """Суточным темпом рулит МС (`uniform_pro`); наш суточный план — ориентир для решений,
    а не лимит наружу. День и час уходят нулями, иначе конфликт по API."""
    from app.dsp.campaigns import build_plan_params
    p = build_plan_params(show_total=500000, date_end="2026-09-30")
    assert p["limits"]["show"] == {"total": 500000, "day": 0, "hour": 0}
    assert p["limits"]["traffic_distribution"] == "uniform_pro"
    assert "status" not in p, "статусом рулит setStatus, edit его не трогает"
    # Незаданное не отправляется: пустой ключ обнулил бы чужой лимит.
    assert "budget" not in p["limits"] and "click" not in p["limits"]


def test_dry_run_shows_the_arithmetic_without_sending():
    """Арифметику видно ДО нажатия: цена ошибки здесь — остановленная раньше срока РК."""
    from app.routers import dsp_demo as D
    out = D.campaign_plan("A" * 16, D.PlanIn(delivered_show=300000, remaining_show=200000,
                                             dry_run=True), None, None)
    assert out["sent"] is False
    assert out["explain"]["show"]["total"] == 500000
    assert out["request"]["limits"]["show"]["total"] == 500000


def test_plan_without_a_remainder_is_refused():
    """Пустая форма не должна уходить в DSP «чем-нибудь»."""
    from fastapi import HTTPException
    from app.routers import dsp_demo as D
    with pytest.raises(HTTPException) as e:
        D.campaign_plan("A" * 16, D.PlanIn(), None, None)
    assert e.value.status_code == 400


def test_pause_and_stop_are_different_statuses():
    """У МС нет отдельной паузы: выдачу останавливает STOPPED. «Стоп» — это ARCHIVE,
    и обратно оно уже не включается. Подписи на экране говорят об этом прямо."""
    from app.routers.dsp_demo import STATUS_ACTIONS
    assert STATUS_ACTIONS["start"] == "LAUNCHED"
    assert STATUS_ACTIONS["pause"] == "STOPPED"
    assert STATUS_ACTIONS["stop"] == "ARCHIVE"


def test_oversized_archive_is_refused_before_it_fills_memory():
    """Ревью 06.09.2026: файл читался целиком (`file.file.read()`) и только потом
    проверялся размер. В контейнере с `mem_limit: 512m` многогигабайтный архив уронил бы
    бэкенд по OOM вместе со всеми чужими запросами — то есть проверка стояла после того,
    от чего защищала. Теперь чтение идёт порциями с потолком.
    """
    from io import BytesIO
    from fastapi import HTTPException, UploadFile
    from app.dsp import creatives as cr
    from app.routers import dsp_demo as D

    class _Big(BytesIO):
        """Бесконечный поток: настоящий гигабайт в тест класть незачем."""
        def read(self, n=-1):
            return b"\0" * (n if n and n > 0 else 1024)

    big = UploadFile(filename="huge.zip", file=_Big())
    with pytest.raises(HTTPException) as e:
        D.upload(file=big, local_ref="demo", user=None)
    assert e.value.status_code == 413
    assert str(cr.MAX_ZIP_BYTES // (1024 * 1024)) in str(e.value.detail)


# ─────────────────────────────────────────────────────────────────────────────
# Работа в БОЕВОМ кабинете (решение владельца 09.09.2026)
#
# Отдельного демо-клиента у нас нет, и экран ходит боевыми ключами. От беды его держат
# три вещи, и каждая проверяется отдельно: приставка в названии, контур журнала и запрет
# трогать чужие кампании. Сломается любая — тренировка начнёт задевать настоящие деньги.
# ─────────────────────────────────────────────────────────────────────────────

def test_demo_keys_win_over_live_ones(monkeypatch):
    """Пока демо-ключи заданы, боевые в этом экране не участвуют вовсе."""
    from app.routers import dsp_demo as D
    monkeypatch.setenv(D.ENV_TOKEN, "demo-token")
    monkeypatch.setenv(D.ENV_PARTNER, "DEMOPARTNER00001")
    monkeypatch.setenv("DSP_ACCESS_TOKEN", "live-token")
    monkeypatch.setenv("DSP_PARTNER_XXHASH", "0123456789ABCDEF")   # выдуманный
    creds = D._creds()
    assert creds["cabinet"] == D.CAB_DEMO
    assert creds["token"] == "demo-token" and creds["partner"] == "DEMOPARTNER00001"


def test_without_demo_keys_the_screen_says_it_is_the_live_cabinet(monkeypatch):
    """Молчаливая подстановка боевого токена была бы худшим исходом: человек тренируется,
    а объекты создаются настоящие. Кабинет назван в ответе, экран рисует по нему плашку."""
    from fastapi import HTTPException
    from app.routers import dsp_demo as D
    monkeypatch.delenv(D.ENV_TOKEN, raising=False)
    monkeypatch.delenv(D.ENV_PARTNER, raising=False)
    monkeypatch.setenv("DSP_ACCESS_TOKEN", "live-token")
    monkeypatch.setenv("DSP_PARTNER_XXHASH", "0123456789ABCDEF")   # выдуманный
    creds = D._creds()
    assert creds["cabinet"] == D.CAB_PROD
    assert creds["token"] == "live-token"

    # А без единого ключа — отказ, а не попытка сходить в никуда.
    monkeypatch.delenv("DSP_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("DSP_PARTNER_XXHASH", raising=False)
    assert D._creds() is None
    with pytest.raises(HTTPException) as e:
        D.demo_client()
    assert e.value.status_code == 400


def test_the_journal_contour_stays_demo_even_on_live_keys(monkeypatch):
    """Контур журнала не зависит от того, чьи ключи. Иначе боевое заведение РК приняло бы
    тренировочные вызовы за свои и решило, что кампания уже создана."""
    from app.dsp.client import DEMO
    from app.routers import dsp_demo as D
    monkeypatch.delenv(D.ENV_TOKEN, raising=False)
    monkeypatch.delenv(D.ENV_PARTNER, raising=False)
    monkeypatch.setenv("DSP_API_URL", "https://example.test/api/v2/")
    monkeypatch.setenv("DSP_ACCESS_TOKEN", "live-token")
    monkeypatch.setenv("DSP_PARTNER_XXHASH", "0123456789ABCDEF")   # выдуманный
    assert D.demo_client().contour == DEMO


def test_live_dedup_skips_training_campaigns():
    """Третья ступень защиты от дублей сверяет название по ВСЕМУ кабинету партнёра. С
    тренировочными в том же кабинете она обязана их пропускать, иначе боевая сделка
    привязалась бы к тренировке — молча и «успешно»."""
    from app.dsp import campaigns as C
    rows = [{"title": C.DEMO_TITLE_PREFIX + "ABC123 · Сделка · 2026-09", "xxhash": "DEAD" * 4},
            {"title": "ABC123 · Сделка · 2026-09", "xxhash": "BEEF" * 4}]
    hits = [r["xxhash"] for r in rows
            if not r["title"].startswith(C.DEMO_TITLE_PREFIX)
            and r["title"] == "ABC123 · Сделка · 2026-09"]
    assert hits == ["BEEF" * 4], 'тренировочная строка не должна совпадать с боевой'
    # И приставка не может родиться у настоящего имени: оно начинается с кода сделки.
    assert not C.campaign_title.__doc__.startswith(C.DEMO_TITLE_PREFIX)


def test_in_the_live_cabinet_the_screen_touches_only_its_own(monkeypatch):
    """Одна вставленная из буфера строка не должна останавливать чужую кампанию.
    Со своим демо-клиентом ограничение снимается само — там портить нечего."""
    from fastapi import HTTPException
    from app.routers import dsp_demo as D
    monkeypatch.delenv(D.ENV_TOKEN, raising=False)
    monkeypatch.delenv(D.ENV_PARTNER, raising=False)
    monkeypatch.setenv("DSP_ACCESS_TOKEN", "live-token")
    monkeypatch.setenv("DSP_PARTNER_XXHASH", "0123456789ABCDEF")   # выдуманный
    with pytest.raises(HTTPException) as e:
        D._assert_ours("AAAAAAAAAAAAAAAA")      # такого хеша в журнале demo нет
    assert e.value.status_code in (403, 503)

    monkeypatch.setenv(D.ENV_TOKEN, "demo-token")
    monkeypatch.setenv(D.ENV_PARTNER, "DEMOPARTNER00001")
    D._assert_ours("AAAAAAAAAAAAAAAA")          # на своём демо-клиенте замка нет
