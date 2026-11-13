# -*- coding: utf-8 -*-
"""Разбор stats-all-summary в настоящем формате сервиса (проба с прода 13.11.2026, после «camp_id добавлено»): одна строка на
кампанию × источник × событие, значение — в `count`, уники — в `users`.

Поломка, которую ловит набор: строки разбираются, но показы и клики выходят нулями (ключи `imp`/`clk` ищутся как поля, а это
значения поля `event`) — крон пишет тихие нули, автостоп по цели не срабатывает никогда, и строгий разбор этого не видит."""
import pytest

from app.prio import stats as S

BODY = {"ok": True, "date_start": "2026-11-12", "date_end": "2026-11-12", "antifraud": True, "stats": [
    {"camp_id": 17, "site_id": 9001, "site_name": "apteka-a.test", "product_name": "", "count": 78, "users": 35, "source": "context", "event": "imp"},
    {"camp_id": 18, "site_id": 9001, "site_name": "apteka-a.test", "product_name": "", "count": 77, "users": 34, "source": "context", "event": "imp"},
    {"camp_id": 28, "site_id": 9002, "site_name": "apteka-b.test", "product_name": "", "count": 2, "users": 1, "source": "search", "event": "imp"},
    {"camp_id": 18, "site_id": 9001, "site_name": "apteka-a.test", "product_name": "", "count": 1, "users": 1, "source": "context", "event": "clk"},
    {"camp_id": 1, "site_id": 9003, "site_name": "apteka-c.test", "product_name": "Препарат", "count": 1, "users": 1, "source": "catalog", "event": "imp"},
    {"camp_id": 1, "site_id": 9003, "site_name": "apteka-c.test", "product_name": "Препарат", "count": 3, "users": 2, "source": "search", "event": "imp"},
    {"camp_id": 1, "site_id": 9003, "site_name": "apteka-c.test", "product_name": "Препарат", "count": 1, "users": 1, "source": "search", "event": "clk"},
]}


def test_long_rows_sum_per_campaign_and_source():
    got = S.parse(BODY)
    assert (got[18]["shows"], got[18]["clicks"]) == (77, 1)
    assert (got[17]["shows"], got[17]["clicks"]) == (78, 0)
    assert (got[1]["shows"], got[1]["clicks"]) == (4, 1)
    assert got[1]["by_type"] == {"catalog": {"shows": 1, "clicks": 0}, "search": {"shows": 3, "clicks": 1}}


def test_strict_parse_refuses_rows_it_cannot_read():
    """Строки с camp_id, но без понятной метрики — сбой, а не нули."""
    with pytest.raises(Exception):
        S.parse_strict({"ok": True, "stats": [{"camp_id": 5, "source": "search", "event": "conversion", "value": 3}]})


def test_test_site_zero_is_dropped():
    """site_id 0 «supertest» в боевом ответе (31.10.2026: 34 354 клика) — не наша кампания, итог не задавливает."""
    got = S.parse({"ok": True, "stats": [{"camp_id": 9, "site_id": 0, "site_name": "supertest", "count": 34354, "source": "catalog", "event": "clk"}]})
    assert got == {}
