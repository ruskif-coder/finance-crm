# -*- coding: utf-8 -*-
"""Ночные проверки биддера, когда база статистики DSP недоступна.

Раньше: если базу DSP не удавалось открыть, проверки шли без неё молча — нигде не видно, что
сверка среза с сырьём пропущена (аудит 06.10.2026). Если же сбой случался на самом запросе
к ней, терялись ВСЕ проверки прогона — одной строкой «проверки не выполнены». Теперь любой
из двух сбоев даёт отдельное предупреждение, а остальные проверки работают.
"""
from sqlalchemy import text

from app.ad import daily_shares


class _DeadDspSession:
    closed = False

    def execute(self, *a, **k):
        raise RuntimeError("connection refused: dsp-db:5432 password=секрет")

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def _codes(rows):
    return {r["code"]: r for r in rows}


def test_dsp_db_that_cannot_be_opened_is_a_visible_warning(monkeypatch, db):
    import app.dsp.db as dsp_db

    def boom():
        raise RuntimeError("нет сети")
    monkeypatch.setattr(dsp_db, "DspSessionLocal", boom)
    got = _codes(daily_shares._checks(db, {"by_fact": True}, []))
    assert "dsp_db_unavailable" in got, "пропуск сверки с DSP не виден"
    assert got["dsp_db_unavailable"]["level"] == "warning"
    assert "checks_failed" not in got


def test_a_failing_dsp_query_costs_one_check_not_all(monkeypatch, db):
    import app.dsp.db as dsp_db
    dead = _DeadDspSession()
    monkeypatch.setattr(dsp_db, "DspSessionLocal", lambda: dead)
    got = _codes(daily_shares._checks(db, {"by_fact": True}, []))
    assert "checks_failed" not in got, "сбой DSP снёс все проверки прогона"
    assert got["dsp_db_unavailable"]["level"] == "warning"
    assert dead.closed
    text_all = str(got["dsp_db_unavailable"])
    assert "секрет" not in text_all, "текст ошибки драйвера (с адресом и паролем) попал в журнал"


def test_without_a_dsp_database_configured_nothing_is_added(monkeypatch, db):
    """Окружение без базы DSP (`DspSessionLocal` пуст) — это не сбой."""
    import app.dsp.db as dsp_db
    monkeypatch.setattr(dsp_db, "DspSessionLocal", None)
    assert "dsp_db_unavailable" not in _codes(daily_shares._checks(db, {"by_fact": True}, []))


def test_nothing_is_written_by_these_checks(db):
    n = db.execute(text("SELECT count(*) FROM bidder_run")).scalar()
    daily_shares._checks(db, {"by_fact": True}, [])
    assert db.execute(text("SELECT count(*) FROM bidder_run")).scalar() == n


def test_a_failure_of_our_own_database_leaves_the_session_usable(monkeypatch, db):
    """`_slice_vs_raw` читает и НАШУ базу. Если упала она, сессия остаётся в оборванной
    транзакции, и всё, что прогон делает дальше (журнал, факт на дату), падало бы следом."""
    from app.bidder import checks as K

    def broken_slice(db_, dsp_, day):
        db_.execute(text("SELECT 1/0"))
    monkeypatch.setattr(K, "_slice_vs_raw", broken_slice)
    g = K.gather(db, object(), __import__("datetime").date(2026, 10, 6))
    assert g["dsp_error"], "сбой не отмечен"
    assert db.execute(text("SELECT 1")).scalar() == 1, "сессия осталась в оборванной транзакции"
