"""Годовой план продаж: план по рекламодателям/брендам с разбивкой по 12 месяцам.

Персональный: строка плана принадлежит сейлзу (sales_rep_id). Обычный сейлз видит и
правит только свой план; «мастер» (право year_plan.deals_scope='all' или admin) может
выбрать чей план смотреть/править, а также режим «Показать все» — сводная read-only
агрегация по всем сейлзам. Механика владения — та же, что у дашборда (SalesRep.user_id).

Хранение — одна строка на пару рекламодатель×бренд×год×сейлз (SalesYearPlanLine).
Факт/бронь не вычисляются на лету: по кнопке «Обновить данные о сделках» реальные сделки
сейлза метчатся с его строками плана и результат замораживается в поле `deals` (статика).

Слой денег — из маппинга стадий (SalesBitrixStageMap.money_layer): «фактические» →
закрытая сделка (closed=1, идёт в факт), остальное → бронь (closed=0).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session
from typing import Optional, List, Dict

from app.database import get_db
from app.routers.auth import get_current_user
from app.permissions import require_permission
from app.audit import log_action
from app.models import User, RolePermission
from app.sales.models import (SalesYearPlanLine, SalesAdvertiser, SalesBrand,
                              SalesService, SalesDeal, SalesStage, SalesRep)

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
    """→ (effective_rep_id, is_master). Не-мастер всегда прижат к своему сейлзу.
    Мастер: rep_id как передан (None — свой по умолчанию, если сам сейлз)."""
    master = _is_master(db, user)
    own = _own_rep_ids(db, user)
    if not master:
        return (own[0] if own else -1), False   # -1 → нет привязки, пустой план
    if rep_id is not None:
        return rep_id, True
    return (own[0] if own else None), True       # мастер без явного выбора → свой (или None)


# ── сериализация ─────────────────────────────────────────────────────────
def _line_out(l: SalesYearPlanLine) -> dict:
    return {
        "id": l.id,
        "advertiser_id": l.advertiser_id,
        "brand_id": l.brand_id,
        "plan_amount": l.plan_amount or 0,
        "months_on": (list(l.months_on or []) + [0] * 12)[:12],
        "sums": l.sums or {},
        "locks": l.locks or {},
        "products": l.products or {},
        "deals": l.deals or {},
        "sort_order": l.sort_order or 0,
    }


def _catalog(db: Session) -> dict:
    advs = (db.query(SalesAdvertiser)
            .filter(SalesAdvertiser.is_active.is_(True))
            .order_by(func.coalesce(SalesAdvertiser.short_name, SalesAdvertiser.name)).all())
    brands = (db.query(SalesBrand).filter(SalesBrand.is_active.is_(True))
              .order_by(SalesBrand.name).all())
    by_adv: Dict[int, list] = {}
    for b in brands:
        by_adv.setdefault(b.advertiser_id, []).append({"id": b.id, "name": b.name})
    services = (db.query(SalesService).filter(SalesService.is_active.is_(True))
                .order_by(SalesService.sort_order, SalesService.name).all())
    return {
        "advertisers": [{"id": a.id, "name": a.short_name or a.name,
                         "brands": by_adv.get(a.id, [])} for a in advs],
        "services": [{"id": s.id, "name": s.name} for s in services],
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
    return {
        "year": year, "lines": [_line_out(l) for l in lines], "catalog": _catalog(db),
        "me": {"is_master": master, "rep_id": eff_rep,
               "own_rep_id": (_own_rep_ids(db, current_user) or [None])[0]},
        "reps": _reps(db) if master else [],
    }


@router.get("/years")
def list_years(db: Session = Depends(get_db), current_user: User = Depends(YP_VIEW)):
    rows = (db.query(SalesYearPlanLine.year).distinct()
            .order_by(SalesYearPlanLine.year.desc()).all())
    return {"years": [r[0] for r in rows]}


# ── сводка по всем сейлзам (только мастер) ───────────────────────────────
@router.get("/all")
def get_all_reps(year: int, db: Session = Depends(get_db),
                 current_user: User = Depends(YP_VIEW)):
    """Read-only агрегация плана по всем сейлзам за год: план/факт/бронь на сейлза
    (и разбивка по рекламодателям внутри). Факт/бронь — из замороженного поля deals."""
    if not _is_master(db, current_user):
        raise HTTPException(status_code=403, detail="Режим «Показать все» доступен только мастеру")

    lines = db.query(SalesYearPlanLine).filter(SalesYearPlanLine.year == year).all()
    rep_names = {r.id: r.name for r in db.query(SalesRep).all()}
    adv_names = {a.id: (a.short_name or a.name) for a in db.query(SalesAdvertiser).all()}

    def fact_booked(l):
        deals = (l.deals or {}).values()
        f = sum(d[1] for arr in deals for d in arr if d[2])
        b = sum(d[1] for arr in deals for d in arr if not d[2])
        return f, b

    # rep_id → {plan, fact, booked, months[12], advs: {advertiser_id: {...}}}
    acc: Dict[Optional[int], dict] = {}
    for l in lines:
        rep = l.sales_rep_id
        a = acc.setdefault(rep, {"plan": 0.0, "fact": 0.0, "booked": 0.0,
                                 "months": [0.0] * 12, "advs": {}})
        f, bk = fact_booked(l)
        a["plan"] += l.plan_amount or 0
        a["fact"] += f
        a["booked"] += bk
        # помесячный план строки (та же формула, что на фронте: сумма/распределение)
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
        av = a["advs"].setdefault(l.advertiser_id, {"plan": 0.0, "fact": 0.0, "booked": 0.0})
        av["plan"] += l.plan_amount or 0
        av["fact"] += f
        av["booked"] += bk

    out = []
    for rep, a in acc.items():
        out.append({
            "rep_id": rep, "rep_name": rep_names.get(rep, "Без сейлза") if rep else "Без сейлза",
            "plan": round(a["plan"], 2), "fact": round(a["fact"], 2), "booked": round(a["booked"], 2),
            "months": [round(x, 2) for x in a["months"]],
            "advertisers": [{"advertiser_id": aid, "name": adv_names.get(aid, "— не выбран"),
                             "plan": round(v["plan"], 2), "fact": round(v["fact"], 2), "booked": round(v["booked"], 2)}
                            for aid, v in sorted(a["advs"].items(), key=lambda kv: -kv[1]["plan"])],
        })
    out.sort(key=lambda r: -r["plan"])
    return {"year": year, "reps": out}


# ── сохранение (replace-all за год для одного сейлза) ─────────────────────
class LineIn(BaseModel):
    advertiser_id: Optional[int] = None
    brand_id: Optional[int] = None
    plan_amount: float = 0
    months_on: List[int] = []
    sums: Dict[str, float] = {}
    locks: Dict[str, int] = {}
    products: Dict[str, List[int]] = {}
    deals: Dict[str, List[list]] = {}
    sort_order: int = 0


class SaveIn(BaseModel):
    year: int
    rep_id: Optional[int] = None
    lines: List[LineIn] = []


@router.post("")
def save_year_plan(payload: SaveIn, db: Session = Depends(get_db),
                   current_user: User = Depends(YP_EDIT)):
    """Полная перезапись строк за (год, сейлз). Не-мастер прижат к своему сейлзу."""
    eff_rep, master = _resolve_rep(db, current_user, payload.rep_id)
    if eff_rep is None or eff_rep < 0:
        raise HTTPException(status_code=400, detail="Не удалось определить сейлза для сохранения плана")

    q = db.query(SalesYearPlanLine).filter(SalesYearPlanLine.year == payload.year,
                                           SalesYearPlanLine.sales_rep_id == eff_rep)
    q.delete(synchronize_session=False)
    for i, ln in enumerate(payload.lines):
        months = (ln.months_on or [])[:12]
        months = months + [0] * (12 - len(months))
        db.add(SalesYearPlanLine(
            year=payload.year, sales_rep_id=eff_rep,
            advertiser_id=ln.advertiser_id, brand_id=ln.brand_id,
            plan_amount=ln.plan_amount or 0, months_on=months,
            sums=ln.sums or {}, locks=ln.locks or {}, products=ln.products or {},
            deals=ln.deals or {}, sort_order=ln.sort_order if ln.sort_order else i,
            created_by=current_user.id,
        ))
    db.commit()
    log_action(db, current_user, "year_plan_save", "year_plan", payload.year,
               f"сейлз {eff_rep}, строк: {len(payload.lines)}")
    lines = (db.query(SalesYearPlanLine)
             .filter(SalesYearPlanLine.year == payload.year, SalesYearPlanLine.sales_rep_id == eff_rep)
             .order_by(SalesYearPlanLine.sort_order, SalesYearPlanLine.id).all())
    return {"year": payload.year, "rep_id": eff_rep, "lines": [_line_out(l) for l in lines]}


# ── метч сделок → статика факта/брони (в разрезе сейлза) ──────────────────
class MatchIn(BaseModel):
    year: int
    rep_id: Optional[int] = None
    pairs: List[List[Optional[int]]] = []


@router.post("/match-deals")
def match_deals(payload: MatchIn, db: Session = Depends(get_db),
                current_user: User = Depends(YP_EDIT)):
    """Метч сделок сейлза под его строки плана: по (advertiser_id, brand_id) и году
    period_from. Факт/бронь считаются ТОЛЬКО по сделкам этого сейлза (sales_rep_id или
    account_manager_id), чтобы выполнение было персональным. closed=1 → «фактические»."""
    eff_rep, _master = _resolve_rep(db, current_user, payload.rep_id)
    # матч всегда в разрезе конкретного сейлза (пишем факт в его план). Нет сейлза —
    # нечего и во что метчить: пустой результат, а НЕ выборка сделок всех сейлзов.
    if eff_rep is None or eff_rep < 0:
        return {"matched": [], "deals_count": 0}
    wanted = {(p[0], p[1] if len(p) > 1 else None) for p in payload.pairs
              if p and p[0] is not None}
    adv_ids = {a for a, _ in wanted}
    if not adv_ids:
        return {"matched": [], "deals_count": 0}

    # Слой денег — от НАШЕЙ стадии сделки (our_stage — мастер), не от Битрикса.
    q = (db.query(SalesDeal, SalesStage.money_layer.label("layer"))
         .outerjoin(SalesStage, SalesStage.id == SalesDeal.our_stage_id)
         .filter(SalesDeal.advertiser_id.in_(adv_ids))
         .filter(SalesDeal.period_from.isnot(None))
         .filter(func.extract("year", SalesDeal.period_from) == payload.year)
         .filter(or_(SalesDeal.sales_rep_id == eff_rep,
                     SalesDeal.account_manager_id == eff_rep)))
    rows = q.all()

    acc: Dict[tuple, Dict[str, list]] = {}
    total = 0
    for deal, layer in rows:
        key = (deal.advertiser_id, deal.brand_id)
        if key not in wanted:
            if (deal.advertiser_id, None) in wanted:
                key = (deal.advertiser_id, None)
            else:
                continue
        m = str(deal.period_from.month - 1)
        closed = 1 if layer == FACT_LAYER else 0
        acc.setdefault(key, {}).setdefault(m, []).append(
            [deal.bitrix_id, round(deal.amount or 0, 2), closed])
        total += 1

    matched = [{"advertiser_id": adv, "brand_id": br, "deals": months}
               for (adv, br), months in acc.items()]
    log_action(db, current_user, "year_plan_match_deals", "year_plan", payload.year,
               f"сейлз {eff_rep}, сделок: {total} на пар: {len(matched)}")
    return {"matched": matched, "deals_count": total}
