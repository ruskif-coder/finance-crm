"""Годовой план продаж: план по рекламодателям/брендам с разбивкой по 12 месяцам.

Годовой план = ПАКЕТ (SalesYearPlan): группировка под задачу. Один рекламодатель может
иметь несколько планов за год (разные агентства/номенклатуры). Строки-бренды
(SalesYearPlanLine) принадлежат плану через plan_id; сделки — жёстко через строку
(SalesDeal.year_plan_line_id + plan_month). Никакого мягкого матча по advertiser+brand:
сделка попадает в план ТОЛЬКО через явный линк (конвейер ставит автоматом; отдельные
сделки — вручную attach/detach).

Персональный: строка/план принадлежит сейлзу (sales_rep_id). Обычный сейлз видит и
правит только свой; «мастер» (year_plan.deals_scope='all' или admin) — любой.

Слой денег — от НАШЕЙ стадии сделки (SalesStage.money_layer): «фактические» → closed=1
(факт), остальное → бронь (closed=0).
"""
import calendar
import uuid as _uuid
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any

from app.database import get_db
from app.permissions import require_permission
from app.audit import log_action
from app.models import User, RolePermission
from app.sales.models import (SalesYearPlan, SalesYearPlanLine, SalesAdvertiser,
                              SalesBrand, SalesService, SalesAddonService, SalesDeal,
                              SalesStage, SalesRep, SalesMediaPlan, SalesMediaPlanRow,
                              SalesMediaPlanExtra)

SALES_VAT_RATE = 0.22   # сделки/МП: amount = БЕЗ НДС, gross = ×(1+ставка)

router = APIRouter()
YP_VIEW = require_permission("year_plan", "view")
YP_EDIT = require_permission("year_plan", "edit")

FACT_LAYER = "фактические"   # слой денег «факт» в маппинге стадий


# ── владение / доступ ────────────────────────────────────────────────────
def _is_master(db: Session, user: User) -> bool:
    """Мастер видит чужие планы: admin, либо year_plan.deals_scope='all'."""
    if user.role and user.role.key == "admin":
        return True
    row = (db.query(RolePermission)
           .filter(RolePermission.role_id == user.role_id,
                   RolePermission.section == "year_plan").first())
    return (not row) or (row.deals_scope or "all") != "own"


def _own_rep_ids(db: Session, user: User) -> List[int]:
    return [r.id for r in db.query(SalesRep.id).filter(SalesRep.user_id == user.id).all()]


def _resolve_rep(db: Session, user: User, rep_id: Optional[int]):
    """→ (effective_rep_id, is_master). Не-мастер всегда прижат к своему сейлзу."""
    master = _is_master(db, user)
    own = _own_rep_ids(db, user)
    if not master:
        return (own[0] if own else -1), False   # -1 → нет привязки, пустой план
    if rep_id is not None:
        return rep_id, True
    return (own[0] if own else None), True       # мастер без явного выбора → свой (или None)


def _guard_plan_owner(db: Session, plan, user: User):
    """403, если роль не мастер и план принадлежит другому сейлзу.

    До 2026-08-23 `update_plan` и `delete_plan` брали план по id и владельца не
    проверяли: сейлз с правом year_plan:edit и областью 'own' мог переименовать,
    переназначить на себя (`PlanPatch.sales_rep_id`) или удалить чужой план —
    а удаление ещё и отвязывает все сделки строк (year_plan_line_id → NULL),
    то есть тихо рвёт связь плана с фактом.
    """
    if _is_master(db, user):
        return
    if plan.sales_rep_id not in _own_rep_ids(db, user):
        raise HTTPException(status_code=403, detail="Это план другого сейлза")


def _guard_deal_owner(db: Session, deal, user: User):
    """403, если роль не мастер и сделка не её.

    Привязка сделки к строке плана — это перенос денег между планами: план
    управляет фактом и бронью, а через них бонусом. Без проверки не-мастер мог
    затянуть чужую сделку в свой план (`attach`) или выдернуть чужую сделку из
    чужого плана (`detach`), и оба действия выглядели бы штатной работой.
    """
    if _is_master(db, user):
        return
    own = set(_own_rep_ids(db, user))
    if not ({deal.sales_rep_id, deal.account_manager_id} & own):
        raise HTTPException(status_code=403, detail="Сделка вне вашей зоны видимости")


# ── план/пакет: автозаголовок и find-or-create ───────────────────────────
def _auto_title(db: Session, advertiser_id: Optional[int], year: int) -> str:
    name = None
    if advertiser_id:
        a = db.get(SalesAdvertiser, advertiser_id)
        if a:
            name = a.short_name or a.name
    return f"{name or 'Без рекламодателя'} · {year}"


def _default_plan(db: Session, advertiser_id: Optional[int], year: int,
                  rep_id: Optional[int], user: User) -> SalesYearPlan:
    """Найти дефолтный план (advertiser, year, rep) или создать. Для строк без явного
    plan_id — чтобы каждая строка всегда была под пакетом (совместимость с легаси)."""
    q = db.query(SalesYearPlan).filter(SalesYearPlan.year == year)
    q = q.filter(SalesYearPlan.advertiser_id == advertiser_id) if advertiser_id is not None \
        else q.filter(SalesYearPlan.advertiser_id.is_(None))
    q = q.filter(SalesYearPlan.sales_rep_id == rep_id) if rep_id is not None \
        else q.filter(SalesYearPlan.sales_rep_id.is_(None))
    plan = q.order_by(SalesYearPlan.id).first()
    if plan:
        return plan
    plan = SalesYearPlan(advertiser_id=advertiser_id, year=year, sales_rep_id=rep_id,
                         account_manager_id=rep_id, title=_auto_title(db, advertiser_id, year),
                         created_by=user.id)
    db.add(plan)
    db.flush()
    return plan


# ── сериализация ─────────────────────────────────────────────────────────
def _norm_products(products: Any) -> dict:
    """Нормализация products в объекты. Легаси-строки хранят [service_id,...] —
    приводим к [{ref_id,type:'service',amount:0,units:0}] для единого фронта.

    inventory (web/app) и mode (100/50/бонус) ОБЯЗАТЕЛЬНО отдаём как есть: раньше они
    здесь терялись, и после сохранения тумблеры в конструкторе сбрасывались на дефолт,
    хотя в МП уходило сохранённое значение — интерфейс и МП расходились.
    deal_idx — номер сделки внутри месяца (разделитель «+ сделка»), легаси → 0."""
    out: Dict[str, list] = {}
    for m, items in (products or {}).items():
        norm = []
        for it in (items or []):
            if isinstance(it, dict):
                o = {"ref_id": it.get("ref_id"), "type": it.get("type", "service"),
                     "amount": it.get("amount", 0) or 0, "units": it.get("units", 0) or 0,
                     "deal_idx": int(it.get("deal_idx") or 0)}
                if it.get("inventory"):
                    o["inventory"] = it["inventory"]
                if it.get("mode"):
                    o["mode"] = it["mode"]
                norm.append(o)
            else:  # легаси: голый service_id
                norm.append({"ref_id": it, "type": "service", "amount": 0, "units": 0, "deal_idx": 0})
        out[m] = norm
    return out


