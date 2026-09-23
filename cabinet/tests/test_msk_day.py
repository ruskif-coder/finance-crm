# -*- coding: utf-8 -*-
"""Счёт суток, показываемый площадке, ведётся по МОСКОВСКОМУ календарю.

ЧТО СЛУЧИЛОСЬ (23.09.2026). «Ждём N дней» считалось как разница гринвичских дат. Сам с
собой счёт сходился — обе метки лежат в UTC, — но граница суток проходила на три часа
позже московской: с полуночи до трёх ночи площадке показывалось на день меньше, чем она
ждёт на самом деле. Число выглядело правдой, просто вчерашней, и проверить его можно
было только ночью.

Прибор держит границу, а не текущее значение: полночь по Москве — это 21:00 предыдущих
суток по Гринвичу, и именно там прежний расчёт ошибался.
"""
from datetime import datetime, timedelta

from app.main import MSK_OFFSET, _msk_today, _to_msk


def test_offset_is_three_hours():
    assert MSK_OFFSET == 3
    assert _to_msk(datetime(2026, 9, 14, 19, 30)) == datetime(2026, 9, 14, 22, 30)


def test_midnight_in_moscow_belongs_to_the_new_day():
    """21:00 UTC — это уже следующие сутки по Москве.

    Ровно та граница, где старый расчёт отдавал предыдущий день.
    """
    assert _to_msk(datetime(2026, 9, 13, 21, 0)).date() == datetime(2026, 9, 14).date()
    assert _to_msk(datetime(2026, 9, 13, 20, 59)).date() == datetime(2026, 9, 13).date()


def test_waiting_days_counts_the_moscow_night_as_a_day():
    """Запрошено в 23:30 МСК 13-го, смотрим в 01:00 МСК 14-го — ждём один день.

    По Гринвичу обе метки лежат в 13-м числе, и старый расчёт отдавал ноль: площадка
    видела «ждём сегодня» о запросе, поданном вчера вечером.
    """
    asked_utc = datetime(2026, 9, 13, 20, 30)        # 23:30 МСК 13-го
    now_utc = datetime(2026, 9, 13, 22, 0)           # 01:00 МСК 14-го
    msk_today = (now_utc + timedelta(hours=MSK_OFFSET)).date()
    assert (msk_today - _to_msk(asked_utc).date()).days == 1
    # А как считалось раньше — для наглядности того, что именно менялось:
    assert (now_utc.date() - asked_utc.date()).days == 0


def test_msk_today_is_three_hours_ahead_of_greenwich_today():
    """`_msk_today` не отстаёт от настоящего московского дня.

    Сверяется с арифметикой, а не с часами машины: прибор должен быть одинаковым в
    любое время суток, иначе он зелёный днём и красный ночью — то есть бесполезен
    ровно тогда, когда нужен.
    """
    expected = (datetime.utcnow() + timedelta(hours=MSK_OFFSET)).date()
    assert _msk_today() == expected


def test_feed_shows_the_moscow_moment():
    """Лента кабинета отдаёт московское время, а не UTC из `pub.log_v1`.

    Экран берёт дату срезом строки (`lib/ui.js: dm`), поэтому событие 01:30 по Москве
    (22:30 UTC прошлых суток) показывалось вчерашним днём.
    """
    from types import SimpleNamespace

    from app.main import _feed_item

    row = SimpleNamespace(id=1, created_at=datetime(2026, 9, 13, 22, 30), action="x",
                          tone=None, side=None, actor_name="", subject="")
    item = _feed_item(row, {})
    assert item["at"] == datetime(2026, 9, 14, 1, 30)
    assert _feed_item(SimpleNamespace(**{**row.__dict__, "created_at": None}), {})["at"] is None
