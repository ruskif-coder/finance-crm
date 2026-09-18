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
from sqlalchemy import func, or_, and_, text
from sqlalchemy.orm import Session, aliased
from typing import Optional, List, Annotated
from pydantic import BaseModel
from datetime import date, datetime
import os
import re

from app.files_safe import existing_upload_path, remove_upload
from app.database import get_db
from app.models import User, Counterparty, AuditLog
from app import own_company
from app.permissions import require_permission, require_any_permission
from app.audit import log_action
from app.sales.models import (SalesDeal, SalesBitrixStageMap, SalesAdvertiser,
                              SalesRep, SalesBrand, SalesBitrixSyncLog,
                              SalesDealFieldOverride, SalesAgency,
                              SalesStage, SalesStagePhase, SalesPipeline)
from app.sales.stages import STAGE_CATALOG
from app.sales.deal_label import deal_label
from app.sales.catalog import Catalog, stage_public
from app.sales.models import SalesDealStageHistory
from app.sales import periods
from app.sales import stage_move
from app.sales import stage_scope
from app.sales.row_context import load_row_context
from app.sales.mp_amounts import mp_amounts_by_deal, eff_net, eff_gross
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
    if row is None:
        # ⚠ АСИММЕТРИЯ УМОЛЧАНИЯ, из-за которой это и написано.
        #
        # ОТСУТСТВИЕ той же самой строки `role_permissions` означает в двух местах
        # ПРОТИВОПОЛОЖНОЕ: в `require_permission` — «запрещено», здесь — «все сделки».
        # То есть роль, которой выдали `creatives`, но не завели строку `sales_registry`,
        # получала доступ ко ВСЕМ чужим сделкам в сборке запуска — молча и по умолчанию
        # (F1-05 внешнего аудита 11.09.2026).
        #
        # Сегодня не стреляет: строка `sales_registry` есть у всех одиннадцати
        # неадминских ролей (замер 11.09.2026), а `own` встречается дважды и обе — у
        # годового плана. Но это свойство ДАННЫХ, а не кода: первая же новая роль,
        # заведённая без неё, откроет чужие сделки.
        #
        # Отказываем ВСЛУХ, а не сужаем до «своих»: сужение дало бы второй тихий отказ —
        # человек с правом видел бы пустой экран и не понимал почему. Текст говорит
        # администратору, что именно настроить.
        raise HTTPException(
            status_code=403,
            detail=(f"Для роли «{user.role.label}» не настроена видимость сделок в "
                    f"разделе «{section}». Пока её нет, показывать чужие сделки нельзя. "
                    f"Откройте Настройки → Роли и задайте область («свои» или «все»)."))
    if (row.deals_scope or "all") != "own":
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
        # Архив — это ЛЮБОЙ терминальный исход, а не только «Архив успешных сделок»
        # (владелец 15.09.2026). Раньше признаком было `stage_key = 'archive'`, а у
        # «Сделка не случилась» и «Сделка сорвалась» ключа нет вовсе — они проходили
        # через ветку `IS NULL` и оставались в выдаче при включённом «скрыть архив».
        # Замер на стенде: 569 сделок в архиве прятались, 3 сорванные — нет.
        #
        # Сделка БЕЗ нашей стадии (`SalesStage.id IS NULL` после LEFT JOIN) остаётся
        # видимой: это «требует разбора», её как раз и надо найти, а не спрятать.
        q = q.filter(or_(SalesStage.id.is_(None),
                         and_(SalesStage.is_terminal.isnot(True),
                              SalesStage.is_lost.isnot(True))))
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
                product=None, stage_key=None, our_stage_id=None):
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
        # Отбор идёт по ФИНАНСОВОМУ ПЕРИОДУ сделки — месяцу, который стоит в её «Периоде»
        # и виден в одноимённом столбце. Правило владельца 15.09.2026.
        #
        # Раньше считалось пересечение ДАТ РАЗМЕЩЕНИЯ с окном, и выборка отвечала на
        # другой вопрос: «какие кампании в эти месяцы крутились». Оттуда и «работает
        # криво»: в марте—мае показывались сделки с периодом «2026-01» (размещение
        # длинное, задевает март), а сделка с периодом «2026-07» пропадала из июля,
        # если у неё испорчен конец — а таких 32, вплоть до года разницы со стартом.
        # Финансовый период в дате окончания не нуждается вовсе, поэтому испортить его
        # больше нечем.
        #
        # Период материализован как первое число месяца в `period_from` (см.
        # `_period_bounds` и правку «Периода» в реестре), поэтому окно — это просто
        # границы месяцев.
        conds = []
        if start:
            conds.append(SalesDeal.period_from >= start)
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

    # НАША стадия — точный фильтр по id из каталога. Именно он показывается в реестре
    # как «Стадия»: битриксовые имена дублируются по воронкам и содержат имена
    # сотрудников («Закрывающие документы | Мария»), выбирать по ним нельзя.
    if our_stage_id:
        q = q.filter(SalesDeal.our_stage_id.in_(list(our_stage_id)))

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


