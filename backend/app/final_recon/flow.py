# -*- coding: utf-8 -*-
"""Цикл сделки (владелец 14.10.2026) — у ВОРОНКИ РЕАЛИЗАЦИИ: «полный цикл» — трафик, DSP/Adfox, факт оттуда; «контур аккаунта» — запуск и
завершение кнопками аккаунта, трафик сделку не ведёт, факт в сверке вручную. Воронка сделки, нет её — воронка услуги, нет и её — полный цикл.

Карта «воронка → цикл» и «услуга → воронка» читается ОДИН раз на сессию базы (`db.info`): цикл спрашивают на каждой сделке очереди
и реестра, и запрос на сделку давал N+1 (прибор test_queue_state). Справочники крошечные и меняются руками."""
from typing import Optional

from sqlalchemy import text

FULL = "полный цикл"
ACCOUNT = "контур аккаунта"
FLOWS = (FULL, ACCOUNT)
_KEY = "final_recon.flow_maps"


def _maps(db) -> tuple:
    cached = db.info.get(_KEY)
    if cached is None:
        pipes = dict(db.execute(text("SELECT id, closing_flow FROM sales_pipelines")).fetchall())
        svcs = dict(db.execute(text("SELECT id, realization_pipeline_id FROM sales_services")).fetchall())
        cached = db.info[_KEY] = (pipes, svcs)
    return cached


def reset(db) -> None:
    """Сбросить карту после правки воронок или услуг в этой же сессии."""
    db.info.pop(_KEY, None)


def service_pipeline(db, service_id: Optional[int]) -> Optional[int]:
    """Воронка реализации услуги (для диалога движения: стадии реализации — только по ней)."""
    if db is None or not service_id:
        return None
    return _maps(db)[1].get(service_id)


def of_ids(db, realization_pipeline_id: Optional[int], service_id: Optional[int]) -> str:
    if db is None or not (realization_pipeline_id or service_id):
        return FULL
    pipes, svcs = _maps(db)
    pid = realization_pipeline_id or svcs.get(service_id)
    return pipes.get(pid) or FULL


def of_deal(db, deal) -> str:
    """`closing_flow` на самом объекте (тесты, заранее посчитанный) имеет приоритет."""
    own = getattr(deal, "closing_flow", None)
    if own:
        return own
    if db is None and hasattr(deal, "_sa_instance_state"):
        from sqlalchemy.orm import object_session
        db = object_session(deal)
    return of_ids(db, getattr(deal, "realization_pipeline_id", None), getattr(deal, "service_id", None))


def is_account(db, deal) -> bool:
    return of_deal(db, deal) == ACCOUNT
