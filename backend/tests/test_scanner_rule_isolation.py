# -*- coding: utf-8 -*-
"""Сканер: падение одного правила не откатывает отметки остальных (аудит 23.09.2026, 5.H3).

Правило, упавшее в середине прогона, делало `db.rollback()` — и вместе с ним откатывались
`last_sent_at` правил, отработавших раньше, и сама строка прогона. Письма при этом уже
ушли: отправка идёт сразу, а откатить её нечем. Итог — стабильно падающее правило
заставляло соседей повторять те же письма каждые 30 минут, а экран состояния говорил
«сканер давно не запускался».

Правила и отправка подменены; состояние сработок и строка прогона — настоящие, в базе
стенда, и снимаются за собой.
"""
from types import SimpleNamespace

import pytest

import app.main  # noqa: F401 — все модели
from app.database import SessionLocal
from app.notify import scanner
from app.notify.models import NotificationAlertState, NotificationScanRun

KEYS = ("test_scan_a", "test_scan_b", "test_scan_c")
ENTITY = 999601


def _hit(n):
    return scanner.Hit("test_entity", ENTITY + n, "первая", f"сработка {n}")


@pytest.fixture
def wired(monkeypatch):
    sent = []

    def broken(db, ev):
        raise RuntimeError("опечатка в правиле")

    monkeypatch.setattr(scanner, "RULES", {
        "test_scan_a": lambda db, ev: [_hit(1)],
        "test_scan_b": lambda db, ev: [_hit(2)],
        "test_scan_c": broken,
    })
    monkeypatch.setattr(scanner, "AFTER_SEND", {})
    monkeypatch.setattr(scanner.registry, "get", lambda key: SimpleNamespace(params={}))
    monkeypatch.setattr(scanner, "emit", lambda db, key, **kw: sent.append(key) or [])

    s = SessionLocal()
    before = s.query(NotificationScanRun.id).order_by(NotificationScanRun.id.desc()).first()
    before = before[0] if before else 0
    yield SimpleNamespace(sent=sent, before=before)
    s.query(NotificationAlertState).filter(
        NotificationAlertState.event_key.in_(KEYS)).delete(synchronize_session=False)
    s.query(NotificationScanRun).filter(NotificationScanRun.id > before).delete()
    s.commit()
    s.close()


def test_a_broken_rule_keeps_the_marks_of_the_others(wired):
    scanner.scan()

    s = SessionLocal()
    try:
        marks = {r.event_key: r.last_sent_at for r in s.query(NotificationAlertState)
                 .filter(NotificationAlertState.event_key.in_(KEYS)).all()}
        runs = s.query(NotificationScanRun).filter(
            NotificationScanRun.id > wired.before).count()
    finally:
        s.close()
    assert marks.get("test_scan_a") and marks.get("test_scan_b"), (
        "отметки отработавших правил откатились вместе с упавшим")
    assert runs >= 1, "строка прогона пропала — экран скажет «сканер не запускался»"

    scanner.scan()
    assert wired.sent.count("test_scan_a") == 1 and wired.sent.count("test_scan_b") == 1, (
        f"повторный прогон снова разослал то же: {wired.sent}")
