# -*- coding: utf-8 -*-
"""Жизнь сработки сканера (аудит 01.10.2026, В-1 и В-2).

В-1: правило вернуло НОЛЬ сработок — открытые состояния не закрывались вовсе (закрытие
шло только по типам из текущих сработок), и строка в панели «жила» вечно.
В-2: закрытое состояние сработало снова на той же стадии — пропускалось навсегда:
счёт просрочили второй раз, а уведомления нет.
"""
from sqlalchemy import text

import app.main  # noqa: F401
from app.database import SessionLocal
from app.notify import scanner as S

ETYPE = "test_lifecycle"
EID = 990001


def _state(db, key):
    return db.execute(text(
        "SELECT resolved_at, sent_count FROM notification_alert_state "
        "WHERE event_key = :k AND entity_type = :t AND entity_id = :i"),
        {"k": key, "t": ETYPE, "i": EID}).first()


def test_close_on_zero_hits_and_reopen_on_return(monkeypatch):
    key = next(iter(S.RULES))
    hits = {"now": [S.Hit(ETYPE, EID, "overdue", "проверка жизни сработки")]}
    sent = []
    monkeypatch.setattr(S, "RULES", {key: lambda db, ev: list(hits["now"])})
    monkeypatch.setattr(S, "emit", lambda db, k, **kw: sent.append(kw["entity_id"]) or [1])
    monkeypatch.setattr(S, "AFTER_SEND", {})
    db = SessionLocal()
    try:
        S.scan(only=key)
        assert sent == [EID]
        assert _state(db, key)[0] is None

        hits["now"] = []                       # проблема ушла
        S.scan(only=key)
        db.expire_all()
        assert _state(db, key)[0] is not None, "В-1: при нуле сработок состояние не закрылось"

        hits["now"] = [S.Hit(ETYPE, EID, "overdue", "проверка жизни сработки")]
        S.scan(only=key)                       # вернулась сразу — «мигание»
        db.expire_all()
        assert sent == [EID], "мигание данных не должно слать повтор"
        assert _state(db, key)[0] is None, "но состояние переоткрыто"

        hits["now"] = []
        S.scan(only=key)                       # снова ушла …
        db.execute(text("UPDATE notification_alert_state SET resolved_at = resolved_at - interval '2 days' "
                        "WHERE entity_type = :t"), {"t": ETYPE})
        db.commit()
        hits["now"] = [S.Hit(ETYPE, EID, "overdue", "проверка жизни сработки")]
        S.scan(only=key)                       # … и вернулась через два дня на той же стадии
        db.expire_all()
        assert sent == [EID, EID], "В-2: вернувшаяся проблема не уведомила"
        assert _state(db, key)[0] is None
    finally:
        db.execute(text("DELETE FROM notification_alert_state WHERE entity_type = :t"), {"t": ETYPE})
        db.commit()
        db.close()



def test_dry_run_does_not_touch_states(monkeypatch):
    key = next(iter(S.RULES))
    monkeypatch.setattr(S, "RULES", {key: lambda db, ev: []})
    db = SessionLocal()
    try:
        db.execute(text("INSERT INTO notification_alert_state (event_key, entity_type, entity_id, stage) "
                        "VALUES (:k, :t, :i, 'overdue')"), {"k": key, "t": ETYPE, "i": EID})
        db.commit()
        S.scan(dry_run=True, only=key)
        db.expire_all()
        assert _state(db, key)[0] is None, "сухой прогон закрыл состояние"
    finally:
        db.execute(text("DELETE FROM notification_alert_state WHERE entity_type = :t"), {"t": ETYPE})
        db.commit()
        db.close()
