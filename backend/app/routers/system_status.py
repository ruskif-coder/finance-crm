"""Экран «Состояние системы» — одна ручка на чтение.

Закрыт `require_admin`, как «Журнал действий» и сводка руководителя: экран показывает
внутренности инфраструктуры — размеры баз, свободное место, состояние внешних связей.
Своего ключа права не заводим по той же причине, что и там: ключ неизменяем, а секцию в
конструкторе ролей можно выдать по неосторожности.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..audit import require_admin
from ..database import get_db
from ..models import User
from ..system import status as sysstatus

router = APIRouter()


@router.get("/status")
def system_status(live: bool = Query(False), db: Session = Depends(get_db),
                  user: User = Depends(require_admin)):
    """`live=1` добавляет запросы к внешним сервисам. По умолчанию их НЕТ: экран
    открывают часто, а чужие API этого не любят."""
    return sysstatus.collect(db, live=live)
