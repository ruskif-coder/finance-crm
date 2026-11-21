# -*- coding: utf-8 -*-
"""Экран «Деньги» — стартовый экран собственника вместо «Сводки руководителя» (владелец 18.11.2026).

Доступ — `require_admin`, как у прежней сводки: экран для одного человека, своё право в SECTIONS не заводится, пока
владелец не скажет, кому ещё его видеть (README хендоффа: финансист тоже, решение не принято). Логика — app/money.
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..audit import require_admin
from ..database import get_db
from ..models import User
from ..money.overview import build
from ..timez import msk_date

router = APIRouter()


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return build(db, msk_date(datetime.utcnow()))


@router.get("/business")
def business(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Вкладка «Бизнес» (20.11.2026): светофор продаж по месяцам, деньги в размещении, сверка с учётом, маржа по услугам."""
    from ..money.business import build as build_business
    return build_business(db, msk_date(datetime.utcnow()))
