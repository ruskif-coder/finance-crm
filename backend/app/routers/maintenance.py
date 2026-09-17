"""Техобслуживание: объявить, снять, спросить состояние.

Разбор режима и почему он живёт в базе — в шапке `app/maintenance.py`.

ЧИТАТЬ СОСТОЯНИЕ МОЖЕТ КАЖДЫЙ ВОШЕДШИЙ, и это обязательно: именно по этому ответу экран
рисует полосу «через N минут» и заглушку. Закрой чтение правом — человек без права
получил бы пустую ошибку вместо объяснения, почему всё закрыто.

ОБЪЯВЛЯЕТ И СНИМАЕТ ТОЛЬКО АДМИН. Действие останавливает работу всем сразу, и права
«настройки» для него мало.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import maintenance as mnt
from app.audit import log_action, require_admin
from app.database import get_db
from app.models import User
from app.routers.auth import get_current_user

router = APIRouter()


class AnnounceIn(BaseModel):
    # Текст можно переопределить, но умолчание стандартное (решение владельца
    # 17.09.2026): сочинять его в спешке — верный способ написать невнятное.
    note: Optional[str] = None


@router.get("")
def maintenance_state(db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    return mnt.state(db)


@router.post("")
def maintenance_announce(payload: AnnounceIn, db: Session = Depends(get_db),
                         user: User = Depends(require_admin)):
    """Объявить обслуживание через 10 минут. Срок фиксирован — выбор из вариантов на
    этой кнопке лишний: она нажимается в спешке, а лишний вопрос в спешке ошибается."""
    st = mnt.announce(db, by=user.name or user.email, note=payload.note)
    log_action(db, user, "maintenance_on", "settings", None,
               f"объявлено обслуживание с {st['from']} UTC")
    return st


@router.delete("")
def maintenance_cancel(db: Session = Depends(get_db),
                       user: User = Depends(require_admin)):
    """Снять режим — и отменой до наступления, и завершением после."""
    was = mnt.state(db)
    st = mnt.cancel(db)
    log_action(db, user, "maintenance_off", "settings", None,
               "обслуживание завершено" if was.get("mode") == "active"
               else "объявление обслуживания отменено")
    return st
