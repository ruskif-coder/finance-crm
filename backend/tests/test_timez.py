# -*- coding: utf-8 -*-
"""Время: в базе UTC, человеку — Москва.

Правило выведено замером 14.09.2026, а не принято по вкусу: контейнеры и postgres живут
в UTC (`TZ` не задана ни у одного сервиса, `now()` отдаёт `+00`), а люди в Москве.

Нарушение этого правила тихое в обе стороны — время выглядит настоящим, просто не тем, —
и за один разбор нашлось в четырёх местах:

* шапка письма показывала UTC: получатель видел время на три часа в прошлом;
* тихие часы ПЛОЩАДОК (21:00–09:00) считались от UTC и работали с 00:00 до 12:00 —
  письмо в 23:00 уходило ночью, утреннее ждало до полудня;
* тихие часы СОТРУДНИКОВ — тот же дефект: заданные 22:00–08:00 работали как 01:00–11:00;
* штампы выгрузок («Выгружено 14.09.2026 19:25») и имена файлов — тоже UTC.

Приборы ниже держат каждую из этих четырёх точек.
"""
import inspect
import re
from datetime import datetime, timedelta

from app import timez
from app.notify import channels
from app.notify.outward import schedule as sc


class _Ch:
    """Каналы сотрудника с заданными тихими часами. Своего класса-заглушки не избежать:
    настоящая строка требует пользователя, профиля и подписки, а проверяется здесь
    арифметика часа."""
    def __init__(self, a, b):
        self.quiet_from, self.quiet_to, self.mute_until = a, b, None


class _Ev:
    locked = False


def test_msk_is_three_hours_ahead_of_utc():
    assert timez.MSK_OFFSET == 3
    d = datetime(2026, 9, 14, 19, 30)
    assert timez.to_msk(d) == datetime(2026, 9, 14, 22, 30)
    assert abs((timez.msk_now() - datetime.utcnow()).total_seconds()
               - 3 * 3600) < 2


def test_employee_quiet_hours_are_moscow(monkeypatch):
    """Тихие часы сотрудника считаются по московскому часу.

    Человек ставит 22:00–08:00, имея в виду свои вечер и утро. Пока час брался из
    `datetime.now()` контейнера, окно работало с 01:00 до 11:00: письмо в 23:00
    приходило ночью, а в 10:00 — не приходило вовсе.
    """
    ch = _Ch(22, 8)
    cases = [(23, True), (2, True), (7, True), (9, False), (14, False), (21, False)]
    for msk_hour, expected in cases:
        fake = datetime(2026, 9, 14, msk_hour, 30)
        monkeypatch.setattr(timez, "msk_now", lambda f=fake: f)
        monkeypatch.setattr(channels.timez, "msk_now", lambda f=fake: f)
        got = channels.quiet_now(ch, _Ev())
        assert got is expected, f"{msk_hour}:30 МСК — ожидалось тихо={expected}"


def test_publisher_quiet_hours_are_utc_in_and_moscow_by_meaning():
    """У площадок вход UTC, а смысл — московский (плюс её собственное смещение).

    Проверяется та пара часов, где ошибка видна в обе стороны: днём и глубокой ночью
    разницы не заметно, а на границах она и живёт.
    """
    # 23:00 МСК = 20:00 UTC — ночь, письмо ждёт утра
    assert sc.due_at(datetime(2026, 9, 14, 20), 0, immediate=False) is not None
    # 09:30 МСК = 06:30 UTC — тихие часы кончились
    assert sc.due_at(datetime(2026, 9, 14, 6, 30), 0, immediate=False) is None


def test_nothing_shows_container_time_to_a_human():
    """Ратчет: `datetime.now()` не возвращается в код.

    Внутри контейнера это UTC, то есть не годится ни для показа (врёт на три часа), ни
    для записи (совпадает с `utcnow()` только пока `TZ` не задана — то есть держится на
    случайности). Для показа есть `timez.msk_now()`, для записи `datetime.utcnow()`.
    """
    from pathlib import Path

    app = Path(__file__).resolve().parent.parent / "app"
    stray = []
    for p in app.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            t = line.lstrip()
            if t.startswith("#") or t.startswith("*"):
                continue
            if re.search(r"\bdatetime\.now\(\s*\)", line):
                stray.append(f"{p.relative_to(app)}:{i}")
    assert not stray, ("datetime.now() внутри контейнера это UTC: "
                       + ", ".join(stray))


def test_letter_default_time_is_moscow():
    """Умолчание времени в письме — московское. Параметр можно забыть, и подставиться
    должно правильное."""
    src = inspect.getsource(__import__("app.mail.render", fromlist=["x"]))
    assert "when = when or msk_now()" in src
    assert "when = when or datetime.now()" not in src


def test_quiet_hours_window_crosses_midnight_for_employees():
    """Окно через полночь: 23 больше начала, 3 меньше конца, оба тихие. Обычное
    сравнение `a <= h < b` даёт здесь ровно наоборот — тихим становится день."""
    ch = _Ch(21, 9)
    quiet = []
    for h in range(24):
        fake = datetime(2026, 9, 14, h)
        import app.notify.channels as c
        orig = c.timez.msk_now
        c.timez.msk_now = lambda f=fake: f
        try:
            if c.quiet_now(ch, _Ev()):
                quiet.append(h)
        finally:
            c.timez.msk_now = orig
    assert quiet == [0, 1, 2, 3, 4, 5, 6, 7, 8, 21, 22, 23]


def test_mute_until_uses_the_moscow_day():
    """«Не беспокоить до» — по московскому календарю: первые три часа суток по UTC
    ещё вчерашние, и молчание кончалось бы на три часа позже обещанного."""
    src = inspect.getsource(channels.quiet_now)
    assert "date.today()" not in src, "день берётся из UTC"
    assert "now.date()" in src


def test_db_writes_stay_utc():
    """В базу пишется `utcnow()`. Колонки наивные, и смешать в них две шкалы значит
    получить сортировку, в которой вечер идёт раньше утра."""
    now_utc = datetime.utcnow()
    assert abs((now_utc - (timez.msk_now() - timedelta(hours=3))).total_seconds()) < 2
