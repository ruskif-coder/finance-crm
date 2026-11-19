"""Личные настройки вида таблиц — только свои (19.11.2026). Права на раздел нет, как у меню и темы: настройка вида, не
данные; в журнал действий не пишется."""
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import ui_prefs
from app.routers.auth import get_current_user
from app.database import get_db
from app.models import User

router = APIRouter()


class _PrefIn(BaseModel):
    value: Any


@router.get("/{key}")
def get_my_pref(key: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"key": key, "value": ui_prefs.read(db, current_user.id, key)}


@router.put("/{key}")
def put_my_pref(key: str, body: _PrefIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"key": key, "value": ui_prefs.save(db, current_user.id, key, body.value)}