def _group(rows, key_fn, excluded_adv=frozenset(), mp=None):
    """Сворачивает выборку по ключу с разбивкой суммы по слоям денег.
    fact — реализованная выручка (фактический слой), исключая рекламодателей
    с флагом «не в выручке» (МП). real/plan — реализуемые/планируемые."""
    mp = mp or {}
    acc = {}
    for deal, layer, _stage_key in rows:
        key = key_fn(deal, layer) or NO_GROUP
        b = acc.setdefault(key, {"name": key, "deals": 0, "amount": 0.0,
                                 "fact": 0.0, "real": 0.0, "plan": 0.0})
        amt = eff_net(deal, mp)
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
    our_stage_id: Annotated[Optional[List[int]], Query()] = None,
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
                     bitrix_stage, brand_id, agency_id, product, stage_key, our_stage_id)
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

    mp = mp_amounts_by_deal(db, [d.id for d, _, _ in rows])
    total_amount = sum(eff_net(d, mp) for d, _, _ in rows)

    by_layer = _group(rows, lambda d, layer: layer, excluded_adv, mp)
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
        "by_pipeline": _group(rows, lambda d, layer: d.pipeline, excluded_adv, mp),
        "by_sales_rep": _group(rows, lambda d, layer: rep_names.get(d.sales_rep_id), excluded_adv, mp),
        "by_account_manager": _group(rows, lambda d, layer: rep_names.get(d.account_manager_id), excluded_adv, mp),
        "by_agency": _group(rows, lambda d, layer: agency_names.get(d.agency_id), excluded_adv, mp)[:50],
        "by_advertiser": _group(rows, lambda d, layer: adv_names.get(d.advertiser_id), excluded_adv, mp)[:50],
        "by_product": _group(rows, lambda d, layer: d.product, excluded_adv, mp)[:50],
        "by_month": sorted(
            _group(rows, lambda d, layer: periods.month_key(d.period_from), excluded_adv, mp),
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
    mp = mp_amounts_by_deal(db, [d.id for d in deals])
    for d in deals:
        amt = eff_net(d, mp)
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
def list_reps(role: str = "sales", db: Session = Depends(get_db),
              current_user: User = Depends(require_any_permission(
                  ("sales_dashboard", "sales_registry", "sales_analytics",
                   "accounts_dashboard"), "view"))):
    """Сотрудники (SalesRep) для селектора «смотреть чужого».

    role='sales'  — продавцы: мастер-сейлз (is_sales_head) ИЛИ кто хоть раз был
                    продавцом сделки. Чистые аккаунт-менеджеры отсекаются.
    role='account'— аккаунты: кто хоть раз был account_manager_id. Отдельный список,
                    а не тот же: в очереди аккаунта выбирать сейлза, который никогда
                    не вёл сделку как аккаунт, бессмысленно — он всегда будет пустым.

    `mine` в ответе — id профиля текущего пользователя (или None): интерфейсу нужно
    отметить «меня» звёздочкой, не угадывая по имени.

    Список НЕ сужается под own-scope сознательно (решение владельца 2026-08-17): имена
    сотрудников в компании считаются открытыми. Роль со scope='own' увидит коллег
    в селекторе, но их сделки ей всё равно не отдадут — видимость режется отдельно
    (_apply_own_scope), и селектор чужого её не обходит."""
    field = SalesDeal.account_manager_id if role == "account" else SalesDeal.sales_rep_id
    seen = {r[0] for r in db.query(field).filter(field.isnot(None)).distinct().all()}
    rows = db.query(SalesRep).order_by(SalesRep.name).all()
    keep = (lambda r: r.id in seen) if role == "account" else \
           (lambda r: r.is_sales_head or r.id in seen)
    mine = db.query(SalesRep.id).filter(SalesRep.user_id == current_user.id).first()
    return {"items": [{"id": r.id, "name": r.name, "linked": r.user_id is not None,
                       "is_head": r.is_sales_head}
                      for r in rows if keep(r)],
            "mine": mine[0] if mine else None}


@router.get("/deals")
def deals_registry(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    pipeline: Annotated[Optional[List[str]], Query()] = None,
    bitrix_stage: Annotated[Optional[List[str]], Query()] = None,
    our_stage_id: Annotated[Optional[List[int]], Query()] = None,
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
                    bitrix_stage, brand_id, agency_id, product, stage_key, our_stage_id)

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
        # «Период» — ФИНАНСОВЫЙ месяц сделки, и сортируется он по месяцу, а не по дате
        # старта (владелец 15.09.2026). Разница видна внутри одного месяца: по датам
        # сделки, начатые 3-го и 25-го, расходятся, хотя период у них ОДИН и в столбце
        # написано одно и то же. Внутри месяца дальше работает общая вторичная
        # сортировка — по рекламодателю. Даты размещения сортируются отдельными
        # колонками «Старт РК» / «Конец РК» — там дата и есть предмет.
        "period": func.date_trunc("month", SalesDeal.period_from),
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

    # ЗДЕСЬ СТОЯЛ `local_first` — «локальные сделки всегда вверху при ЛЮБОЙ сортировке»,
    # первым ключом ORDER BY. Снято 15.09.2026 по жалобе с прода: список, отсортированный
    # по периоду, шёл 2026-10, 2026-09 … и только потом 2027-09, 2027-05 … То есть
    # таблица распадалась на ДВА независимо отсортированных блока, и человек читал это
    # как «2027 год в середине». На стенде дефект не воспроизводился: там локальных
    # сделок ноль, признак был константой и порядок не менял.
    #
    # Правило простое: человек нажал на колонку — колонка и решает. Служебный признак,
    # стоящий выше выбранного, делает сортировку ложью, а не подсказкой.
    #
    # Локальные при этом не теряются: сортировка по умолчанию — `date_create` по
    # убыванию, а они самые свежие, то есть и так наверху; плюс у них своя метка «→БХ».
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
    rows = (q.order_by(ordering, adv_a.name.asc().nullslast(), SalesDeal.id.desc())
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
    mp_amt = mp_amounts_by_deal(db, page_ids)
    manual = {}
    files_map = {}
    our_mp_map = {}
    annex_map = {}
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
                # Без `status`: колонка заморожена вместе со стейт-машиной МП
                # (30.08.2026) и застыла на `draft` у всех. Карточка сделки его уже не
                # отдаёт — здесь контракт с ней сходится.
                g[p.group_id] = {"id": p.id, "title": p.title, "version": p.version}
        # Приложения к договору — одним запросом на страницу, а не по строке: реестр и
        # карточка обязаны показывать ОДНО состояние ДС, иначе на доске «нет документа»,
        # а в карточке номер, и оба утверждения выглядят правдой.
        from app.sales.models import SalesAnnex, SalesDealAnnexAllocation as _Alloc
        for a, did in (db.query(SalesAnnex, _Alloc.deal_id)
                       .join(_Alloc, _Alloc.annex_id == SalesAnnex.id)
                       .filter(_Alloc.deal_id.in_(page_ids))
                       .order_by(SalesAnnex.no.is_(None).desc(), SalesAnnex.id.desc()).all()):
            annex_map.setdefault(did, []).append(
                {"id": a.id, "no": a.no, "number": a.number, "date": a.date,
                 "is_draft": a.no is None})

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
    # Цвет услуги и документы — общие для реестра и очереди аккаунта, поэтому берутся
    # одним контекстом (app/sales/row_context.py), а не считаются здесь на месте.
    row_ctx = load_row_context(db, page_ids)

    def _row_extra(item, deal):
        return row_ctx.apply(item, deal)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_row_extra({
            "id": d.id,
            "code": d.code,
            "bitrix_id": d.bitrix_id,
            "title": d.title,
            "pipeline": d.pipeline,
            "product": d.product,
            # docs и product_color дописываются ниже из row_ctx (общий контекст строки).
            "probability_color": d.probability_color,
            "period": periods.month_key(d.period_from),
            "bitrix_stage": d.bitrix_stage,
            "money_layer": layer or NO_GROUP,
            "stage_key": stage_key,
            "our_stage": stage_public(cat.by_id.get(d.our_stage_id), cat),
            # Через общую точку: у терминала следующей нет, неприменимые к услуге
            # стадии проскакиваются. Иначе реестр называет одну стадию, а кнопка
            # ведёт в другую.
            "our_next_stage": stage_public(stage_move.next_stage(db, d, cat)),
            "realization_pipeline_id": d.realization_pipeline_id,
            "agency": agencies.get(d.agency_id),
            "agency_full": agency_full.get(d.agency_id),
            "agency_id": d.agency_id,
            "payer_name": d.payer_name,
            # выбранный/дефолтный плательщик и варианты для выпадашки
            "payer": resolve_payer(d),
            "payer_counterparty_id": d.payer_counterparty_id,
            "agency_legals": payer_options(d),
            "amount": eff_net(d, mp_amt),
            "our_sum": round(eff_net(d, mp_amt) * (1 - ((sk_by_agency.get(d.agency_id, default_sk_pct) if d.agency_id else 0) or 0) / 100)),
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
            "annexes": annex_map.get(d.id, []),
            # состояние брифа для иконки: none — ещё не подгружали, empty — пусто,
            # filled — есть текст. Текст брифа тут НЕ отдаём (ленивая подгрузка по клику).
            "brief_state": ("none" if d.brief is None
                            else ("empty" if not (d.brief or "").strip() else "filled")),
            "sync_status": d.sync_status,
            "sync_issues": (d.sync_report or {}).get("issues", []),
            "sync_changes": (d.sync_report or {}).get("changes", []),
            "sync_checked_at": (d.sync_report or {}).get("checked_at"),
        }, d) for d, layer, stage_key in rows],
    }


class DealPatch(BaseModel):
    """Ручная правка полей сделки. Передаются только изменяемые поля.
    Значение None означает «очистить», отсутствие ключа — «не трогать»."""
    advertiser_id: Optional[int] = None
    agency_id: Optional[int] = None
    brand_id: Optional[int] = None
    sales_rep_id: Optional[int] = None
    account_manager_id: Optional[int] = None
    # Наш ответственный за материал. В Битриксе его нет — поэтому он в EDITABLE_OURS_INT,
    # а не в EDITABLE_INT: последний питает очередь заливки, и поле уехало бы в никуда.
    traffic_manager_id: Optional[int] = None
    payer_counterparty_id: Optional[int] = None
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    title: Optional[str] = None
    product: Optional[str] = None
    bitrix_stage: Optional[str] = None
    is_self_promo: Optional[bool] = None


# Поля, доступные ручной правке. Расширять осознанно: каждое попадёт
# в очередь на заливку в Битрикс.
EDITABLE_INT = ("advertiser_id", "agency_id", "brand_id", "sales_rep_id",
                "account_manager_id", "payer_counterparty_id",
                )
# `our_stage_id` в этом списке БЫЛ и убран 13.09.2026: модель запроса `DealPatch` его
# никогда не объявляла, Pydantic отбрасывал поле, и инлайн-правка стадии физически не
# работала — то есть «третий путь записи стадии» существовал только в комментарии.
# Стадию меняют двумя путями: диалог `/deals/{id}/move` и массовая правка. Понадобится
# третий — объявить поле в `DealPatch` И провести через `app/sales/stage_move.py`.
EDITABLE_DATE = ("period_from", "period_to")
EDITABLE_STR = ("product", "bitrix_stage", "title")
# Наши собственные признаки: в Битрикс не заливаются и в очередь заливки не попадают,
# поэтому обрабатываются отдельно от EDITABLE_* и без записи в overrides.
EDITABLE_OURS = ("is_self_promo",)
# Наши числовые поля. Отдельно от EDITABLE_INT: те уезжают в Битрикс, эти — наши и
# остаются здесь. `traffic_manager_id` — ссылка на sales_reps, ответственный за проверку
# материала; по нему распределяется очередь трафика (app/routers/traffic.py).
EDITABLE_OURS_INT = ("traffic_manager_id",)
# Наши строковые поля. Список пуст, но заведён намеренно: EDITABLE_OURS приводит значение
# к bool, и первое же строковое поле, попавшее туда по невнимательности, молча стало бы
# True. Посадочная страница жила здесь один день и уехала на получателя — грань оказалась
# «сделка × площадка» (миграция 2026-08-27_target_landing_urls.sql).
EDITABLE_OURS_STR = ()


