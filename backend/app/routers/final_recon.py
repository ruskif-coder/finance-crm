# -*- coding: utf-8 -*-
"""Итоговая сверка (спринт 4). Логика — пакет `app/final_recon`; здесь только HTTP. Сейчас: СК юрлица и СК сделки на закрытии."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit import log_action, require_admin
from app.database import get_db
from app.final_recon import assembly as ASM
from app.final_recon import closing as CL
from app.final_recon import flow as FLOW
from app.final_recon import launch as LAUNCH
from app.final_recon import sk as SK
from app.models import Counterparty, User
from app.permissions import require_permission
from app.routers.sales_dashboard import _assert_deal_in_scope
from app.sales.models import SalesDeal

router = APIRouter()

DEAL_VIEW = require_permission("sales_registry", "view")
DEAL_EDIT = require_permission("sales_registry", "edit")
CP_EDIT = require_permission("counterparties", "edit")


class SkIn(BaseModel):
    mode: Optional[str] = None
    percent: Optional[float] = None


def _deal(db: Session, deal_id: int, user) -> SalesDeal:
    d = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    if not d:
        raise HTTPException(404, "Сделка не найдена")
    _assert_deal_in_scope(db, user, d)
    return d


def _fmt(mode, percent) -> str:
    return f"{mode or 'способ не задан'}, {'—' if percent is None else f'{percent:g} %'}"


@router.get("/deal/{deal_id}/sk")
def deal_sk(deal_id: int, db: Session = Depends(get_db), user: User = Depends(DEAL_VIEW)):
    return SK.of_deal(db, _deal(db, deal_id, user))


@router.put("/deal/{deal_id}/sk")
def set_deal_sk(deal_id: int, payload: SkIn, db: Session = Depends(get_db), user: User = Depends(DEAL_EDIT)):
    d = _deal(db, deal_id, user)
    was = SK.of_deal(db, d)
    try:
        SK.set_deal(db, d, payload.mode, payload.percent, user)
    except SK.SkError as e:
        raise HTTPException(e.status, e.message)
    db.commit()
    log_action(db, user, "deal_sk_set", "sales_deal", d.id,
               f"СК на закрытии: {_fmt(was['mode'], was['percent'])} → {_fmt(payload.mode, payload.percent)}")
    return SK.of_deal(db, d)


@router.put("/counterparty/{cp_id}/sk")
def set_counterparty_sk(cp_id: int, payload: SkIn, db: Session = Depends(get_db), user: User = Depends(CP_EDIT)):
    cp = db.query(Counterparty).filter(Counterparty.id == cp_id).first()
    if not cp:
        raise HTTPException(404, "Контрагент не найден")
    was = _fmt(cp.sk_mode, cp.sk_percent)
    try:
        SK.set_counterparty(cp, payload.mode, payload.percent)
    except SK.SkError as e:
        raise HTTPException(e.status, e.message)
    db.commit()
    log_action(db, user, "counterparty_sk_set", "counterparty", cp.id, f"{cp.name}: СК {was} → {_fmt(cp.sk_mode, cp.sk_percent)}")
    return {"sk_mode": cp.sk_mode, "sk_percent": cp.sk_percent}


class ClosingIn(BaseModel):
    mode: str                          # fact / plan / manual
    manual_net: Optional[float] = None
    manual_volume: Optional[float] = None
    reason: Optional[str] = None       # причина ручной суммы — в журнал


class BonusIn(BaseModel):
    mode: Optional[str] = None         # pct / qty / rub; пусто — бонус не заказан
    value: Optional[float] = None


def _privileged(user) -> bool:
    from app.sales import stage_move
    return stage_move.is_master(user)


@router.get("/deal/{deal_id}/closing")
def deal_closing(deal_id: int, db: Session = Depends(get_db), user: User = Depends(DEAL_VIEW)):
    """Блок «Итоговая сверка» карточки: итог по строкам МП, план/факт/бонус, вывод, пины суммы ДС (владелец 15.10.2026)."""
    d = _deal(db, deal_id, user)
    out = CL.compute(db, d)
    return {**out, "may_manual": _privileged(user), "master": _master_of(db, d)}


def _master_of(db: Session, d) -> Optional[dict]:
    """В какой мастер-сделке сделка (п. 40 плана: отметка «в мастер-сделке №…» в карточке)."""
    from app.master_deal import service as MS
    from app.master_deal.models import MasterDeal
    it = MS.item_of(db, d.id)
    if not it:
        return None
    m = db.get(MasterDeal, it.master_deal_id)
    # Кто собирает пакет (16.10.2026): если не аккаунт этой сделки — в карточке «собирает <кто>».
    from app.notify.master_deal import _owner_user_id
    by = db.get(User, m.created_by) if m.created_by else None
    st = MS.deal_status(db, d)
    # Своя сверка готова, а пакет ещё нет (владелец 21.10.2026: отметка вместо отдельной стадии) — каких сделок ждём.
    wait = [x["code"] for x in MS.gate(db, m)["wait"]] if st["state"] == "done" and m.status == "черновик" else []
    return {"code": m.code, "status": m.status, **st, "package_wait": wait,
            "by": (by.name or by.email) if by else None,
            "foreign": bool(by and by.id != _owner_user_id(db, d))}


@router.put("/deal/{deal_id}/closing")
def set_deal_closing(deal_id: int, payload: ClosingIn, db: Session = Depends(get_db), user: User = Depends(DEAL_EDIT)):
    d = _deal(db, deal_id, user)
    if payload.mode == "manual" and not (payload.reason or "").strip():
        raise HTTPException(400, "Укажите причину ручной суммы")
    was = CL.compute(db, d)
    try:
        out = CL.set_mode(db, d, payload.mode, payload.manual_net, user, privileged=_privileged(user),
                         manual_volume=payload.manual_volume)
    except CL.ClosingError as e:
        raise HTTPException(e.status, e.message)
    db.commit()
    label = {"fact": "по факту", "plan": "под МП", "manual": "вручную"}
    log_action(db, user, "deal_closing_mode", "sales_deal", d.id,
               f"{d.code}: сумма в ДС {label[was['mode']]} {was['base_ds_net']} → {label[out['mode']]} {out['base_ds_net']}"
               + (f"; причина: {payload.reason.strip()}" if payload.reason else ""))
    return {**out, "may_manual": _privileged(user)}


class FactRowIn(BaseModel):
    row_id: int
    fact: float
    clicks: Optional[float] = None
    completed: Optional[float] = None          # досмотры 100 % (видео)
    reference_shows: Optional[float] = None    # показы справочно (фикс)


class FactIn(BaseModel):
    rows: List[FactRowIn]
    note: Optional[str] = None


@router.put("/deal/{deal_id}/fact")
def set_deal_fact(deal_id: int, payload: FactIn, db: Session = Depends(get_db), user: User = Depends(DEAL_EDIT)):
    """Факт по строкам МП, введённый аккаунтом, — для услуг без РК (владелец 19.10.2026)."""
    d = _deal(db, deal_id, user)
    try:
        out = CL.save_fact(db, d, {r.row_id: r.dict(exclude={"row_id"}) for r in payload.rows}, payload.note, user)
    except CL.ClosingError as e:
        db.rollback()
        raise HTTPException(e.status, e.message)
    db.commit()
    log_action(db, user, "deal_fact_entered", "sales_deal", d.id,
               f"{d.code}: факт " + ", ".join(f"строка {r.row_id} = {r.fact:g}" for r in payload.rows)
               + (f"; источник: {payload.note.strip()}" if (payload.note or "").strip() else ""))
    return {**out, "may_manual": _privileged(user), "master": _master_of(db, d)}


class CostIn(BaseModel):
    cost_net: Optional[float] = None


@router.put("/deal/{deal_id}/cost")
def set_deal_cost(deal_id: int, payload: CostIn, db: Session = Depends(get_db), user: User = Depends(DEAL_EDIT)):
    """Себестоимость сделки без НДС — вносит аккаунт на закрытии (19.10.2026)."""
    d = _deal(db, deal_id, user)
    was = CL.compute(db, d)["cost_net"]
    try:
        out = CL.save_cost(db, d, payload.cost_net, user)
    except CL.ClosingError as e:
        db.rollback()
        raise HTTPException(e.status, e.message)
    db.commit()
    log_action(db, user, "deal_cost_set", "sales_deal", d.id, f"{d.code}: себестоимость {was or '—'} → {out['cost_net'] or '—'}")
    return {**out, "may_manual": _privileged(user), "master": _master_of(db, d)}


class ConfirmIn(BaseModel):
    on: bool


@router.put("/deal/{deal_id}/closing/confirm")
def confirm_deal_closing(deal_id: int, payload: ConfirmIn, db: Session = Depends(get_db), user: User = Depends(DEAL_EDIT)):
    """«Подтвердить сверку» / снять подтверждение (клик по пину). Пишется в журнал: кто, когда, сумма, режим."""
    d = _deal(db, deal_id, user)
    try:
        out = CL.confirm(db, d, payload.on, user)
    except CL.ClosingError as e:
        raise HTTPException(e.status, e.message)
    db.commit()
    label = {"fact": "по факту", "plan": "под МП", "manual": "вручную"}
    log_action(db, user, "deal_closing_confirm", "sales_deal", d.id,
               f"{d.code}: сверка {'подтверждена' if payload.on else 'подтверждение снято'} — {label[out['mode']]}, к закрытию {out['total_gross']} с НДС")
    return {**out, "may_manual": _privileged(user)}


@router.put("/deal/{deal_id}/bonus-traffic")
def set_bonus_traffic(deal_id: int, payload: BonusIn, db: Session = Depends(get_db), user: User = Depends(DEAL_EDIT)):
    """Бонусный трафик — особенность РК: одно из трёх — % от плана, показы или сумма без НДС (владелец 15.10.2026)."""
    d = _deal(db, deal_id, user)
    mode = payload.mode or None
    if mode is not None and mode not in ("pct", "qty", "rub"):
        raise HTTPException(400, "Бонус: % от плана, показы или сумма")
    if mode and not (payload.value and payload.value > 0):
        raise HTTPException(400, "Укажите значение бонуса больше нуля")
    if mode == "pct" and payload.value > 100:
        raise HTTPException(400, "Бонус в процентах — не больше 100")
    was = (d.bonus_traffic_mode, d.bonus_traffic_value)
    d.bonus_traffic_mode, d.bonus_traffic_value = mode, (payload.value if mode else None)
    db.commit()
    log_action(db, user, "deal_bonus_traffic", "sales_deal", d.id, f"{d.code}: бонусный трафик {was[0] or '—'} {was[1] or ''} → {mode or '—'} {d.bonus_traffic_value or ''}")
    return {"mode": d.bonus_traffic_mode, "value": d.bonus_traffic_value}


@router.post("/deal/{deal_id}/close-no-docs")
def close_deal_no_docs(deal_id: int, db: Session = Depends(get_db), user: User = Depends(DEAL_EDIT)):
    """«Закрыть без документов»: бонусное размещение (к закрытию 0 ₽) — сверка замораживается, сделка в «Архив успешных сделок»."""
    from app.final_recon import no_docs as ND
    d = _deal(db, deal_id, user)
    try:
        out = ND.close(db, d, user)
    except CL.ClosingError as e:
        db.rollback()
        raise HTTPException(e.status, e.message)
    db.commit()
    log_action(db, user, "deal_closed_no_docs", "sales_deal", d.id, f"{d.code}: {ND.REASON} → «{out['moved_to'] or '—'}»")
    return {**out, "may_manual": _privileged(user), "master": _master_of(db, d)}


@router.get("/deal/{deal_id}/flow")
def deal_flow(deal_id: int, db: Session = Depends(get_db), user: User = Depends(DEAL_VIEW)):
    """Цикл услуги сделки и какая кнопка аккаунта сейчас доступна (`launch` / `finish` / None)."""
    d = _deal(db, deal_id, user)
    return {"flow": FLOW.of_deal(db, d), "action": LAUNCH.available(db, d)}


@router.post("/deal/{deal_id}/{action}")
def deal_action(deal_id: int, action: str, db: Session = Depends(get_db), user: User = Depends(DEAL_EDIT)):
    """«Запустить» / «Завершить» в контуре аккаунта — тем же путём, что диалог движения (требования, история, уведомления)."""
    d = _deal(db, deal_id, user)
    try:
        out = LAUNCH.run(db, d, action, user)
    except LAUNCH.LaunchError as e:
        raise HTTPException(e.status, e.message)
    db.commit()
    log_action(db, user, "deal_account_" + action, "sales_deal", d.id, f"{d.code}: → «{out['stage']}» (контур аккаунта)")
    return out


@router.get("/assembly")
def assembly_matrix(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Матрица «что требует учёта — по услугам»: все требования стадий по смысловым блокам и для каких услуг каждое действует.
    Только администратор (владелец 14.10.2026): матрица меняет правила движения сделок для всех."""
    return ASM.matrix(db)


class AssemblyStateIn(BaseModel):
    key: str
    service_id: int
    state: str          # off — не требуется, warn — уведомляет, block — требуется


@router.put("/assembly")
def assembly_set(payload: AssemblyStateIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    try:
        ASM.set_state(db, payload.key, payload.service_id, payload.state)
    except ASM.AssemblyError as e:
        raise HTTPException(e.status, e.message)
    db.commit()
    word = {"off": "не требуется", "warn": "уведомляет", "block": "требуется"}[payload.state]
    log_action(db, user, "assembly_check_toggle", "sales_service", payload.service_id, f"{payload.key}: {word}")
    return {"ok": True}
