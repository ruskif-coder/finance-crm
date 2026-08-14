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
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import func, or_, and_, case
from sqlalchemy.orm import Session, aliased
from typing import Optional, List, Annotated
from pydantic import BaseModel
from datetime import date, datetime
import os
import re

from app.database import get_db
from app.models import User, Counterparty, AuditLog
from app.permissions import require_permission, require_any_permission
from app.audit import log_action
from app.sales.models import (SalesDeal, SalesBitrixStageMap, SalesAdvertiser,
                              SalesRep, SalesBrand, SalesBitrixSyncLog,
                              SalesDealFieldOverride, SalesAgency,
                              SalesStage, SalesPipeline)
from app.sales.stages import STAGE_CATALOG
from app.sales.catalog import Catalog, stage_public
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
    поиск (название / код / bitrix_id / рекламодатель / бренд / агентство /
    контрагент-плательщик), «незаполненные» (включая контрагента).
    Держим в одном месте, чтобы список и сводка считались по одинаковым условиям."""
    if hide_archive:
        q = q.filter(or_(SalesStage.stage_key.is_(None),
                         SalesStage.stage_key != "archive"))
    if search:
        pattern = f"%{search.strip()}%"
        adv_ids = (db.query(SalesAdvertiser.id)
                   .filter(func.coalesce(SalesAdvertiser.short_name,
                                         SalesAdvertiser.name).ilike(pattern)))
        brand_ids = db.query(SalesBrand.id).filter(SalesBrand.name.ilike(pattern))
        agency_ids = (db.query(SalesAgency.id)
                      .filter(func.coalesce(SalesAgency.short_name,
                                            SalesAgency.name).ilike(pattern)))
        # Контрагент (плательщик): ищем по тому же правилу, по которому он выводится
        # в колонке (resolve_payer) — ручное юрлицо -> юрлицо агентства ->
        # юрлицо рекламодателя -> текстовое имя. Иначе поиск не нашёл бы тех,
        # у кого плательщик подставлен по связи, а не выбран руками.
        from app.sales.models import SalesAgencyCounterparty, SalesAdvertiserCounterparty
        cp_ids = db.query(Counterparty.id).filter(Counterparty.name.ilike(pattern))
        ag_by_cp = (db.query(SalesAgencyCounterparty.agency_id)
                    .filter(SalesAgencyCounterparty.counterparty_id.in_(cp_ids)))
        adv_by_cp = (db.query(SalesAdvertiserCounterparty.advertiser_id)
                     .filter(SalesAdvertiserCounterparty.counterparty_id.in_(cp_ids)))
        payer_match = or_(
            SalesDeal.payer_counterparty_id.in_(cp_ids),
            SalesDeal.payer_name.ilike(pattern),
            and_(SalesDeal.payer_counterparty_id.is_(None),
                 SalesDeal.agency_id.isnot(None),
                 SalesDeal.agency_id.in_(ag_by_cp)),
            and_(SalesDeal.payer_counterparty_id.is_(None),
                 SalesDeal.agency_id.is_(None),
                 SalesDeal.advertiser_id.in_(adv_by_cp)),
        )
        q = q.filter(or_(SalesDeal.title.ilike(pattern),
                         SalesDeal.bitrix_id.ilike(pattern),
                         SalesDeal.code.ilike(pattern),
                         SalesDeal.advertiser_id.in_(adv_ids),
                         SalesDeal.brand_id.in_(brand_ids),
                         SalesDeal.agency_id.in_(agency_ids),
                         payer_match))
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
    """Сделки, склеенные со слоем денег НАШЕЙ стадии (our_stage — мастер).
    Джойн LEFT по our_stage_id: у сделки без нашей стадии (сид не сматчил —
    «требует разбора») слой NULL → «Без группы», а не исчезает.
    Битрикс-маппинг (SalesBitrixStageMap) больше НЕ мастер денег — только
    легаси-мост при сидировании our_stage (см. app/sales/stage_resolve.py)."""
    q = db.query(SalesDeal,
                 SalesStage.money_layer.label("layer"),
                 SalesStage.stage_key.label("stage_key")).outerjoin(
        SalesStage, SalesStage.id == SalesDeal.our_stage_id)

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
        _in(SalesDeal.sales_rep_id, sales_rep_id),
        _in(SalesDeal.account_manager_id, account_manager_id),
        _in(SalesDeal.advertiser_id, advertiser_id),
        _in(SalesDeal.brand_id, brand_id),
        _in(SalesDeal.agency_id, agency_id),
        _in(SalesDeal.product, product),
        _in(SalesStage.money_layer, money_layer),
        _in(SalesStage.stage_key, stage_key),
    ):
        if condition is not None:
            q = q.filter(condition)

    # bitrix_stage: значения — простые имена ИЛИ пары "воронка\x1fстадия" (per-pipeline
    # выбор: одинаковая стадия в разных воронках фильтруется независимо).
    if bitrix_stage:
        raw, pairs = [], []
        for v in bitrix_stage:
            if "\x1f" in v:
                _p, _s = v.split("\x1f", 1); pairs.append((_p, _s))
            else:
                raw.append(v)
        conds = []
        if raw:
            conds.append(SalesDeal.bitrix_stage.in_(raw))
        conds += [and_(SalesDeal.pipeline == _p, SalesDeal.bitrix_stage == _s) for _p, _s in pairs]
        if conds:
            q = q.filter(or_(*conds))
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
    # Слой/под-этап — от НАШЕЙ стадии сделки (our_stage — мастер), не от Битрикса.
    stage_key_by_id = {s.id: s.stage_key for s in db.query(SalesStage).all()}

    # СК берём по агентству сделки (sales_agencies.sk_percent), дефолт — константа, если агентства нет.
    sk_by_agency = dict(db.query(SalesAgency.id, SalesAgency.sk_percent).all())
    default_sk_pct = SALES_AGENCY_SK * 100

    def net_of(amount, agency_id):
        # Прямая сделка (без агентства) → СК нет, вся сумма наша.
        pct = sk_by_agency.get(agency_id, default_sk_pct) if agency_id else 0
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
        sk = stage_key_by_id.get(d.our_stage_id)
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
    only_planned: bool = False,
    search: Optional[str] = None,
    gaps: Annotated[Optional[List[str]], Query()] = None,
    sort: str = "period_from",
    direction: str = "desc",
    # Границы задаём в валидации, а не в SQL: min(limit, 500) не спасал от отрицательного
    # значения — Postgres отвечал «LIMIT must not be negative», и ?limit=-1 роняло реестр
    # в 500 вместо 422.
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
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

    # «Только плановые» — сделки, привязанные жёстким линком к строке годового плана.
    if only_planned:
        q = q.filter(SalesDeal.year_plan_line_id.isnot(None))

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
        "money_layer": SalesStage.money_layer,
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
            .limit(limit).offset(offset).all())   # границы — в Query(ge=…, le=…) выше

    adv = dict(db.query(SalesAdvertiser.id, func.coalesce(SalesAdvertiser.short_name, SalesAdvertiser.name)).all())
    reps = dict(db.query(SalesRep.id, SalesRep.name).all())
    brands = dict(db.query(SalesBrand.id, SalesBrand.name).all())
    cps = dict(db.query(Counterparty.id, Counterparty.name).all())
    agencies = dict(db.query(SalesAgency.id, func.coalesce(SalesAgency.short_name, SalesAgency.name)).all())
    # СК по агентству (как в сводке) — для «нашей суммы» в карточке сделки.
    sk_by_agency = dict(db.query(SalesAgency.id, SalesAgency.sk_percent).all())
    default_sk_pct = SALES_AGENCY_SK * 100

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
    our_mp_map = {}
    if page_ids:
        for o in (db.query(SalesDealFieldOverride)
                  .filter(SalesDealFieldOverride.deal_id.in_(page_ids)).all()):
            manual.setdefault(o.deal_id, []).append(o.field_name)
        from app.sales.models import SalesDealFile, SalesMediaPlan
        for frec in (db.query(SalesDealFile)
                     .filter(SalesDealFile.deal_id.in_(page_ids)).all()):
            files_map.setdefault(frec.deal_id, []).append({"kind": frec.kind, "filename": frec.filename})
        # Наши медиапланы, привязанные к сделке (последняя версия каждого group_id).
        for p in (db.query(SalesMediaPlan)
                  .filter(SalesMediaPlan.deal_id.in_(page_ids))
                  .order_by(SalesMediaPlan.group_id, SalesMediaPlan.version.desc()).all()):
            g = our_mp_map.setdefault(p.deal_id, {})
            if p.group_id not in g:
                g[p.group_id] = {"id": p.id, "title": p.title, "version": p.version, "status": p.status}

    # Материнский годовой план сделки (для блока «Годовой план» в раскрытии строки).
    # deal → year_plan_line_id → строка → plan_id → SalesYearPlan.
    plan_meta = {}   # line_id -> {plan_id, line_id, title, comment, year, rep_id}
    line_ids = list({d.year_plan_line_id for d, _, _ in rows if d.year_plan_line_id})
    if line_ids:
        from app.sales.models import SalesYearPlanLine, SalesYearPlan
        pairs = (db.query(SalesYearPlanLine, SalesYearPlan)
                 .outerjoin(SalesYearPlan, SalesYearPlan.id == SalesYearPlanLine.plan_id)
                 .filter(SalesYearPlanLine.id.in_(line_ids)).all())
        # Комментарий рекламодателя из плана хранится в brief.adv_comment строк
        # (см. year_plan): у своей строки, иначе — у любой соседней того же плана.
        plan_ids = {ln.plan_id for ln, _ in pairs if ln.plan_id}
        siblings = {}
        if plan_ids:
            for sl in (db.query(SalesYearPlanLine)
                       .filter(SalesYearPlanLine.plan_id.in_(plan_ids)).all()):
                c = ((sl.brief or {}).get("adv_comment") or "").strip()
                if c and not siblings.get(sl.plan_id):
                    siblings[sl.plan_id] = c
        for ln, pl in pairs:
            own = ((ln.brief or {}).get("adv_comment") or "").strip()
            plan_meta[ln.id] = {
                "line_id": ln.id,
                "plan_id": ln.plan_id,
                "title": (pl.title if pl else None),
                "comment": own or siblings.get(ln.plan_id) or None,
                "year": (pl.year if pl else ln.year),
                "rep_id": (pl.sales_rep_id if pl else ln.sales_rep_id),
            }

    cat = Catalog(db)   # наш каталог стадий — для our_stage/следующей стадии в строке

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [{
            "id": d.id,
            "code": d.code,
            "bitrix_id": d.bitrix_id,
            "title": d.title,
            "pipeline": d.pipeline,
            "product": d.product,
            "probability_color": d.probability_color,
            "period": d.period_from.strftime("%Y-%m") if d.period_from else None,
            "bitrix_stage": d.bitrix_stage,
            "money_layer": layer or NO_GROUP,
            "stage_key": stage_key,
            "our_stage": stage_public(cat.by_id.get(d.our_stage_id), cat),
            "our_next_stage": stage_public(cat.next_of(d.our_stage_id)),
            "realization_pipeline_id": d.realization_pipeline_id,
            "agency": agencies.get(d.agency_id),
            "agency_full": agency_full.get(d.agency_id),
            "agency_id": d.agency_id,
            "payer_name": d.payer_name,
            # выбранный/дефолтный плательщик и варианты для выпадашки
            "payer": resolve_payer(d),
            "payer_counterparty_id": d.payer_counterparty_id,
            "agency_legals": payer_options(d),
            "amount": d.amount,
            "our_sum": round(float(d.amount or 0) * (1 - ((sk_by_agency.get(d.agency_id, default_sk_pct) if d.agency_id else 0) or 0) / 100)),
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
            "year_plan_line_id": d.year_plan_line_id,
            "plan_month": d.plan_month,
            "year_plan": plan_meta.get(d.year_plan_line_id) if d.year_plan_line_id else None,
            "date_create": d.date_create,
            "date_modify": d.date_modify,
            # id нужны интерфейсу для выпадающих списков при правке
            "advertiser_id": d.advertiser_id,
            "brand_id": d.brand_id,
            "sales_rep_id": d.sales_rep_id,
            "account_manager_id": d.account_manager_id,
            "manual_fields": manual.get(d.id, []),
            "files": files_map.get(d.id, []),
            "our_mps": list(our_mp_map.get(d.id, {}).values()),
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
    product: Optional[str] = None
    bitrix_stage: Optional[str] = None


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

    # Стадия — денормализованный строковый ключ (только имя). Фронт-фильтр склеивает
    # опции как "воронка\x1fстадия" (\x1f = разделитель): если такое значение прилетит
    # в bitrix_stage, срезаем префикс, иначе в реестре плодятся стадии-двойники.
    if isinstance(changes.get("bitrix_stage"), str) and "\x1f" in changes["bitrix_stage"]:
        changes["bitrix_stage"] = changes["bitrix_stage"].split("\x1f")[-1]

    # own-scope: как в patch_deal — own-роль может назначать сделки только на себя
    own = _own_rep_ids_or_all(db, current_user)
    if own is not None:
        own_set = set(own)
        for fld in ("sales_rep_id", "account_manager_id"):
            if changes.get(fld) is not None and changes[fld] not in own_set:
                raise HTTPException(status_code=403, detail="Можно назначать сделки только на себя")

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


@router.get("/deals/whoami")
def deal_whoami(db: Session = Depends(get_db),
                current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Кто создаёт сделку: rep_id пользователя + его рабочая группа (seller/account/…) —
    фронт формы автоподставляет продавца ИЛИ аккаунта. Объявлен ДО /deals/{deal_id}."""
    r = db.query(SalesRep.id).filter(SalesRep.user_id == current_user.id).first()
    return {"rep_id": (r[0] if r else None),
            "group": getattr(current_user.role, "staff_group", None)}


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

    # Автоподстановка создателя: продавец ИЛИ аккаунт — по рабочей группе его роли.
    my_rep = db.query(SalesRep.id).filter(SalesRep.user_id == current_user.id).first()
    my_rep = my_rep[0] if my_rep else None
    group = getattr(current_user.role, "staff_group", None)
    rep_id = payload.sales_rep_id
    acc_id = payload.account_manager_id
    if group == "account":
        if acc_id is None:
            acc_id = my_rep
    else:  # продавец и прочие — создатель по умолчанию продавец
        if rep_id is None:
            rep_id = my_rep
    # own-роль создаёт сделки только на себя (свой = продавец ИЛИ аккаунт)
    own = _own_rep_ids_or_all(db, current_user)
    if own is not None:
        own_set = set(own)
        if rep_id not in own_set and acc_id not in own_set:
            raise HTTPException(status_code=403, detail="Можно создавать сделки только на себя")

    # Сделка рождается у нас — стартовая стадия каталога (МП Подготовка)
    from app.sales.catalog import Catalog
    _first = Catalog(db).first()
    our_stage_id = _first.id if _first else None

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
        product=payload.product, sales_rep_id=rep_id, account_manager_id=acc_id,
        our_stage_id=our_stage_id,
        period_from=pf, period_to=pt,
        date_create=datetime.utcnow(),
    )
    from app.sales.deal_code import assign_code
    assign_code(db, deal)
    db.add(deal)
    db.commit()
    db.refresh(deal)
    log_action(db, current_user, "create_deal", "sales_deal", deal.id,
               f"локально: {payload.title or '(без названия)'} · {payload.period}")
    return {"id": deal.id, "code": deal.code, "bitrix_id": deal.bitrix_id}


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