def _is_account_master(user) -> bool:
    """Админ или мастер АККАУНТОВ — не мастер вообще.

    Понятие заведено под снятие статуса «самореклама» (26.08.2026) и с 14.09.2026
    держит второе правило того же рода: снятие доп. параметра РК «нужен пиксель».
    Обе отмены делает один и тот же человек, и два предиката на одно понятие разошлись
    бы при первой же правке.

    Правило владельца 26.08.2026, и оно уже раз было понято шире. `Role.is_master` —
    один флаг на две рабочие группы: мастер стоит и у «Мастер Сейлз», и у «Мастер
    аккаунт». Проверять только его — значит отдать снятие ещё и продажам, а признак
    отвечает за маркировку, то есть за зону аккаунтов. Отсюда пара is_master +
    staff_group, а не один флаг, как у движения сделки назад.
    """
    role = getattr(user, "role", None)
    if role is None:
        return False
    if role.key == "admin":
        return True
    return (bool(getattr(role, "is_master", False))
            and getattr(role, "staff_group", None) == "account")


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
    # Пока распределения по трафикам нет, его роль исполняет массовая правка: выбрали
    # сделки — назначили ответственного.
    traffic_manager_id: Optional[int] = None
    product: Optional[str] = None
    # bitrix_stage оставлен для совместимости, но интерфейс им больше не пользуется:
    # это поле мастера-Битрикса, и запись в него из реестра однажды уже утащила
    # в базу составной ключ фильтра («воронка\x1fстадия»), наплодив стадии-двойники.
    bitrix_stage: Optional[str] = None
    # НАША стадия: массовый перевод по каталогу. Идёт через ту же точку, что диалог
    # (`app/sales/stage_move.py`), — с проверкой требований и записью истории.
    our_stage_id: Optional[int] = None
    # Причина обхода требований. Только мастеру и только при массовом переводе стадии:
    # без неё запертые сделки просто пропускаются.
    override_reason: Optional[str] = None
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
    stale_end_ids: list = []
    if "period" in changes:
        pv = (changes.pop("period") or "").strip()
        if pv:
            if not _PERIOD_RE.match(pv):
                raise HTTPException(status_code=400, detail="Период должен быть ГГГГ-ММ")
            updates[SalesDeal.period_from] = date(int(pv[:4]), int(pv[5:7]), 1)
            changes["period_from"] = updates[SalesDeal.period_from]
            # Те из выбранных, у кого прежний конец остаётся ПОЗАДИ нового старта. Их
            # конец снимаем — то же правило, что у поштучной правки (patch_deal), и по
            # той же причине: конец РК в интерфейсе не редактируется, а протухшая дата
            # прячет сделку от отбора по периоду. Список считаем ДО обновления: после
            # него прежнего значения уже не спросить.
            stale_end_ids = [
                d.id for d in db.query(SalesDeal)
                .filter(SalesDeal.id.in_(payload.deal_ids)).all()
                if periods.end_is_stale(updates[SalesDeal.period_from], d.period_to)]
    for f in ("advertiser_id", "agency_id", "sales_rep_id", "account_manager_id",
              "traffic_manager_id", "product", "bitrix_stage"):
        if f in changes:
            updates[getattr(SalesDeal, f)] = changes[f]

    # Массовый перевод по НАШЕЙ лестнице — через ту же точку, что и диалог
    # (`app/sales/stage_move.py`). До 13.09.2026 он писал стадию напрямую и требований не
    # спрашивал: «инструмент разбора накопленного, а не движение по конвейеру». Пока
    # требований не было, разница была незаметна; с их появлением этот путь стал тихим
    # обходом гейта, доступным именно админу, — а значит гейт превратился бы в
    # декорацию.
    #
    # Запертые сделки ПРОПУСКАЮТСЯ, а не роняют всю пачку: отказать в двадцати сделках
    # из-за одной значит заставить человека искать её вручную. В ответ уходит, сколько
    # переведено и сколько не пустило, с именами первых.
    # ДВИЖЕНИЕ НАЗАД ЗДЕСЬ РАЗРЕШЕНО ВСЕМ, И ЭТО СОЗНАТЕЛЬНО (владелец 13.09.2026).
    #
    # Диалог `/deals/{id}/move` отдаёт немастеру 403 на признаке «движение назад», а
    # массовая правка этот признак не смотрит вовсе. Расхождение выглядит дырой и однажды уже было
    # поднято проверкой безопасности — поэтому записано здесь, а не держится в голове:
    # массовая правка это ИНСТРУМЕНТ РАЗБОРА накопленного, а не движение по конвейеру.
    # Ею чинят чужие ошибки и раскладывают подгруженные сделки; требовать на это мастера
    # значит сделать разбор невозможным для тех, кто им занимается.
    #
    # Что ограничение всё-таки держит: область видимости (`_scope_deal_ids` выше — чужую
    # сделку не тронуть) и ТРЕБОВАНИЯ цели (`plan.blockers` ниже). Обходит требования
    # только мастер и только с причиной.
    #
    # Асимметрия закреплена прибором `test_bulk_allows_going_back_on_purpose`: если
    # кто-то «починит» её, не спросив, тест объяснит, почему так.
    moved = 0
    skipped: list = []
    target_id_used = bool(changes.get("our_stage_id"))
    if changes.get("our_stage_id"):
        target_id = int(changes["our_stage_id"])
        target = db.query(SalesStage).filter(SalesStage.id == target_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="Стадия не найдена")
        cat = Catalog(db)
        master = stage_move.is_master(current_user)
        force = master and bool((payload.override_reason or "").strip())
        reason = (payload.override_reason or "").strip() or "массовая правка стадии"
        for d in db.query(SalesDeal).filter(SalesDeal.id.in_(payload.deal_ids)).all():
            if d.our_stage_id == target_id:
                continue
            plan = stage_move.plan_move(db, deal=d, target=target, catalog=cat)
            if plan.blockers and not force:
                # Не просто «не прошла», а ЧТО именно не выполнено и где чинится —
                # иначе человек получает список кодов и идёт открывать их по одному.
                skipped.append({
                    "code": d.code or str(d.id),
                    "title": d.title,
                    "lines": [_line_public(ln) for ln in plan.blockers],
                })
                continue
            if stage_move.apply_move(db, d, target, current_user, catalog=cat,
                                     force=force and bool(plan.blockers),
                                     reason=reason)["moved"]:
                moved += 1
        # Стадию из общего обновления УБИРАЕМ: она уже проставлена поштучно теми, кого
        # пустило. Оставить её здесь значило бы двинуть и пропущенных — тем самым
        # обходом, который мы только что закрыли.
        changes.pop("our_stage_id", None)
        updates.pop(SalesDeal.our_stage_id, None)

    if updates:
        db.query(SalesDeal).filter(SalesDeal.id.in_(payload.deal_ids)).update(
            updates, synchronize_session=False)
    if stale_end_ids:
        db.query(SalesDeal).filter(SalesDeal.id.in_(stale_end_ids)).update(
            {SalesDeal.period_to: None}, synchronize_session=False)

    # помечаем как ручные правки (защита от синхронизации)
    existing = {(o.deal_id, o.field_name): o for o in db.query(SalesDealFieldOverride)
                .filter(SalesDealFieldOverride.deal_id.in_(payload.deal_ids)).all()}
    for did in stale_end_ids:
        # Снятый конец — тоже ручная правка: без пометки ближайшая сверка вернула бы
        # прошлогоднюю дату из Битрикса, и сделка снова выпала бы из отбора.
        row = existing.get((did, "period_to"))
        if row is None:
            row = SalesDealFieldOverride(deal_id=did, field_name="period_to")
            db.add(row)
            existing[(did, "period_to")] = row
        row.value_int = None
        row.value_text = None
        row.set_by = current_user.id if current_user else None
        row.set_at = datetime.utcnow()
        row.pushed_at = None
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
    label = f"{len(payload.deal_ids)} сделок: {', '.join(changes.keys()) or 'стадия'}"
    if moved:
        label += f"; переведено {moved}"
    if skipped:
        label += f"; не пустили требования: {len(skipped)}"
    log_action(db, current_user, "bulk_update_deals", "sales_deal", None, label)
    # Число ЧЕСТНОЕ: до 13.09.2026 в ответ шла длина входного списка, и человек читал
    # «Обновлено сделок: 20» рядом со списком из тринадцати непереведённых. Обе фразы
    # правдивы по отдельности, вместе бессмысленны.
    msg = (f"Полей обновлено у сделок: {len(payload.deal_ids)}" if changes
           else f"Обработано сделок: {len(payload.deal_ids)}")
    if target_id_used:
        msg += f". Переведено на новую стадию: {moved}"
    if skipped:
        # Называем поимённо: «часть не прошла» без списка означает искать вручную.
        codes = [x["code"] for x in skipped]
        head = ", ".join(codes[:5]) + (f" и ещё {len(codes) - 5}" if len(codes) > 5 else "")
        msg += f". Не переведены — не выполнены требования: {head}"
    return {"message": msg, "moved": moved, "skipped": skipped}


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


