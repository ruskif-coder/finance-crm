# -*- coding: utf-8 -*-
"""Автодозапуск площадок приоритезации (владелец 16.11.2026).

РК сделки уже идёт хотя бы на одной площадке, у запроса включено «дозапускать сам» (`prio_requests.auto_launch_more`) —
площадка, которая согласовала и получила ЕРИД позже, запускается сама: тем же `launch.launch` (замок, анти-дубль, перечитка),
что и кнопка. Аккаунту — `prio_auto_launched`, площадке — то же «старт рк», что при ручном запуске.

Когда: сразу, как маркер площадки стал «готов» (`erid._after` — выпуск после «ок», ручная кнопка, крон) и проходом крона
автовыпуска ЕРИД (`erid.run_part`) — на случай, если сразу не вышло (сервис приоритезации лежал). Не запустилось — площадка
остаётся «согласовано», строка сделки показывает «есть незапущенные площадки», причина — в журнале.
Выключено или РК ещё не запускали (первый запуск — всегда руками аккаунта) — ничего не делаем."""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.ord import readiness
from app.prio import models as M

log = logging.getLogger("finance.prio")


def ready(p: M.PrioPlacement) -> bool:
    """Готова к запуску: площадка согласовала и маркер выпущен. Одно правило для чек-листа, плашки и автозапуска."""
    return p.status == M.APPROVED and readiness.erid_ready(p)


def placements(db: Session, request_id: int) -> list:
    return db.query(M.PrioPlacement).filter(M.PrioPlacement.request_id == request_id).order_by(M.PrioPlacement.id).all()


def armed(db: Session, r: Optional[M.PrioRequest]) -> bool:
    """Дозапуск возможен: флаг включён и хотя бы одна площадка запроса сейчас идёт."""
    return bool(r and r.auto_launch_more) and any(x.status == M.LIVE for x in placements(db, r.id))


def try_one(db: Session, deal, p: M.PrioPlacement, client=None, audit_fail: bool = True) -> bool:
    """Запустить площадку, если дозапуск взведён. → запущена ли. Сбой не поднимается: площадка ждёт, плашка видна.
    `audit_fail=False` — проход крона: сбой в лог сервера, а не в журнал действий (иначе запись на каждый прогон, ревью 16.11)."""
    from app.audit import log_action
    from app.prio import launch as L
    from app.prio.erid import _deal_is_closed
    from app.prio.service import PrioError
    r = db.get(M.PrioRequest, p.request_id)
    if not ready(p) or not armed(db, r) or _deal_is_closed(db, deal):
        return False
    try:
        L.launch(db, deal, p.id, client)
        db.commit()
    except PrioError as e:
        db.rollback()
        log.warning("приоритезация %s: автодозапуск площадки %s не прошёл: %s", deal.code, p.id, e.message)
        if audit_fail:
            log_action(db, None, "prio_auto_launch_failed", "sales_deal", deal.id,
                       f"{deal.code}: площадка запроса {p.id} — автодозапуск не прошёл: {e.message}")
        return False
    log_action(db, None, "prio_auto_launch", "sales_deal", deal.id, f"{deal.code}: площадка запроса {p.id} — запущена автоматически")
    from app.notify import prio as N
    N.auto_launched(db, deal, p)
    try:
        N.live_to_site(db, deal, p, True)
    except Exception:  # noqa: BLE001 — площадка запущена; письмо о старте не важнее запуска
        db.rollback()
        log.exception("приоритезация %s: «старт рк» площадке %s не ушёл", deal.code, p.id)
    return True


def run(db: Session, client=None) -> list:
    """Проход крона: все готовые площадки запросов с взведённым дозапуском. → [{deal, placement}] запущенных.
    Запрос с прошедшим периодом не трогаем: запускать площадку на окончившийся период незачем."""
    from datetime import date

    from app.sales.models import SalesDeal
    out = []
    todo = (db.query(M.PrioPlacement).join(M.PrioRequest, M.PrioRequest.id == M.PrioPlacement.request_id)
            .filter(M.PrioRequest.auto_launch_more.is_(True), M.PrioPlacement.status == M.APPROVED)
            .order_by(M.PrioPlacement.id).all())
    for p in todo:
        r = db.get(M.PrioRequest, p.request_id)
        if r.date_end and r.date_end < date.today():
            continue
        deal = db.get(SalesDeal, r.deal_id)
        if deal is not None and try_one(db, deal, p, client, audit_fail=False):
            out.append({"deal": deal.code, "placement": p.id})
    return out
