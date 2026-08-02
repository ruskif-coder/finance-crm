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
from sqlalchemy import func, or_, and_, case
from sqlalchemy.orm import Session, aliased
from typing import Optional, List, Annotated
from pydantic import BaseModel
from datetime import date, datetime
import os
import re

from app.database import get_db
from app.models import User, Counterparty
from app.permissions import require_permission, require_any_permission
from app.audit import log_action
from app.sales.models import (SalesDeal, SalesBitrixStageMap, SalesAdvertiser,
                              SalesRep, SalesBrand, SalesBitrixSyncLog,
                              SalesDealFieldOverride, SalesAgency)
from app.sales.stages import STAGE_CATALOG
import logging

router = APIRouter()
logger = logging.getLogger("finance")

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


def _own_rep_ids_or_all(db: Session, user: User, section: str = "sales_registry"):
    """Видимость сделок роли для конкретной страницы продаж. None — «все» (без
    ограничения). Список id — «только свои»: сделки, где пользователь сейлз или
    аккаунт (SalesRep.user_id). Пустой список у 'own' без привязки → ничего.
    section — какая страница спрашивает (у каждой свой deals_scope)."""
    if user.role.key == "admin":
        return None
    from app.models import RolePermission
    row = (db.query(RolePermission)
           .filter(RolePermission.role_id == user.role_id,
                   RolePermission.section == section).first())
    if not row or (row.deals_scope or "all") != "own":
        return None
    return [r.id for r in db.query(SalesRep.id).filter(SalesRep.user_id == user.id).all()]


def _apply_own_scope(q, own_ids):
    """Ограничивает выборку своими сделками, если роль — 'own'."""
    if own_ids is None:
        return q
    ids = own_ids or [-1]   # нет привязки к сейлзу → пустая выдача, а не «все»
    return q.filter(or_(SalesDeal.sales_rep_id.in_(ids),
                        SalesDeal.account_manager_id.in_(ids)))


def _deal_owned(deal_rep_id, deal_acct_id, own_ids) -> bool:
    """True, если сделка принадлежит own-роли (own_ids — rep-id пользователя).
    Сделка «своя», если пользователь по ней продавец ИЛИ аккаунт-менеджер."""
    ids = set(own_ids or ())
    return deal_rep_id in ids or deal_acct_id in ids


def _assert_deal_in_scope(db, user, deal):
    """Own-scope и на доступе по прямому id (чтение/правка одной сделки): роль 'own'
    не может трогать чужую сделку. Для 'all'/admin — без ограничения."""
    own = _own_rep_ids_or_all(db, user, "sales_registry")
    if own is None:
        return
    if not _deal_owned(deal.sales_rep_id, deal.account_manager_id, own):
        raise HTTPException(status_code=403, detail="Сделка вне вашей зоны видимости")


def _scope_deal_ids(db, user, deal_ids):
    """Own-scope для bulk-операций: если роль 'own' передала чужие id — 403 (а не
    молчаливый пропуск). Для 'all'/admin возвращает список как есть."""
    own = _own_rep_ids_or_all(db, user, "sales_registry")
    if own is None:
        return deal_ids
    ids = set(own or ())
    rows = (db.query(SalesDeal.id, SalesDeal.sales_rep_id, SalesDeal.account_manager_id)
            .filter(SalesDeal.id.in_(deal_ids)).all())
    allowed = {r.id for r in rows if _deal_owned(r.sales_rep_id, r.account_manager_id, ids)}
    if set(deal_ids) - allowed:
        raise HTTPException(status_code=403, detail="Среди выбранных есть сделки вне вашей зоны видимости")
    return deal_ids


_SALES_SCOPE_SECTIONS = ("sales_registry", "sales_analytics")


def _pick_scope_section(requested, viewable):
    """Чистый выбор секции для own-scope сводки. `viewable` — {section: deals_scope}
    ТОЛЬКО по секциям, которые пользователь реально может смотреть (can_view).

    Секцию НЕ доверяем клиенту вслепую: она определяет, чей deals_scope применить,
    и подстановкой недоступной секции роль 'own' могла увидеть чужие сделки.
    Разрешаем запрошенную секцию только если она доступна; иначе берём самую
    строгую из доступных (own приоритетнее all); при пустом наборе — sales_registry."""
    if requested in viewable:
        return requested
    if not viewable:
        return "sales_registry"
    return sorted(viewable, key=lambda s: 0 if (viewable[s] or "all") == "own" else 1)[0]


def _resolve_scope_section(db, user, requested):
    """Безопасно резолвит секцию для own-scope: строит набор доступных пользователю
    sales-секций из role_permissions и отдаёт результат _pick_scope_section."""
    if getattr(user.role, "key", None) == "admin":
        return requested if requested in _SALES_SCOPE_SECTIONS else "sales_registry"
    from app.models import RolePermission
    rows = (db.query(RolePermission)
            .filter(RolePermission.role_id == user.role_id,
                    RolePermission.section.in_(_SALES_SCOPE_SECTIONS)).all())
    viewable = {r.section: (r.deals_scope or "all") for r in rows if r.can_view}
    return _pick_scope_section(requested, viewable)


def _brand_orphaned(brand_advertiser_id, new_advertiser_id):
    """True, если текущий бренд сделки не принадлежит новому рекламодателю —
    такой бренд надо сбросить при смене только advertiser_id."""
    return brand_advertiser_id is not None and brand_advertiser_id != new_advertiser_id


def _apply_extra_filters(q, db, hide_archive=False, search=None, gaps=None):
    """Фильтры, общие для реестра и его строки статистики: «скрыть архив»,
    поиск (название/ID/рекламодатель/бренд), «незаполненные» (включая плательщика).
    Держим в одном месте, чтобы список и сводка считались по одинаковым условиям."""
    if hide_archive:
        q = q.filter(or_(SalesBitrixStageMap.stage_key.is_(None),
                         SalesBitrixStageMap.stage_key != "archive"))
    if search:
        pattern = f"%{search.strip()}%"
        adv_ids = (db.query(SalesAdvertiser.id)
                   .filter(func.coalesce(SalesAdvertiser.short_name,
                                         SalesAdvertiser.name).ilike(pattern)))
        brand_ids = db.query(SalesBrand.id).filter(SalesBrand.name.ilike(pattern))
        q = q.filter(or_(SalesDeal.title.ilike(pattern),
                         SalesDeal.bitrix_id.ilike(pattern),
                         SalesDeal.advertiser_id.in_(adv_ids),
                         SalesDeal.brand_id.in_(brand_ids)))
    if gaps:
        gap_columns = {
            "advertiser_id": SalesDeal.advertiser_id, "agency_id": SalesDeal.agency_id,
            "brand_id": SalesDeal.brand_id, "sales_rep_id": SalesDeal.sales_rep_id,
            "account_manager_id": SalesDeal.account_manager_id,
            "period_from": SalesDeal.period_from, "period_to": SalesDeal.period_to,
        }
        conds = [gap_columns[g].is_(None) for g in gaps if g in gap_columns]
        if "payer" in gaps:
            from app.sales.models import SalesAgencyCounterparty, SalesAdvertiserCounterparty
            ag_legal = [r[0] for r in db.query(SalesAgencyCounterparty.agency_id).distinct().all()] or [-1]
            adv_legal = [r[0] for r in db.query(SalesAdvertiserCounterparty.advertiser_id).distinct().all()] or [-1]
            conds.append(and_(
                SalesDeal.payer_counterparty_id.is_(None),
                or_(and_(SalesDeal.agency_id.isnot(None), SalesDeal.agency_id.notin_(ag_legal)),
                    and_(SalesDeal.agency_id.is_(None),
                         or_(SalesDeal.advertiser_id.is_(None), SalesDeal.advertiser_id.notin_(adv_legal)))),
            ))
        if conds:
            q = q.filter(or_(*conds))
    return q


def _base_query(db: Session, date_from, date_to, pipeline, sales_rep_id,
                account_manager_id, advertiser_id, money_layer,
                bitrix_stage=None, brand_id=None, agency_id=None,
                product=None, stage_key=None):
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
        _in(SalesDeal.product, product),
        _in(SalesBitrixStageMap.money_layer, money_layer),
        _in(SalesBitrixStageMap.stage_key, stage_key),
    ):
        if condition is not None:
            q = q.filter(condition)
    return q


