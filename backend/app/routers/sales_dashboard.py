"""
Витрина дашборда продаж.

Считается на лету, без материализации: объёмы малы (2340 сделок), а материализация
вводит вопрос момента пересчёта и расхождения витрины с источником.

Два правила, заложенных в каждый разрез:

1. Слой денег НЕ читается из колонки sales_deals — выводится джойном на
   sales_bitrix_stage_map. Иначе правка маппинга не влияла бы на уже загруженные
   сделки, и обещание «раскладка меняется без деплоя» было бы ложным.

2. Каждая ось содержит корзину «Без группы». Итог по осям обязан сходиться
   с общим итогом. Это прямая профилактика дефекта, известного в P&L финмодуля,
   где операции без article.group молча исчезают из отчёта.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session
from typing import Optional
import os
import re

from app.database import get_db
from app.models import User
from app.permissions import require_permission
from app.sales.models import (SalesDeal, SalesBitrixStageMap, SalesAdvertiser,
                              SalesRep, SalesBitrixSyncLog)

router = APIRouter()

NO_GROUP = "Без группы"
_PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")


def _month_bounds(value: str, is_end: bool):
    """'2026-03' -> первое или последнее число месяца. Формат тот же, что
    в отчётах финмодуля (/api/reports/dds), чтобы фильтры выглядели одинаково."""
    if not value:
        return None
    if not _PERIOD_RE.match(value):
        raise HTTPException(status_code=400, detail=f"Период «{value}» должен быть в формате ГГГГ-ММ")
    year, month = int(value[:4]), int(value[5:7])
    if not is_end:
        return f"{year:04d}-{month:02d}-01"
    if month == 12:
        year, month = year + 1, 1
    else:
        month += 1
    return f"{year:04d}-{month:02d}-01"


def _base_query(db: Session, date_from, date_to, pipeline, sales_rep_id,
                account_manager_id, advertiser_id, money_layer):
    """Сделки, склеенные с маппингом стадий. Джойн LEFT и только по активным
    строкам маппинга: неизвестная или намеренно отключённая стадия («Сделка
    провалена») даёт NULL и попадает в «Без группы», а не исчезает."""
    q = db.query(SalesDeal, SalesBitrixStageMap.money_layer.label("layer")).outerjoin(
        SalesBitrixStageMap,
        and_(SalesBitrixStageMap.pipeline == SalesDeal.pipeline,
             SalesBitrixStageMap.bitrix_stage == SalesDeal.bitrix_stage,
             SalesBitrixStageMap.is_active.is_(True)),
    )

    start, end = _month_bounds(date_from, False), _month_bounds(date_to, True)
    if start or end:
        # Пересечение периода размещения с запрошенным окном.
        # period_to = NULL означает календарный месяц period_from.
        eff_to = func.coalesce(SalesDeal.period_to, SalesDeal.period_from)
        conds = []
        if start:
            conds.append(eff_to >= start)
        if end:
            conds.append(SalesDeal.period_from < end)
        q = q.filter(and_(*conds))

    if pipeline:
        q = q.filter(SalesDeal.pipeline == pipeline)
    if sales_rep_id is not None:
        q = q.filter(SalesDeal.sales_rep_id == sales_rep_id)
    if account_manager_id is not None:
        q = q.filter(SalesDeal.account_manager_id == account_manager_id)
    if advertiser_id is not None:
        q = q.filter(SalesDeal.advertiser_id == advertiser_id)
    if money_layer:
        q = q.filter(SalesBitrixStageMap.money_layer == money_layer)
    return q


def _group(rows, key_fn):
    """Сворачивает выборку по ключу, пустой ключ — в «Без группы»."""
    acc = {}
    for deal, layer in rows:
        key = key_fn(deal, layer) or NO_GROUP
        bucket = acc.setdefault(key, {"name": key, "deals": 0, "amount": 0.0})
        bucket["deals"] += 1
        bucket["amount"] += float(deal.amount or 0)
    return sorted(acc.values(), key=lambda b: -b["amount"])


@router.get("/dashboard")
def dashboard(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    pipeline: Optional[str] = None,
    sales_rep_id: Optional[int] = None,
    account_manager_id: Optional[int] = None,
    advertiser_id: Optional[int] = None,
    money_layer: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sales_dashboard", "view")),
):
    rows = _base_query(db, date_from, date_to, pipeline, sales_rep_id,
                       account_manager_id, advertiser_id, money_layer).all()

    adv_names = dict(db.query(SalesAdvertiser.id, SalesAdvertiser.name).all())
    rep_names = dict(db.query(SalesRep.id, SalesRep.name).all())

    total_amount = sum(float(d.amount or 0) for d, _ in rows)

    by_layer = _group(rows, lambda d, layer: layer)
    # Сверка: сумма по слоям обязана совпасть с общим итогом.
    # Расхождение означает потерянные строки — показываем его, а не прячем.
    layers_sum = sum(b["amount"] for b in by_layer)

    # Сделки без периода размещения не попадают ни в один месяц. Их видно
    # отдельной строкой: 53% сделок в источнике не имеют «Старт РК».
    no_period = sum(1 for d, _ in rows if d.period_from is None)

    last_sync = (db.query(SalesBitrixSyncLog)
                 .filter(SalesBitrixSyncLog.status == "success")
                 .order_by(SalesBitrixSyncLog.finished_at.desc()).first())

    return {
        "filters": {
            "date_from": date_from, "date_to": date_to, "pipeline": pipeline,
            "sales_rep_id": sales_rep_id, "account_manager_id": account_manager_id,
            "advertiser_id": advertiser_id, "money_layer": money_layer,
        },
        "totals": {
            "deals": len(rows),
            "amount": round(total_amount, 2),
            "deals_without_period": no_period,
            "reconciles": round(layers_sum, 2) == round(total_amount, 2),
        },
        "by_layer": by_layer,
        "by_pipeline": _group(rows, lambda d, layer: d.pipeline),
        "by_sales_rep": _group(rows, lambda d, layer: rep_names.get(d.sales_rep_id)),
        "by_account_manager": _group(rows, lambda d, layer: rep_names.get(d.account_manager_id)),
        "by_advertiser": _group(rows, lambda d, layer: adv_names.get(d.advertiser_id))[:50],
        "by_month": sorted(
            _group(rows, lambda d, layer: d.period_from.strftime("%Y-%m") if d.period_from else None),
            key=lambda b: b["name"],
        ),
        # Витрина всегда сообщает возраст данных: молча устаревшие цифры —
        # худшее поведение для отчётной системы.
        "last_sync_at": last_sync.finished_at.isoformat() if last_sync and last_sync.finished_at else None,
    }


@router.get("/sync/status")
def sync_status(db: Session = Depends(get_db),
                current_user: User = Depends(require_permission("sales_dashboard", "view"))):
    rows = (db.query(SalesBitrixSyncLog)
            .order_by(SalesBitrixSyncLog.started_at.desc()).limit(10).all())
    return {"items": [{
        "id": r.id, "started_at": r.started_at, "finished_at": r.finished_at,
        "status": r.status, "entity": r.entity, "fetched": r.fetched,
        "created": r.created, "updated": r.updated, "rejected": r.rejected,
        "error_text": r.error_text,
    } for r in rows]}


@router.post("/sync")
def run_sync(db: Session = Depends(get_db),
             current_user: User = Depends(require_permission("sales_dashboard", "edit"))):
    """Принудительная синхронизация с Битрикс24.

    Пока вебхук не настроен, честно отвечает 503 вместо создания пустого
    успешного прогона: витрина не должна показывать «синхронизировано»,
    когда синхронизации не было."""
    if not os.getenv("BITRIX_WEBHOOK_URL"):
        raise HTTPException(
            status_code=503,
            detail="BITRIX_WEBHOOK_URL не задан в .env — синхронизация с Битрикс24 не настроена",
        )
    raise HTTPException(
        status_code=501,
        detail="Загрузка из Битрикс24 ещё не подключена: данные загружены из Excel",
    )
