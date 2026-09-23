# -*- coding: utf-8 -*-
"""Прибор: «ошибок за 24 ч» на экране состояния — это ровно сутки.

С 23.09.2026 процесс живёт по Москве, и метки строк `backend.log` пишутся московские.
Граница же считалась от UTC — то есть на три часа раньше, и «сутки» на экране были
двадцатью семью часами. Ошибку позавчерашнего вечера человек видел как сегодняшнюю.
"""
from datetime import timedelta

from app import timez
from app.system import status


def _line(dt, msg):
    return dt.strftime("%Y-%m-%d %H:%M:%S") + ",000 ERROR finance: " + msg + "\n"


def test_errors_window_is_exactly_one_day(tmp_path, monkeypatch):
    now = timez.msk_now()
    log = tmp_path / "backend.log"
    log.write_text(
        _line(now - timedelta(hours=25), "позавчерашний вечер")
        + _line(now - timedelta(hours=23), "вчерашняя")
        + _line(now - timedelta(minutes=5), "свежая"),
        encoding="utf-8")
    monkeypatch.setattr(status, "LOG_PATH", str(log))
    got = status.errors_24h()
    assert got["count"] == 2, got
    assert "свежая" in got["last"]


def test_restart_moment_is_shown_by_moscow(monkeypatch):
    """Запуск в 22:30 UTC — это 01:30 МСК следующего дня; подпись — по Москве, как журнал."""
    from datetime import datetime, timezone

    from app.system import status
    monkeypatch.setattr(status, "STARTED_AT", datetime(2026, 9, 23, 22, 30, tzinfo=timezone.utc))
    assert status.started_label() == "24.09 в 01:30"
