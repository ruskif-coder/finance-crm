# -*- coding: utf-8 -*-
"""Сбой записи попытки входа не должен быть тихим.

`_note_login` глотает ошибку сознательно — вход из-за учёта попытки ронять нельзя. Но
молчаливый сбой на ЗАПИСИ НЕУДАЧИ отключает защиту от перебора: счётчик не растёт, блокировка
не наступает, а снаружи всё выглядит нормально (аудит 06.10.2026). Проверка блокировки при
сбое закрывает вход (`return 1`), запись неудачи — раньше нет. Теперь сбой виден в журнале.

В запись попадает только вид ошибки: у ошибок драйвера в тексте стоят параметры запроса,
то есть почта.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import main as cab_main          # noqa: E402


class _BrokenSession:
    rolled_back = closed = False

    def execute(self, *a, **k):
        raise RuntimeError("select pub.register_failed_login('secret@mail.test') не найдена")

    def commit(self):
        raise AssertionError("не должно дойти")

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_failed_attempt_note_that_cannot_be_written_is_logged_not_swallowed(monkeypatch, caplog):
    s = _BrokenSession()
    monkeypatch.setattr(cab_main, "plain_session", lambda: s)
    with caplog.at_level(logging.ERROR):
        cab_main._note_login("secret@mail.test", ok=False)      # вход не роняем
    assert s.rolled_back and s.closed
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "RuntimeError" in text, "сбой записи неудачи прошёл молча"
    assert "secret@mail.test" not in text, "почта попала в журнал"


def test_successful_login_note_failure_is_also_logged(monkeypatch, caplog):
    monkeypatch.setattr(cab_main, "plain_session", lambda: _BrokenSession())
    with caplog.at_level(logging.ERROR):
        cab_main._note_login("a@b.test", ok=True)
    assert any("RuntimeError" in r.getMessage() for r in caplog.records)
