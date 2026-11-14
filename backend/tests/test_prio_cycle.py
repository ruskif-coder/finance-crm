# -*- coding: utf-8 -*-
"""Свой цикл приоритезации (владелец 13.11.2026): запуск и завершение — кнопками аккаунта, трафик не участвует; РК заводится как
носитель факта; факт — из статистики сервиса или, по решению аккаунта на итоговой сверке, из загруженного файла по шаблону Adfox
без номера креатива («переключатель уже на итоговой сверке, у аккаунта решение подгружать или нет»).

Поломки, которые ловят тесты: проверки полного цикла (площадка собрана, РК в DSP) запирают приоритезацию; «Завершить» недоступна;
запуск первой площадки не двигает сделку; ночной сбор перетирает загруженный файлом факт; файл пишет не в ту площадку или не те
дни; условие «цикл» списком не понимается и «сделка завершена аккаунтом» перестаёт действовать у контура аккаунта."""
from datetime import date
from io import BytesIO

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.final_recon import flow
from app.final_recon import launch as LAUNCH
from app.prio import fact_file as FF
from app.prio import launch as L
from app.prio import models as M
from app.prio import service as S
from app.prio import stats as ST
from app.sales import stage_checks as sc
from tests.test_prio import FakeApi, _U, _ready
from tests.test_prio import env as _prio_env

env = _prio_env


def _prio_pipeline(db):
    pid = db.execute(text("SELECT id FROM sales_pipelines WHERE name = 'Приоритезация'")).scalar()
    if pid is None:
        pytest.skip("на стенде нет воронки «Приоритезация» (миграция 2026-11-13_prio_cycle.sql)")
    return pid


def _as_prio(db, d):
    d.realization_pipeline_id = _prio_pipeline(db)
    db.flush()
    flow.reset(db)


def _stage(db, name):
    return db.execute(text("SELECT id FROM sales_stages WHERE name = :n"), {"n": name}).scalar()


def test_scope_closing_flow_accepts_a_list():
    class _D:
        closing_flow = "контур аккаунта"
    assert sc.scope_matches({"closing_flow": ["контур аккаунта", "приоритезация"]}, _D())
    assert sc.scope_matches({"closing_flow": "контур аккаунта"}, _D())
    assert not sc.scope_matches({"closing_flow": ["приоритезация"]}, _D())


def test_prio_deal_has_its_own_cycle(env):
    db, d, _ = env
    _as_prio(db, d)
    assert flow.of_deal(db, d) == flow.PRIO
    assert not flow.is_account(db, d), "не контур аккаунта: факт — из статистики, РК заводится"
    assert flow.has_account_buttons(db, d), "«Запустить» / «Завершить» — кнопки аккаунта"


def test_finish_button_moves_prio_deal_to_recon(env):
    db, d, _ = env
    _as_prio(db, d)
    d.our_stage_id = _stage(db, "В размещении")
    db.flush()
    assert LAUNCH.available(db, d) == "finish"


def test_live_needs_a_running_placement(env):
    db, d, pubs = env
    _as_prio(db, d)
    p = _ready(db, d, pubs[0])
    assert sc.REGISTRY["prio_live"].fn(sc.Ctx(db, d)).state == sc.NOT_YET
    p.status = M.LIVE
    db.flush()
    assert sc.REGISTRY["prio_live"].fn(sc.Ctx(db, d)).state == sc.OK


def test_first_launch_moves_deal_to_live(env, monkeypatch):
    db, d, pubs = env
    _as_prio(db, d)
    p = _ready(db, d, pubs[0])
    S.edit_placement(db, d, p.id, {"product_url": "https://maksavit.ru/p/1"})
    S.send(db, d, p.id, _U())
    S.set_sku(db, p, "1234567")
    S.verdict(db, p, "ок", None)
    p.erid = "2SDnjcTest01"
    monkeypatch.setattr("app.ord.readiness.erid_ready", lambda *_: True)
    db.flush()
    L.launch(db, d, p.id, FakeApi())
    stage = db.execute(text("SELECT name FROM sales_stages WHERE id = :s"), {"s": d.our_stage_id}).scalar()
    assert stage == "В размещении"


def _xlsx(rows):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["День", "Название кампании", "Показы", "Переходы", "Уникальные показы"])
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_fact_file_writes_days_to_its_placement_and_switches_source(env):
    db, d, pubs = env
    _as_prio(db, d)
    p = _ready(db, d, pubs[0])
    code = "ZTST"                                       # код площадки — часть названия кампании в файле; в транзакции теста
    db.execute(text("UPDATE sales_publishers SET code = :c WHERE id = :p"), {"c": code, "p": pubs[0]})
    from app.ad import build
    if not db.execute(text("SELECT 1 FROM ad_campaign WHERE deal_id = :d"), {"d": d.id}).first():
        build.ensure_campaign_on_move(db, d, db.execute(text("SELECT * FROM sales_stages WHERE name = 'Готовятся к старту'")).first())
    data = _xlsx([["05.11.2026", f"{d.code}-{code}", 1000, 7, 900], ["06.11.2026", f"{d.code}-{code}", 1500, 9, 1300],
                  ["06.11.2026", "ЧУЖОЕ-ИМЯ", 5, 0, 5]])
    out = FF.apply(db, d, data, _U())
    assert out["written"] == 2 and out["unknown"] == ["ЧУЖОЕ-ИМЯ"]
    shows = db.execute(text("""SELECT sum(s.shows) FROM ad_campaign_stat s JOIN ad_campaign c ON c.id = s.campaign_id
                                WHERE c.deal_id = :d AND s.source = 'prio' AND s.date IN ('2026-11-05', '2026-11-06')"""),
                       {"d": d.id}).scalar()
    assert int(shows) == 2500
    assert db.execute(text("SELECT fact_source FROM prio_placements WHERE id = :i"), {"i": p.id}).scalar() == "файл",         "переключатель записан в базу, а не только на объекте"


def test_nightly_pull_does_not_overwrite_file_fact(env):
    db, d, pubs = env
    _as_prio(db, d)
    p = _ready(db, d, pubs[0])
    p.camp_id, p.fact_source = 777001, "файл"
    db.flush()

    class _Api:
        def stats(self, a, b):
            return {"ok": True, "stats": [{"camp_id": 777001, "site_id": 1, "source": "search", "event": "imp", "count": 42}]}
    out = ST.pull(db, _Api(), [date(2026, 11, 5)], commit=False)
    assert out["snapshots"] == 1, "снимок для автостопа сохраняется"
    assert out["written"] == 0, "факт площадки с файлом ночной сбор не трогает"


def test_ds_needs_fact_for_every_launched_placement(env):
    db, d, pubs = env
    _as_prio(db, d)
    p = _ready(db, d, pubs[0])
    p.status, p.camp_id = M.STOPPED, 777002
    db.flush()
    assert sc.REGISTRY["prio_fact_complete"].fn(sc.Ctx(db, d)).state == sc.NOT_YET
    db.add(M.PrioStatRaw(camp_id=777002, day=date(2026, 11, 5), shows=10, clicks=0))
    db.flush()
    assert sc.REGISTRY["prio_fact_complete"].fn(sc.Ctx(db, d)).state == sc.OK