def _group(rows, key_fn, excluded_adv=frozenset()):
    """Сворачивает выборку по ключу с разбивкой суммы по слоям денег.
    fact — реализованная выручка (фактический слой), исключая рекламодателей
    с флагом «не в выручке» (МП). real/plan — реализуемые/планируемые."""
    acc = {}
    for deal, layer, _stage_key in rows:
        key = key_fn(deal, layer) or NO_GROUP
        b = acc.setdefault(key, {"name": key, "deals": 0, "amount": 0.0,
                                 "fact": 0.0, "real": 0.0, "plan": 0.0})
        amt = float(deal.amount or 0)
        b["deals"] += 1
        b["amount"] += amt
        if layer == "фактические":
            if deal.advertiser_id not in excluded_adv:
                b["fact"] += amt
        elif layer == "реализуемые":
            b["real"] += amt
        elif layer == "планируемые":
            b["plan"] += amt
    # сортируем по факту, затем по общей сумме — фронт показывает выручку первой
    return sorted(acc.values(), key=lambda x: (-x["fact"], -x["amount"]))


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
    product: Annotated[Optional[List[str]], Query()] = None,
    money_layer: Annotated[Optional[List[str]], Query()] = None,
    stage_key: Annotated[Optional[List[str]], Query()] = None,
    hide_archive: bool = False,
    search: Optional[str] = None,
    gaps: Annotated[Optional[List[str]], Query()] = None,
    scope_section: str = "sales_analytics",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission(("sales_registry", "sales_analytics"), "view")),
):
    _q = _base_query(db, date_from, date_to, pipeline, sales_rep_id,
                     account_manager_id, advertiser_id, money_layer,
                     bitrix_stage, brand_id, agency_id, product, stage_key)
    # сводку зовёт и реестр (scope_section=sales_registry), и аналитика (по умолчанию).
    # Секцию от клиента НЕ применяем напрямую — резолвим по реально доступным правам,
    # иначе роль 'own' могла бы подставить чужую секцию и увидеть чужие сделки.
    safe_section = _resolve_scope_section(db, current_user, scope_section)
    _q = _apply_own_scope(_q, _own_rep_ids_or_all(db, current_user, safe_section))
    # те же фильтры, что и в списке реестра, чтобы статистика совпадала с выборкой
    _q = _apply_extra_filters(_q, db, hide_archive, search, gaps)
    rows = _q.all()

    adv_names = dict(db.query(SalesAdvertiser.id,
                              func.coalesce(SalesAdvertiser.short_name, SalesAdvertiser.name)).all())
    rep_names = dict(db.query(SalesRep.id, SalesRep.name).all())
    agency_names = dict(db.query(SalesAgency.id,
                                 func.coalesce(SalesAgency.short_name, SalesAgency.name)).all())
    # рекламодатели «не в выручке» (МП) — их факт не идёт в выручку
    excluded_adv = frozenset(x[0] for x in db.query(SalesAdvertiser.id)
                             .filter(SalesAdvertiser.exclude_from_revenue.is_(True)).all())

    total_amount = sum(float(d.amount or 0) for d, _, _ in rows)

    by_layer = _group(rows, lambda d, layer: layer, excluded_adv)
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
            "fact": round(sum(b["fact"] for b in by_layer), 2),          # реализованная выручка
            "work": round(sum(b["real"] + b["plan"] for b in by_layer), 2),  # в работе
            "deals_without_period": no_period,
            "reconciles": round(layers_sum, 2) == round(total_amount, 2),
        },
        "by_layer": by_layer,
        "by_pipeline": _group(rows, lambda d, layer: d.pipeline, excluded_adv),
        "by_sales_rep": _group(rows, lambda d, layer: rep_names.get(d.sales_rep_id), excluded_adv),
        "by_account_manager": _group(rows, lambda d, layer: rep_names.get(d.account_manager_id), excluded_adv),
        "by_agency": _group(rows, lambda d, layer: agency_names.get(d.agency_id), excluded_adv)[:50],
        "by_advertiser": _group(rows, lambda d, layer: adv_names.get(d.advertiser_id), excluded_adv)[:50],
        "by_product": _group(rows, lambda d, layer: d.product, excluded_adv)[:50],
        "by_month": sorted(
            _group(rows, lambda d, layer: d.period_from.strftime("%Y-%m") if d.period_from else None, excluded_adv),
            key=lambda b: b["name"],
        ),
        # Витрина всегда сообщает возраст данных: молча устаревшие цифры —
        # худшее поведение для отчётной системы.
        "last_sync_at": last_sync.finished_at.isoformat() if last_sync and last_sync.finished_at else None,
    }


# ===== Бонус-виджеты сейлза (квартальная система) =====
# База: amount трактуем как БЕЗ НДС (поле «Клиентская стоимость до НДС»), поэтому НЕ делим.
# Если перейдём на «основную сумму с НДС» — делить на (1 + SALES_VAT_RATE). Константы — чтобы легко править.
SALES_VAT_RATE = 0.22
SALES_AGENCY_SK = 0.30       # базовый СК агентства (потом из справочника по агентству)
SALES_BONUS_RATE = 0.03      # доля сейлза от «нашей» суммы
_CLOSED_FUNNEL = "ДО"        # воронка «доведено до результата»
BRIEF_FIELD = "ufCrm_1761318500"   # Битрикс-поле сделки «Бриф - Описание задач» (текст)
_SANDBOX_KEYS = {"media_plan"}
_BOOKING_KEYS = {"booking", "launch_prep", "launch"}


def _current_quarter(today: date):
    q0 = (today.month - 1) // 3
    m0 = q0 * 3 + 1
    start = date(today.year, m0, 1)
    end = date(today.year + 1, 1, 1) if q0 == 3 else date(today.year, m0 + 3, 1)
    return start, end, f"{today.year} Q{q0 + 1}"


def _parse_quarter(s):
    import re
    m = re.search(r"(\d{4}).*?([1-4])", s or "")
    if not m:
        return None
    year, q = int(m.group(1)), int(m.group(2))
    m0 = (q - 1) * 3 + 1
    start = date(year, m0, 1)
    end = date(year + 1, 1, 1) if q == 4 else date(year, m0 + 3, 1)
    return start, end, f"{year} Q{q}"


@router.get("/dashboard/bonus")
def dashboard_bonus(
    quarter: Optional[str] = None,
    rep_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_permission(("sales_dashboard", "sales_registry"), "view")),
):
    """Бонус-виджеты сейлза за квартал. По умолчанию — текущий квартал и SalesRep залогиненного
    (по user_id). Админ может смотреть чужой квартал/сейлза через ?quarter=2026-Q2&rep_id=."""
    is_admin = current_user.role.key == "admin"
    my_reps = db.query(SalesRep).filter(SalesRep.user_id == current_user.id).all()
    is_head = any(r.is_sales_head for r in my_reps)
    can_view_others = is_admin or is_head
    if rep_id is not None and can_view_others:
        rep_ids = [rep_id]
    else:
        rep_ids = [r.id for r in my_reps]   # по умолчанию — на себя

    if quarter == "all":
        # «Показать все» — весь период без ограничения по кварталу
        start, end, label = date(1970, 1, 1), date(2100, 1, 1), "Всё время"
    else:
        rng = _parse_quarter(quarter) if quarter else _current_quarter(date.today())
        if not rng:
            raise HTTPException(status_code=400, detail="Неверный формат квартала (ожидается «2026-Q2»)")
        start, end, label = rng
    rep_names = [n for (n,) in db.query(SalesRep.name).filter(SalesRep.id.in_(rep_ids)).all()] if rep_ids else []
    params = {"vat_rate": SALES_VAT_RATE, "agency_sk": SALES_AGENCY_SK, "bonus_rate": SALES_BONUS_RATE}

    base = {"quarter": label, "rep": ", ".join(rep_names), "linked": bool(rep_ids),
            "can_view_others": can_view_others, "rep_ids": rep_ids, "params": params,
            "sandbox": {"count": 0, "amount": 0},
            "booking": {"amount": 0, "our_sum": 0, "bonus": 0, "by_stage": []},
            "closed": {"amount": 0, "our_sum": 0}, "forming_bonus": 0}
    if not rep_ids:
        return base

    deals = (db.query(SalesDeal)
             .filter(SalesDeal.sales_rep_id.in_(rep_ids),
                     SalesDeal.period_from >= start, SalesDeal.period_from < end).all())
    stage_key = {(m.pipeline, m.bitrix_stage): m.stage_key
                 for m in db.query(SalesBitrixStageMap).all()}

    # СК берём по агентству сделки (sales_agencies.sk_percent), дефолт — константа, если агентства нет.
    sk_by_agency = dict(db.query(SalesAgency.id, SalesAgency.sk_percent).all())
    default_sk_pct = SALES_AGENCY_SK * 100

    def net_of(amount, agency_id):
        pct = sk_by_agency.get(agency_id, default_sk_pct)
        return float(amount or 0) * (1 - (pct or 0) / 100)

    sandbox_cnt = 0
    sandbox_sum = booking_sum = closed_sum = 0.0
    closed_our = booking_our = 0.0
    booking_stages = {}
    for d in deals:
        amt = float(d.amount or 0)
        if d.pipeline == _CLOSED_FUNNEL:
            closed_sum += amt
            closed_our += net_of(amt, d.agency_id)
            continue
        sk = stage_key.get((d.pipeline, d.bitrix_stage))
        if sk in _SANDBOX_KEYS:
            sandbox_cnt += 1
            sandbox_sum += amt
        elif sk in _BOOKING_KEYS:
            booking_sum += amt
            booking_our += net_of(amt, d.agency_id)
            booking_stages[d.bitrix_stage] = booking_stages.get(d.bitrix_stage, 0.0) + amt
    base.update({
        "sandbox": {"count": sandbox_cnt, "amount": round(sandbox_sum)},
        "booking": {
            "amount": round(booking_sum), "our_sum": round(booking_our),
            "bonus": round(booking_our * SALES_BONUS_RATE),
            "by_stage": sorted(({"stage": k, "amount": round(v)} for k, v in booking_stages.items()),
                               key=lambda x: -x["amount"]),
        },
        "closed": {"amount": round(closed_sum), "our_sum": round(closed_our)},
        "forming_bonus": round(closed_our * SALES_BONUS_RATE),
    })
    return base


