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
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session, aliased
from typing import Optional, List, Annotated
from pydantic import BaseModel
from datetime import date, datetime
import os
import re

from app.database import get_db
from app.models import User, Counterparty
from app.permissions import require_permission
from app.audit import log_action
from app.sales.models import (SalesDeal, SalesBitrixStageMap, SalesAdvertiser,
                              SalesRep, SalesBrand, SalesBitrixSyncLog,
                              SalesDealFieldOverride, SalesAgency)

router = APIRouter()

NO_GROUP = "Без группы"

def _short_fio(full):
    """«Андрей Мошков» -> «Андрей М.». Первое слово + первая буква второго."""
    if not full:
        return None
    parts = str(full).split()
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][:1].upper()}."

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


def _in(column, values):
    """Фильтр «одно из списка». Пустой список означает «без ограничения»,
    а не «ничего не подходит» — иначе снятие всех галочек обнуляло бы выборку."""
    return column.in_(values) if values else None


def _base_query(db: Session, date_from, date_to, pipeline, sales_rep_id,
                account_manager_id, advertiser_id, money_layer,
                bitrix_stage=None, brand_id=None, agency_id=None):
    """Сделки, склеенные с маппингом стадий. Джойн LEFT и только по активным
    строкам маппинга: неизвестная или намеренно отключённая стадия («Сделка
    провалена») даёт NULL и попадает в «Без группы», а не исчезает."""
    q = db.query(SalesDeal,
                 SalesBitrixStageMap.money_layer.label("layer"),
                 SalesBitrixStageMap.stage_key.label("stage_key")).outerjoin(
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

    for condition in (
        _in(SalesDeal.pipeline, pipeline),
        _in(SalesDeal.bitrix_stage, bitrix_stage),
        _in(SalesDeal.sales_rep_id, sales_rep_id),
        _in(SalesDeal.account_manager_id, account_manager_id),
        _in(SalesDeal.advertiser_id, advertiser_id),
        _in(SalesDeal.brand_id, brand_id),
        _in(SalesDeal.agency_id, agency_id),
        _in(SalesBitrixStageMap.money_layer, money_layer),
    ):
        if condition is not None:
            q = q.filter(condition)
    return q


def _group(rows, key_fn):
    """Сворачивает выборку по ключу, пустой ключ — в «Без группы»."""
    acc = {}
    for deal, layer, _stage_key in rows:
        key = key_fn(deal, layer) or NO_GROUP
        bucket = acc.setdefault(key, {"name": key, "deals": 0, "amount": 0.0})
        bucket["deals"] += 1
        bucket["amount"] += float(deal.amount or 0)
    return sorted(acc.values(), key=lambda b: -b["amount"])


@router.get("/dashboard")
def dashboard(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    pipeline: Annotated[Optional[List[str]], Query()] = None,
    bitrix_stage: Annotated[Optional[List[str]], Query()] = None,
    sales_rep_id: Annotated[Optional[List[int]], Query()] = None,
    account_manager_id: Annotated[Optional[List[int]], Query()] = None,
    advertiser_id: Annotated[Optional[List[int]], Query()] = None,
    brand_id: Annotated[Optional[List[int]], Query()] = None,
    agency_id: Annotated[Optional[List[int]], Query()] = None,
    money_layer: Annotated[Optional[List[str]], Query()] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sales_dashboard", "view")),
):
    rows = _base_query(db, date_from, date_to, pipeline, sales_rep_id,
                       account_manager_id, advertiser_id, money_layer,
                       bitrix_stage, brand_id, agency_id).all()

    adv_names = dict(db.query(SalesAdvertiser.id, SalesAdvertiser.name).all())
    rep_names = dict(db.query(SalesRep.id, SalesRep.name).all())

    total_amount = sum(float(d.amount or 0) for d, _, _ in rows)

    by_layer = _group(rows, lambda d, layer: layer)
    # Сверка: сумма по слоям обязана совпасть с общим итогом.
    # Расхождение означает потерянные строки — показываем его, а не прячем.
    layers_sum = sum(b["amount"] for b in by_layer)

    # Сделки без периода размещения не попадают ни в один месяц. Их видно
    # отдельной строкой: 53% сделок в источнике не имеют «Старт РК».
    no_period = sum(1 for d, _, _ in rows if d.period_from is None)

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


@router.get("/deals")
def deals_registry(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    pipeline: Annotated[Optional[List[str]], Query()] = None,
    bitrix_stage: Annotated[Optional[List[str]], Query()] = None,
    sales_rep_id: Annotated[Optional[List[int]], Query()] = None,
    account_manager_id: Annotated[Optional[List[int]], Query()] = None,
    advertiser_id: Annotated[Optional[List[int]], Query()] = None,
    brand_id: Annotated[Optional[List[int]], Query()] = None,
    agency_id: Annotated[Optional[List[int]], Query()] = None,
    money_layer: Annotated[Optional[List[str]], Query()] = None,
    search: Optional[str] = None,
    gaps: Annotated[Optional[List[str]], Query()] = None,
    sort: str = "period_from",
    direction: str = "desc",
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sales_dashboard", "view")),
):
    """Реестр сделок — базовое представление, от которого строится всё остальное.

    Отдаёт учётные поля как есть, включая незаполненные: пустое поле — это факт
    о данных, и прятать его нельзя. Часть атрибутов (продукты, агентства,
    клиентская сумма) пока живёт только в сыром слое sales_bitrix_raw и в колонки
    не вынесена — см. раздел 13 спецификации."""
    q = _base_query(db, date_from, date_to, pipeline, sales_rep_id,
                    account_manager_id, advertiser_id, money_layer,
                    bitrix_stage, brand_id, agency_id)

    if search:
        pattern = f"%{search.strip()}%"
        q = q.filter(or_(SalesDeal.title.ilike(pattern),
                         SalesDeal.bitrix_id.ilike(pattern)))

    # Фильтр «незаполненные»: показать только сделки с пробелами в этих полях.
    # Несколько значений складываются по «или» — «покажи всё, где чего-то не хватает».
    if gaps:
        gap_columns = {
            "advertiser_id": SalesDeal.advertiser_id,
            "agency_id": SalesDeal.agency_id,
            "brand_id": SalesDeal.brand_id,
            "sales_rep_id": SalesDeal.sales_rep_id,
            "account_manager_id": SalesDeal.account_manager_id,
            "period_from": SalesDeal.period_from,
            "period_to": SalesDeal.period_to,
        }
        conds = [gap_columns[g].is_(None) for g in gaps if g in gap_columns]
        if conds:
            q = q.filter(or_(*conds))

    total = q.count()

    # Сортировка по именам исполнителей и рекламодателя — через отдельные алиасы
    # sales_reps: продавец и аккаунт-менеджер ссылаются на одну таблицу, и без
    # алиасов SQLAlchemy не сможет соединить её дважды.
    rep_a, acct_a, adv_a = aliased(SalesRep), aliased(SalesRep), aliased(SalesAdvertiser)
    q = (q.outerjoin(rep_a, rep_a.id == SalesDeal.sales_rep_id)
          .outerjoin(acct_a, acct_a.id == SalesDeal.account_manager_id)
          .outerjoin(adv_a, adv_a.id == SalesDeal.advertiser_id))

    sortable = {
        "bitrix_id": SalesDeal.bitrix_id,
        "title": SalesDeal.title,
        "pipeline": SalesDeal.pipeline,
        "bitrix_stage": SalesDeal.bitrix_stage,
        "money_layer": SalesBitrixStageMap.money_layer,
        "amount": SalesDeal.amount,
        "advertiser": adv_a.name,
        "sales_rep": rep_a.name,
        "account_manager": acct_a.name,
        "period_from": SalesDeal.period_from,
        "period_to": SalesDeal.period_to,
        "date_create": SalesDeal.date_create,
    }
    column = sortable.get(sort)
    if column is None:
        raise HTTPException(status_code=400, detail=f"Сортировка по «{sort}» не поддерживается")

    # nullslast в обоих направлениях: незаполненные поля не должны занимать
    # начало списка — их и так много, и они вытеснили бы содержательные строки.
    ordering = column.desc().nullslast() if direction == "desc" else column.asc().nullslast()
    rows = q.order_by(ordering, SalesDeal.id.desc()).limit(min(limit, 500)).offset(offset).all()

    adv = dict(db.query(SalesAdvertiser.id, func.coalesce(SalesAdvertiser.short_name, SalesAdvertiser.name)).all())
    reps = dict(db.query(SalesRep.id, SalesRep.name).all())
    brands = dict(db.query(SalesBrand.id, SalesBrand.name).all())
    cps = dict(db.query(Counterparty.id, Counterparty.name).all())
    agencies = dict(db.query(SalesAgency.id, func.coalesce(SalesAgency.short_name, SalesAgency.name)).all())

    # Юрлица, прикреплённые к агентствам — для колонки «Плательщик»:
    # по умолчанию первое, по клику можно выбрать другое.
    from app.sales.models import SalesAgencyCounterparty
    agency_legals = {}
    for lk in db.query(SalesAgencyCounterparty).order_by(SalesAgencyCounterparty.id).all():
        agency_legals.setdefault(lk.agency_id, []).append(
            {"id": lk.counterparty_id, "name": cps.get(lk.counterparty_id)})

    def resolve_payer(d):
        # приоритет: выбранное вручную юрлицо -> первое юрлицо агентства -> текст «Компания»
        if d.payer_counterparty_id:
            return cps.get(d.payer_counterparty_id)
        legals = agency_legals.get(d.agency_id)
        if legals:
            return legals[0]["name"]
        return d.payer_name

    # Какие поля на этой странице заполнены вручную — чтобы интерфейс их пометил
    # и было видно, что синхронизация их не тронет.
    page_ids = [d.id for d, _, _ in rows]
    manual = {}
    if page_ids:
        for o in (db.query(SalesDealFieldOverride)
                  .filter(SalesDealFieldOverride.deal_id.in_(page_ids)).all()):
            manual.setdefault(o.deal_id, []).append(o.field_name)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [{
            "id": d.id,
            "bitrix_id": d.bitrix_id,
            "title": d.title,
            "pipeline": d.pipeline,
            "product": d.product,
            "period": d.period_from.strftime("%Y-%m") if d.period_from else None,
            "bitrix_stage": d.bitrix_stage,
            "money_layer": layer or NO_GROUP,
            "stage_key": stage_key,
            "agency": agencies.get(d.agency_id),
            "agency_id": d.agency_id,
            "payer_name": d.payer_name,
            # выбранный/дефолтный плательщик и варианты для выпадашки
            "payer": resolve_payer(d),
            "payer_counterparty_id": d.payer_counterparty_id,
            "agency_legals": agency_legals.get(d.agency_id, []),
            "amount": d.amount,
            "currency": d.currency,
            "advertiser": adv.get(d.advertiser_id),
            "brand": brands.get(d.brand_id),
            "sales_rep": _short_fio(reps.get(d.sales_rep_id)),
            "account_manager": _short_fio(reps.get(d.account_manager_id)),
            "counterparty": cps.get(d.counterparty_id),
            "period_from": d.period_from,
            "period_to": d.period_to,
            "annex_id": d.annex_id,
            "date_create": d.date_create,
            "date_modify": d.date_modify,
            # id нужны интерфейсу для выпадающих списков при правке
            "advertiser_id": d.advertiser_id,
            "brand_id": d.brand_id,
            "sales_rep_id": d.sales_rep_id,
            "account_manager_id": d.account_manager_id,
            "manual_fields": manual.get(d.id, []),
        } for d, layer, stage_key in rows],
    }


