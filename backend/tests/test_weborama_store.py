# -*- coding: utf-8 -*-
"""Хранение съёма Weborama: идемпотентность, отсутствие догадок, неучастие в факте.

Главный прибор файла — последний: строки верификатора, лежащие в `ad_campaign_stat`
рядом с нашим фактом, НЕ должны менять ни одного числа на дашборде. Это то самое
удвоение, которое не падает и выглядит правдоподобно; проверять его надо сквозным
замером «до и после», а не чтением кода.

Тесты ходят в обе живые базы стенда и убирают за собой в `finally`. Аккаунт `TEST-WCM`
выдуман намеренно: с боевыми данными он не пересекается ни в одной таблице.
"""
from datetime import date

import pytest
from sqlalchemy import text

from app.weborama import stats as S
from app.weborama import store

ACC = "TEST-WCM"
DAY = date(2026, 9, 11)
INS_KNOWN = "999001"      # с записью в реестре
INS_ALIEN = "999002"      # заведена мимо нас — прицепить не к чему


def _dsp():
    from app.dsp.db import DspSessionLocal, dsp_engine
    try:
        dsp_engine()
    except Exception:
        pytest.skip("аналитическая база недоступна")
    return DspSessionLocal()


def _main():
    from app.database import SessionLocal
    return SessionLocal()


def _some_placement(db):
    row = db.execute(text(
        "SELECT id, campaign_id FROM ad_campaign_placement ORDER BY id LIMIT 1")).first()
    if not row:
        pytest.skip("на стенде нет ни одной площадки РК")
    return row[0], row[1]


def _pull(rows):
    return S.WcmPull(rows=rows, absent_metrics=(), asked_metrics=("impression",),
                     start=DAY, end=DAY, grand_total=sum(r.impression for r in rows))


def _row(ins, imp, clk=0, label="TEST"):
    return S.WcmDayRow(day=DAY, insertion_id=ins, label=label, impression=imp, click=clk,
                       metrics={"impression": imp, "click": clk})


def _cleanup(dsp_db, db, placement_id=None):
    dsp_db.execute(text("DELETE FROM wcm_stat_daily WHERE account_id = :a"), {"a": ACC})
    dsp_db.execute(text("DELETE FROM wcm_sync_cursor WHERE account_id = :a"), {"a": ACC})
    dsp_db.commit()
    db.execute(text("DELETE FROM weborama_refs WHERE account_id = :a"), {"a": ACC})
    if placement_id:
        db.execute(text("DELETE FROM ad_campaign_stat "
                        "WHERE placement_id = :p AND source = 'weborama'"),
                   {"p": placement_id})
    db.commit()


def test_raw_is_replaced_not_accumulated():
    """Окно перезабора перекрывает трое суток — одни сутки приезжают по нескольку раз.

    Если бы съём добавлял строку вместо замещения, показы росли бы сами собой при
    каждом прогоне, и рост выглядел бы как открутка.
    """
    dsp_db, db = _dsp(), _main()
    try:
        store.save_raw(dsp_db, ACC, _pull([_row(INS_KNOWN, 100)]))
        store.save_raw(dsp_db, ACC, _pull([_row(INS_KNOWN, 140)]))
        got = dsp_db.execute(text(
            "SELECT count(*), sum(impression) FROM wcm_stat_daily WHERE account_id = :a"),
            {"a": ACC}).first()
        assert got[0] == 1, "второй прогон тех же суток обязан замещать, а не добавлять"
        assert got[1] == 140, "побеждает последнее значение — они дозаливают задним числом"
    finally:
        _cleanup(dsp_db, db)
        dsp_db.close(); db.close()


def test_insertion_without_a_ref_is_left_alone_and_counted():
    """Чужую вставку не угадываем — но и не молчим о ней.

    Замер 12.09.2026: в аккаунте 452 вставки, в реестре 0. Прогон, отчитавшийся
    «успешно», не положил бы на дашборд ни одного числа, и понять это по слову
    «успешно» было бы нельзя.
    """
    dsp_db, db = _dsp(), _main()
    placement_id, campaign_id = _some_placement(db)
    try:
        db.execute(text("INSERT INTO weborama_refs (account_id, kind, local_id, wcm_id, label) "
                        "VALUES (:a,'insertion',:l,:w,'TEST')"),
                   {"a": ACC, "l": placement_id, "w": INS_KNOWN})
        db.commit()
        store.save_raw(dsp_db, ACC, _pull([_row(INS_KNOWN, 100), _row(INS_ALIEN, 7000)]))
        got = store.push_daily(db, dsp_db, ACC, DAY, DAY)
        assert got["written"] == 1
        assert got["skipped"] == 1
        assert got["unmatched_impressions"] == 7000
        assert got["mapped_insertions"] == 1
    finally:
        _cleanup(dsp_db, db, placement_id)
        dsp_db.close(); db.close()


