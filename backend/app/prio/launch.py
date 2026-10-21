# -*- coding: utf-8 -*-
"""«Запустить» / «Стоп» / «Старт» площадки запроса — РК в системе приоритезации (владелец 19.10.2026).

Запуск: согласовано → `POST /api/campaigns` (`toggle_on` и `autostart` = true: площадка согласовала — аптека запускает по
календарю) → camp_id и ссылки трекера → перечитать (`GET ?camp_id`) и сверить → «идёт». Повтор после оборванного POST не плодит
дубль: сначала ищем РК площадки с тем же SKU и ЕРИД за период (своего ключа повтора у API нет).
Стоп / старт — `PUT {"toggle_on": false|true}` с перечиткой."""
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.prio import models as M
from app.prio.client import PrioApiError, PrioClient
from app.prio.service import PrioError, placement, request_of

TRACKER_KEYS = ("imp_token_search", "imp_token_catalog", "imp_token_context",
                "clk_token_search", "clk_token_catalog", "clk_token_context")


def payload(db: Session, deal, p: M.PrioPlacement) -> dict:
    r = request_of(db, deal)
    site = db.execute(text("SELECT prio_site_id FROM sales_publishers WHERE id = :p"), {"p": p.publisher_id}).scalar()
    return {"site_id": site, "product_id": p.product_id, "product_name": r.product_name,
            "date_start": r.date_start.isoformat(), "date_end": r.date_end.isoformat(),
            "toggle_on": True, "autostart": True, "erid": p.erid, "erid_meta": r.erid_meta,
            "goal_imp": int(p.goal_imp or 0), "target_competitors": r.target_competitors or "",
            "target_mnn": r.target_mnn or "", "target_meta": r.target_meta or ""}


def _existing(client: PrioClient, body: dict):
    """РК, уже заведённая этим же запросом (оборванный ответ на POST): площадка + SKU + ЕРИД за период."""
    for c in client.campaigns(date_start=body["date_start"], date_end=body["date_end"]):
        if (c.get("site_id") == body["site_id"] and str(c.get("product_id")) == str(body["product_id"])
                and (c.get("erid") or "") == (body["erid"] or "")):
            return c
    return None


def _check(client: PrioClient, camp_id: int, want: dict) -> None:
    got = (client.campaigns(camp_id=camp_id) or [None])[0]
    if not got:
        raise PrioError(502, f"РК {camp_id} не нашлась в системе приоритезации после записи")
    diff = [k for k, v in want.items() if k in got and str(got[k]).lower() != str(v).lower()]
    if diff:
        raise PrioError(502, f"РК {camp_id}: в системе приоритезации не то, что отправили — {', '.join(diff)}")


def launch(db: Session, deal, pid: int, client: PrioClient = None) -> M.PrioPlacement:
    p = placement(db, deal, pid)
    if p.status != M.APPROVED:
        raise PrioError(409, f"Запустить можно согласованную площадку, а она «{p.status}»")
    body = payload(db, deal, p)
    if not body["site_id"]:
        raise PrioError(409, "У площадки нет site_id системы приоритезации")
    try:
        c = client or PrioClient()
        camp = _existing(c, body) or c.create(body)
        camp_id = camp.get("camp_id")
        if not camp_id:
            raise PrioError(502, "Система приоритезации не вернула camp_id")
        _check(c, camp_id, {"toggle_on": True, "autostart": True, "goal_imp": body["goal_imp"]})
    except PrioApiError as e:
        raise PrioError(502, str(e))
    now = datetime.utcnow()
    p.camp_id, p.tracker = camp_id, {k: camp.get(k) for k in TRACKER_KEYS if camp.get(k)}
    p.status, p.toggle_on, p.launched_at, p.updated_at = M.LIVE, True, now, now
    db.flush()
    return p


def toggle(db: Session, deal, pid: int, on: bool, client: PrioClient = None) -> M.PrioPlacement:
    p = placement(db, deal, pid)
    if p.status not in ((M.STOPPED,) if on else (M.LIVE,)) or not p.camp_id:
        raise PrioError(409, "Старт — у остановленной площадки, стоп — у идущей")
    try:
        c = client or PrioClient()
        c.update(p.camp_id, {"toggle_on": on})
        _check(c, p.camp_id, {"toggle_on": on})
    except PrioApiError as e:
        raise PrioError(502, str(e))
    p.toggle_on, p.status, p.updated_at = on, (M.LIVE if on else M.STOPPED), datetime.utcnow()
    db.flush()
    return p
