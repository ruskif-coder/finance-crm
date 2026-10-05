# -*- coding: utf-8 -*-
"""Текст ошибки опроса статусов ЕРИД — в записи прогона, тревоге и «Статусе системы»
(05.10.2026). До этого сохранялось только число: «ошибок опроса статуса: 11», и чтобы
узнать, что ОРД отвечает 403 «нет прав», пришлось лезть в ОРД руками."""
from app.launch_prep import erid_auto as E

ERR403 = "ОРД отказал в доступе (403) — у учётной записи нет прав на эту операцию."


def _out(refresh_failed):
    return {"issue": {"issued": [], "pending": [], "blocked": [], "failed": []},
            "refresh": {"checked": len(refresh_failed), "changed": [], "failed": refresh_failed}}


def test_same_errors_are_grouped_with_count():
    got = E.refresh_errors([{"set_id": i, "error": ERR403} for i in range(11)]
                           + [{"set_id": 99, "error": "таймаут"}])
    assert got[0] == f"{ERR403} — 11 компл." and got[1] == "таймаут — 1 компл."


def test_alert_body_has_error_text(monkeypatch):
    sent = {}
    import app.notify.bus as bus
    monkeypatch.setattr(bus, "emit", lambda db, ev, **kw: sent.update(kw))

    class _Db:
        def commit(self):
            pass
    E._alert(_Db(), _out([{"set_id": 1, "error": ERR403}]))
    assert "403" in sent["body"] and "опрос" in sent["body"]


def test_status_page_shows_error_text(monkeypatch):
    import json
    from datetime import datetime
    from app.system import status as S
    last = {"at": datetime.utcnow().isoformat(timespec="seconds"), "issued": 0,
            "failed": [], "refresh_failed": 11, "refresh_errors": [f"{ERR403} — 11 компл."]}

    class _Res:
        def scalar(self):
            return json.dumps(last, ensure_ascii=False)

    class _Db:
        def execute(self, *a, **k):
            return _Res()
    row = S.check_erid_auto(_Db())
    assert "403" in json.dumps(row, ensure_ascii=False)