class DealPatch(BaseModel):
    """Ручная правка полей сделки. Передаются только изменяемые поля.
    Значение None означает «очистить», отсутствие ключа — «не трогать»."""
    advertiser_id: Optional[int] = None
    agency_id: Optional[int] = None
    brand_id: Optional[int] = None
    sales_rep_id: Optional[int] = None
    account_manager_id: Optional[int] = None
    payer_counterparty_id: Optional[int] = None
    period_from: Optional[date] = None
    period_to: Optional[date] = None


# Поля, доступные ручной правке. Расширять осознанно: каждое попадёт
# в очередь на заливку в Битрикс.
EDITABLE_INT = ("advertiser_id", "agency_id", "brand_id", "sales_rep_id",
                "account_manager_id", "payer_counterparty_id")
EDITABLE_DATE = ("period_from", "period_to")
EDITABLE_STR = ("product",)


class BulkUpdate(BaseModel):
    """Массовое изменение выбранных сделок. Передаются только меняемые поля;
    отсутствие ключа = не трогать. period — строка ГГГГ-ММ (ставится в period_from)."""
    deal_ids: List[int]
    advertiser_id: Optional[int] = None
    agency_id: Optional[int] = None
    sales_rep_id: Optional[int] = None
    account_manager_id: Optional[int] = None
    product: Optional[str] = None
    period: Optional[str] = None