@router.get("/reps")
def list_reps(db: Session = Depends(get_db),
              current_user: User = Depends(require_any_permission(("sales_dashboard", "sales_registry", "sales_analytics"), "view"))):
    """Продавцы (SalesRep) — для селектора «смотреть чужой» на дашборде (админ).
    Только сейлзы: мастер-сейлз (is_sales_head) ИЛИ кто хоть раз был продавцом сделки
    (sales_rep_id). Чистые аккаунт-менеджеры (только account_manager_id) отсекаются."""
    seller_ids = {r[0] for r in db.query(SalesDeal.sales_rep_id)
                  .filter(SalesDeal.sales_rep_id.isnot(None)).distinct().all()}
    rows = db.query(SalesRep).order_by(SalesRep.name).all()
    return {"items": [{"id": r.id, "name": r.name, "linked": r.user_id is not None,
                       "is_head": r.is_sales_head}
                      for r in rows if r.is_sales_head or r.id in seller_ids]}


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
    product: Annotated[Optional[List[str]], Query()] = None,
    money_layer: Annotated[Optional[List[str]], Query()] = None,
    stage_key: Annotated[Optional[List[str]], Query()] = None,
    hide_archive: bool = False,
    search: Optional[str] = None,
    gaps: Annotated[Optional[List[str]], Query()] = None,
    sort: str = "period_from",
    direction: str = "desc",
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sales_registry", "view")),
):
    """Реестр сделок — базовое представление, от которого строится всё остальное.

    Отдаёт учётные поля как есть, включая незаполненные: пустое поле — это факт
    о данных, и прятать его нельзя. Часть атрибутов (продукты, агентства,
    клиентская сумма) пока живёт только в сыром слое sales_bitrix_raw и в колонки
    не вынесена — см. раздел 13 спецификации."""
    q = _base_query(db, date_from, date_to, pipeline, sales_rep_id,
                    account_manager_id, advertiser_id, money_layer,
                    bitrix_stage, brand_id, agency_id, product, stage_key)

    # Видимость сделок роли: «только свои» ограничивает выборку сразу.
    q = _apply_own_scope(q, _own_rep_ids_or_all(db, current_user))

    # Общие фильтры (скрыть архив, поиск, незаполненные) — в одном месте,
    # чтобы список и строка статистики считались по одинаковым условиям.
    q = _apply_extra_filters(q, db, hide_archive, search, gaps)

    total = q.count()

    # Сортировка по именам исполнителей и рекламодателя — через отдельные алиасы
    # sales_reps: продавец и аккаунт-менеджер ссылаются на одну таблицу, и без
    # алиасов SQLAlchemy не сможет соединить её дважды.
    rep_a, acct_a, adv_a = aliased(SalesRep), aliased(SalesRep), aliased(SalesAdvertiser)
    brand_a, agency_a = aliased(SalesBrand), aliased(SalesAgency)
    q = (q.outerjoin(rep_a, rep_a.id == SalesDeal.sales_rep_id)
          .outerjoin(acct_a, acct_a.id == SalesDeal.account_manager_id)
          .outerjoin(adv_a, adv_a.id == SalesDeal.advertiser_id)
          .outerjoin(brand_a, brand_a.id == SalesDeal.brand_id)
          .outerjoin(agency_a, agency_a.id == SalesDeal.agency_id))

    # Плательщик для сортировки повторяет приоритет resolve_payer():
    # выбранное вручную юрлицо -> первое юрлицо агентства (мин. id связи) -> текстовое имя.
    from app.sales.models import SalesAgencyCounterparty
    payer_cp = aliased(Counterparty)
    first_link_sq = (
        db.query(SalesAgencyCounterparty.agency_id.label("aid"),
                 func.min(SalesAgencyCounterparty.id).label("min_id"))
          .group_by(SalesAgencyCounterparty.agency_id).subquery())
    link_a = aliased(SalesAgencyCounterparty)
    agency_cp = aliased(Counterparty)
    q = (q.outerjoin(payer_cp, payer_cp.id == SalesDeal.payer_counterparty_id)
          .outerjoin(first_link_sq, first_link_sq.c.aid == SalesDeal.agency_id)
          .outerjoin(link_a, link_a.id == first_link_sq.c.min_id)
          .outerjoin(agency_cp, agency_cp.id == link_a.counterparty_id))
    payer_expr = func.coalesce(payer_cp.name, agency_cp.name, SalesDeal.payer_name)

    sortable = {
        "bitrix_id": SalesDeal.bitrix_id,
        "title": SalesDeal.title,
        "pipeline": SalesDeal.pipeline,
        "product": SalesDeal.product,
        "period": SalesDeal.period_from,
        "bitrix_stage": SalesDeal.bitrix_stage,
        "money_layer": SalesBitrixStageMap.money_layer,
        "amount": SalesDeal.amount,
        "advertiser": adv_a.name,
        "brand": brand_a.name,
        "agency": func.coalesce(agency_a.short_name, agency_a.name),
        "payer": payer_expr,
        "sales_rep": rep_a.name,
        "account_manager": acct_a.name,
        "period_from": SalesDeal.period_from,
        "period_to": SalesDeal.period_to,
        "date_create": SalesDeal.date_create,
    }
    column = sortable.get(sort)
    if column is None:
        raise HTTPException(status_code=400, detail=f"Сортировка по «{sort}» не поддерживается")

    # Локальные (ещё не выгруженные в Битрикс) сделки — всегда вверху таблицы
    # при любой сортировке (если попали в выборку по фильтрам).
    local_first = case((SalesDeal.bitrix_id.like("local-%"), 0), else_=1)
    if sort == "date_create":
        # У недавно импортированных сделок date_create бывает NULL — считаем такие
        # «только что добавленными» (NULL → now()), чтобы они не тонули в конец.
        primary = func.coalesce(SalesDeal.date_create, func.now())
        ordering = primary.desc() if direction == "desc" else primary.asc()
    else:
        # nullslast в обоих направлениях: незаполненные поля не должны занимать
        # начало списка — их и так много, и они вытеснили бы содержательные строки.
        ordering = column.desc().nullslast() if direction == "desc" else column.asc().nullslast()
    # Вторичная сортировка — по рекламодателю: в рамках одного ключа
    # сделки идут по алфавиту рекламодателя.
    rows = (q.order_by(local_first, ordering, adv_a.name.asc().nullslast(), SalesDeal.id.desc())
            .limit(min(limit, 500)).offset(offset).all())

    adv = dict(db.query(SalesAdvertiser.id, func.coalesce(SalesAdvertiser.short_name, SalesAdvertiser.name)).all())
    reps = dict(db.query(SalesRep.id, SalesRep.name).all())
    brands = dict(db.query(SalesBrand.id, SalesBrand.name).all())
    cps = dict(db.query(Counterparty.id, Counterparty.name).all())
    agencies = dict(db.query(SalesAgency.id, func.coalesce(SalesAgency.short_name, SalesAgency.name)).all())

    # Полная подпись «краткое | ENG | Рус» для тултипа в реестре (наведение на
    # агентство/рекламодателя, где показано только краткое имя).
    def _full(short, en, ru, name):
        parts = [p.strip() for p in (short, en, ru) if p and p.strip()]
        return " | ".join(dict.fromkeys(parts)) if parts else name
    adv_full = {a.id: _full(a.short_name, a.name_en, a.name_ru, a.name)
                for a in db.query(SalesAdvertiser).all()}
    agency_full = {a.id: _full(a.short_name, a.name_en, a.name_ru, a.name)
                   for a in db.query(SalesAgency).all()}

    # Юрлица, прикреплённые к агентствам И рекламодателям — для колонки «Плательщик».
    from app.sales.models import SalesAgencyCounterparty, SalesAdvertiserCounterparty
    agency_legals = {}
    for lk in db.query(SalesAgencyCounterparty).order_by(SalesAgencyCounterparty.id).all():
        agency_legals.setdefault(lk.agency_id, []).append(
            {"id": lk.counterparty_id, "name": cps.get(lk.counterparty_id)})
    advertiser_legals = {}
    for lk in db.query(SalesAdvertiserCounterparty).order_by(SalesAdvertiserCounterparty.id).all():
        advertiser_legals.setdefault(lk.advertiser_id, []).append(
            {"id": lk.counterparty_id, "name": cps.get(lk.counterparty_id)})

    def payer_options(d):
        # Правило: есть агентство -> ВСЕГДА юрлица агентства; агентства нет -> юрлица рекламодателя.
        if d.agency_id:
            return agency_legals.get(d.agency_id) or []
        return advertiser_legals.get(d.advertiser_id) or []

    def resolve_payer(d):
        # приоритет: ручное юрлицо -> первое юрлицо агентства -> первое юрлицо
        # рекламодателя (когда рекламодатель платит сам) -> текстовое имя
        if d.payer_counterparty_id:
            return cps.get(d.payer_counterparty_id)
        opts = payer_options(d)
        if opts:
            return opts[0]["name"]
        return d.payer_name

    # Какие поля на этой странице заполнены вручную — чтобы интерфейс их пометил
    # и было видно, что синхронизация их не тронет.
    page_ids = [d.id for d, _, _ in rows]
    manual = {}
    files_map = {}
    if page_ids:
        for o in (db.query(SalesDealFieldOverride)
                  .filter(SalesDealFieldOverride.deal_id.in_(page_ids)).all()):
            manual.setdefault(o.deal_id, []).append(o.field_name)
        from app.sales.models import SalesDealFile
        for frec in (db.query(SalesDealFile)
                     .filter(SalesDealFile.deal_id.in_(page_ids)).all()):
            files_map.setdefault(frec.deal_id, []).append({"kind": frec.kind, "filename": frec.filename})

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
            "agency_full": agency_full.get(d.agency_id),
            "agency_id": d.agency_id,
            "payer_name": d.payer_name,
            # выбранный/дефолтный плательщик и варианты для выпадашки
            "payer": resolve_payer(d),
            "payer_counterparty_id": d.payer_counterparty_id,
            "agency_legals": payer_options(d),
            "amount": d.amount,
            "currency": d.currency,
            "advertiser": adv.get(d.advertiser_id),
            "advertiser_full": adv_full.get(d.advertiser_id),
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
            "files": files_map.get(d.id, []),
            # состояние брифа для иконки: none — ещё не подгружали, empty — пусто,
            # filled — есть текст. Текст брифа тут НЕ отдаём (ленивая подгрузка по клику).
            "brief_state": ("none" if d.brief is None
                            else ("empty" if not (d.brief or "").strip() else "filled")),
            "sync_status": d.sync_status,
            "sync_issues": (d.sync_report or {}).get("issues", []),
            "sync_changes": (d.sync_report or {}).get("changes", []),
            "sync_checked_at": (d.sync_report or {}).get("checked_at"),
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
    title: Optional[str] = None


