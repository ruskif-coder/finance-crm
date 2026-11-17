"""Экран «Статус системы» (v2 по хендоффу design_handoff_status, 16.11.2026).

Закрыт `require_admin`, как «Журнал действий» и сводка руководителя: экран показывает внутренности инфраструктуры —
размеры баз, свободное место, состояние внешних связей. Своего ключа права не заводим и с хендоффом (владелец
16.11.2026: «только админ»): ключ неизменяем, а секцию в конструкторе ролей можно выдать по неосторожности. Запуск
заданий и оповещения — тоже только админ. Единственная ручка для всех — отметка открытия страницы (`/hit`).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import log_action, require_admin
from ..database import get_db
from ..models import User
from ..system import alerts, jobs, presence, screen, watch
from .auth import get_current_user

router = APIRouter()


@router.get("/status")
def system_status(live: bool = Query(False), db: Session = Depends(get_db),
                  user: User = Depends(require_admin)):
    """Открытие экрана и автообновление раз в 30 с: проверки без запросов наружу — живые строки берутся из последнего
    фонового прогона. `live=1` — то же, что кнопка «Проверить», но без записи истории (оставлено для совместимости)."""
    from ..system import status as st
    return screen.build(db, st.collect(db, live=True) if live else None)


@router.post("/status/check")
def system_check_now(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """«Проверить»: полный фоновый прогон сейчас — живые проверки, запись истории, оповещения при смене состояния."""
    return screen.build(db, watch.run_once(db))


class HitIn(BaseModel):
    path: str = Field(min_length=1, max_length=300)


@router.post("/hit")
def page_hit(payload: HitIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Отметка «открыл страницу» — для «Онлайн сейчас». Ставит фронт на каждом переходе, для всех сотрудников."""
    presence.hit(db, user.id, payload.path)
    return {"ok": True}


@router.post("/jobs/{key}/run")
def run_job(key: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Ручной запуск фонового задания. Повторный запуск того же задания, пока идёт первый, — 409."""
    if key not in jobs.JOBS:
        raise HTTPException(404, "Такого задания нет")
    from ..system import status as st
    title = next((c["title"] for c in st.collect(db, live=False)["checks"] if c["key"] == key), key)
    try:
        jobs.start(db, key, user.id, title=title)
    except jobs.AlreadyRunning:
        raise HTTPException(409, "Задание уже выполняется — дождитесь итога")
    log_action(db, user, "system_job_run", "settings", None, f"ручной запуск: {title}")
    return {"ok": True}


class AlertsIn(BaseModel):
    bad: Optional[bool] = None
    warn: Optional[bool] = None
    ok: Optional[bool] = None
    tg: Optional[bool] = None
    mail: Optional[bool] = None


@router.put("/alerts")
def save_alerts(payload: AlertsIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    before = alerts.config(db)
    cfg = alerts.save(db, {**before, **payload.dict(exclude_unset=True, exclude_none=True)})
    names = {"bad": "отказ", "warn": "сводка предупреждений", "ok": "возврат в норму", "tg": "Телеграм", "mail": "почта"}
    diff = ", ".join(f"{names[k]} {'вкл' if cfg[k] else 'выкл'}" for k in cfg if cfg[k] != before[k])
    if diff:
        log_action(db, user, "system_alerts_changed", "settings", None, f"оповещения статуса: {diff}")
    return {**cfg, "on": alerts.is_on(cfg)}