class BulkDelete(BaseModel):
    deal_ids: List[int]


@router.post("/deals/bulk-update")
def bulk_update_deals(payload: BulkUpdate, db: Session = Depends(get_db),
                      current_user: User = Depends(require_permission("sales_dashboard", "edit"))):
    """Применяет заданные поля ко всем выбранным сделкам и помечает их ручными
    (синхронизация не перезапишет). Пустые/непереданные поля не трогаются."""
    if not payload.deal_ids:
        raise HTTPException(status_code=400, detail="Не выбрано ни одной сделки")

    changes = payload.dict(exclude_unset=True, exclude={"deal_ids"})
    if not changes:
        raise HTTPException(status_code=400, detail="Не задано ни одного поля")

    # period ГГГГ-ММ -> period_from = первое число месяца
    updates = {}
    if "period" in changes:
        pv = (changes.pop("period") or "").strip()
        if pv:
            if not _PERIOD_RE.match(pv):
                raise HTTPException(status_code=400, detail="Период должен быть ГГГГ-ММ")
            updates[SalesDeal.period_from] = date(int(pv[:4]), int(pv[5:7]), 1)
            changes["period_from"] = updates[SalesDeal.period_from]
    for f in ("advertiser_id", "agency_id", "sales_rep_id", "account_manager_id", "product"):
        if f in changes:
            updates[getattr(SalesDeal, f)] = changes[f]

    if updates:
        db.query(SalesDeal).filter(SalesDeal.id.in_(payload.deal_ids)).update(
            updates, synchronize_session=False)

    # помечаем как ручные правки (защита от синхронизации)
    existing = {(o.deal_id, o.field_name): o for o in db.query(SalesDealFieldOverride)
                .filter(SalesDealFieldOverride.deal_id.in_(payload.deal_ids)).all()}
    for did in payload.deal_ids:
        for field, value in changes.items():
            row = existing.get((did, field))
            if row is None:
                row = SalesDealFieldOverride(deal_id=did, field_name=field)
                db.add(row)
            row.value_int = value if field in EDITABLE_INT else None
            row.value_text = (value.isoformat() if hasattr(value, "isoformat")
                              else (str(value) if field in EDITABLE_STR and value is not None else None))
            row.set_by = current_user.id if current_user else None
            row.set_at = datetime.utcnow()
            row.pushed_at = None

    db.commit()
    log_action(db, current_user, "bulk_update_deals", "sales_deal", None,
               f"{len(payload.deal_ids)} сделок: {', '.join(changes.keys())}")
    return {"message": f"Обновлено сделок: {len(payload.deal_ids)}"}