# Поля, доступные ручной правке. Расширять осознанно: каждое попадёт
# в очередь на заливку в Битрикс.
EDITABLE_INT = ("advertiser_id", "agency_id", "brand_id", "sales_rep_id",
                "account_manager_id", "payer_counterparty_id")
EDITABLE_DATE = ("period_from", "period_to")
EDITABLE_STR = ("product", "bitrix_stage", "title")


def _upsert_override(db, deal_id, field, value_int, value_text, user):
    """Помечает поле сделки ручной правкой (защита от синхронизации).
    Единая точка: используется массовой правкой и подстановкой брендов."""
    row = (db.query(SalesDealFieldOverride)
           .filter(SalesDealFieldOverride.deal_id == deal_id,
                   SalesDealFieldOverride.field_name == field).first())
    if row is None:
        row = SalesDealFieldOverride(deal_id=deal_id, field_name=field)
        db.add(row)
    row.value_int = value_int
    row.value_text = value_text
    row.set_by = user.id if user else None
    row.set_at = datetime.utcnow()
    row.pushed_at = None


class BulkUpdate(BaseModel):
    """Массовое изменение выбранных сделок. Передаются только меняемые поля;
    отсутствие ключа = не трогать. period — строка ГГГГ-ММ (ставится в period_from)."""
    deal_ids: List[int]
    advertiser_id: Optional[int] = None
    agency_id: Optional[int] = None
    sales_rep_id: Optional[int] = None
    account_manager_id: Optional[int] = None
    product: Optional[str] = None
    bitrix_stage: Optional[str] = None
    period: Optional[str] = None


class BulkDelete(BaseModel):
    deal_ids: List[int]