def _line_out(l: SalesYearPlanLine) -> dict:
    return {
        "id": l.id,
        "plan_id": l.plan_id,
        "advertiser_id": l.advertiser_id,
        "brand_id": l.brand_id,
        "plan_amount": l.plan_amount or 0,
        "months_on": (list(l.months_on or []) + [0] * 12)[:12],
        "sums": l.sums or {},
        "locks": l.locks or {},
        "products": _norm_products(l.products),
        "deals": l.deals or {},
        "brief": l.brief or {},
        "service_forecast": l.service_forecast or {},
        "sort_order": l.sort_order or 0,
    }


def _plan_out(p: SalesYearPlan) -> dict:
    return {
        "id": p.id, "advertiser_id": p.advertiser_id, "year": p.year,
        "title": p.title, "account_manager_id": p.account_manager_id,
        "sales_rep_id": p.sales_rep_id,
    }


def _catalog(db: Session) -> dict:
    advs = (db.query(SalesAdvertiser)
            .filter(SalesAdvertiser.is_active.is_(True))
            .order_by(func.coalesce(SalesAdvertiser.short_name, SalesAdvertiser.name)).all())
    brands = (db.query(SalesBrand).filter(SalesBrand.is_active.is_(True))
              .order_by(SalesBrand.name).all())
    rep_user = {r.id: r.user_id for r in db.query(SalesRep).all()}
    by_adv: Dict[int, list] = {}
    for b in brands:
        by_adv.setdefault(b.advertiser_id, []).append({"id": b.id, "name": b.name})
    services = (db.query(SalesService).filter(SalesService.is_active.is_(True))
                .order_by(SalesService.sort_order, SalesService.name).all())
    addons = (db.query(SalesAddonService).filter(SalesAddonService.is_active.is_(True))
              .order_by(SalesAddonService.sort_order, SalesAddonService.name).all())
    return {
        # sales_rep_user_id — закреплённый за рекламодателем сейлз УЧЁТКОЙ: бриф строки
        # хранит ответственных как id пользователей (как и медиаплан), а не как sales_reps.
        "advertisers": [{"id": a.id, "name": a.short_name or a.name,
                         "sales_rep_user_id": rep_user.get(a.sales_rep_id),
                         "brands": by_adv.get(a.id, [])} for a in advs],
        "services": [{"id": s.id, "name": s.name, "separate_price": bool(s.separate_price),
                      "unit_price": s.unit_price, "unit_price_web": s.unit_price_web,
                      "unit_price_app": s.unit_price_app, "calc_form": s.calc_form} for s in services],
        "addons": [{"id": a.id, "name": a.name, "unit_price": a.unit_price,
                    "can_be_bonus": bool(a.can_be_bonus)} for a in addons],
    }


def _reps(db: Session) -> list:
    rows = (db.query(SalesRep).filter(SalesRep.is_active.is_(True))
            .order_by(SalesRep.name).all())
    return [{"id": r.id, "name": r.name} for r in rows]


# ── чтение ───────────────────────────────────────────────────────────────
@router.get("")
def get_year_plan(year: int, rep_id: Optional[int] = None,
                  db: Session = Depends(get_db), current_user: User = Depends(YP_VIEW)):
    eff_rep, master = _resolve_rep(db, current_user, rep_id)
    q = db.query(SalesYearPlanLine).filter(SalesYearPlanLine.year == year)
    q = q.filter(SalesYearPlanLine.sales_rep_id == eff_rep) if eff_rep is not None \
        else q.filter(SalesYearPlanLine.sales_rep_id.is_(None))
    lines = q.order_by(SalesYearPlanLine.sort_order, SalesYearPlanLine.id).all()
    # планы, к которым принадлежат строки (для группировки на фронте)
    plan_ids = {l.plan_id for l in lines if l.plan_id}
    plans = (db.query(SalesYearPlan).filter(SalesYearPlan.id.in_(plan_ids)).all()
             if plan_ids else [])
    return {
        "year": year, "lines": [_line_out(l) for l in lines],
        "plans": [_plan_out(p) for p in plans], "catalog": _catalog(db),
        "me": {"is_master": master, "rep_id": eff_rep,
               "own_rep_id": (_own_rep_ids(db, current_user) or [None])[0]},
        "reps": _reps(db) if master else [],
    }


@router.get("/years")
def list_years(db: Session = Depends(get_db), current_user: User = Depends(YP_VIEW)):
    rows = (db.query(SalesYearPlanLine.year).distinct()
            .order_by(SalesYearPlanLine.year.desc()).all())
    return {"years": [r[0] for r in rows]}


# ── план/пакет CRUD ──────────────────────────────────────────────────────
class PlanIn(BaseModel):
    year: int
    advertiser_id: Optional[int] = None
    title: Optional[str] = None
    rep_id: Optional[int] = None
    account_manager_id: Optional[int] = None


@router.post("/plans")
def create_plan(payload: PlanIn, db: Session = Depends(get_db),
                current_user: User = Depends(YP_EDIT)):
    eff_rep, _ = _resolve_rep(db, current_user, payload.rep_id)
    if eff_rep is not None and eff_rep < 0:
        eff_rep = None
    plan = SalesYearPlan(
        advertiser_id=payload.advertiser_id, year=payload.year, sales_rep_id=eff_rep,
        account_manager_id=payload.account_manager_id or eff_rep,
        title=payload.title or _auto_title(db, payload.advertiser_id, payload.year),
        created_by=current_user.id)
    db.add(plan)
    db.commit()
    log_action(db, current_user, "year_plan_create", "year_plan", plan.id, plan.title)
    return _plan_out(plan)


