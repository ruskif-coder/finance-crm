# -*- coding: utf-8 -*-
"""Кабинет площадки показывает факт ЗА ВЫЧЕТОМ «кукухи» (владелец 03.10.2026).

Правило живёт в двух местах по необходимости: витрина `pub.campaign_v1` (SQL — кабинет
читает её ролью базы, Python ему недоступен) и `app/traffic/stats.py` (страница
«Статистика»). Прибор сверяет их ЧИСЛАМИ на данных стенда: факт кабинета по каждому
размещению = «база» страницы. Разъедутся — площадка увидит одно, мы другое.
"""
import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.traffic import stats


def test_view_fact_equals_stats_base():
    db = SessionLocal()
    try:
        rows = [r for r in stats.compute(db)["rows"] if r["publisher_id"]]
        if not rows:
            pytest.skip("на стенде нет текущих РК с фактом")
        pubs = sorted({r["publisher_id"] for r in rows})
        db.execute(text("SELECT set_config('app.publisher_ids', :p, false)"),
                   {"p": ",".join(map(str, pubs))})
        view = {(r[1], r[0]): r[2] for r in db.execute(text("""
            SELECT v.publisher_id, c.id, v.fact FROM pub.campaign_v1 v
              JOIN launch_prep_target t ON t.id = v.placement_id
              JOIN ad_campaign c ON c.deal_id = t.deal_id""")).all()}
        both = [r for r in rows if (r["campaign_id"], r["publisher_id"]) in view]
        if not both:
            pytest.skip("витрина не видит ни одного размещения текущих РК")
        bad = [(r["deal"], r["publisher"], r["base"], view[(r["campaign_id"], r["publisher_id"])])
               for r in both if view[(r["campaign_id"], r["publisher_id"])] != r["base"]]
        assert not bad, f"кабинет и «Статистика» разошлись: {bad[:5]}"
    finally:
        db.rollback()
        db.close()


def test_view_subtracts_block_stat():
    body = SessionLocal().execute(text(
        "SELECT pg_get_viewdef('pub.campaign_v1'::regclass)")).scalar().lower()
    assert "dsp_block_stat" in body, "витрина кабинета не вычитает «кукуху»"
