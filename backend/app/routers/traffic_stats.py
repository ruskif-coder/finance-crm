# -*- coding: utf-8 -*-
"""«Трафики → Статистика» (владелец 03.10.2026): общая стата текущих РК, «Block SIMB», база.

Расчёт — `app/traffic/stats.py`; здесь право и область видимости. Право своё
(`traffic_stats`, только просмотр), без бэкфилла: экран пока только владельцу.
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ad.models import AdCampaign
from app.database import get_db
from app.models import User
from app.permissions import require_permission
from app.routers.traffic import _apply_scope
from app.sales.models import SalesDeal
from app.traffic import stats

router = APIRouter()
VIEW = require_permission("traffic_stats", "view")


@router.get("")
def get_stats(period: Optional[str] = None, db: Session = Depends(get_db),
              user: User = Depends(VIEW)):
    """`period` пуст — текущие РК; `ГГГГ-ММ` — РК сделок этого месяца."""
    if period and not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", period):
        raise HTTPException(400, "Период — месяц в виде ГГГГ-ММ")
    q = (db.query(AdCampaign.id, SalesDeal.id)
         .join(SalesDeal, SalesDeal.id == AdCampaign.deal_id))
    allowed = {r[0] for r in _apply_scope(q, db, user, all_reps=True).all()}
    return stats.compute(db, allowed, period or None)