class PlanPatch(BaseModel):
    title: Optional[str] = None
    advertiser_id: Optional[int] = None
    account_manager_id: Optional[int] = None
    sales_rep_id: Optional[int] = None


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: int, payload: PlanPatch, db: Session = Depends(get_db),
                current_user: User = Depends(YP_EDIT)):
    plan = db.get(SalesYearPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="План не найден")
    _guard_plan_owner(db, plan, current_user)
    fields = payload.dict(exclude_unset=True)
    # Смена ответственных — только мастеру: иначе не-мастер переписывает план на себя
    # (или сбрасывает с себя чужой). В модели это и заявлено: «мастер может сменить».
    if not _is_master(db, current_user):
        for locked in ("sales_rep_id", "account_manager_id"):
            if locked in fields:
                raise HTTPException(status_code=403,
                                    detail="Смена ответственного доступна только мастеру")
    for f, v in fields.items():
        setattr(plan, f, v)
    db.commit()
    log_action(db, current_user, "year_plan_update", "year_plan", plan.id, plan.title)
    return _plan_out(plan)


@router.get("/export.xlsx")
def export_year_xlsx(year: int, advertiser_id: int, rep_id: Optional[int] = None,
                     db: Session = Depends(get_db), current_user: User = Depends(YP_VIEW)):
    """Годовая выгрузка: сводная + бриф + лист на каждый месяц с закупкой.

    Единица выгрузки — РЕКЛАМОДАТЕЛЬ за год, со всеми его брендами (см.
    docs/SPEC_годовой_МП_в_Excel.md). Именно так устроена страница годового плана:
    строка = рекламодатель, внутри бренды. Выгружать по плану/пакету нельзя — бренды
    одного рекламодателя могут лежать в РАЗНЫХ планах (их заводили в разное время),
    и тогда в книгу попал бы только один бренд из трёх."""
    import os
    from io import BytesIO
    from fastapi.responses import StreamingResponse
    from types import SimpleNamespace
    from urllib.parse import quote
    from app.year_mp_export import build_workbook
    from app.routers.media_plans import TEMPLATE_PATH, _names

    eff_rep, _master = _resolve_rep(db, current_user, rep_id)
    q = (db.query(SalesYearPlanLine)
         .filter(SalesYearPlanLine.year == year,
                 SalesYearPlanLine.advertiser_id == advertiser_id))
    q = q.filter(SalesYearPlanLine.sales_rep_id == eff_rep) if eff_rep is not None \
        else q.filter(SalesYearPlanLine.sales_rep_id.is_(None))
    lines = q.order_by(SalesYearPlanLine.sort_order, SalesYearPlanLine.id).all()
    if not lines:
        raise HTTPException(status_code=404, detail="У рекламодателя нет строк плана на этот год")
    adv = db.get(SalesAdvertiser, advertiser_id)
    adv_name = (adv.short_name or adv.name) if adv else f"#{advertiser_id}"
    # Заголовок берём у плана-пакета только если он один: при нескольких планах его
    # название описывает лишь часть брендов и вводило бы в заблуждение.
    plan_ids = {l.plan_id for l in lines if l.plan_id}
    plan_title = None
    if len(plan_ids) == 1:
        p0 = db.get(SalesYearPlan, next(iter(plan_ids)))
        plan_title = p0.title if p0 else None
    plan = SimpleNamespace(id=advertiser_id, year=year, advertiser_id=advertiser_id,
                           title=plan_title or f"{adv_name} · {year}")
    tpl = os.path.abspath(TEMPLATE_PATH)
    if not os.path.exists(tpl):
        raise HTTPException(status_code=500, detail="Нет шаблона медиаплана")
    wb, data = build_workbook(db, plan, lines, {s.id: s for s in db.query(SalesService).all()},
                              {a.id: a for a in db.query(SalesAddonService).all()},
                              _names(db), tpl, SALES_VAT_RATE)
    if not data["months"]:
        raise HTTPException(status_code=400, detail="В плане нет месяцев с закупкой")
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    log_action(db, current_user, "year_plan_export", "year_plan", advertiser_id,
               f"{adv_name} · {year}, брендов: {len(data['brands'])}, месяцев: {len(data['months'])}")
    # Штамп даты-времени в имени — как у выгрузок МП: иначе две выгрузки за день
    # называются одинаково. Время московское, как и везде в интерфейсе.
    from datetime import datetime, timedelta, timezone
    stamp = datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H-%M")
    name = f"Годовой МП Simb-AD {adv_name} {year} {stamp}"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f"attachment; filename=year_plan_{advertiser_id}_{year}.xlsx; "
                 f"filename*=UTF-8''{quote(name)}.xlsx"})


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(YP_EDIT)):
    plan = db.get(SalesYearPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="План не найден")
    _guard_plan_owner(db, plan, current_user)
    lines = db.query(SalesYearPlanLine).filter(SalesYearPlanLine.plan_id == plan_id).all()
    line_ids = [l.id for l in lines]
    # Открепляем сделки (FK nullable, NO ACTION) прежде чем удалять строки.
    if line_ids:
        (db.query(SalesDeal).filter(SalesDeal.year_plan_line_id.in_(line_ids))
         .update({SalesDeal.year_plan_line_id: None, SalesDeal.plan_month: None},
                 synchronize_session=False))
        for l in lines:
            db.delete(l)
    db.delete(plan)
    db.commit()
    log_action(db, current_user, "year_plan_delete", "year_plan", plan_id,
               f"{plan.title}, строк: {len(line_ids)}")
    return {"ok": True, "deleted_lines": len(line_ids)}


def _guard_advertiser_change(db, row: SalesYearPlanLine, new_adv):
    """Запрет смены рекламодателя у СОХРАНЁННОЙ строки — как и у бренда.

    Назначение строки меняется только через удаление: рекламодатель — это то, чему
    принадлежат её услуги, суммы, бриф и привязанные сделки. Раньше смена молча
    проходила обычным setattr и рвала сразу несколько связей: сделки оставались
    привязанными к строке (факт и бронь уходили чужому рекламодателю), бренд
    обнулялся при живых услугах и суммах, а пакет sales_year_plans оставался на
    прежнем рекламодателе — строка и пакет расходились."""
    if new_adv is None or new_adv == row.advertiser_id:
        return
    deals = db.query(SalesDeal.id).filter(SalesDeal.year_plan_line_id == row.id).count()
    raise HTTPException(status_code=400, detail=(
        "Нельзя сменить рекламодателя у сохранённой строки плана"
        + (f" (привязано сделок: {deals})" if deals else "")
        + ". Услуги, суммы, бриф и сделки строки принадлежат прежнему рекламодателю — "
          "удалите строку и заведите её у нужного."))


