"""Закреплённые и недавние экраны меню — только свои (навигация v3, 17.11.2026). Права на раздел нет: ответ на
вопрос «чьё это» всегда «моё», как у темы интерфейса. В журнал действий не пишется — настройка вида, не данные."""
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import nav_prefs
from app.routers.auth import get_current_user
from app.database import get_db
from app.models import User

router = APIRouter()


class _PrefsIn(BaseModel):
    pinned: List[str] = Field(default_factory=list, max_length=20)
    recent: List[str] = Field(default_factory=list, max_length=40)


@router.get("")
def get_my_nav(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return nav_prefs.read(db, current_user.id)


@router.put("")
def put_my_nav(body: _PrefsIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return nav_prefs.save(db, current_user.id, body.pinned, body.recent)