@router.post("/deals/bulk-update")
def bulk_update_deals(payload: BulkUpdate, db: Session = Depends(get_db),
                      current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Применяет заданные поля ко всем выбранным сделкам и помечает их ручными
    (синхронизация не перезапишет). Пустые/непереданные поля не трогаются."""
    if not payload.deal_ids:
        raise HTTPException(status_code=400, detail="Не выбрано ни одной сделки")
    _scope_deal_ids(db, current_user, payload.deal_ids)

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
    for f in ("advertiser_id", "agency_id", "sales_rep_id", "account_manager_id",
              "product", "bitrix_stage"):
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


@router.get("/deals/brand-suggestions")
def brand_suggestions(limit: int = 500, db: Session = Depends(get_db),
                      current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Сделки без бренда, где в названии однозначно упомянут бренд из справочника.
    Предлагает бренд и его рекламодателя. Только однозначные совпадения —
    неоднозначные (несколько брендов в названии) не предлагаем, чтобы не гадать."""
    brands = db.query(SalesBrand).all()
    adv = dict(db.query(SalesAdvertiser.id,
                        func.coalesce(SalesAdvertiser.short_name, SalesAdvertiser.name)).all())

    def norm(s):
        return re.sub(r"\s+", " ", str(s or "").lower()).strip()

    # бренды длиной >=3 символа, чтобы не ловить мусорные совпадения
    bidx = [(norm(b.name), b) for b in brands if len(norm(b.name)) >= 3]

    deals_q = _apply_own_scope(
        db.query(SalesDeal).filter(SalesDeal.brand_id.is_(None), SalesDeal.title.isnot(None)),
        _own_rep_ids_or_all(db, current_user))
    deals = deals_q.order_by(SalesDeal.date_create.desc()).all()

    out = []
    for d in deals:
        t = norm(d.title)
        # граница слова с учётом кириллицы (\b плохо работает с не-ASCII)
        hits = {b.id: b for key, b in bidx
                if re.search(r"(?<![a-zа-я0-9])" + re.escape(key) + r"(?![a-zа-я0-9])", t)}
        if len(hits) != 1:
            continue
        b = next(iter(hits.values()))
        conflict = d.advertiser_id is not None and d.advertiser_id != b.advertiser_id
        out.append({
            "deal_id": d.id,
            "bitrix_id": d.bitrix_id,
            "title": d.title,
            "brand_id": b.id,
            "brand": b.name,
            "advertiser_id": b.advertiser_id,
            "advertiser": adv.get(b.advertiser_id),
            "current_advertiser_id": d.advertiser_id,
            "current_advertiser": adv.get(d.advertiser_id),
            "conflict": conflict,   # у сделки уже другой рекламодатель
        })
        if len(out) >= limit:
            break
    return {"items": out, "total": len(out)}


class ApplyBrand(BaseModel):
    deal_id: int
    brand_id: int
    set_advertiser: bool = True   # проставить рекламодателя бренда, если у сделки пусто


class ApplyBrands(BaseModel):
    items: List[ApplyBrand]


@router.post("/deals/apply-brand-suggestions")
def apply_brand_suggestions(payload: ApplyBrands, db: Session = Depends(get_db),
                            current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Проставляет подтверждённые бренды (и рекламодателя бренда, если у сделки
    его нет) как ручные правки — синхронизация не перезапишет."""
    if not payload.items:
        raise HTTPException(status_code=400, detail="Нечего применять")
    _scope_deal_ids(db, current_user, [it.deal_id for it in payload.items])

    brand_adv = dict(db.query(SalesBrand.id, SalesBrand.advertiser_id).all())
    applied = 0; adv_set = 0
    for it in payload.items:
        deal = db.query(SalesDeal).filter(SalesDeal.id == it.deal_id).first()
        if not deal:
            continue
        deal.brand_id = it.brand_id
        _upsert_override(db, it.deal_id, "brand_id", it.brand_id, None, current_user)
        applied += 1
        # рекламодателя ставим только если у сделки его нет — чужой не трогаем
        if it.set_advertiser and deal.advertiser_id is None:
            aid = brand_adv.get(it.brand_id)
            if aid:
                deal.advertiser_id = aid
                _upsert_override(db, it.deal_id, "advertiser_id", aid, None, current_user)
                adv_set += 1
    db.commit()
    log_action(db, current_user, "apply_brand_suggestions", "sales_deal", None,
               f"брендов {applied}, рекламодателей {adv_set}")
    return {"message": f"Проставлено брендов: {applied}, рекламодателей: {adv_set}"}


@router.post("/deals/bulk-delete")
def bulk_delete_deals(payload: BulkDelete, db: Session = Depends(get_db),
                      current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Удаляет выбранные сделки. Правки и разнесения уходят каскадом,
    сырьё в sales_bitrix_raw остаётся историей.

    Каждый bitrix_id пишется в надгробия (sales_deleted_deals): будущая
    синхронизация с Битриксом обязана их пропускать, иначе удалённые сделки
    воскреснут — в Битриксе они ещё существуют."""
    if not payload.deal_ids:
        raise HTTPException(status_code=400, detail="Не выбрано ни одной сделки")
    _scope_deal_ids(db, current_user, payload.deal_ids)

    from app.sales.models import SalesDeletedDeal
    deals = db.query(SalesDeal).filter(SalesDeal.id.in_(payload.deal_ids)).all()
    tombstoned = {t.bitrix_id for t in db.query(SalesDeletedDeal.bitrix_id).all()}
    for d in deals:
        if d.bitrix_id and d.bitrix_id not in tombstoned:
            db.add(SalesDeletedDeal(bitrix_id=d.bitrix_id, reason="удалено вручную из реестра",
                                    deleted_by=(current_user.id if current_user else None)))
            tombstoned.add(d.bitrix_id)

    n = db.query(SalesDeal).filter(SalesDeal.id.in_(payload.deal_ids)).delete(
        synchronize_session=False)
    db.commit()
    log_action(db, current_user, "bulk_delete_deals", "sales_deal", None, f"удалено {n}")
    return {"message": f"Удалено сделок: {n} (не вернутся при синхронизации)"}


def _period_bounds(period):
    """'ГГГГ-ММ' → (первое число, последнее число месяца). None при плохом формате."""
    import re
    import calendar as _cal
    if not period or not re.match(r"^\d{4}-\d{2}$", period):
        return None
    y, m = int(period[:4]), int(period[5:7])
    if not (1 <= m <= 12):
        return None
    return date(y, m, 1), date(y, m, _cal.monthrange(y, m)[1])


class DealCreate(BaseModel):
    agency_id: Optional[int] = None
    advertiser_id: Optional[int] = None
    brand_id: Optional[int] = None
    product: Optional[str] = None
    pipeline: str
    bitrix_stage: str
    period: str
    amount: Optional[float] = None
    amount_with_vat: Optional[float] = None
    sales_rep_id: Optional[int] = None
    account_manager_id: Optional[int] = None
    title: Optional[str] = None


@router.post("/deals")
def create_deal(payload: DealCreate, db: Session = Depends(get_db),
                current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Создаёт сделку ЛОКАЛЬНО (bitrix_id=local-<uuid>). В Битрикс не шлём — отдельной кнопкой."""
    import uuid as _uuid
    bounds = _period_bounds(payload.period)
    if not bounds:
        raise HTTPException(status_code=400, detail="Период должен быть ГГГГ-ММ")
    if payload.amount is None and payload.amount_with_vat is None:
        raise HTTPException(status_code=400, detail="Нужна сумма (с НДС или без НДС)")
    if not payload.agency_id and not payload.advertiser_id:
        raise HTTPException(status_code=400, detail="Нужно агентство или рекламодатель")
    if payload.brand_id:
        brand = db.query(SalesBrand).filter(SalesBrand.id == payload.brand_id).first()
        if not brand:
            raise HTTPException(status_code=400, detail="Бренд не найден")
        if payload.advertiser_id and brand.advertiser_id != payload.advertiser_id:
            raise HTTPException(status_code=400, detail="Бренд не принадлежит рекламодателю сделки")

    rep_id = payload.sales_rep_id
    if rep_id is None:
        r = db.query(SalesRep.id).filter(SalesRep.user_id == current_user.id).first()
        rep_id = r[0] if r else None
    # own-роль может создавать сделки только на себя, не на чужого продавца
    own = _own_rep_ids_or_all(db, current_user)
    if own is not None and rep_id not in set(own):
        raise HTTPException(status_code=403, detail="Можно создавать сделки только на себя")

    # Единый базис: amount = БЕЗ НДС. Дозаполняем недостающую сумму по ставке НДС.
    vat_mult = 1 + SALES_VAT_RATE
    amount, amount_wv = payload.amount, payload.amount_with_vat
    if amount is None and amount_wv is not None:
        amount = round(amount_wv / vat_mult, 2)
    if amount_wv is None and amount is not None:
        amount_wv = round(amount * vat_mult, 2)

    pf, pt = bounds
    deal = SalesDeal(
        bitrix_id="local-" + _uuid.uuid4().hex,
        title=payload.title, pipeline=payload.pipeline, bitrix_stage=payload.bitrix_stage,
        amount=amount, amount_with_vat=amount_wv, currency="RUB",
        advertiser_id=payload.advertiser_id, brand_id=payload.brand_id, agency_id=payload.agency_id,
        product=payload.product, sales_rep_id=rep_id, account_manager_id=payload.account_manager_id,
        period_from=pf, period_to=pt,
        date_create=datetime.utcnow(),
    )
    db.add(deal)
    db.commit()
    db.refresh(deal)
    log_action(db, current_user, "create_deal", "sales_deal", deal.id,
               f"локально: {payload.title or '(без названия)'} · {payload.period}")
    return {"id": deal.id, "bitrix_id": deal.bitrix_id}


@router.post("/deals/{deal_id}/push-to-bitrix")
def push_deal_to_bitrix(deal_id: int, db: Session = Depends(get_db),
                        current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """ЗАПИСЬ В ПРОД-БИТРИКС: создаёт локальную сделку в Битриксе, заменяет local-id на реальный.
    Маппит только резолвимые поля; рекламодателя/бренд пока не шлём (коды не опознаны)."""
    from app.sales.bitrix.transport import vibecode_post, list_bitrix_services
    from app.sales.models import SalesAgency, SalesPipeline, SalesPipelineStage
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    if not (deal.bitrix_id or "").startswith("local-"):
        raise HTTPException(status_code=409, detail="Сделка уже в Битриксе")

    body = {"title": deal.title or ""}
    pipe = db.query(SalesPipeline).filter(SalesPipeline.name == deal.pipeline).first()
    if pipe and pipe.bitrix_category_id is not None:
        body["categoryId"] = pipe.bitrix_category_id
        st = (db.query(SalesPipelineStage)
              .filter(SalesPipelineStage.bitrix_category_id == pipe.bitrix_category_id,
                      SalesPipelineStage.name == deal.bitrix_stage).first())
        if st:
            body["stageId"] = st.status_id
    if deal.amount is not None:
        body["ufCrm_1690138678699"] = f"{deal.amount}|RUB"
    if deal.period_from:
        body["ufCrm_1723639172"] = deal.period_from.isoformat()
    if deal.period_to:
        body["ufCrm_1723639189"] = deal.period_to.isoformat()
    if deal.agency_id:
        ag = db.query(SalesAgency).filter(SalesAgency.id == deal.agency_id).first()
        if ag and ag.bx_id:
            try:
                body["companyId"] = int(ag.bx_id)
            except (TypeError, ValueError):
                pass
    if deal.product:
        try:
            svc = {s["title"]: s["id"] for s in list_bitrix_services()}
            if deal.product in svc:
                body["parentId1050"] = int(svc[deal.product])
        except Exception:
            pass
    if deal.sales_rep_id:
        rep = db.query(SalesRep).filter(SalesRep.id == deal.sales_rep_id).first()
        if rep and rep.bitrix_user_id:
            try:
                body["ufCrm_1761319635"] = int(rep.bitrix_user_id)
            except (TypeError, ValueError):
                pass

    try:
        res = vibecode_post("/deals", body)
    except Exception as e:
        logger.error("push_deal_to_bitrix: deal=%s: %s", deal.id, e)
        raise HTTPException(status_code=502, detail="Битрикс отклонил создание сделки (детали в логе сервера)")
    new_id = (res.get("data") or {}).get("id") or res.get("id")
    if not new_id:
        raise HTTPException(status_code=502, detail="Битрикс не вернул id сделки")
    deal.bitrix_id = str(new_id)
    db.commit()
    log_action(db, current_user, "push_deal_to_bitrix", "sales_deal", deal.id, f"→ bx {new_id}")
    return {"bitrix_id": deal.bitrix_id}


class BriefIn(BaseModel):
    brief: str


def _deal_is_local(deal) -> bool:
    return (deal.bitrix_id or "").startswith("local-")


@router.get("/deals/{deal_id}/brief")
def get_deal_brief(deal_id: int, refresh: int = 0, db: Session = Depends(get_db),
                   current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Бриф сделки. Ленивая подгрузка: если ещё не тянули (brief IS NULL) или refresh=1 —
    читаем из Битрикса поле ufCrm_1761318500 и кэшируем. Локальные сделки (local-) — только БД."""
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    if (deal.brief is None or refresh) and not _deal_is_local(deal):
        from app.sales.bitrix.transport import vibecode_get
        try:
            r = vibecode_get(f"/deals/{deal.bitrix_id}", {})
            d = (r.get("data") if isinstance(r, dict) else None) or {}
            deal.brief = d.get(BRIEF_FIELD) or ""
            deal.brief_synced_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            if deal.brief is None:      # кэша ещё нет — сообщаем об ошибке
                logger.error("get_deal_brief: deal=%s: %s", deal.id, e)
                raise HTTPException(status_code=502, detail="Битрикс недоступен (детали в логе сервера)")
    return {"brief": deal.brief or "", "loaded": deal.brief is not None,
            "is_local": _deal_is_local(deal),
            "synced_at": deal.brief_synced_at.isoformat() if deal.brief_synced_at else None}


@router.put("/deals/{deal_id}/brief")
def save_deal_brief(deal_id: int, payload: BriefIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Двусторонняя запись брифа: в нашу БД и (для сделок из Битрикса) в поле
    ufCrm_1761318500. Для локальных сделок пишем только в БД."""
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    text_val = payload.brief or ""
    pushed = False
    if not _deal_is_local(deal):
        from app.sales.bitrix.transport import vibecode_patch
        try:
            vibecode_patch(f"/deals/{deal.bitrix_id}", {BRIEF_FIELD: text_val})
            pushed = True
        except Exception as e:
            logger.error("save_deal_brief: deal=%s: %s", deal.id, e)
            raise HTTPException(status_code=502, detail="Битрикс отклонил запись брифа (детали в логе сервера)")
    deal.brief = text_val
    deal.brief_synced_at = datetime.utcnow()
    db.commit()
    log_action(db, current_user, "save_deal_brief", "sales_deal", deal.id,
               f"бриф {len(text_val)} симв.{' → Битрикс' if pushed else ' (локально)'}")
    return {"brief": deal.brief, "pushed_to_bitrix": pushed,
            "synced_at": deal.brief_synced_at.isoformat()}


# ── Сверка полей: наша карточка ↔ живой Битрикс ──────────────────────
BX_PORTAL = "https://simb-ad.bitrix24.ru"

# (наше поле, подпись, известный код в Битриксе или None — None = «требует опознания»)
DEAL_FIELD_MAP = [
    ("bitrix_id", "ID сделки", "id"),
    ("title", "Название", "title"),
    ("pipeline", "Воронка", "categoryId"),
    ("bitrix_stage", "Стадия", "stageId"),
    ("amount", "Сумма до НДС", "ufCrm_1690138678699"),
    ("amount_with_vat", "Сумма с НДС", "amount"),          # стандартное поле opportunity
    ("period_from", "Старт РК", "ufCrm_1723639172"),
    ("period_to", "Конец РК", "ufCrm_1723639189"),
    ("advertiser", "Рекламодатель (Лид)", "ufCrm_1761214459"),   # crm-поле → лид рекламодателя
    ("brand", "Бренд", "ufCrm_64BD76BC5BC45"),
    ("agency", "Рекламное агентство", "companyId"),
    ("product", "Продукты Simb-ad", "parentId1050"),
    ("sales_rep", "Sale manager (Продавец)", "ufCrm_1761319635"),        # employee
    ("account_manager", "Key account (Ответственный КС)", "ufCrm_1723638961"),  # employee
    ("brief", "Бриф — Описание задач", "ufCrm_1761318500"),
    ("mp", "МП (медиаплан, файл)", "ufCrm_1690138838403"),               # file
    ("contract_flag", "Договор — подписан?", "ufCrm_1761216445"),        # enumeration
    ("contract_file", "Договор (файл)", "ufCrm_1690897647759"),          # file
    ("payer", "ЮрЛицо | Контрагент | Заказчик", "ufCrm_1785165889"),     # iblock_element; у нас — из связки плательщика
    ("date_create", "Дата создания", "dateCreate"),
]
AGENCY_FIELD_MAP = [
    ("bx_id", "ID компании", "id"), ("name", "Название", "title"),
    ("short_name", "Краткое имя", None), ("name_en", "Имя EN", None), ("name_ru", "Имя RU", None),
    ("holding", "Холдинг", None), ("sk_percent", "СК, %", None),
    ("legal_entity", "Юрлицо", None), ("inn", "ИНН", None),
]
ADVERTISER_FIELD_MAP = [
    ("bx_id", "ID компании", "id"), ("name", "Название", "title"),
    ("short_name", "Краткое имя", None), ("name_en", "Имя EN", None), ("name_ru", "Имя RU", None),
    ("website", "Сайт", None), ("inn", "ИНН", None), ("exclude_from_revenue", "Исключён из выручки", None),
]


def _stringify(v):
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        import json
        return json.dumps(v, ensure_ascii=False)[:300]
    return str(v)[:300]


@router.get("/field-audit/deal/{deal_id}")
def field_audit_deal(deal_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(require_permission("settings", "view"))):
    """Сверка одной сделки: наши поля ↔ живой payload Битрикса (читается каждый раз)."""
    from app.sales.bitrix.transport import vibecode_get
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if _deal_is_local(deal):
        raise HTTPException(status_code=400, detail="Локальная сделка ещё не в Битриксе — сверять нечего")
    adv = db.query(SalesAdvertiser).filter(SalesAdvertiser.id == deal.advertiser_id).first() if deal.advertiser_id else None
    brand = db.query(SalesBrand).filter(SalesBrand.id == deal.brand_id).first() if deal.brand_id else None
    agency = db.query(SalesAgency).filter(SalesAgency.id == deal.agency_id).first() if deal.agency_id else None
    rep = db.query(SalesRep).filter(SalesRep.id == deal.sales_rep_id).first() if deal.sales_rep_id else None
    acct = db.query(SalesRep).filter(SalesRep.id == deal.account_manager_id).first() if deal.account_manager_id else None
    vals = {
        "bitrix_id": deal.bitrix_id, "title": deal.title, "pipeline": deal.pipeline,
        "bitrix_stage": deal.bitrix_stage, "amount": deal.amount, "amount_with_vat": deal.amount_with_vat,
        "period_from": deal.period_from.isoformat() if deal.period_from else None,
        "period_to": deal.period_to.isoformat() if deal.period_to else None,
        "advertiser": (adv.short_name or adv.name) if adv else None,
        "brand": brand.name if brand else None,
        "agency": (agency.short_name or agency.name) if agency else deal.payer_name,
        "product": deal.product, "sales_rep": rep.name if rep else None,
        "account_manager": acct.name if acct else None,
        "brief": ((deal.brief[:80] + "…") if deal.brief and len(deal.brief) > 80 else deal.brief),
        "payer": deal.payer_name,
        "date_create": deal.date_create.isoformat() if deal.date_create else None,
    }
    our = [{"field": f, "label": lab, "bx_code": code, "value": _stringify(vals.get(f))}
           for f, lab, code in DEAL_FIELD_MAP]
    try:
        r = vibecode_get(f"/deals/{deal.bitrix_id}", {})
    except Exception as e:
        logger.error("field_audit_deal %s: %s", deal_id, e)
        raise HTTPException(status_code=502, detail="Битрикс недоступен (детали в логе сервера)")
    data = (r.get("data") if isinstance(r, dict) else None) or (r if isinstance(r, dict) else {})
    bitrix = sorted(({"code": k, "value": _stringify(v)} for k, v in data.items()),
                    key=lambda x: (not str(x["code"]).startswith("uf"), str(x["code"]).lower()))
    return {"entity": "deal", "our": our, "bitrix": bitrix,
            "bitrix_url": f"{BX_PORTAL}/crm/deal/details/{deal.bitrix_id}/",
            "bitrix_id": deal.bitrix_id, "title": deal.title}


@router.get("/field-audit/company/{kind}/{our_id}")
def field_audit_company(kind: str, our_id: int, db: Session = Depends(get_db),
                        current_user: User = Depends(require_permission("settings", "view"))):
    """Сверка одной компании (агентство/рекламодатель): наши поля ↔ живой Битрикс."""
    from app.sales.bitrix.transport import vibecode_get
    if kind == "agency":
        e = db.query(SalesAgency).filter(SalesAgency.id == our_id).first()
        fmap = AGENCY_FIELD_MAP
    elif kind == "advertiser":
        e = db.query(SalesAdvertiser).filter(SalesAdvertiser.id == our_id).first()
        fmap = ADVERTISER_FIELD_MAP
    else:
        raise HTTPException(status_code=400, detail="kind должен быть agency или advertiser")
    if not e:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    if not e.bx_id:
        raise HTTPException(status_code=400, detail="Нет привязки к Битриксу (bx_id пуст)")
    cp = None
    if getattr(e, "counterparty_id", None):
        cp = db.query(Counterparty).filter(Counterparty.id == e.counterparty_id).first()
    vals = {
        "bx_id": e.bx_id, "name": e.name, "short_name": e.short_name,
        "name_en": e.name_en, "name_ru": e.name_ru,
        "holding": getattr(e, "holding", None), "sk_percent": getattr(e, "sk_percent", None),
        "legal_entity": getattr(e, "legal_entity", None) or (cp.name if cp else None),
        "inn": getattr(e, "inn", None) or (cp.inn if cp and getattr(cp, "inn", None) else None),
        "website": getattr(e, "website", None),
        "exclude_from_revenue": getattr(e, "exclude_from_revenue", None),
    }
    our = [{"field": f, "label": lab, "bx_code": code, "value": _stringify(vals.get(f))}
           for f, lab, code in fmap]
    try:
        r = vibecode_get(f"/companies/{e.bx_id}", {})
    except Exception as ex:
        logger.error("field_audit_company %s/%s: %s", kind, our_id, ex)
        raise HTTPException(status_code=502, detail="Битрикс недоступен (детали в логе сервера)")
    data = (r.get("data") if isinstance(r, dict) else None) or (r if isinstance(r, dict) else {})
    bitrix = sorted(({"code": k, "value": _stringify(v)} for k, v in data.items()),
                    key=lambda x: (not str(x["code"]).startswith("uf"), str(x["code"]).lower()))
    return {"entity": kind, "our": our, "bitrix": bitrix,
            "bitrix_url": f"{BX_PORTAL}/crm/company/details/{e.bx_id}/",
            "bitrix_id": e.bx_id, "title": e.short_name or e.name}


@router.post("/deals/{deal_id}/sync-from-bitrix")
def sync_from_bitrix(deal_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Обработчик «⟳ Обновить из Битрикса»: тянет живую сделку, обновляет наши
    поля (продавец/аккаунт/суммы/рекламодатель/бренд) и качает файлы МП/Договора."""
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    from app.sales.bitrix.deal_sync import sync_deal_from_bitrix
    try:
        report = sync_deal_from_bitrix(db, deal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("sync_from_bitrix %s: %s", deal_id, e)
        raise HTTPException(status_code=502, detail="Ошибка синхронизации с Битриксом (детали в логе сервера)")
    log_action(db, current_user, "sync_deal_from_bitrix", "sales_deal", deal.id,
               f"полей: {len(report['changes'])}, файлов: {len(report['files'])}, предупреждений: {len(report['warnings'])}")
    return report


class SyncBulkIn(BaseModel):
    deal_ids: list[int]


@router.post("/deals/bulk-sync-from-bitrix")
def sync_bulk_from_bitrix(payload: SyncBulkIn, db: Session = Depends(get_db),
                          current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Массовая синхронизация выбранных сделок (кап 50 за раз — щадим Битрикс)."""
    from app.sales.bitrix.deal_sync import sync_deal_from_bitrix
    ids = list(dict.fromkeys(payload.deal_ids))[:50]
    summary = {"green": 0, "blue": 0, "red": 0, "errors": 0, "skipped": 0, "total": len(ids)}
    for did in ids:
        deal = db.query(SalesDeal).filter(SalesDeal.id == did).first()
        if not deal or (deal.bitrix_id or "").startswith("local-"):
            summary["skipped"] += 1
            continue
        try:
            _assert_deal_in_scope(db, current_user, deal)
            rep = sync_deal_from_bitrix(db, deal)
            summary[rep["status"]] = summary.get(rep["status"], 0) + 1
        except Exception as e:
            logger.error("sync_bulk %s: %s", did, e)
            summary["errors"] += 1
    log_action(db, current_user, "sync_bulk_from_bitrix", "sales_deal", None,
               f"массовая синхронизация {summary}")
    return summary


@router.get("/deals/{deal_id}/files/{kind}/download")
def download_deal_file(deal_id: int, kind: str, db: Session = Depends(get_db),
                       current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Отдаёт сохранённый у нас файл сделки (МП/договор)."""
    import os
    from fastapi.responses import FileResponse
    from app.sales.models import SalesDealFile
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    rec = (db.query(SalesDealFile)
           .filter(SalesDealFile.deal_id == deal_id, SalesDealFile.kind == kind).first())
    if not rec:
        raise HTTPException(status_code=404, detail="Файл не найден")
    abspath = os.path.join("/app/uploads", rec.path)
    if not os.path.exists(abspath):
        raise HTTPException(status_code=404, detail="Файл отсутствует на диске")
    return FileResponse(abspath, filename=rec.filename or "file",
                        media_type=rec.content_type or "application/octet-stream")


@router.patch("/deals/{deal_id}")
def patch_deal(
    deal_id: int,
    payload: DealPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sales_registry", "edit")),
):
    """Правит поля сделки у нас и помечает их как заполненные вручную.

    Помеченные поля синхронизация не перезаписывает, а заливка в Битрикс
    берёт их по признаку pushed_at IS NULL."""
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)

    # exclude_unset: отличаем «поле не прислали» от «прислали null, очисти».
    changes = payload.dict(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Не передано ни одного поля")

    # Бренд можно поставить только принадлежащий рекламодателю сделки.
    if changes.get("brand_id"):
        brand = db.query(SalesBrand).filter(SalesBrand.id == changes["brand_id"]).first()
        if not brand:
            raise HTTPException(status_code=400, detail="Бренд не найден")
        target_adv = changes.get("advertiser_id", deal.advertiser_id)
        if brand.advertiser_id != target_adv:
            raise HTTPException(status_code=400,
                                detail="Бренд не принадлежит рекламодателю сделки")

    # Смена только рекламодателя осиротит бренд чужого рекламодателя — очищаем его,
    # иначе нарушается инвариант, который стережёт create_deal.
    if "advertiser_id" in changes and "brand_id" not in changes and deal.brand_id:
        cur_brand = db.query(SalesBrand).filter(SalesBrand.id == deal.brand_id).first()
        if _brand_orphaned(cur_brand.advertiser_id if cur_brand else None, changes["advertiser_id"]):
            changes["brand_id"] = None

    existing = {o.field_name: o for o in db.query(SalesDealFieldOverride)
                .filter(SalesDealFieldOverride.deal_id == deal_id).all()}

    for field, value in changes.items():
        if field not in EDITABLE_INT + EDITABLE_DATE + EDITABLE_STR:
            raise HTTPException(status_code=400, detail=f"Поле «{field}» не редактируется")

        setattr(deal, field, value)

        row = existing.get(field)
        if row is None:
            row = SalesDealFieldOverride(deal_id=deal_id, field_name=field)
            db.add(row)
        row.value_int = value if field in EDITABLE_INT else None
        if field in EDITABLE_DATE:
            row.value_text = value.isoformat() if value else None
        elif field in EDITABLE_STR:
            row.value_text = value if value is not None else None
        else:
            row.value_text = None
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
    current_user: User = Depends(require_permission("sales_registry", "edit")),
):
    """Снимает ручную пометку: поле возвращается под управление синхронизации.

    Само значение не откатывается — оно вернётся при следующем прогоне
    из источника. Это и есть механизм отката."""
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if deal:
        _assert_deal_in_scope(db, current_user, deal)
    row = (db.query(SalesDealFieldOverride)
           .filter(SalesDealFieldOverride.deal_id == deal_id,
                   SalesDealFieldOverride.field_name == field_name).first())
    if not row:
        raise HTTPException(status_code=404, detail="Ручная правка по этому полю не найдена")
    db.delete(row)
    db.commit()
    log_action(db, current_user, "drop_sales_override", "sales_deal", deal_id, field_name)
    return {"message": "Поле возвращено под управление синхронизации"}


@router.get("/brands-by-advertiser")
def brands_by_advertiser(db: Session = Depends(get_db),
                         current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Активные бренды, сгруппированные по рекламодателю. Для правки бренда
    в ячейке реестра — предлагаем только бренды рекламодателя этой сделки.
    Ключи — строки (advertiser_id), значения отсортированы по имени."""
    rows = (db.query(SalesBrand.advertiser_id, SalesBrand.id, SalesBrand.name)
            .filter(SalesBrand.is_active.is_(True))
            .order_by(SalesBrand.name).all())
    out = {}
    for aid, bid, name in rows:
        out.setdefault(str(aid), []).append({"value": bid, "label": name})
    return out


@router.get("/filters")
def filter_options(db: Session = Depends(get_db),
                   current_user: User = Depends(require_any_permission(("sales_registry", "sales_analytics"), "view"))):
    """Значения для фильтров-чекбоксов, с числом сделок по каждому.

    Считается по всем сделкам, а не по текущей выборке: иначе, сняв галочку,
    пользователь не смог бы вернуть её обратно — значение исчезло бы из списка."""
    # own-scope: у роли 'own' счётчики фильтров считаются только по её сделкам,
    # чтобы не утекали имена/объёмы чужих (сам список справочников остаётся полным).
    own = _own_rep_ids_or_all(db, current_user, "sales_registry")

    def counted(column):
        rows = (_apply_own_scope(db.query(column, func.count(SalesDeal.id)), own)
                  .group_by(column).order_by(func.count(SalesDeal.id).desc()).all())
        return [{"value": v, "count": c} for v, c in rows if v is not None]

    def named(model, fk):
        rows = (_apply_own_scope(db.query(model.id, model.name, func.count(SalesDeal.id))
                                 .join(SalesDeal, fk == model.id), own)
                  .group_by(model.id, model.name)
                  .order_by(func.count(SalesDeal.id).desc()).all())
        return [{"value": i, "label": n, "count": c} for i, n, c in rows]

    def _full(short, en, ru, name):
        parts = []
        for p in (short, en, ru):
            p = (p or "").strip()
            if p and p not in parts:
                parts.append(p)
        return " | ".join(parts) if parts else name

    def directory(model, fk):
        """ВЕСЬ активный справочник (не только использованное в сделках), подписи
        «краткое | ENG | Рус» как в тултипах реестра, + число сделок (0 если нет)."""
        counts = dict(_apply_own_scope(db.query(fk, func.count(SalesDeal.id)), own).group_by(fk).all())
        rows = db.query(model).filter(model.is_active.is_(True)).all()
        opts = [{"value": m.id, "label": _full(m.short_name, m.name_en, m.name_ru, m.name),
                 "count": counts.get(m.id, 0)} for m in rows]
        return sorted(opts, key=lambda x: (x["label"] or "").lower())

    rep_a, acct_a = aliased(SalesRep), aliased(SalesRep)
    # Число сделок по позициям светофора 2/2/2 — для фильтра «Слой денег» (6 пунктов).
    sk_counts = dict(
        _apply_own_scope(
            db.query(SalesBitrixStageMap.stage_key, func.count(SalesDeal.id))
              .join(SalesDeal, and_(SalesBitrixStageMap.pipeline == SalesDeal.pipeline,
                                    SalesBitrixStageMap.bitrix_stage == SalesDeal.bitrix_stage,
                                    SalesBitrixStageMap.is_active.is_(True))), own)
          .group_by(SalesBitrixStageMap.stage_key).all())
    return {
        "money_layer": [{"value": l, "label": l} for l in ("планируемые", "реализуемые", "фактические")],
        "stage_key": [{"value": s["key"], "label": f"{s['label']} · {s['money_layer']}",
                       "count": sk_counts.get(s["key"], 0)} for s in STAGE_CATALOG],
        "pipeline": [{"value": r["value"], "label": r["value"], "count": r["count"]}
                     for r in counted(SalesDeal.pipeline)],
        "bitrix_stage": [{"value": r["value"], "label": r["value"], "count": r["count"]}
                         for r in counted(SalesDeal.bitrix_stage)],
        "advertiser_id": directory(SalesAdvertiser, SalesDeal.advertiser_id),
        "brand_id": named(SalesBrand, SalesDeal.brand_id),
        "agency_id": directory(SalesAgency, SalesDeal.agency_id),
        "sales_rep_id": named(rep_a, SalesDeal.sales_rep_id),
        "account_manager_id": named(acct_a, SalesDeal.account_manager_id),
        "product": [{"value": r["value"], "label": r["value"], "count": r["count"]}
                    for r in counted(SalesDeal.product)],
    }


@router.get("/sync/status")
def sync_status(db: Session = Depends(get_db),
                current_user: User = Depends(require_permission("sales_registry", "view"))):
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
             current_user: User = Depends(require_permission("sales_registry", "edit"))):
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


# v1: льём в Битрикс только безопасный набор. brand/advertiser/agency/reps/product/
# stage — позже, после синхронизации справочников и обратного маппинга.
PUSHABLE_FIELDS = {"title"}


@router.post("/push-edits")
def push_edits_to_bitrix(commit: int = 0, db: Session = Depends(get_db),
                         current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Заливка наших ручных правок (pushed_at IS NULL) в Битрикс.
    commit=0 — превью (что и куда уйдёт), commit=1 — запись + отметка pushed_at.
    v1 — только title; остальные поля показываются как «пропущено»."""
    from app.sales.models import SalesDealFieldOverride
    pending = (db.query(SalesDealFieldOverride)
               .filter(SalesDealFieldOverride.pushed_at.is_(None)).all())
    by_field = {}
    for o in pending:
        by_field[o.field_name] = by_field.get(o.field_name, 0) + 1
    will = {f: c for f, c in by_field.items() if f in PUSHABLE_FIELDS}
    skipped = {f: c for f, c in by_field.items() if f not in PUSHABLE_FIELDS}
    targets = [o for o in pending if o.field_name in PUSHABLE_FIELDS]
    deal_ids = list({o.deal_id for o in targets})
    deals = ({d.id: d for d in db.query(SalesDeal).filter(SalesDeal.id.in_(deal_ids)).all()}
             if deal_ids else {})
    # локальные (ещё не в Битриксе) сделки заливать некуда — исключаем из счётчиков
    live = [o for o in targets if deals.get(o.deal_id)
            and not (deals[o.deal_id].bitrix_id or "").startswith("local-")]

    if commit == 0:
        return {"will_push": will, "skipped": skipped,
                "deals": len({o.deal_id for o in live}), "total": len(live)}

    from app.sales.bitrix.transport import vibecode_patch
    pushed = 0
    errors = []
    for o in live:
        deal = deals[o.deal_id]
        body = {"title": deal.title}   # v1: только title
        try:
            vibecode_patch(f"/deals/{deal.bitrix_id}", body)
            o.pushed_at = datetime.utcnow()
            pushed += 1
        except Exception as e:
            logger.error("push_edits deal=%s: %s", o.deal_id, e)
            errors.append({"deal": deal.bitrix_id, "error": repr(e)[:80]})
    db.commit()
    log_action(db, current_user, "push_edits_to_bitrix", "sales_deal", None,
               f"залито title: {pushed}, ошибок: {len(errors)}")
    return {"pushed": pushed, "errors": errors, "skipped": skipped}