class TrafficBriefIn(BaseModel):
    traffic_brief: str


@router.put("/deals/{deal_id}/traffic-brief")
def save_deal_traffic_brief(deal_id: int, payload: TrafficBriefIn, db: Session = Depends(get_db),
                            current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """«Цели и особенности РК»: аккаунт пишет, трафик читает (владелец 05.09.2026).

    В Битрикс НЕ уходит, в отличие от соседнего брифа: это передача задачи внутри
    команды, и клиентская карточка о ней знать не должна. Отсюда и отдельная ручка —
    у `save_deal_brief` половина тела про Битрикс, и общий код означал бы риск однажды
    отправить туда внутренний текст.

    Длину ограничиваем: поле свободное, и без потолка сюда однажды вставят весь бриф
    целиком вместе с медиапланом.
    """
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    text_val = (payload.traffic_brief or "").strip()
    if len(text_val) > 8000:
        raise HTTPException(status_code=400, detail="Слишком длинный текст: максимум 8000 символов")
    was = len(deal.traffic_brief or "")
    deal.traffic_brief = text_val
    db.commit()
    log_action(db, current_user, "save_deal_traffic_brief", "sales_deal", deal.id,
               f"цели и особенности РК: {was} → {len(text_val)} симв.")
    return {"traffic_brief": deal.traffic_brief}


class CampaignExtraIn(BaseModel):
    weborama_pixel: bool
    # own — заводим вставку и забираем пиксель сами; external — тег принесли готовым.
    mode: Optional[str] = None
    tag: Optional[str] = None
    insertion: Optional[str] = None


@router.put("/deals/{deal_id}/campaign-extra")
def save_deal_campaign_extra(deal_id: int, payload: CampaignExtraIn,
                             db: Session = Depends(get_db),
                             current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Доп. параметры РК. Пока один: нужен ли пиксель Weborama (владелец 14.09.2026).

    ВКЛЮЧЕНИЕ НЕОБРАТИМО ДЛЯ ОБЫЧНОГО АККАУНТА. Причина не в бюрократии: включение
    поднимает требование пикселя в выгрузке в DSP и рождает задачу трафику. Снятая
    задним числом галочка означала бы, что трафик получил указание, сделал работу во
    внешней системе — и следа о том, зачем, не осталось. Снять может мастер аккаунта
    или админ — тем же предикатом `_is_account_master`, что снимает «саморекламу»:
    отмену в зоне аккаунтов делает один и тот же человек, и второе понятие про то же
    самое разошлось бы с первым при первой правке.

    Повторное включение уже включённого — не ошибка и не событие: ничего не меняется,
    уведомление не рождается, в журнал не пишем. Иначе двойное нажатие кнопки в
    интерфейсе выглядело бы как две разные задачи трафику.
    """
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)

    was = bool(deal.weborama_pixel)
    want = bool(payload.weborama_pixel)
    if was and not want and not _is_account_master(current_user):
        raise HTTPException(
            status_code=403,
            detail="Снять требование пикселя может только мастер аккаунта или админ: "
                   "трафик уже получил задачу")

    mode = (payload.mode or deal.weborama_pixel_mode or "own").strip().lower()
    if mode not in ("own", "external"):
        raise HTTPException(status_code=400, detail="Способ бывает own или external")

    tag = None
    if want and mode == "external":
        from app.weborama.naming import check_external_pixel
        try:
            tag = check_external_pixel(payload.tag or deal.weborama_pixel_tag)
        except ValueError as e:
            # Причина — текстом наружу: человек вставляет тег из чужой таблицы, и
            # «неверный формат» заставит его перебирать столбцы наугад.
            raise HTTPException(status_code=400, detail=str(e))
    ins = ((payload.insertion or "").strip() or None) if payload.insertion is not None         else deal.weborama_ext_insertion

    # Проверка «ничего не изменилось» идёт ПОСЛЕ разбора тела, а не до него. Сперва было
    # наоборот, и замер 14.09.2026 показал, чем это кончается: у сделки с уже включённым
    # признаком ручка выходила на первой строке — то есть заведомо кривой тег принимался
    # молча, а исправить опечатку в уже загруженном теге было нечем вовсе.
    setup_changed = want and (mode != (deal.weborama_pixel_mode or "own")
                              or tag != deal.weborama_pixel_tag
                              or ins != deal.weborama_ext_insertion)
    # ВЫБОР ЗАСЧИТЫВАЕТСЯ ДАЖЕ ТОГДА, КОГДА НИЧЕГО НЕ ИЗМЕНИЛОСЬ. «Не надо» по сделке,
    # где флаг и так false, не меняет ни одного поля — но это РЕШЕНИЕ человека, и без
    # отметки блок остался бы развёрнутым навсегда, а нажатие выглядело бы как
    # проигнорированное (владелец 18.09.2026).
    deal.weborama_pixel_decided_at = datetime.utcnow()
    if was == want and not setup_changed:
        db.commit()
        return _campaign_extra_out(deal)

    deal.weborama_pixel = want
    if want:
        if was != want:
            deal.weborama_pixel_at = datetime.utcnow()
        deal.weborama_pixel_mode = mode
        # Тег и вставка хранятся только у внешнего. Переключение external → own их
        # ЧИСТИТ: оставленный тег однажды вшился бы в креатив по кампании, которая давно
        # считается своим пикселем, и расхождение искали бы в цифрах, а не в настройке.
        deal.weborama_pixel_tag = tag if mode == "external" else None
        deal.weborama_ext_insertion = ins if mode == "external" else None
    db.commit()

    if want and was != want:
        # Событие трафику — «нужен пиксель». Рождается ТОЛЬКО на включении: это переход,
        # а не состояние, и повтор при каждом сохранении карточки превратил бы его в шум.
        #
        # ОТДЕЛЬНОЙ транзакцией, ПОСЛЕ сохранения параметра. Уведомление — следствие, а
        # не часть решения: сорвавшаяся рассылка не должна означать, что галочка не
        # поставилась. Человек в этом случае видит успех, а молчание разбирается по логу.
        try:
            from app.notify.bus import emit
            emit(db, "weborama_pixel_needed", entity_type="deal", entity_id=deal.id,
                 title=f"{deal_label(deal)}: нужен пиксель Weborama",
                 link="/traffic/dashboard", actor=current_user, ctx={"deal": deal})
            db.commit()
        except Exception as e:                      # noqa: BLE001
            db.rollback()
            print(f"weborama_pixel_needed: уведомление не ушло — {type(e).__name__}: {e}")

    if not want:
        what = "требование пикселя снято"
    elif was != want:
        what = ("пиксель Weborama требуется, "
                + ("внешний тег" if mode == "external" else "получаем сами"))
    else:
        what = "правка настройки пикселя: " + ("внешний тег" if mode == "external"
                                               else "получаем сами")
    log_action(db, current_user, "deal_weborama_pixel", "sales_deal", deal.id, what)
    return _campaign_extra_out(deal)


def _campaign_extra_out(deal) -> dict:
    return {"weborama_pixel": bool(deal.weborama_pixel),
            "weborama_pixel_at": deal.weborama_pixel_at.isoformat()
            if deal.weborama_pixel_at else None,
            "weborama_pixel_decided": deal.weborama_pixel_decided_at is not None,
            "weborama_pixel_mode": deal.weborama_pixel_mode or "own",
            "weborama_pixel_tag": deal.weborama_pixel_tag,
            "weborama_ext_insertion": deal.weborama_ext_insertion}


class VerifierShowsIn(BaseModel):
    shows: Optional[int] = None
    period_to: Optional[date] = None


@router.put("/deals/{deal_id}/verifier-shows")
def save_verifier_shows(deal_id: str, payload: VerifierShowsIn,
                        db: Session = Depends(get_db),
                        current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Показы по данным Weborama, введённые руками. Только для ВНЕШНЕГО пикселя.

    Зачем ручной ввод вообще. У внешнего пикселя вставка одна на всю сеть, заводил её
    клиент, и в нашем реестре соответствий её нет — тянуть статистику неоткуда. Их отчёт
    приходит файлом: показы за период, одним числом, без кликов («ImpOnly»). Решение
    владельца 14.09.2026: вводим руками на сверке.

    ИСТОЧНИК ОТДЕЛЬНЫЙ (`weborama_manual`), хотя складывается он так же, как снятый через
    API. Разница не в арифметике, а в доверии: одно измерено, другое перепечатано
    человеком с чужого файла, и на экране они выглядят одинаково. Различить их потом
    можно будет только по источнику.

    В ФАКТ не входит никогда — как и любой верификатор (`app/ad/stat_sources.py`).

    Одна строка на кампанию, без площадки: разбивки в их отчёте нет, и раскладывать одно
    число по девятнадцати площадкам значило бы выдумать данные. Дата — конец периода, за
    который отчитались; она не рисует ни один график, потому что верификатор в графики не
    идёт, и нужна только чтобы строка была одна на период.

    Пустое значение СТИРАЕТ строку: ошиблись при вводе — надо иметь чем убрать, иначе
    неверное число останется в сверке навсегда.
    """
    from app.ad.models import AdCampaign

    deal = _deal_by_ref(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    if not (deal.weborama_pixel and (deal.weborama_pixel_mode or "own") == "external"):
        raise HTTPException(
            status_code=400,
            detail="Ручной ввод — только для внешнего пикселя: по своему цифры "
                   "снимаются автоматически")
    c = db.query(AdCampaign).filter(AdCampaign.deal_id == deal.id).first()
    if not c:
        raise HTTPException(status_code=400, detail="РК ещё не собрана")

    when = payload.period_to or c.date_end or date.today()
    if payload.shows is None:
        db.execute(text("DELETE FROM ad_campaign_stat WHERE campaign_id = :c "
                        "AND placement_id IS NULL AND source = 'weborama_manual'"),
                   {"c": c.id})
        db.commit()
        log_action(db, current_user, "deal_verifier_shows", "sales_deal", deal.id,
                   "ручные показы Weborama удалены")
        return {"shows": None, "period_to": None}
    if payload.shows < 0:
        raise HTTPException(status_code=400, detail="Показы не бывают отрицательными")

    # Одна строка на кампанию: прежнюю убираем целиком, а не апсертим по дате — иначе
    # исправленный период оставил бы рядом старое число, и в сверку пошла бы их сумма.
    db.execute(text("DELETE FROM ad_campaign_stat WHERE campaign_id = :c "
                    "AND placement_id IS NULL AND source = 'weborama_manual'"),
               {"c": c.id})
    db.execute(text(
        "INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks,"
        " source) VALUES (:c, NULL, :d, :s, 0, 'weborama_manual')"),
        {"c": c.id, "d": when, "s": int(payload.shows)})
    db.commit()
    log_action(db, current_user, "deal_verifier_shows", "sales_deal", deal.id,
               f"ручные показы Weborama: {payload.shows} на {when}")
    return {"shows": int(payload.shows), "period_to": when.isoformat()}


@router.get("/deals/{deal_id}/campaign")
def deal_campaign(deal_id: str, db: Session = Depends(get_db),
                  current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Сводка рекламной кампании сделки — для блока «Рекламная кампания» на карточке и,
    тем же ответом, для предварительной сверки (владелец 05.09.2026).

    Ничего не считает сама: и флайт, и распределение по площадкам, и цели берутся у тех
    же функций, что рисуют дашборд трафика. Второй расчёт того же недокрута разошёлся бы
    с первым при первой правке порогов — как уже было со статусом площадки.

    Право — реестра сделок, а не дашборда трафика: смотрит АККАУНТ на своей карточке.
    Область видимости сделки проверяется, как во всех ручках, трогающих сделку.

    `has` = false означает «показывать блок нечего»: РК ещё не собрана или по ней нет ни
    одного замера. Блок появляется, когда пошла статистика, — раньше в нём одни прочерки.
    """
    from app.ad import build as ad_build
    from app.ad.flight import (PLACEMENT_RUNNING, best_chain_status, distribute,
                               effective_campaign_status, flight_of, progress)
    from app.ad.stat_sources import mismatch_pct
    from app.ad.models import AdCampaign
    from app.routers import traffic_dashboard as td

    deal = _deal_by_ref(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)

    c = db.query(AdCampaign).filter(AdCampaign.deal_id == deal.id).first()
    if not c:
        return {"has": False, "reason": "РК ещё не собрана"}

    facts = td._facts(db, [c.id]).get(c.id, {})
    fact_shows = facts.get("shows")
    if fact_shows is None:
        return {"has": False, "reason": "Статистика ещё не пришла"}

    today = date.today()
    fl = flight_of(c.date_start, c.date_end, today)
    pls = td._placements_of(db, [c.id]).get(c.id, [])
    by_pl = td._creatives_all(db, [c.id]).get(c.id, {})
    for p_ in pls:
        p_["status"] = td.effective_status(p_["status"], best_chain_status(
            td._as_placement_scale(x) for x in by_pl.get(p_["id"], [])))
    rows = distribute(c.plan_show, fact_shows, fl, pls)["rows"]
    fc = progress(c.plan_show, fact_shows, c.date_start, c.date_end, today)

    by_day = td._stat_by_day(db, [c.id]).get(c.id, {})
    all_clicks = sum(v[1] or 0 for v in by_day.values())

    # Верификатор — ОТДЕЛЬНОЙ величиной, рядом с фактом и никогда внутри него
    # (решение владельца 10.09.2026). Расхождение считает общая функция, а не экран:
    # тот же вопрос задаёт дашборд трафика, и два счёта разошлись бы знаком или
    # знаменателем — ошибка, которую видно только при сверке с площадкой.
    # Как устроен пиксель — экрану нужно, чтобы отличить «Weborama не измеряла» от
    # «внешний тег: цифры вносятся руками». Для человека это разные состояния: первое
    # ждёт данных само, второе ждёт ЕГО.
    px = ad_build.pixel_setup(db, deal.id)
    manual = db.execute(text(
        "SELECT shows, date FROM ad_campaign_stat WHERE campaign_id = :c "
        "AND placement_id IS NULL AND source = 'weborama_manual'"), {"c": c.id}).first()

    ver = td._verifier(db, [c.id]).get(c.id) or {}
    ver_by_pl = ver.get("by_placement", {})
    ver_shows = ver.get("shows")

    # СРАВНИВАЕМ СОПОСТАВИМОЕ. Верификатор покрывает не все площадки: соответствие
    # «их вставка → наша площадка» появляется только у тех, что заводили мы, и на
    # 14.09.2026 таких нет вовсе. Если делить их сумму на НАШ факт по всей РК, число
    # получается арифметически верным и по смыслу ложным: замер 14.09 дал «расхождение
    # 77 %» там, где по единственной покрытой площадке оно было 10 %, а остальные
    # восемнадцать просто не измерялись. Такое число на карточке читается как «половина
    # показов не засчитана» и ведёт разбираться не туда.
    #
    # Поэтому итог считается по ПОКРЫТЫМ площадкам, а рядом отдаётся охват — сколько из
    # скольких. Строки верификатора без площадки (замер по РК целиком) сопоставлять
    # не с чем по частям, и тогда сравнение идёт по всей РК.
    covered = [r for r in rows if r.get("id") in ver_by_pl]
    if covered:
        own_cmp = sum(r.get("fact_shows") or 0 for r in covered)
        ver_cmp = sum(ver_by_pl[r["id"]] for r in covered)
    else:
        own_cmp, ver_cmp = fact_shows, ver_shows

    return {
        "has": True,
        "campaign_id": c.id,
        "status": effective_campaign_status(c.status, None) if c.status else None,
        "date_start": c.date_start, "date_end": c.date_end,
        "plan_show": c.plan_show, "fact_shows": fact_shows, "fact_clicks": all_clicks,
        "ctr": round(all_clicks / fact_shows * 100, 2) if fact_shows else None,
        # Деньги — аккаунту они нужнее показов (владелец 05.09.2026). План берём из
        # медиаплана, факт СЧИТАЕМ ПО ТОЙ ЖЕ ЦЕНЕ: открученные показы по CPM плана.
        # Это оценка, а не выставленная сумма: настоящая цена закрытия определится на
        # сверке, и подменять её здесь нельзя. Экран так и подписывает — «по цене плана».
        "plan_budget": c.plan_budget,
        "fact_budget": (round(fact_shows / c.plan_show * c.plan_budget)
                        if (c.plan_budget and c.plan_show) else None),
        "placements": len(pls),
        "placements_on": sum(1 for p_ in pls if p_["status"] in PLACEMENT_RUNNING),
        # Цели приёмки — из ТОГО ЖЕ медиаплана, что дал план показов.
        "goals": ad_build.deal_goals(db, deal.id),
        # Факт верификатора и расхождение с нашим счётчиком. None означает «сравнивать
        # нечем» — реестр соответствий «их вставка → наша площадка» может быть пуст, и
        # тогда честный ответ прочерк, а не ноль: «сошлось» и «не с чем сверять» —
        # разные утверждения, и ноль подменил бы второе первым.
        "verifier_shows": ver_shows,
        "mismatch_pct": mismatch_pct(own_cmp, ver_cmp),
        # Охват верификатора: без него процент выглядит приговором всей РК, хотя
        # посчитан по части площадок. Экран подписывает «по N из M».
        "verifier_placements": len(covered),
        "pixel_mode": px["mode"] if px["needed"] else None,
        "verifier_manual": ({"shows": manual[0], "period_to": manual[1].isoformat()}
                            if manual else None),
        # Строки площадок — для отчёта в модалке: доля, план, факт, недокрут.
        # Строки площадок — для расхлопа: доля, план, факт, недокрут и та же пара
        # «верификатор / расхождение», что в шапке. Считается тем же выражением —
        # иначе итог и расхлоп однажды разойдутся, и правым окажется неизвестно кто.
        "rows": [{**{k: r.get(k) for k in ("id", "domain", "code", "status", "weight",
                                           "share", "plan_show", "fact_shows", "under",
                                           "done_pct")},
                  "verifier_shows": ver_by_pl.get(r.get("id")),
                  "mismatch_pct": mismatch_pct(r.get("fact_shows"),
                                               ver_by_pl.get(r.get("id")))}
                 for r in rows],
        **fc,
    }


@router.get("/deals/{deal_id}/campaign/stat")
def deal_campaign_stat(deal_id: str, grain: str = "day",
                       db: Session = Depends(get_db),
                       current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Динамика показов РК сделки — та же, что в кабинете трафика, тем же ядром.

    Отдельной ручкой от сводки, как и в дашборде: гранулярность переключают часто, и
    тянуть ради этого площадки с долями заново незачем.
    """
    from app.ad.flight import GRAIN_DAYS, daily_buckets, flight_of
    from app.ad.models import AdCampaign
    from app.routers import traffic_dashboard as td

    if grain not in GRAIN_DAYS:
        raise HTTPException(status_code=400, detail=f"Гранулярность бывает {tuple(GRAIN_DAYS)}")
    deal = _deal_by_ref(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    c = db.query(AdCampaign).filter(AdCampaign.deal_id == deal.id).first()
    if not c:
        return {"buckets": [], "grain": grain, "totals": None}

    by_day = td._stat_by_day(db, [c.id]).get(c.id, {})
    fact = td._facts(db, [c.id]).get(c.id, {}).get("shows")
    out = daily_buckets(c.plan_show, fact, flight_of(c.date_start, c.date_end), by_day,
                        grain=grain)
    if out is None:
        return {"buckets": [], "grain": grain, "totals": None}
    today = date.today()
    t_shows, t_clicks = by_day.get(today, (0, 0))
    all_shows = sum(v[0] or 0 for v in by_day.values())
    all_clicks = sum(v[1] or 0 for v in by_day.values())
    out["totals"] = {
        "today": {"shows": t_shows, "clicks": t_clicks,
                  "ctr": round(t_clicks / t_shows * 100, 2) if t_shows else None},
        "period": {"shows": all_shows, "clicks": all_clicks,
                   "ctr": round(all_clicks / all_shows * 100, 2) if all_shows else None},
    }
    return out


class CommentIn(BaseModel):
    text: str


def _comment_out(row, who: dict) -> dict:
    return {"id": row.id, "text": row.text, "user_id": row.user_id,
            "author": who.get(row.user_id) or "—",
            "at": row.created_at.isoformat() if row.created_at else None}


@router.get("/deals/{deal_id}/comments")
def list_deal_comments(deal_id: str, db: Session = Depends(get_db),
                       current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Лента комментариев сделки, свежие сверху.

    Отдельно от истории (владелец 05.09.2026): история — системные события из журнала,
    комментарий — то, что человек сказал сам. В одном потоке фильтр «только
    комментарии» становится обязательным, а нужен он всегда.

    Имена авторов подтягиваются ОДНИМ запросом: лента на сотню записей иначе даёт сотню
    обращений к `users` — та же готча, что с площадками в дашборде трафика.
    """
    from app.sales.models import SalesDealComment

    deal = _deal_by_ref(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    rows = (db.query(SalesDealComment)
            .filter(SalesDealComment.deal_id == deal.id)
            .order_by(SalesDealComment.created_at.desc(), SalesDealComment.id.desc())
            .limit(200).all())
    who = {}
    if rows:
        uids = {r.user_id for r in rows}
        who = {u.id: _short_fio(u.name or u.email)
               for u in db.query(User).filter(User.id.in_(uids)).all()}
    return {"items": [_comment_out(r, who) for r in rows]}


@router.post("/deals/{deal_id}/comments")
def add_deal_comment(deal_id: str, payload: CommentIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_permission("sales_registry", "edit"))):
    """Добавить комментарий. Права — общие правила сделки, без своей секции: пишет тот,
    кто и так правит эту сделку (владелец 05.09.2026). Трафик карточку читает, а пишет
    только если право у него есть.

    Пустой комментарий не заводим: строка без текста в ленте — мусор, который потом
    нельзя удалить.
    """
    from app.sales.models import SalesDealComment

    deal = _deal_by_ref(db, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)
    text_val = (payload.text or "").strip()
    if not text_val:
        raise HTTPException(status_code=400, detail="Пустой комментарий")
    if len(text_val) > 4000:
        raise HTTPException(status_code=400, detail="Слишком длинный комментарий: максимум 4000 символов")
    row = SalesDealComment(deal_id=deal.id, user_id=current_user.id, text=text_val)
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "add_deal_comment", "sales_deal", deal.id,
               text_val[:80] + ("…" if len(text_val) > 80 else ""))
    who = {current_user.id: _short_fio(current_user.name or current_user.email)}
    return _comment_out(row, who)


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
    # Путь из базы — через общую проверку границы хранилища (`app/files_safe`).
    # До 11.09.2026 она была ровно в одном месте из десяти.
    abspath = existing_upload_path(rec.path)
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
        # Условие «путь другой» обязательно: совпал — файл уже перезаписан по тому же
        # адресу, и удаление стёрло бы только что загруженное.
        if rec.path and rec.path != rel:
            remove_upload(rec.path)
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
    remove_upload(rec.path)
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
    "self_promo_on": "Присвоена самореклама",
    "self_promo_off": "Снята самореклама",
    "ord_bind_initial": "Привязан изначальный договор",
    "ord_bind_initial_forced": "Изначальный привязан вне связей ОРД",
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


def _own_company_out(db) -> Optional[dict]:
    """Наше юрлицо для карточки сделки. Правило — общее, см. app/own_company.py."""
    return own_company.public(db)


@router.get("/own-company")
def get_own_company(db: Session = Depends(get_db),
                    current_user: User = Depends(require_permission("sales_registry", "view"))):
    """Юрлицо, от которого оказываем услуги, и его ставка НДС.

    Отдельной точкой, потому что читателей уже двое: карточка сделки получает
    юрлицо вместе со сделкой, а конструктор медиаплана сделки может не иметь
    вовсе — новый МП заводится и без привязки.
    """
    return _own_company_out(db)


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


def _deal_annexes(db: Session, deal_id: int) -> list:
    """Приложения сделки — через таблицу разнесения сумм: одно приложение может закрывать
    несколько сделок, поэтому связь идёт не полем, а строкой разнесения."""
    from app.sales.models import SalesAnnex, SalesDealAnnexAllocation as Alloc
    rows = (db.query(SalesAnnex, Alloc.amount)
            .join(Alloc, Alloc.annex_id == SalesAnnex.id)
            .filter(Alloc.deal_id == deal_id)
            .order_by(SalesAnnex.no.is_(None).desc(), SalesAnnex.id.desc()).all())
    return [{"id": a.id, "no": a.no, "number": a.number, "date": a.date,
             "amount": amt, "is_draft": a.no is None} for a, amt in rows]


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
    traf = db.query(SalesRep).filter(SalesRep.id == deal.traffic_manager_id).first() if deal.traffic_manager_id else None
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
            # Статуса у плана нет с 30.08.2026 — его состояние это стадия сделки,
            # которая тут же, в этой же карточке.
            our_mps[mp.group_id] = {"id": mp.id, "title": mp.title, "version": mp.version,
                                    "updated_at": mp.updated_at}
    cat = Catalog(db)
    _mp_amt = mp_amounts_by_deal(db, [deal.id])
    _card_ctx = load_row_context(db, [deal.id])
    return {
        "id": deal.id, "code": deal.code, "bitrix_id": deal.bitrix_id, "title": deal.title,
        "advertiser": (adv.short_name or adv.name) if adv else None, "advertiser_id": deal.advertiser_id,
        "brand": brand.name if brand else None,
        "agency": (agc.short_name or agc.name) if agc else None, "agency_id": deal.agency_id,
        "product": deal.product,
        # Поверхность услуги (web/app) и гео — тем же контекстом, что в реестре и
        # очереди: второе выражение здесь разъехалось бы с ними при первой же правке.
        # Гео у сделки своего нет, оно читается из шапки её медиаплана; до 15.09.2026
        # карточка рисовала на этом месте зашитый прочерк.
        "inventory": _card_ctx.inventory(deal.id, deal.product),
        "geo": _card_ctx.geo(deal.id),
        "payer": payer, "payer_counterparty_id": deal.payer_counterparty_id,
        "counterparty_id": deal.payer_counterparty_id or deal.counterparty_id,
        "period": periods.month_key(deal.period_from),
        "period_from": deal.period_from, "period_to": deal.period_to,
        "bitrix_stage": deal.bitrix_stage,
        "sales_rep": _short_fio(rep.name) if rep else None,
        "account_manager": _short_fio(acc.name) if acc else None,
        "traffic_manager": _short_fio(traf.name) if traf else None,
        # Учётка за профилем — карточка назначает трафика по НЕЙ (app/sales/reps.py),
        # а не по строке справочника: у трафиков её может ещё не быть.
        "traffic_manager_user_id": traf.user_id if traf else None,
        # «Цели и особенности РК» едут вместе с карточкой, а не отдельным запросом:
        # это не ленивый бриф из Битрикса, а наше поле, и второй заход за строчкой
        # текста добавил бы экрану состояние загрузки на пустом месте.
        "traffic_brief": deal.traffic_brief or "",
        # Доп. параметры РК (миграция 2026-09-14). Пока один.
        "weborama_pixel": bool(deal.weborama_pixel),
        "weborama_pixel_at": deal.weborama_pixel_at.isoformat()
        if deal.weborama_pixel_at else None,
        "weborama_pixel_decided": deal.weborama_pixel_decided_at is not None,
        "weborama_pixel_mode": deal.weborama_pixel_mode or "own",
        "weborama_pixel_tag": deal.weborama_pixel_tag,
        "weborama_ext_insertion": deal.weborama_ext_insertion,
        # Замок рисуется сразу, а не узнаётся из 403 после клика — как у саморекламы.
        "can_unset_weborama_pixel": _is_account_master(current_user),
        # Признак саморекламы: меняет правила маркировки в ОРД, поэтому виден на карточке
        # рядом со стадией, а не спрятан в форме правки.
        "is_self_promo": bool(deal.is_self_promo),
        # Снять признак может только мастер аккаунт: отдаём это карточке, чтобы она
        # рисовала замок сразу, а не узнавала о запрете из 403 после клика.
        "can_unset_self_promo": _is_account_master(current_user),
        # Суммы из нашего МП, если он привязан и посчитан (иначе — из сделки).
        "amount": eff_net(deal, _mp_amt),
        "amount_with_vat": (eff_gross(deal, _mp_amt) if deal.id in _mp_amt
                            else (deal.amount_with_vat if deal.amount_with_vat is not None
                                  else (round(float(deal.amount) * (1 + SALES_VAT_RATE), 2)
                                        if deal.amount is not None else None))),
        "our_sum": round(eff_net(deal, _mp_amt) * (1 - (sk_pct or 0) / 100)),
        "currency": deal.currency, "files": files, "date_create": deal.date_create,
        "plan_month": deal.plan_month, "year_plan_line_id": deal.year_plan_line_id,
        "year_plan": _year_plan_of_deal(db, deal),
        # Ставка НДС по нашим услугам — от нашего юрлица, не из константы во фронте.
        "own_company": _own_company_out(db),
        # для бара стадий и диалога движения — тот же контракт, что в реестре
        "our_stage": stage_public(cat.by_id.get(deal.our_stage_id), cat),
        # Следующая стадия — с учётом применимости к услуге сделки: неприменимые
        # проскакиваются, и кнопка «двинуть» ведёт туда же, куда указывает подпись.
        "our_next_stage": stage_public(stage_move.next_stage(db, deal, cat)),
        # Какие блоки карточки показывать. Пустой словарь означал бы «спрятать всё»,
        # поэтому источник один и он всегда полный (см. app/sales/stage_scope.py).
        "card_blocks": stage_scope.visible_blocks(db, deal, cat),
        # Вход в ТЕКУЩУЮ стадию — из истории движения, того же источника, что у правила
        # срочности. До 13.09.2026 карточка считала это по журналу действий (последняя
        # запись `move_deal`), а очередь — по истории: при переводе не через диалог
        # (массовая правка, завершение РК, прикрепление плана) два числа расходились, и
        # каждое было «правдиво» по своему источнику. None — сделка не двигалась у нас,
        # и это честнее выдуманной даты.
        "stage_since": _stage_since(db, deal),
        "realization_pipeline_id": deal.realization_pipeline_id,
        "our_mps": list(our_mps.values()),
        # Приложения к договору, которые закрывают эту сделку. В карточке строка «Доп.
        # соглашение» показывает номер и дату, а не «не загружен»: ДС у нас теперь не
        # приносят файлом, а собирают — и строка обязана говорить о собранном документе.
        "annexes": _deal_annexes(db, deal.id),
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


MOVE_EVENT_TITLES = {
    "deal_lost": "Сделка не состоялась",
    "deal_done": "Сделка доведена",
    "deal_booked": "Сделка ушла в бронь",
}


def move_event_key(prev_key, is_lost, is_terminal, stage_key):
    """Какое сейлзовое событие порождает переход. None — никакое.

    Чистая функция: исходы взаимоисключающие и порядок их проверки — единственное, что
    здесь можно перепутать (терминальная стадия срыва тоже is_terminal, и без проверки
    is_lost первым срыв уехал бы в «доведена»).
    """
    if is_lost:
        return "deal_lost"
    if is_terminal:
        return "deal_done"
    # Повторный вход в ту же стадию события не порождает: снаружи это выглядело бы как
    # «сделка ушла в бронь» второй раз, хотя ничего не произошло.
    if stage_key == "booking" and prev_key != "booking":
        return "deal_booked"
    return None


def _notify_move(db, deal, prev, target, comment, actor):
    """Сейлзовые события перехода сделки. Зовётся из `stage_move.apply_move` — то есть
    из ЕДИНСТВЕННОЙ точки перевода, а значит на всех путях, не только из диалога."""
    from app.notify.bus import emit

    key = move_event_key(getattr(prev, "stage_key", None), target.is_lost,
                         target.is_terminal, target.stage_key)
    if key is None:
        return
    where = deal_label(deal)
    # Комментарий к переходу обязателен на входе, и для срыва он и есть содержание
    # уведомления: «сделка сорвалась» без причины не говорит ничего.
    emit(db, key, title=f"{MOVE_EVENT_TITLES[key]}: {where}",
         body=(comment or "").strip() or None,
         link=f"/sales/deals/{deal.code or deal.id}",
         entity_type="sales_deal", entity_id=deal.id, actor=actor, ctx={"deal": deal})


def _stage_since(db, deal):
    """Когда сделка вошла в текущую стадию. Один источник с правилом срочности."""
    if not deal.our_stage_id:
        return None
    row = db.query(func.max(SalesDealStageHistory.at)).filter(
        SalesDealStageHistory.deal_id == deal.id,
        SalesDealStageHistory.to_stage_id == deal.our_stage_id).first()
    return row[0].isoformat() if row and row[0] else None


def _line_public(ln) -> dict:
    """Строка требования для экрана. `where`/`link` обязательны в выдаче: список «чего
    не хватает» без ответа «куда идти» заставляет человека спрашивать нас."""
    return {
        "key": ln.key, "title": ln.title, "hint": ln.hint,
        "is_blocking": bool(ln.is_blocking),
        "where": ln.where, "link": ln.link,
        "state": ln.result.state, "detail": ln.result.detail,
        "blockers": list(ln.result.blockers),
    }


@router.get("/deals/{deal_id}/move-preview")
def move_preview(
    deal_id: int,
    to_stage_id: Optional[int] = None,
    realization_pipeline_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("sales_registry", "view")),
):
    """Что требуется для перехода — ДО попытки.

    Нужна затем, чтобы отказ не прилетал после нажатия кнопки: человек должен видеть
    список заранее, вместе с местом, где каждое чинится. Без цели считает следующую
    стадию по цепочке — то же, что сделает кнопка «двинуть» без выбора.
    """
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _assert_deal_in_scope(db, current_user, deal)

    cat = Catalog(db)
    target = cat.by_id.get(to_stage_id) if to_stage_id else cat.next_of(deal.our_stage_id)
    if target is None:
        return {"target": None, "lines": [], "allowed": True,
                "reason": "Некуда двигать — сделка на последней стадии"}

    # Воронку, ВЫБРАННУЮ ПРЯМО СЕЙЧАС, надо учесть: диалог выбирает стадию и воронку
    # одним списком («В размещении · Pharm»), и до отправки формы у сделки её ещё нет.
    # Без этого требование «воронка выбрана» всегда отвечало бы «не выбрана», кнопка
    # гасла, и сделка без воронки не прошла бы дальше «Брони» НИКОГДА — а таких на
    # 13.09.2026 тридцать четыре.
    if realization_pipeline_id:
        deal.realization_pipeline_id = realization_pipeline_id
    try:
        plan = stage_move.plan_move(db, deal, target, cat)
        out = {
            "target": stage_public(target, cat),
            "is_back": plan.is_back,
            "needs_pipeline": plan.needs_pipeline,
            "allowed": plan.allowed,
            "can_override": stage_move.is_master(current_user),
            "lines": [_line_public(ln) for ln in plan.lines],
            "blocking": [_line_public(ln) for ln in plan.blockers],
        }
    finally:
        # Ручка ЧИТАЮЩАЯ: подставленную воронку в базу не пускаем. Autoflush мог
        # отправить её вместе с любым запросом внутри plan_move — откат гарантирует,
        # что предпросмотр ничего не изменил.
        db.rollback()
    return out


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

    # Воронку принимаем ДО расчёта: без неё план сказал бы «нужна воронка», хотя её
    # только что прислали в этом же запросе.
    if target.phase and target.phase.is_realization and not target.is_terminal:
        if payload.realization_pipeline_id is not None:
            deal.realization_pipeline_id = payload.realization_pipeline_id

    plan = stage_move.plan_move(db, deal, target, cat)
    master = stage_move.is_master(current_user)
    if plan.is_back and not master:
        raise HTTPException(status_code=403, detail="Двигать сделку назад может только мастер")

    # Воронка нужна рабочим стадиям реализационного этапа: одна и та же стадия живёт в
    # каждой продуктовой воронке. Терминальные — исключение: сделка умерла, привязывать
    # её к воронке незачем, а требование воронки сделало бы «сорвалась» недостижимой у
    # сделок, которые до реализации не дошли.
    if plan.needs_pipeline:
        raise HTTPException(status_code=400, detail="Выберите воронку реализации под продукт")

    # Требования цели. Обход разрешён мастеру и ТОЛЬКО с причиной: иначе «в обход» стало
    # бы неотличимо от «правило не сработало», и разбирать было бы нечего.
    override = bool(plan.blockers) and master and bool((payload.override_reason or "").strip())
    if plan.blockers and not override:
        detail = stage_move.refusal_text(plan)
        if master:
            detail += ". Мастер может провести мимо — укажите причину обхода."
        raise HTTPException(status_code=400, detail=detail)

    prev = plan.current
    stage_move.apply_move(
        db, deal, target, current_user, catalog=cat, force=override,
        reason=(payload.override_reason or payload.comment or ""))
    # Уведомление шлёт сама `apply_move` — одна точка на все пути движения.
    db.commit()

    label = f"{prev.name if prev else '—'} → {target.name}"
    if override:
        label += f" (В ОБХОД ТРЕБОВАНИЙ: {payload.override_reason})"
    elif payload.override_reason:
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

    # Старт уехал за прежний конец — конец протух. В реестре правится ТОЛЬКО месяц
    # старта (конец РК нигде не редактируется), поэтому отказать значило бы запереть
    # человека: починить конец ему нечем. Снимаем его: NULL по контракту модели читается
    # как «календарный месяц старта» — это утверждение, а не потеря данных, и оно
    # заведомо вернее прошлогодней даты. Настоящий конец приедет со сверкой из Битрикса,
    # где кампанию и переносили (теперь она его тянет — см. deal_sync.F_PERIOD_TO).
    if ("period_from" in changes and "period_to" not in changes
            and periods.end_is_stale(changes["period_from"], deal.period_to)):
        changes["period_to"] = None

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
        # Наша строка: посадочная страница уезжает в ОРД как advertiserUrls. Схема
        # реестра принимает только http/https — проверка та же, что у ссылки на документ
        # договора, и по той же причине: «javascript:» в поле, которое где-то отрисуется
        # ссылкой, это XSS, а не опечатка.
        if field in EDITABLE_OURS_STR:
            text = (value or "").strip()
            if text and not text.startswith(("http://", "https://")):
                raise HTTPException(status_code=400,
                                    detail="Ссылка должна начинаться с http:// или https://")
            setattr(deal, field, text or None)
            continue

        # Наш собственный признак: ставим и идём дальше, в очередь на Битрикс он
        # не попадает и синхронизацией не перезаписывается — его там просто нет.
        if field in EDITABLE_OURS:
            new_val = bool(value)
            if field == "is_self_promo" and new_val != bool(deal.is_self_promo):
                # Односторонний признак (решение владельца 26.08.2026): пометить
                # саморекламой может любой, у кого есть право правки, а снять —
                # только мастер. Самореклама меняет цепочку маркировки: свой тип
                # договора в ОРД и обязательный isSelfPromotion у креатива, — то
                # есть последствия уходят наружу, и «передумал» стоит дороже, чем
                # «поставил». Правило и его формулировка те же, что у движения
                # сделки назад (см. move_deal ниже) — второго правила не заводим.
                if not new_val and not _is_account_master(current_user):
                    raise HTTPException(
                        status_code=403,
                        detail="Снять статус «самореклама» может только мастер аккаунт или админ")
                setattr(deal, field, new_val)
                log_action(db, current_user,
                           "self_promo_on" if new_val else "self_promo_off",
                           entity_type="sales_deal", entity_id=deal.id,
                           details=("Присвоен статус «самореклама»" if new_val
                                    else "Снят статус «самореклама»"))
                continue
            setattr(deal, field, new_val)
            continue

        # Наше числовое поле: ставим и выходим, не попадая в очередь на Битрикс — там
        # такого поля нет. Значение проверяем: ссылка на несуществующего ответственного
        # тихо оставила бы сделку без трафика при заполненном на вид поле.
        if field in EDITABLE_OURS_INT:
            if value is not None:
                if not db.query(SalesRep.id).filter(SalesRep.id == int(value)).first():
                    raise HTTPException(status_code=400, detail="Ответственный не найден")
                setattr(deal, field, int(value))
            else:
                setattr(deal, field, None)
            continue

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

    # НАША лестница: группировка по этапам, счётчик сделок, срыв красится красным.
    # Стадии без сделок остаются в списке (count=0) — иначе, сняв галочку, вернуть
    # её было бы нельзя.
    our_counts = dict(_apply_own_scope(
        db.query(SalesDeal.our_stage_id, func.count(SalesDeal.id)), own)
        .group_by(SalesDeal.our_stage_id).all())
    our_stage_opts = []
    for ph in (db.query(SalesStagePhase).order_by(SalesStagePhase.sort_order).all()):
        for st in sorted(ph.stages, key=lambda x: (x.sort_order, x.id)):
            opt = {"value": st.id, "label": st.name, "group": ph.name,
                   "count": our_counts.get(st.id, 0)}
            if st.is_lost:
                opt["tone"] = "danger"
            our_stage_opts.append(opt)

    return {
        "money_layer": [{"value": l, "label": l} for l in ("планируемые", "реализуемые", "фактические")],
        "our_stage_id": our_stage_opts,
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
