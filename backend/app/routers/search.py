"""Глобальный поиск в шапке — `POST /api/search`.

Своего права у поиска нет (решение 27.09.2026, по образцу `/exec`): данных он не
владеет, каждая группа выдачи закрыта правом `view` своего типа. Права читаются здесь,
в теле ручки, и передаются движку — так гейт виден инвентарю `test_route_guards`.

Строка запроса — в теле, не в адресе: ИНН и названия юрлиц не должны оседать в журналах
Caddy (правило «персональных данных в URL нет»).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.permissions import get_permissions_for_user
from app.routers.auth import get_current_user
from app.search import engine

router = APIRouter()


class SearchIn(BaseModel):
    q: str = Field(..., max_length=500)
    types: Optional[List[str]] = Field(None, max_length=20)
    per_type: int = Field(5, ge=1, le=50)
    offset: int = Field(0, ge=0, le=10000)


@router.post("")
def search(payload: SearchIn, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    engine.check_rate_limit(user.id)
    perms = get_permissions_for_user(db, user)
    return engine.run(db, user, payload.q, types=payload.types, per_type=payload.per_type,
                      offset=payload.offset, perms=perms)