@router.post("/deals/bulk-delete")
def bulk_delete_deals(payload: BulkDelete, db: Session = Depends(get_db),
                      current_user: User = Depends(require_permission("sales_dashboard", "edit"))):
    """Удаляет выбранные сделки. Правки и разнесения уходят каскадом,
    сырьё в sales_bitrix_raw остаётся историей."""
    if not payload.deal_ids:
        raise HTTPException(status_code=400, detail="Не выбрано ни одной сделки")
    n = db.query(SalesDeal).filter(SalesDeal.id.in_(payload.deal_ids)).delete(
        synchronize_session=False)
    db.commit()
    log_action(db, current_user, "bulk_delete_deals", "sales_deal", None, f"удалено {n}")
    return {"message": f"Удалено сделок: {n}"}


@router.patch("/deals/{deal_id}")
def patch_deal(
    deal_id: int,
    payload: DealPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sales_dashboard", "edit")),
):
    """Правит поля сделки у нас и помечает их как заполненные вручную.

    Помеченные поля синхронизация не перезаписывает, а заливка в Битрикс
    берёт их по признаку pushed_at IS NULL."""
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")

    # exclude_unset: отличаем «поле не прислали» от «прислали null, очисти».
    changes = payload.dict(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Не передано ни одного поля")

    existing = {o.field_name: o for o in db.query(SalesDealFieldOverride, SalesAgency)
                .filter(SalesDealFieldOverride.deal_id == deal_id).all()}

    for field, value in changes.items():
        if field not in EDITABLE_INT + EDITABLE_DATE:
            raise HTTPException(status_code=400, detail=f"Поле «{field}» не редактируется")

        setattr(deal, field, value)

        row = existing.get(field)
        if row is None:
            row = SalesDealFieldOverride(deal_id=deal_id, field_name=field)
            db.add(row)
        row.value_int = value if field in EDITABLE_INT else None
        row.value_text = value.isoformat() if (field in EDITABLE_DATE and value) else None
        row.set_by = current_user.id if current_user else None
        row.set_at = datetime.utcnow()
        # Правка снова становится неотправленной: значение изменилось,
        # прошлая отправка в Битрикс больше не актуальна.
        row.pushed_at = None

    db.commit()
    log_action(db, current_user, "patch_sales_deal", "sales_deal", deal_id,
               ", ".join(changes.keys()))
    return {"message": "Сохранено", "fields": list(changes.keys())}


@router.delete("/deals/{deal_id}/overrides/{field_name}")
def drop_override(
    deal_id: int,
    field_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sales_dashboard", "edit")),
):
    """Снимает ручную пометку: поле возвращается под управление синхронизации.

    Само значение не откатывается — оно вернётся при следующем прогоне
    из источника. Это и есть механизм отката."""
    row = (db.query(SalesDealFieldOverride, SalesAgency)
           .filter(SalesDealFieldOverride.deal_id == deal_id,
                   SalesDealFieldOverride.field_name == field_name).first())
    if not row:
        raise HTTPException(status_code=404, detail="Ручная правка по этому полю не найдена")
    db.delete(row)
    db.commit()
    log_action(db, current_user, "drop_sales_override", "sales_deal", deal_id, field_name)
    return {"message": "Поле возвращено под управление синхронизации"}


@router.get("/filters")
def filter_options(db: Session = Depends(get_db),
                   current_user: User = Depends(require_permission("sales_dashboard", "view"))):
    """Значения для фильтров-чекбоксов, с числом сделок по каждому.

    Считается по всем сделкам, а не по текущей выборке: иначе, сняв галочку,
    пользователь не смог бы вернуть её обратно — значение исчезло бы из списка."""
    def counted(column):
        rows = (db.query(column, func.count(SalesDeal.id))
                  .group_by(column).order_by(func.count(SalesDeal.id).desc()).all())
        return [{"value": v, "count": c} for v, c in rows if v is not None]

    def named(model, fk):
        rows = (db.query(model.id, model.name, func.count(SalesDeal.id))
                  .join(SalesDeal, fk == model.id)
                  .group_by(model.id, model.name)
                  .order_by(func.count(SalesDeal.id).desc()).all())
        return [{"value": i, "label": n, "count": c} for i, n, c in rows]

    rep_a, acct_a = aliased(SalesRep), aliased(SalesRep)
    return {
        "money_layer": [{"value": l, "label": l} for l in ("планируемые", "реализуемые", "фактические")],
        "pipeline": [{"value": r["value"], "label": r["value"], "count": r["count"]}
                     for r in counted(SalesDeal.pipeline)],
        "bitrix_stage": [{"value": r["value"], "label": r["value"], "count": r["count"]}
                         for r in counted(SalesDeal.bitrix_stage)],
        "advertiser_id": named(SalesAdvertiser, SalesDeal.advertiser_id),
        "brand_id": named(SalesBrand, SalesDeal.brand_id),
        "agency_id": named(SalesAgency, SalesDeal.agency_id),
        "sales_rep_id": named(rep_a, SalesDeal.sales_rep_id),
        "account_manager_id": named(acct_a, SalesDeal.account_manager_id),
        "product": [{"value": r["value"], "label": r["value"], "count": r["count"]}
                    for r in counted(SalesDeal.product)],
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