def _deal_by_ref(db, ref):
    """Резолв сделки по числовому id ИЛИ по нашей метке (code, 6 симв, регистронезависимо)."""
    ref = str(ref).strip()
    if ref.isdigit():
        return db.query(SalesDeal).filter(SalesDeal.id == int(ref)).first()
    d = db.query(SalesDeal).filter(func.upper(SalesDeal.code) == ref.upper()).first()
    if not d:   # фолбэк для старых пинов/ссылок с bitrix_id (в т.ч. local-…)
        d = db.query(SalesDeal).filter(SalesDeal.bitrix_id == ref).first()
    return d


@router.get("/deals/{deal_id}/brief")
def get_deal_brief(deal_id: str, refresh: int = 0, db: Session = Depends(get_db),
                   current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Бриф сделки. Ленивая подгрузка: если ещё не тянули (brief IS NULL) или refresh=1 —
    читаем из Битрикса поле ufCrm_1761318500 и кэшируем. Локальные сделки (local-) — только БД."""
    deal = _deal_by_ref(db, deal_id)
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
                     current_user: User = Depends(require_permission("settings_field_audit", "view"))):
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
                        current_user: User = Depends(require_permission("settings_field_audit", "view"))):
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
    except RuntimeError as e:
        # Не настроена интеграция (нет VIBECODE_API_KEY) — это конфигурация, а не сбой.
        # Показываем причину прямо в интерфейсе, иначе «детали в логе сервера» ничего не говорят.
        logger.error("sync_from_bitrix %s: %s", deal_id, e)
        raise HTTPException(status_code=503, detail=f"Синхронизация с Битриксом не настроена: {e}")
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
    failed = []   # где отвалилось: [{id, title, error}]
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
            failed.append({"id": did, "title": (deal.title or f"#{did}"), "error": str(e)[:160]})
    summary["done"] = summary["green"] + summary["blue"] + summary["red"]   # успешно отработано
    summary["failed"] = failed
    log_action(db, current_user, "sync_bulk_from_bitrix", "sales_deal", None,
               f"массовая синхронизация: всего {summary['total']}, ок {summary['done']}, ошибок {summary['errors']}, пропущено {summary['skipped']}")
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


# Документы сделки: что можно грузить руками. mp/contract приходят из Битрикса
# синком — их не даём перетирать вручную, чтобы синк и ручная копия не разъезжались.
DEAL_DOC_KINDS = {
    "ds": "Доп. соглашение", "invoice": "Счёт", "upd": "УПД", "report": "Отчёт", "act": "Акт",
    "creatives": "Креативы", "brief_file": "Бриф (файл)",
}
# Креативы — рекламные материалы под размещение: почти всегда архив или картинки,
# поэтому список расширений общий (zip/rar/7z/jpg/png уже разрешены).
DEAL_DOC_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png", ".gif",
                 ".zip", ".rar", ".7z"}
DEAL_DOC_MAX_BYTES = 20 * 1024 * 1024   # как в договорах — 20 МБ


@router.post("/deals/{deal_id}/files/{kind}")
async def upload_deal_file(deal_id: str, kind: str, file: UploadFile = File(...),
                           db: Session = Depends(get_db),
                           current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Загрузка документа сделки (ДС/счёт/отчёт/акт/бриф-файл). Один файл на вид:
    повторная загрузка заменяет предыдущий (UNIQUE(deal_id, kind) в модели)."""
    import os
    import re as _re
    from app.sales.models import SalesDealFile
    if kind not in DEAL_DOC_KINDS:
        raise HTTPException(status_code=400, detail=f"Неизвестный вид документа: {kind}")
    deal = _deal_by_ref(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)

    original = file.filename or "document"
    ext = os.path.splitext(original)[1].lower()
    if ext not in DEAL_DOC_EXTS:
        raise HTTPException(status_code=415,
                            detail=f"Недопустимый тип файла. Разрешены: {', '.join(sorted(DEAL_DOC_EXTS))}")
    content = await file.read()
    if len(content) > DEAL_DOC_MAX_BYTES:
        raise HTTPException(status_code=413,
                            detail=f"Файл слишком большой (максимум {DEAL_DOC_MAX_BYTES // 1024 // 1024} МБ)")

    subdir = os.path.join("/app/uploads", "deal_files")
    os.makedirs(subdir, exist_ok=True)
    safe = _re.sub(r"[^\w\.\-]", "_", original)
    rel = os.path.join("deal_files", f"{deal.id}_{kind}_{safe}")
    rec = (db.query(SalesDealFile)
           .filter(SalesDealFile.deal_id == deal.id, SalesDealFile.kind == kind).first())
    if rec:   # заменяем: старый файл с диска убираем, чтобы не копить мусор
        old = os.path.join("/app/uploads", rec.path or "")
        if rec.path and os.path.exists(old) and old != os.path.join("/app/uploads", rel):
            try:
                os.remove(old)
            except OSError:
                logger.warning("upload_deal_file: не удалось удалить старый %s", old)
    with open(os.path.join("/app/uploads", rel), "wb") as fh:
        fh.write(content)
    if not rec:
        rec = SalesDealFile(deal_id=deal.id, kind=kind)
        db.add(rec)
    rec.filename = original
    rec.path = rel
    rec.size = len(content)
    rec.content_type = file.content_type
    db.commit()
    log_action(db, current_user, "upload_deal_file", "sales_deal", deal.id,
               f"{DEAL_DOC_KINDS[kind]}: {original}")
    return {"kind": kind, "filename": original, "size": len(content)}


@router.delete("/deals/{deal_id}/files/{kind}")
def delete_deal_file(deal_id: str, kind: str, db: Session = Depends(get_db),
                     current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Удаление документа сделки. Файлы из Битрикса (mp/contract) не трогаем —
    их владелец синк, ручное удаление разошлось бы с источником."""
    import os
    from app.sales.models import SalesDealFile
    if kind not in DEAL_DOC_KINDS:
        raise HTTPException(status_code=400, detail="Этот документ удаляется только синхронизацией")
    deal = _deal_by_ref(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    rec = (db.query(SalesDealFile)
           .filter(SalesDealFile.deal_id == deal.id, SalesDealFile.kind == kind).first())
    if not rec:
        raise HTTPException(status_code=404, detail="Файл не найден")
    p = os.path.join("/app/uploads", rec.path or "")
    if rec.path and os.path.exists(p):
        try:
            os.remove(p)
        except OSError:
            logger.warning("delete_deal_file: не удалось удалить %s", p)
    db.delete(rec)
    db.commit()
    log_action(db, current_user, "delete_deal_file", "sales_deal", deal.id, DEAL_DOC_KINDS[kind])
    return {"message": "Файл удалён", "kind": kind}


# Человекочитаемые ярлыки событий сделки и полей — для секции «История» в карточке.
_DEAL_EVENT_LABELS = {
    "upload_deal_file": "Документ загружен",
    "delete_deal_file": "Документ удалён",
    "move_deal": "Смена стадии",
    "create_deal": "Сделка создана",
    "patch_sales_deal": "Изменение полей",
    "save_deal_brief": "Бриф обновлён",
    "push_deal_to_bitrix": "Отправлена в Битрикс",
    "sync_deal_from_bitrix": "Синхронизирована из Битрикса",
}
_DEAL_FIELD_LABELS = {
    "title": "Название", "advertiser_id": "Рекламодатель", "brand_id": "Бренд",
    "agency_id": "Агентство", "sales_rep_id": "Продавец", "account_manager_id": "Аккаунт",
    "payer_counterparty_id": "Плательщик", "period_from": "Старт РК", "period_to": "Конец РК",
    "product": "Услуга", "bitrix_stage": "Стадия",
}


@router.get("/deals/{deal_id}/history")
def deal_history(deal_id: str, db: Session = Depends(get_db),
                 current_user: User = Depends(require_permission("sales_registry", "view"))):
    """История сделки из журнала действий (audit_log) — событие, инициатор, время.
    Показывает только действия через наше приложение (правки прямо в Битриксе сюда не
    попадают); массовые операции пишутся без entity_id и здесь не отображаются."""
    deal = _deal_by_ref(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    rows = (db.query(AuditLog)
            .filter(AuditLog.entity_type == "sales_deal", AuditLog.entity_id == deal.id)
            .order_by(AuditLog.created_at.desc()).limit(100).all())

    def _detail(r):
        if r.action == "patch_sales_deal" and r.details:
            return ", ".join(_DEAL_FIELD_LABELS.get(f.strip(), f.strip()) for f in r.details.split(","))
        return r.details

    return {"items": [{
        "action": r.action,
        "label": _DEAL_EVENT_LABELS.get(r.action, r.action),
        "who": r.user_name,          # инициатор (денормализовано в audit_log)
        "at": r.created_at,          # UTC; фронт показывает в Europe/Moscow
        "details": _detail(r),
    } for r in rows]}


def _year_plan_of_deal(db, deal):
    """Материнский годовой план сделки для карточки (тот же контракт, что в реестре).
    Комментарий рекламодателя живёт в brief.adv_comment строк плана."""
    if not deal or not deal.year_plan_line_id:
        return None
    from app.sales.models import SalesYearPlanLine, SalesYearPlan
    ln = db.query(SalesYearPlanLine).filter(SalesYearPlanLine.id == deal.year_plan_line_id).first()
    if not ln:
        return None
    pl = db.query(SalesYearPlan).filter(SalesYearPlan.id == ln.plan_id).first() if ln.plan_id else None
    comment = ((ln.brief or {}).get("adv_comment") or "").strip()
    if not comment and ln.plan_id:
        for sl in db.query(SalesYearPlanLine).filter(SalesYearPlanLine.plan_id == ln.plan_id).all():
            c = ((sl.brief or {}).get("adv_comment") or "").strip()
            if c:
                comment = c
                break
    return {
        "line_id": ln.id, "plan_id": ln.plan_id,
        "title": (pl.title if pl else None), "comment": comment or None,
        "year": (pl.year if pl else ln.year),
        "rep_id": (pl.sales_rep_id if pl else ln.sales_rep_id),
        "month": deal.plan_month,
    }


@router.get("/deals/{deal_id}")
def get_deal(deal_id: str, db: Session = Depends(get_db),
             current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Одна сделка для карточки /deals/{code|id}: поля как в реестре + our_sum и файлы."""
    from app.sales.models import SalesDealFile
    deal = _deal_by_ref(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)

    adv = db.query(SalesAdvertiser).filter(SalesAdvertiser.id == deal.advertiser_id).first() if deal.advertiser_id else None
    agc = db.query(SalesAgency).filter(SalesAgency.id == deal.agency_id).first() if deal.agency_id else None
    brand = db.query(SalesBrand).filter(SalesBrand.id == deal.brand_id).first() if deal.brand_id else None
    rep = db.query(SalesRep).filter(SalesRep.id == deal.sales_rep_id).first() if deal.sales_rep_id else None
    acc = db.query(SalesRep).filter(SalesRep.id == deal.account_manager_id).first() if deal.account_manager_id else None
    payer = None
    if deal.payer_counterparty_id:
        cp = db.query(Counterparty).filter(Counterparty.id == deal.payer_counterparty_id).first()
        payer = cp.name if cp else None
    payer = payer or deal.payer_name
    # Прямая сделка (без агентства) → СК нет, вся сумма наша.
    sk_pct = dict(db.query(SalesAgency.id, SalesAgency.sk_percent).all()).get(deal.agency_id, SALES_AGENCY_SK * 100) if deal.agency_id else 0
    files = [{"kind": f.kind, "filename": f.filename, "size": f.size} for f in
             db.query(SalesDealFile).filter(SalesDealFile.deal_id == deal.id).all()]
    # Наши медиапланы сделки — последняя версия каждой группы (как в реестре).
    from app.sales.models import SalesMediaPlan
    our_mps = {}
    for mp in (db.query(SalesMediaPlan).filter(SalesMediaPlan.deal_id == deal.id)
               .order_by(SalesMediaPlan.group_id, SalesMediaPlan.version.desc()).all()):
        if mp.group_id not in our_mps:
            our_mps[mp.group_id] = {"id": mp.id, "title": mp.title, "version": mp.version,
                                    "status": mp.status, "updated_at": mp.updated_at}
    cat = Catalog(db)
    return {
        "id": deal.id, "code": deal.code, "bitrix_id": deal.bitrix_id, "title": deal.title,
        "advertiser": (adv.short_name or adv.name) if adv else None, "advertiser_id": deal.advertiser_id,
        "brand": brand.name if brand else None,
        "agency": (agc.short_name or agc.name) if agc else None, "agency_id": deal.agency_id,
        "product": deal.product,
        "payer": payer, "payer_counterparty_id": deal.payer_counterparty_id,
        "counterparty_id": deal.payer_counterparty_id or deal.counterparty_id,
        "period": deal.period_from.strftime("%Y-%m") if deal.period_from else None,
        "period_from": deal.period_from, "period_to": deal.period_to,
        "bitrix_stage": deal.bitrix_stage,
        "sales_rep": _short_fio(rep.name) if rep else None,
        "account_manager": _short_fio(acc.name) if acc else None,
        "amount": deal.amount,
        # amount — до НДС; gross берём сохранённый, а если его нет (старые записи) —
        # считаем по ставке, чтобы карточка не показывала пусто
        "amount_with_vat": deal.amount_with_vat if deal.amount_with_vat is not None
        else (round(float(deal.amount) * (1 + SALES_VAT_RATE), 2) if deal.amount is not None else None),
        "our_sum": round(float(deal.amount or 0) * (1 - (sk_pct or 0) / 100)),
        "currency": deal.currency, "files": files, "date_create": deal.date_create,
        "plan_month": deal.plan_month, "year_plan_line_id": deal.year_plan_line_id,
        "year_plan": _year_plan_of_deal(db, deal),
        # для бара стадий и диалога движения — тот же контракт, что в реестре
        "our_stage": stage_public(cat.by_id.get(deal.our_stage_id), cat),
        "our_next_stage": stage_public(cat.next_of(deal.our_stage_id)),
        "realization_pipeline_id": deal.realization_pipeline_id,
        "our_mps": list(our_mps.values()),
    }


class ProbabilityIn(BaseModel):
    color: Optional[str] = None   # grey | orange | green | None (снять)


@router.post("/deals/{deal_id}/probability")
def set_deal_probability(
    deal_id: int,
    payload: ProbabilityIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sales_registry", "edit")),
):
    """Светофор вероятности сделки (наша ручная разметка): grey|orange|green|None.
    В синке/заливке в Битрикс НЕ участвует — это чисто наш индикатор."""
    color = (payload.color or "").strip().lower() or None
    if color is not None and color not in ("grey", "orange", "green"):
        raise HTTPException(status_code=400, detail="Недопустимый цвет")
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    deal.probability_color = color
    db.commit()
    return {"message": "Сохранено", "probability_color": color}


class MoveIn(BaseModel):
    to_stage_id: Optional[int] = None       # None → следующая стадия по цепочке
    comment: str
    realization_pipeline_id: Optional[int] = None
    override_reason: Optional[str] = None


def _reflect_stage_binding(db, deal, target):
    """Отражает привязку целевой стадии на полях deal.pipeline/bitrix_stage (для реестра
    и последующего толкания в Битрикс). Воронка: реализационный этап → выбранная на сделке,
    иначе — зафиксированная на стадии. No-op, если привязка не задана."""
    from app.sales.models import SalesPipelineStage
    realization = bool(target.phase and target.phase.is_realization)
    pipe_id = deal.realization_pipeline_id if realization else target.bitrix_pipeline_id
    if not pipe_id or not target.bitrix_status_id:
        return
    pipe = db.query(SalesPipeline).filter(SalesPipeline.id == pipe_id).first()
    st = (db.query(SalesPipelineStage)
          .filter(SalesPipelineStage.pipeline_id == pipe_id,
                  SalesPipelineStage.status_id == target.bitrix_status_id).first())
    if pipe:
        deal.pipeline = pipe.name
    if st:
        deal.bitrix_stage = st.name


@router.post("/deals/{deal_id}/move")
def move_deal(
    deal_id: int,
    payload: MoveIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sales_registry", "edit")),
):
    """Двигает сделку по нашему каталогу стадий (E2). Дефолт (to_stage_id=None) — на
    следующую стадию. Назад — только мастера. Реализационный этап требует воронку.
    Комментарий обязателен. Толкание в Битрикс — отражением привязки (см. _reflect)."""
    if not (payload.comment or "").strip():
        raise HTTPException(status_code=400, detail="Комментарий обязателен")
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)

    cat = Catalog(db)
    if not cat.stages:
        raise HTTPException(status_code=400, detail="Каталог стадий пуст")
    cur_id = deal.our_stage_id
    if payload.to_stage_id:
        # Неизвестный id раньше проваливался в общую ветку и отвечал «сделка на последней
        # стадии» — сообщение, по которому невозможно понять, что стадии просто нет.
        target = cat.by_id.get(payload.to_stage_id)
        if target is None:
            raise HTTPException(status_code=404,
                                detail=f"Стадия {payload.to_stage_id} не найдена в каталоге")
    else:
        target = cat.next_of(cur_id)
        if target is None:
            raise HTTPException(status_code=400, detail="Некуда двигать — сделка на последней стадии")

    is_back = cur_id is not None and not target.is_terminal and cat.is_before(target.id, cur_id)
    is_master = (current_user.role.key == "admin") or bool(getattr(current_user.role, "is_master", False))
    if is_back and not is_master:
        raise HTTPException(status_code=403, detail="Двигать сделку назад может только мастер")

    # МП обязателен со стадии «МП согласование» и далее — двигаем только с привязанным МП
    if getattr(target, "requires_media_plan", False) and not target.is_terminal:
        from app.sales.models import SalesMediaPlan
        has_mp = db.query(SalesMediaPlan.id).filter(SalesMediaPlan.deal_id == deal.id).first()
        if not has_mp:
            raise HTTPException(status_code=400,
                detail="Нужен привязанный медиаплан — привяжите МП к сделке в конструкторе")

    # Воронка нужна рабочим стадиям реализационного этапа: одна и та же стадия живёт в
    # каждой продуктовой воронке. Терминальные — исключение: сделка умерла, привязывать
    # её к воронке незачем, а требование воронки сделало бы «сорвалась» недостижимой у
    # сделок, которые до реализации не дошли.
    if target.phase and target.phase.is_realization and not target.is_terminal:
        if payload.realization_pipeline_id is not None:
            deal.realization_pipeline_id = payload.realization_pipeline_id
        if not deal.realization_pipeline_id:
            raise HTTPException(status_code=400, detail="Выберите воронку реализации под продукт")

    prev = cat.by_id.get(cur_id)
    deal.our_stage_id = target.id
    _reflect_stage_binding(db, deal, target)
    db.commit()

    label = f"{prev.name if prev else '—'} → {target.name}"
    if payload.override_reason:
        label += f" (оверрайд: {payload.override_reason})"
    log_action(db, current_user, "move_deal", "sales_deal", deal.id,
               f"{label}. Комментарий: {payload.comment.strip()}")
    return {"message": "Сделка перемещена",
            "our_stage": stage_public(target, cat),
            "our_next_stage": stage_public(cat.next_of(target.id)),
            "realization_pipeline_id": deal.realization_pipeline_id}


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

    # Стадия — только имя (см. bulk_update_deals): срезаем составной ключ "воронка\x1fстадия".
    if isinstance(changes.get("bitrix_stage"), str) and "\x1f" in changes["bitrix_stage"]:
        changes["bitrix_stage"] = changes["bitrix_stage"].split("\x1f")[-1]

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

    # own-роль не может переназначить сделку на чужого продавца/аккаунт
    # (симметрично create_deal). Сделку в своей зоне видимости уже подтвердил
    # _assert_deal_in_scope выше; здесь ограничиваем НОВОГО ответственного.
    own = _own_rep_ids_or_all(db, current_user)
    if own is not None:
        own_set = set(own)
        for fld in ("sales_rep_id", "account_manager_id"):
            if changes.get(fld) is not None and changes[fld] not in own_set:
                raise HTTPException(status_code=403, detail="Можно назначать сделки только на себя")

    # Плательщик — только юрлицо, привязанное к агентству (а если агентства нет —
    # к рекламодателю) сделки. Иначе можно привязать произвольного контрагента.
    if changes.get("payer_counterparty_id") is not None:
        from app.sales.models import SalesAgencyCounterparty, SalesAdvertiserCounterparty
        eff_agency = changes.get("agency_id", deal.agency_id)
        eff_adv = changes.get("advertiser_id", deal.advertiser_id)
        if eff_agency:
            allowed = {r[0] for r in db.query(SalesAgencyCounterparty.counterparty_id)
                       .filter(SalesAgencyCounterparty.agency_id == eff_agency).all()}
        else:
            allowed = {r[0] for r in db.query(SalesAdvertiserCounterparty.counterparty_id)
                       .filter(SalesAdvertiserCounterparty.advertiser_id == eff_adv).all()}
        if changes["payer_counterparty_id"] not in allowed:
            raise HTTPException(status_code=400,
                                detail="Плательщик должен быть юрлицом агентства/рекламодателя сделки")

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
            db.query(SalesStage.stage_key, func.count(SalesDeal.id))
              .join(SalesStage, SalesStage.id == SalesDeal.our_stage_id), own)
          .group_by(SalesStage.stage_key).all())

    # ── Воронки в логическом порядке (настройки: sort_order) + группировка стадий ──
    from app.sales.models import SalesPipeline, SalesPipelineStage
    tracked_pipes = (db.query(SalesPipeline).filter(SalesPipeline.is_tracked.is_(True))
                     .order_by(SalesPipeline.sort_order, SalesPipeline.bitrix_category_id).all())
    pipe_names = [p.name for p in tracked_pipes]
    stage_key_idx = {s["key"]: i for i, s in enumerate(STAGE_CATALOG)}   # порядок светофора
    smap = {(m.pipeline, m.bitrix_stage): m.stage_key
            for m in db.query(SalesBitrixStageMap).filter(SalesBitrixStageMap.is_active.is_(True)).all()}
    ps_native = {}   # родной порядок стадии в воронке (тай-брейк внутри одного слоя)
    for _p in tracked_pipes:
        for _st in (db.query(SalesPipelineStage)
                    .filter(SalesPipelineStage.bitrix_category_id == _p.bitrix_category_id).all()):
            ps_native[(_p.name, _st.name)] = _st.sort_order

    def _stage_rank(pipe_name, stage_name):
        n = (stage_name or "").lower()
        native = ps_native.get((pipe_name, stage_name), 999)
        if "провал" in n or "не случил" in n or "отказ" in n:   # LOSE — в самый конец
            return (99, native)
        if "архив" in n:                                          # Архив — перед провалом
            return (90, native)
        sk = smap.get((pipe_name, stage_name))                   # по светофору; неразмеченные — середина
        return (stage_key_idx.get(sk, 50), native)

    # Счётчики сделок по (воронка, стадия) — own-scope.
    ps_counts = {}
    for _pipe, _stage, _c in (_apply_own_scope(
            db.query(SalesDeal.pipeline, SalesDeal.bitrix_stage, func.count(SalesDeal.id)), own)
            .group_by(SalesDeal.pipeline, SalesDeal.bitrix_stage).all()):
        ps_counts[(_pipe, _stage)] = _c

    # Воронки: логический порядок из настроек, + прочие из сделок в конец.
    _pcnt = {}
    for (_pipe, _stage), _c in ps_counts.items():
        _pcnt[_pipe] = _pcnt.get(_pipe, 0) + _c
    pipeline_opts = [{"value": n, "label": n, "count": _pcnt.get(n, 0)} for n in pipe_names]
    for _pipe in sorted(k for k in _pcnt if k and k not in pipe_names):
        pipeline_opts.append({"value": _pipe, "label": _pipe, "count": _pcnt[_pipe]})

    # Стадии: сгруппированы по воронке (логический порядок), внутри — по светофору,
    # Архив и «Сделка провалена» в конце группы. group — заголовок группы в дропдауне.
    # Берём ВСЕ стадии воронки из настроек (sales_pipeline_stages) + исторические
    # названия из сделок — чтобы список совпадал с настройками воронок (даже стадии
    # без сделок, count=0), а не только использованные.
    # value — пара "воронка\x1fстадия": одинаковые имена стадий в разных воронках
    # выбираются НЕЗАВИСИМО (иначе выбор «Архив» цеплял бы все воронки сразу).
    # tone='danger' — «Сделка провалена»: фронт красит красным в списке.
    stage_opts = []
    for n in pipe_names:
        names = {st for (pp, st) in ps_native if pp == n and st}
        names |= {st for (pp, st) in ps_counts if pp == n and st}
        for s in sorted(names, key=lambda st: _stage_rank(n, st)):
            low = (s or "").lower()
            lost = "провал" in low or "не случил" in low or "отказ" in low
            opt = {"value": f"{n}\x1f{s}", "label": s, "count": ps_counts.get((n, s), 0), "group": n}
            if lost:
                opt["tone"] = "danger"
            stage_opts.append(opt)

    return {
        "money_layer": [{"value": l, "label": l} for l in ("планируемые", "реализуемые", "фактические")],
        "stage_key": [{"value": s["key"], "label": f"{s['label']} · {s['money_layer']}",
                       "count": sk_counts.get(s["key"], 0)} for s in STAGE_CATALOG],
        "pipeline": pipeline_opts,
        "bitrix_stage": stage_opts,
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