def test_push_is_idempotent():
    dsp_db, db = _dsp(), _main()
    placement_id, campaign_id = _some_placement(db)
    try:
        db.execute(text("INSERT INTO weborama_refs (account_id, kind, local_id, wcm_id, label) "
                        "VALUES (:a,'insertion',:l,:w,'TEST')"),
                   {"a": ACC, "l": placement_id, "w": INS_KNOWN})
        db.commit()
        store.save_raw(dsp_db, ACC, _pull([_row(INS_KNOWN, 100)]))
        store.push_daily(db, dsp_db, ACC, DAY, DAY)
        store.save_raw(dsp_db, ACC, _pull([_row(INS_KNOWN, 250)]))
        store.push_daily(db, dsp_db, ACC, DAY, DAY)
        rows = db.execute(text(
            "SELECT count(*), sum(shows) FROM ad_campaign_stat "
            "WHERE placement_id = :p AND source = 'weborama'"), {"p": placement_id}).first()
        assert rows[0] == 1 and rows[1] == 250
    finally:
        _cleanup(dsp_db, db, placement_id)
        dsp_db.close(); db.close()


def test_verifier_rows_do_not_move_the_fact():
    """СКВОЗНОЙ ЗАМЕР: факт на дашборде до и после записи измерителя.

    Ради этого и заводился реестр источников. Показы Weborama лежат в той же таблице,
    что наш счётчик, и до 12.09.2026 все шесть запросов дашборда сложили бы их вместе.
    """
    from app.routers.traffic_dashboard import _facts, _stat_by_day

    dsp_db, db = _dsp(), _main()
    placement_id, campaign_id = _some_placement(db)
    try:
        before = _facts(db, [campaign_id]).get(campaign_id, {}).get("shows") or 0
        before_day = dict(_stat_by_day(db, [campaign_id]).get(campaign_id, {}))

        db.execute(text("INSERT INTO weborama_refs (account_id, kind, local_id, wcm_id, label) "
                        "VALUES (:a,'insertion',:l,:w,'TEST')"),
                   {"a": ACC, "l": placement_id, "w": INS_KNOWN})
        db.commit()
        store.save_raw(dsp_db, ACC, _pull([_row(INS_KNOWN, 123456)]))
        store.push_daily(db, dsp_db, ACC, DAY, DAY)

        # строка измерителя действительно легла — иначе тест доказывал бы пустоту
        landed = db.execute(text(
            "SELECT sum(shows) FROM ad_campaign_stat "
            "WHERE placement_id = :p AND source = 'weborama'"), {"p": placement_id}).scalar()
        assert landed == 123456

        after = _facts(db, [campaign_id]).get(campaign_id, {}).get("shows") or 0
        assert after == before, "показы верификатора попали в факт — это то самое удвоение"
        assert dict(_stat_by_day(db, [campaign_id]).get(campaign_id, {})) == before_day
    finally:
        _cleanup(dsp_db, db, placement_id)
        dsp_db.close(); db.close()


def test_cursor_remembers_silence_and_failure():
    """Прогон, который не состоялся, с экрана неотличим от прогона, ничего не нашедшего."""
    dsp_db, db = _dsp(), _main()
    try:
        pull = S.WcmPull(rows=[], absent_metrics=("visibility",),
                         asked_metrics=("impression", "visibility"),
                         start=DAY, end=DAY, grand_total=None)
        store.remember(dsp_db, ACC, pull=pull)
        row = dsp_db.execute(text(
            "SELECT last_rows, last_absent, last_error, last_pulled_day "
            "FROM wcm_sync_cursor WHERE account_id = :a"), {"a": ACC}).first()
        assert row[0] == 0 and row[1] == "visibility" and row[2] is None

        store.remember(dsp_db, ACC, error="Weborama недоступна")
        row = dsp_db.execute(text(
            "SELECT last_error, last_pulled_day FROM wcm_sync_cursor WHERE account_id = :a"),
            {"a": ACC}).first()
        assert row[0] == "Weborama недоступна"
        assert row[1] == DAY, "отказ не должен стирать отметку о прошлой удачной выкачке"
    finally:
        _cleanup(dsp_db, db)
        dsp_db.close(); db.close()


def test_sync_reports_enough_to_judge_without_opening_the_database():
    dsp_db, db = _dsp(), _main()

    class FakeClient:
        def statistics(self, dimensions, metrics, **opts):
            return {"data": {"insertion": {INS_ALIEN: {"day": {
                "2026-09-11": {"metrics": {"impression": 500}}}}},
                "metrics": {"impression": 500}}, "metadata": {}}

    try:
        got = store.sync(db, dsp_db, FakeClient(), ACC, start=DAY, end=DAY)
        assert got["rows"] == 1 and got["impressions"] == 500
        assert got["discrepancy"] == 0
        assert got["written"] == 0 and got["skipped"] == 1
        assert got["unmatched_impressions"] == 500
    finally:
        _cleanup(dsp_db, db)
        dsp_db.close(); db.close()