# ── сохранение строк (upsert-by-id, FK-safe) ─────────────────────────────
class LineIn(BaseModel):
    id: Optional[int] = None
    plan_id: Optional[int] = None
    advertiser_id: Optional[int] = None
    brand_id: Optional[int] = None
    plan_amount: float = 0
    months_on: List[int] = []
    sums: Dict[str, float] = {}
    locks: Dict[str, int] = {}
    products: Dict[str, List[dict]] = {}
    deals: Dict[str, List[list]] = {}
    brief: dict = {}
    service_forecast: dict = {}
    sort_order: int = 0


class SaveIn(BaseModel):
    year: int
    rep_id: Optional[int] = None
    lines: List[LineIn] = []


@router.post("")
def save_year_plan(payload: SaveIn, db: Session = Depends(get_db),
                   current_user: User = Depends(YP_EDIT)):
    """Upsert строк за (год, сейлз) БЕЗ delete-all — id строк (и линки сделок) сохраняются.
    Строки, которых нет в payload, удаляются; их сделки предварительно откручиваются."""
    eff_rep, _master = _resolve_rep(db, current_user, payload.rep_id)
    if eff_rep is None or eff_rep < 0:
        raise HTTPException(status_code=400, detail="Не удалось определить сейлза для сохранения плана")

    existing = {l.id: l for l in db.query(SalesYearPlanLine)
                .filter(SalesYearPlanLine.year == payload.year,
                        SalesYearPlanLine.sales_rep_id == eff_rep).all()}
    seen: set = set()

    for i, ln in enumerate(payload.lines):
        months = ((ln.months_on or [])[:12]) + [0] * (12 - len(ln.months_on or []))
        plan_id = ln.plan_id
        if not plan_id:  # без явного пакета — под дефолтный (find-or-create)
            plan_id = _default_plan(db, ln.advertiser_id, payload.year, eff_rep, current_user).id
        fields = dict(
            plan_id=plan_id, advertiser_id=ln.advertiser_id, brand_id=ln.brand_id,
            plan_amount=ln.plan_amount or 0, months_on=months,
            sums=ln.sums or {}, locks=ln.locks or {}, products=ln.products or {},
            deals=ln.deals or {}, brief=ln.brief or {},
            service_forecast=ln.service_forecast or {},
            sort_order=ln.sort_order if ln.sort_order else i)
        row = existing.get(ln.id) if ln.id else None
        if row is not None:
            _guard_advertiser_change(db, row, ln.advertiser_id)
            for f, v in fields.items():
                setattr(row, f, v)
            seen.add(row.id)
        else:
            row = SalesYearPlanLine(year=payload.year, sales_rep_id=eff_rep,
                                    created_by=current_user.id, **fields)
            db.add(row)

    # удалить пропавшие строки (открепив сделки)
    stale = [l for lid, l in existing.items() if lid not in seen]
    if stale:
        stale_ids = [l.id for l in stale]
        (db.query(SalesDeal).filter(SalesDeal.year_plan_line_id.in_(stale_ids))
         .update({SalesDeal.year_plan_line_id: None, SalesDeal.plan_month: None},
                 synchronize_session=False))
        for l in stale:
            db.delete(l)

    db.commit()
    log_action(db, current_user, "year_plan_save", "year_plan", payload.year,
               f"сейлз {eff_rep}, строк: {len(payload.lines)}")
    lines = (db.query(SalesYearPlanLine)
             .filter(SalesYearPlanLine.year == payload.year, SalesYearPlanLine.sales_rep_id == eff_rep)
             .order_by(SalesYearPlanLine.sort_order, SalesYearPlanLine.id).all())
    return {"year": payload.year, "rep_id": eff_rep, "lines": [_line_out(l) for l in lines]}


# ── жёсткий линк сделки ↔ ячейка плана ────────────────────────────────────
class AttachIn(BaseModel):
    line_id: int
    month: int   # 0..11


