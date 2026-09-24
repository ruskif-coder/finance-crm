# -*- coding: utf-8 -*-
"""Заявка о сбое из кабинета площадки (аудит 23.09.2026, 5.H1 и 5.L9).

5.H1. Ручка писала в журнал кабинета действие `заявка_о_сбое`, которого в журнале нет:
`journal.write` бросал ValueError, заявка откатывалась, а площадка видела «Не удалось
сохранить». То есть сообщить нам о сбое из кабинета было нельзя НИКОГДА — и тестов на
это не было. Прибор ниже ловит весь класс: каждое действие, которое код пишет в журнал
буквальной строкой, обязано быть объявлено.

5.L9. Повторный «заявка дописана» слал владельцу второе уведомление о той же заявке.
"""
import io
import re
from pathlib import Path
from types import SimpleNamespace

import app.models  # noqa: F401
from app.cabinet import journal
from app.routers import bugs as bug_api
from app.routers import cabinet_gateway as gw

APP = Path(__file__).resolve().parent.parent / "app"


def test_every_journal_action_written_by_the_code_is_declared():
    used = set()
    for f in APP.rglob("*.py"):
        src = io.open(f, encoding="utf-8").read()
        used |= set(re.findall(r"journal\.write\(\s*db\s*,\s*'([^']+)'", src))
    missing = sorted(used - set(journal.BY_KEY))
    assert not missing, f"в журнал кабинета пишутся необъявленные действия: {missing}"


def test_a_publisher_can_report_a_failure(monkeypatch):
    written = []
    monkeypatch.setattr(gw, "_actor", lambda db, a, p: SimpleNamespace(
        id=a, name="Площадка", cabinet_id=7))
    monkeypatch.setattr(bug_api, "create_report", lambda db, **kw: SimpleNamespace(id=55))
    real = journal.write
    monkeypatch.setattr(journal, "write",
                        lambda db, action, **kw: written.append(action) or real(
                            _NoDb(), action, **kw))
    out = gw.cabinet_bug_create(3, gw.BugIn(publisher_id=1, comment="не грузится"), _NoDb())
    assert out == {"id": 55}
    assert written == ["заявка_о_сбое"]


class _NoDb:
    def add(self, row):
        pass

    def commit(self):
        pass


def test_second_sent_does_not_announce_twice(monkeypatch):
    calls = []
    report = SimpleNamespace(id=55, author_account_id=3)

    class Db(_NoDb):
        def __init__(self, announced):
            self.announced = announced

        def query(self, model):
            return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: report))

        def execute(self, sql, params=None):
            return SimpleNamespace(scalar=lambda: self.announced)

    monkeypatch.setattr(bug_api, "announce", lambda db, r, actor=None: calls.append(r.id))
    gw.cabinet_bug_sent(55, 3, Db(announced=0))
    gw.cabinet_bug_sent(55, 3, Db(announced=1))
    assert calls == [55], "владелец получил второе уведомление о той же заявке"
