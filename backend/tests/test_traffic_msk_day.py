# -*- coding: utf-8 -*-
"""Прибор: очередь трафика и срок хранения считают день по Москве (ревью 23.09.2026).

С 23.09.2026 процесс живёт по Москве, и `date.today()` — московский день. Колонки
`asked_at` и момент закрытия сделки остались в UTC (`now()` базы в поясе UTC). `.date()`
у такого момента — день по Гринвичу: запрос, пришедший в 01:30 МСК 24-го, лежит как
22:30 UTC 23-го и считался «ждёт сутки» в день прихода, а файлы сделки, закрытой ночью,
стирались на сутки раньше срока.
"""
from datetime import date, datetime
from types import SimpleNamespace

from app.routers import traffic
from app.traffic import retention

NIGHT_UTC = datetime(2026, 9, 23, 22, 30)      # 01:30 МСК 24.09


def test_request_that_came_at_night_is_dated_by_moscow():
    t = SimpleNamespace(verdict=None, asked_at=NIGHT_UTC)
    target = SimpleNamespace(period_from=date(2026, 10, 1), state="согласование")
    f = traffic._facts(t, target, SimpleNamespace(period_from=None))
    assert f.asked_at == date(2026, 9, 24)


def test_files_of_a_deal_closed_at_night_live_their_full_term():
    # Закрыта 01:30 МСК 24.09; срок 30 дней. 24.10 по Москве — ровно 30 дней, ещё не пора.
    assert retention.is_expired(NIGHT_UTC, 30, date(2026, 10, 24)) is False
    assert retention.is_expired(NIGHT_UTC, 30, date(2026, 10, 25)) is True