@router.post("/deals/{deal_id}/attach")
def attach_deal(deal_id: int, payload: AttachIn, db: Session = Depends(get_db),
                current_user: User = Depends(YP_EDIT)):
    deal = db.get(SalesDeal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _guard_deal_owner(db, deal, current_user)
    line = db.get(SalesYearPlanLine, payload.line_id)
    if not line:
        raise HTTPException(status_code=404, detail="Строка плана не найдена")
    if line.plan_id:
        _guard_plan_owner(db, db.get(SalesYearPlan, line.plan_id), current_user)
    if not (0 <= payload.month <= 11):
        raise HTTPException(status_code=400, detail="month вне диапазона 0..11")
    deal.year_plan_line_id = line.id
    deal.plan_month = payload.month
    db.commit()
    log_action(db, current_user, "year_plan_attach_deal", "sales_deal", deal.id,
               f"строка {line.id}, месяц {payload.month}")
    return {"ok": True}


@router.post("/deals/{deal_id}/detach")
def detach_deal(deal_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(YP_EDIT)):
    deal = db.get(SalesDeal, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    _guard_deal_owner(db, deal, current_user)
    deal.year_plan_line_id = None
    deal.plan_month = None
    db.commit()
    log_action(db, current_user, "year_plan_detach_deal", "sales_deal", deal.id, "")
    return {"ok": True}


# ── обновление факта/брони по ЖЁСТКОМУ линку (замена мягкого матча) ────────
class RefreshIn(BaseModel):
    year: int
    rep_id: Optional[int] = None


@router.post("/match-deals")
def refresh_deals(payload: RefreshIn, db: Session = Depends(get_db),
                  current_user: User = Depends(YP_EDIT)):
    """Перечёт deals по ЖЁСТКОМУ линку: для строк (год, сейлз) читаем привязанные сделки
    (SalesDeal.year_plan_line_id) живьём и раскладываем по plan_month. Никакого совпадения
    по advertiser+brand — только явный линк. Правки суммы/месяца в сделке отражаются тут."""
    eff_rep, _master = _resolve_rep(db, current_user, payload.rep_id)
    if eff_rep is None or eff_rep < 0:
        return {"matched": [], "deals_count": 0}

    lines = (db.query(SalesYearPlanLine)
             .filter(SalesYearPlanLine.year == payload.year,
                     SalesYearPlanLine.sales_rep_id == eff_rep).all())
    line_ids = [l.id for l in lines]
    if not line_ids:
        return {"matched": [], "deals_count": 0}

    rows = (db.query(SalesDeal, SalesStage.money_layer.label("layer"))
            .outerjoin(SalesStage, SalesStage.id == SalesDeal.our_stage_id)
            .filter(SalesDeal.year_plan_line_id.in_(line_ids))
            .filter(SalesDeal.plan_month.isnot(None)).all())

    by_line: Dict[int, Dict[str, list]] = {}
    total = 0
    stages = _stage_index(db)
    for deal, layer in rows:
        m = str(deal.plan_month)
        closed = 1 if layer == FACT_LAYER else 0
        # Четвёртый элемент — срыв. Отдельно от `closed`, а не третьим его значением:
        # экран читает `closed` как булево, и «−1» или «2» посчиталось бы фактом, раздув
        # выручку. Провалённая сделка обязана быть ВИДНА (иначе пустая ячейка приглашает
        # пересобрать её заново и потерять причину), но не считаться ни фактом, ни бронью.
        st = stages.get(deal.our_stage_id) if deal.our_stage_id else None
        lost = 1 if (st is not None and getattr(st, "is_lost", False)) else 0
        by_line.setdefault(deal.year_plan_line_id, {}).setdefault(m, []).append(
            [deal.code or deal.bitrix_id, round(deal.amount or 0, 2), closed, lost])
        total += 1

    matched = []
    for l in lines:
        fresh = by_line.get(l.id, {})     # живой срез по линку
        # Замок = заморозка в обе стороны: пины заблокированных месяцев оставляем
        # как есть, иначе правка суммы в сделке протекла бы в закрытый месяц плана.
        prev = l.deals or {}
        merged = {m: v for m, v in fresh.items() if not _is_locked(l, int(m))}
        for m, v in prev.items():
            try:
                if _is_locked(l, int(m)):
                    merged[m] = v
            except (TypeError, ValueError):
                continue
        l.deals = merged                  # пусто → очистка (кроме замороженных)
        matched.append({"line_id": l.id, "advertiser_id": l.advertiser_id,
                        "brand_id": l.brand_id, "deals": l.deals})
    db.commit()
    log_action(db, current_user, "year_plan_match_deals", "year_plan", payload.year,
               f"сейлз {eff_rep}, сделок по линку: {total}")
    return {"matched": matched, "deals_count": total}


# ── КОНВЕЙЕР: создание сделок из плана (сделка + прикреплённый МП) ────────
def _pbounds(period: str):
    y, mo = int(period[:4]), int(period[5:7])
    return date(y, mo, 1), date(y, mo, calendar.monthrange(y, mo)[1])


def _month_items(line: SalesYearPlanLine, m: int) -> list:
    return [it for it in (line.products or {}).get(str(m), [])
            if isinstance(it, dict) and it.get("ref_id") is not None]


def _month_groups(line: SalesYearPlanLine, m: int) -> list:
    """Услуги месяца, разложенные по сделкам: [(deal_idx, [услуги…]), …].

    Группа = то, что в конструкторе отделено кнопкой «+ сделка» (deal_idx).
    Пустые группы (услуги удалили) не возвращаем. Порядок — по возрастанию idx,
    чтобы номера сделок были стабильны между прогонами."""
    groups: Dict[int, list] = {}
    for it in _month_items(line, m):
        groups.setdefault(int(it.get("deal_idx") or 0), []).append(it)
    return [(idx, items) for idx, items in sorted(groups.items()) if items]


def _intended_amount(line: SalesYearPlanLine, m: int, items: Optional[list] = None) -> float:
    """Сумма (до НДС) месяца целиком или одной группы-сделки, если передан items."""
    src = _month_items(line, m) if items is None else items
    return round(sum(float(it.get("amount") or 0) for it in src), 2)


def _is_locked(line: SalesYearPlanLine, m: int) -> bool:
    """Замок месяца = полная заморозка: конвейер не создаёт и не пересобирает сделки
    этого месяца, а /match-deals не перетирает его пины. Правки в обе стороны стоят."""
    return bool((line.locks or {}).get(str(m)))


def _stage_index(db: Session) -> dict:
    return {st.id: st for st in db.query(SalesStage).all()}


def _deal_frozen(deal, stages: dict) -> Optional[str]:
    """Дошедшая сделка — безусловный мастер: причина заморозки или None.

    Правило владельца 27.08.2026. Как только сделка ушла со стадии планирования, план
    перестаёт быть её источником: реквизиты, суммы и медиаплан правились уже под живое
    размещение, и повторный прогон конвейера затёр бы эту работу молча — вместе с
    медиапланом, который он удаляет и пересобирает.

    Заморозка ВЫЧИСЛЯЕТСЯ из стадии, а не хранится в `locks`. Причин две, обе замерены:
      · замок висит на паре «строка × месяц», а в пяти ячейках из тринадцати лежит по ДВЕ
        сделки — заморозив месяц, остановили бы и ту, что ещё плановая;
      · `locks` — ручной переключатель владельца. Проставленный автоматом, он выглядит
        как чужое действие, а снятый снова открывает сделку в работе под перезапись,
        то есть защита оказалась бы выключаемой кнопкой, которая значит другое.

    Провал — тоже заморозка: пустая ячейка приглашает пересобрать её заново и потерять
    факт срыва вместе с причиной.
    """
    st = stages.get(deal.our_stage_id) if deal.our_stage_id else None
    if st is None:
        return None
    if getattr(st, "is_lost", False):
        return "сделка не случилась"
    if st.money_layer in ("реализуемые", "фактические"):
        return "в работе"
    if getattr(st, "is_terminal", False):
        return "сделка закрыта"
    return None


def _season_k(line: SalesYearPlanLine, m: int) -> float:
    """Сезонный коэффициент месяца из брифа (12 чисел). Пусто/0/мусор → 1.0."""
    arr = (line.brief or {}).get("seasonality") or []
    try:
        k = float(arr[m])
    except (IndexError, TypeError, ValueError):
        return 1.0
    return k if k > 0 else 1.0


# Прогнозные поля, которые масштабирует сезонность. Цена НЕ масштабируется
# (это тариф, а не сезонное поведение аудитории); показы считаются из суммы и
# тарифа, поэтому тоже остаются как есть. Производные (охват/клики/чеки/CPO/ROI)
# пересчитываются сами из этих полей.
SEASON_FIELDS = ("freq", "ctr", "cr", "sov")


def _apply_season(fc: dict, k: float) -> dict:
    """Прогноз услуги с поправкой на сезонность месяца."""
    if not fc or k == 1.0:
        return dict(fc or {})
    out = dict(fc)
    for f in SEASON_FIELDS:
        v = out.get(f)
        try:
            if v not in (None, ""):
                out[f] = round(float(v) * k, 4)
        except (TypeError, ValueError):
            pass
    return out


def _planned_months(line: SalesYearPlanLine) -> list:
    on = list(line.months_on or [])
    return [m for m in range(12) if m < len(on) and on[m] and _month_items(line, m)]


def _target_lines(db, eff_rep, year, advertiser_id, line_id):
    q = db.query(SalesYearPlanLine).filter(SalesYearPlanLine.year == year,
                                           SalesYearPlanLine.sales_rep_id == eff_rep)
    if line_id:
        q = q.filter(SalesYearPlanLine.id == line_id)
    elif advertiser_id:
        q = q.filter(SalesYearPlanLine.advertiser_id == advertiser_id)
    return q.order_by(SalesYearPlanLine.sort_order, SalesYearPlanLine.id).all()


def _brief_missing(line: SalesYearPlanLine) -> list:
    """Обязательные поля брифа для создания сделки. Пусто → бриф заполнен."""
    b = line.brief or {}
    miss = []
    if not b.get("sales_rep_id"):
        miss.append("ответственный сейлз")
    return miss


def _product_label(line, m, svc, add, items=None) -> str:
    """Метка продукта сделки = ПЕРВАЯ основная услуга-размещение (не перечень).
    Доп услугу берём в название только если основных нет (она единственная).
    items — услуги конкретной сделки месяца (группа «+ сделка»)."""
    items = _month_items(line, m) if items is None else items
    mains = [it for it in items if it.get("type") != "addon"]
    if mains:
        s = svc.get(mains[0]["ref_id"])
        return (s.name if s else "") or ""
    if items:   # только доп услуги — берём первую
        a = add.get(items[0]["ref_id"])
        return (a.name if a else "") or ""
    return ""


def mp_parts(line, m, svc, add, items=None) -> tuple:
    """Строки размещений и доп. услуг месяца — БЕЗ записи в базу.

    Единственный источник правды для «как из годового плана получается МП»: им
    пользуется и конвейер сделок (_build_mp), и годовая выгрузка в Excel. Держать
    две копии этой арифметики нельзя — выгрузка разъедется со сделками.

    Возвращает (rows, extras) словарями в том же виде, в каком их отдаёт
    media_plans._plan_full, чтобы рендер шаблона принимал их без переходника.
    """
    period = f"{line.year}-{m + 1:02d}"
    mp_items = _month_items(line, m) if items is None else items
    k = _season_k(line, m)
    fc = line.service_forecast or {}
    rows, extras = [], []
    for it in mp_items:
        if it.get("type") == "addon":
            a = add.get(it["ref_id"])
            # price — базовая цена по прайсу, total — что реально в счёте (с учётом
            # режима 100/50/бонус; в плане это уже посчитано в amount). БЕЗ total
            # конструктор считает доп. услугу нулём и итог МП расходится с суммой сделки.
            charged = float(it.get("amount") or 0)
            base = float((a.unit_price if a else None) or charged)
            extras.append({"name": (a.name if a else None), "period": period,
                           "mode": it.get("mode", "full"), "price": base, "total": charged})
        else:
            s = svc.get(it["ref_id"])
            # inventory строго по прайсу услуги: раздельный → web/app (как выбрали), иначе cross
            if s and s.separate_price:
                inv = "app" if it.get("inventory") == "app" else "web"
                price = s.unit_price_app if inv == "app" else s.unit_price_web
            else:
                inv = "cross"
                price = s.unit_price if s else None
            # volume из суммы (до НДС) и цены: бюджет строки = volume×price/(CPM?1000:1) = amount
            amt = float(it.get("amount") or 0)
            model = str((s.calc_form if s else "") or "").upper()
            if price and price > 0:
                volume = amt / price * (1000 if model == "CPM" else 1)
            else:
                volume = float(it.get("units") or 0)
            rows.append({"position": (s.name if s else None),
                         "format": (s.placement_type if s else None),
                         "model": (s.calc_form if s else None),
                         "inventory": inv, "volume": volume, "unit_price": price, "discount": 0,
                         "forecast": _apply_season(fc.get(f"service:{it['ref_id']}") or {}, k)})
    return rows, extras


def _build_mp(db, deal, line, m, svc, add, created_by, items=None):
    """Собирает МП (голова + строки размещений + доп услуги) из услуг месяца, брифа и прогноза.
    items — услуги конкретной сделки месяца (группа «+ сделка»); None = весь месяц.
    Прогноз каждой строки идёт с поправкой на сезонный коэффициент месяца."""
    b = line.brief or {}
    period = f"{line.year}-{m + 1:02d}"
    pf, pt = _pbounds(period)
    mp_items = _month_items(line, m) if items is None else items
    net = _intended_amount(line, m, mp_items)
    mp = SalesMediaPlan(
        version=1, status="draft", title=deal.title,
        advertiser_id=line.advertiser_id, brand_id=line.brand_id, agency_id=b.get("agency_id"),
        payer_counterparty_id=b.get("payer_counterparty_id"), period=period, geo_id=b.get("geo_id"),
        date_from=pf, date_to=pt, targeting=b.get("targeting") or {}, goals={},
        sales_rep_id=b.get("sales_rep_id"), account_manager_id=b.get("account_manager_id"),
        amount_net=net, amount_gross=round(net * (1 + SALES_VAT_RATE), 2),
        deal_id=deal.id, created_by=created_by)
    db.add(mp); db.flush()
    mp.group_id = mp.id
    rows, extras = mp_parts(line, m, svc, add, mp_items)
    for order, r in enumerate(rows):
        db.add(SalesMediaPlanRow(plan_id=mp.id, sort_order=order, **r))
    for order, e in enumerate(extras):
        db.add(SalesMediaPlanExtra(plan_id=mp.id, sort_order=order, **e))
    return mp


class ConveyorIn(BaseModel):
    year: int
    rep_id: Optional[int] = None
    advertiser_id: Optional[int] = None   # запуск по всей строке рекламодателя
    line_id: Optional[int] = None         # запуск по одной строке-бренду


@router.post("/create-deals/preview")
def create_deals_preview(payload: ConveyorIn, db: Session = Depends(get_db),
                         current_user: User = Depends(YP_EDIT)):
    """Диф перед созданием: что будет создано (new) и что изменится у ранее созданных (changed)."""
    eff_rep, _ = _resolve_rep(db, current_user, payload.rep_id)
    if eff_rep is None or eff_rep < 0:
        return {"new": [], "changed": [], "unchanged": 0, "in_work": []}
    lines = _target_lines(db, eff_rep, payload.year, payload.advertiser_id, payload.line_id)
    brand_names = {b.id: b.name for b in db.query(SalesBrand).all()}
    new_items, changed, unchanged, blocked, locked = [], [], 0, [], []
    in_work = []                      # дошедшие сделки: их конвейер не трогает
    stages = _stage_index(db)
    for line in lines:
        if not line.brand_id:
            continue
        if not _planned_months(line):
            continue
        miss = _brief_missing(line)
        if miss:   # бриф не заполнен — строку не создаём
            blocked.append({"line_id": line.id, "brand": brand_names.get(line.brand_id), "missing": miss})
            continue
        for m in _planned_months(line):
            if _is_locked(line, m):   # замок — месяц заморожен целиком, показываем в дифе
                locked.append({"line_id": line.id, "brand": brand_names.get(line.brand_id), "month": m})
                continue
            for idx, items in _month_groups(line, m):
                amt = _intended_amount(line, m, items)
                if amt <= 0:
                    continue
                base = {"line_id": line.id, "brand": brand_names.get(line.brand_id),
                        "month": m, "deal_idx": idx, "amount": amt}
                existing = (db.query(SalesDeal)
                            .filter(SalesDeal.year_plan_line_id == line.id,
                                    SalesDeal.plan_month == m,
                                    func.coalesce(SalesDeal.plan_deal_idx, 0) == idx).first())
                if not existing:
                    new_items.append(base)
                else:
                    # Дошедшая сделка — безусловный мастер: показываем отдельно, а не в
                    # «изменится». Иначе человек жмёт «создать», ожидая пересборки.
                    why = _deal_frozen(existing, stages)
                    if why:
                        in_work.append({**base, "deal_id": existing.id,
                                        "code": existing.code, "reason": why})
                    else:   # перегенерируем (название/метка/МП) при повторном запуске
                        changed.append({**base, "deal_id": existing.id,
                                        "old_amount": round(existing.amount or 0, 2)})
    return {"new": new_items, "changed": changed, "unchanged": unchanged,
            "blocked": blocked, "locked": locked, "in_work": in_work}


@router.post("/create-deals")
def create_deals(payload: ConveyorIn, db: Session = Depends(get_db),
                 current_user: User = Depends(YP_EDIT)):
    """Создаёт (или обновляет ранее созданные) локальные сделки бренд×месяц + прикреплённый МП.
    Идемпотентно: неизменившиеся ячейки пропускаются, изменившиеся — обновляются."""
    eff_rep, _ = _resolve_rep(db, current_user, payload.rep_id)
    if eff_rep is None or eff_rep < 0:
        raise HTTPException(status_code=400, detail="Не удалось определить сейлза")
    lines = _target_lines(db, eff_rep, payload.year, payload.advertiser_id, payload.line_id)
    svc = {s.id: s for s in db.query(SalesService).all()}
    add = {a.id: a for a in db.query(SalesAddonService).all()}
    # бриф хранит USER id (из справочника «Сотрудники»), а SalesDeal.*_id — FK на sales_reps
    rep_by_user = {}
    for r in db.query(SalesRep).all():
        if r.user_id is not None:
            rep_by_user.setdefault(r.user_id, r.id)
    _rep = lambda uid: rep_by_user.get(uid) if uid else None
    from app.sales.models import SalesAgency
    adv_names = {a.id: (a.short_name or a.name) for a in db.query(SalesAdvertiser).all()}
    brand_names = {b.id: b.name for b in db.query(SalesBrand).all()}
    agc_names = {a.id: (a.short_name or a.name) for a in db.query(SalesAgency).all()}
    from app.sales.catalog import Catalog
    first = Catalog(db).first()
    stage_id = first.id if first else None

    created = updated = blocked = frozen = 0
    in_work = []                      # дошедшие сделки, пропущенные конвейером
    stages = _stage_index(db)
    for line in lines:
        if not line.brand_id:
            continue
        if not _planned_months(line):
            continue
        if _brief_missing(line):   # бриф не заполнен — отказываем в создании
            blocked += 1
            continue
        b = line.brief or {}
        for m in _planned_months(line):
            if _is_locked(line, m):   # замок = полная заморозка месяца в обе стороны
                frozen += 1
                continue
            period = f"{line.year}-{m + 1:02d}"
            pf, pt = _pbounds(period)
            for idx, items in _month_groups(line, m):
                net = _intended_amount(line, m, items)
                if net <= 0:
                    continue
                gross = round(net * (1 + SALES_VAT_RATE), 2)
                # Шаблон названия: Рекламодатель · [Агентство] · Бренд · Услуга · Период
                product = _product_label(line, m, svc, add, items)
                agc = agc_names.get(b.get("agency_id")) if b.get("agency_id") else None
                title = " · ".join([p for p in [
                    adv_names.get(line.advertiser_id), agc, brand_names.get(line.brand_id), product, period
                ] if p])
                existing = (db.query(SalesDeal)
                            .filter(SalesDeal.year_plan_line_id == line.id,
                                    SalesDeal.plan_month == m,
                                    func.coalesce(SalesDeal.plan_deal_idx, 0) == idx).first())
                if existing:
                    # Дошедшая сделка — безусловный мастер (владелец, 27.08.2026): её
                    # реквизиты и медиаплан правились уже под живое размещение, а ветка
                    # ниже переписывает всё и УДАЛЯЕТ медиапланы. Пропускаем и называем.
                    why = _deal_frozen(existing, stages)
                    if why:
                        in_work.append({"deal_id": existing.id, "code": existing.code,
                                        "brand": brand_names.get(line.brand_id),
                                        "month": m, "reason": why})
                        continue
                    # повторный запуск всегда пересобирает сделку и МП под текущий план/бриф
                    existing.amount = net; existing.amount_with_vat = gross
                    existing.title = title; existing.product = product
                    # Рекламодатель и бренд обязаны переписываться вместе с названием.
                    # Их тут не было, и это дало сделку, которая называется одним, а
                    # ссылается на другое: строку плана переназначили с BEIERSDORF на
                    # BINNO, повторный прогон переписал заголовок на «BINNO · Аккерслим»,
                    # а advertiser_id/brand_id остались от BEIERSDORF. В карточке и
                    # реестре видно имя из ссылки — то есть чужого рекламодателя.
                    existing.advertiser_id = line.advertiser_id
                    existing.brand_id = line.brand_id
                    existing.agency_id = b.get("agency_id"); existing.payer_counterparty_id = b.get("payer_counterparty_id")
                    _sr = _rep(b.get("sales_rep_id"))
                    if _sr:
                        existing.sales_rep_id = _sr
                    existing.account_manager_id = _rep(b.get("account_manager_id"))
                    for mp in db.query(SalesMediaPlan).filter(SalesMediaPlan.deal_id == existing.id).all():
                        db.delete(mp)   # cascade строк/доп
                    db.flush()
                    _build_mp(db, existing, line, m, svc, add, current_user.id, items)
                    updated += 1
                else:
                    deal = SalesDeal(
                        bitrix_id="local-" + _uuid.uuid4().hex, title=title, pipeline="", bitrix_stage="",
                        amount=net, amount_with_vat=gross, currency="RUB",
                        advertiser_id=line.advertiser_id, brand_id=line.brand_id, agency_id=b.get("agency_id"),
                        payer_counterparty_id=b.get("payer_counterparty_id"), product=product,
                        sales_rep_id=_rep(b.get("sales_rep_id")) or line.sales_rep_id,
                        account_manager_id=_rep(b.get("account_manager_id")), our_stage_id=stage_id,
                        period_from=pf, period_to=pt, date_create=datetime.utcnow(),
                        year_plan_line_id=line.id, plan_month=m, plan_deal_idx=idx)
                    from app.sales.deal_code import assign_code
                    assign_code(db, deal)
                    db.add(deal); db.flush()
                    _build_mp(db, deal, line, m, svc, add, current_user.id, items)
                    created += 1
    if created or updated:
        # Владельцу плана, а не запустившему: emit не шлёт актору, поэтому свой же
        # прогон человек не получает, а прогон мастера за него — получает.
        from app.notify.bus import emit
        parts = [f"создано {created}"] if created else []
        if updated:
            parts.append(f"обновлено {updated}")
        emit(db, "plan_deals_generated",
             title=f"Конвейер плана {payload.year}: " + ", ".join(parts),
             body=(f"Пропущено: без брифа {blocked}, заморожено замком {frozen}"
                   if (blocked or frozen) else None),
             link="/sales/year-plan", entity_type="year_plan", entity_id=payload.year,
             actor=current_user, ctx={"rep_id": eff_rep})
    db.commit()
    log_action(db, current_user, "year_plan_create_deals", "year_plan", payload.year,
               f"сейлз {eff_rep}: создано {created}, обновлено {updated}, "
               f"без брифа {blocked}, заморожено замком {frozen}")
    return {"created": created, "updated": updated, "blocked": blocked,
            "frozen": frozen, "in_work": in_work}


# ── сводка по всем сейлзам (только мастер) ───────────────────────────────
@router.get("/all")
def get_all_reps(year: int, db: Session = Depends(get_db),
                 current_user: User = Depends(YP_VIEW)):
    """Read-only агрегация плана по всем сейлзам за год. Факт/бронь — из поля deals
    (заполняется /match-deals по жёсткому линку)."""
    if not _is_master(db, current_user):
        raise HTTPException(status_code=403, detail="Режим «Показать все» доступен только мастеру")

    lines = db.query(SalesYearPlanLine).filter(SalesYearPlanLine.year == year).all()
    rep_names = {r.id: r.name for r in db.query(SalesRep).all()}
    adv_names = {a.id: (a.short_name or a.name) for a in db.query(SalesAdvertiser).all()}
    brand_names = {b.id: b.name for b in db.query(SalesBrand).all()}
    plan_titles = {p.id: p.title for p in db.query(SalesYearPlan).filter(SalesYearPlan.year == year).all()}

    def fact_booked(l):
        deals = (l.deals or {}).values()
        f = sum(d[1] for arr in deals for d in arr if d[2])
        b = sum(d[1] for arr in deals for d in arr if not d[2])
        return f, b

    acc: Dict[Optional[int], dict] = {}
    for l in lines:
        rep = l.sales_rep_id
        a = acc.setdefault(rep, {"plan": 0.0, "fact": 0.0, "booked": 0.0,
                                 "months": [0.0] * 12, "advs": {}})
        f, bk = fact_booked(l)
        a["plan"] += l.plan_amount or 0
        a["fact"] += f
        a["booked"] += bk
        months_on = (l.months_on or [])
        sums = l.sums or {}
        locks = l.locks or {}
        locked_sum = sum(sums.get(str(k), 0) for k in range(12) if k < len(months_on) and months_on[k] and str(k) in locks)
        free = sum(1 for k in range(12) if k < len(months_on) and months_on[k] and str(k) not in locks)
        for k in range(12):
            if k >= len(months_on) or not months_on[k]:
                continue
            if str(k) in sums:
                mv = sums[str(k)]
            else:
                mv = max(0, (l.plan_amount or 0) - locked_sum) / free if free else 0
            a["months"][k] += mv
        av = a["advs"].setdefault(l.advertiser_id, {"plan": 0.0, "fact": 0.0, "booked": 0.0, "plans": {}})
        av["plan"] += l.plan_amount or 0
        av["fact"] += f
        av["booked"] += bk
        # Сами планы-пакеты с брендами — чтобы в режиме «Показать все» их можно было
        # раскрыть и перейти в редактирование, а не только видеть полосу выполнения.
        pk = av["plans"].setdefault(l.plan_id, {"plan_id": l.plan_id,
                                                "title": plan_titles.get(l.plan_id),
                                                "plan": 0.0, "fact": 0.0, "booked": 0.0, "brands": []})
        pk["plan"] += l.plan_amount or 0
        pk["fact"] += f
        pk["booked"] += bk
        pk["brands"].append({
            "line_id": l.id, "brand": brand_names.get(l.brand_id) or "— бренд не выбран",
            "plan": round(l.plan_amount or 0, 2), "fact": round(f, 2), "booked": round(bk, 2),
            "months_on": (list(l.months_on or []) + [0] * 12)[:12],
        })

    out = []
    for rep, a in acc.items():
        out.append({
            "rep_id": rep, "rep_name": rep_names.get(rep, "Без сейлза") if rep else "Без сейлза",
            "plan": round(a["plan"], 2), "fact": round(a["fact"], 2), "booked": round(a["booked"], 2),
            "months": [round(x, 2) for x in a["months"]],
            "advertisers": [{"advertiser_id": aid, "name": adv_names.get(aid, "— не выбран"),
                             "plan": round(v["plan"], 2), "fact": round(v["fact"], 2), "booked": round(v["booked"], 2),
                             "plans": [{**pk, "plan": round(pk["plan"], 2), "fact": round(pk["fact"], 2),
                                        "booked": round(pk["booked"], 2)}
                                       for pk in sorted(v["plans"].values(), key=lambda p: -p["plan"])]}
                            for aid, v in sorted(a["advs"].items(), key=lambda kv: -kv[1]["plan"])],
        })
    out.sort(key=lambda r: -r["plan"])
    return {"year": year, "reps": out}
