# -*- coding: utf-8 -*-
"""«Продажи → Агентские условия» (владелец 27.10.2026, docs/СХЕМА_СК.md): правила СК, спец. условия, расчёт за месяц и
квартал, закрытый месяц, Excel. Логика — `app/agency_terms`, здесь двери, права и журнал.

Права: `sk_terms` — смотреть (продажи и аккаунты) / править правила и закрывать месяц (мастера); `sk_special` — скрытая
вкладка спец. условий; открыть закрытый месяц заново — только админ."""
from datetime import date
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agency_terms import calc as C
from app.agency_terms import service as S
from app.agency_terms.models import SkSpecialTerm, SkWorkTerm
from app.audit import log_action, require_admin
from app.database import get_db
from app.models import User
from app.permissions import require_any_permission, require_permission

router = APIRouter()
VIEW = require_permission("sk_terms", "view")
EDIT = require_permission("sk_terms", "edit")
SPECIAL_VIEW = require_permission("sk_special", "view")
SPECIAL_EDIT = require_permission("sk_special", "edit")
# Плашка «Условия работы» в конструкторе МП — всем, кто открывает медиаплан (владелец 27.10.2026)
MP_VIEW = require_any_permission(("media_plans", "media_plans_editor", "sk_terms"), "view")


def _err(e):
    raise HTTPException(e.status, e.message)


class RuleIn(BaseModel):
    kind: str
    contract_id: Optional[int] = None
    agency_id: Optional[int] = None
    advertiser_id: Optional[int] = None
    brand_id: Optional[int] = None
    service_id: Optional[int] = None
    recipient_id: Optional[int] = None
    mode: str
    percent: float
    valid_from: date
    valid_to: Optional[date] = None
    note: Optional[str] = None


class SpecialIn(BaseModel):
    scope_kind: str
    scope_id: int
    title: str
    percent: Optional[float] = None
    amount: Optional[float] = None
    threshold: Optional[float] = None
    valid_from: date
    valid_to: Optional[date] = None
    note: Optional[str] = None


def _rule_text(r: dict) -> str:
    """Запись журнала. Журнал видят по праву «Журнал», не «Спец. условия» (ревью 27.10.2026) — по партнёрской СК только номер."""
    if r.get("kind") == "партнёрская":
        return f"СК партнёрская: правило №{r.get('id')} сохранено"
    who = ", ".join(f"{k.replace('_id', '')} {r[k]}" for k in ("contract_id", "agency_id", "advertiser_id", "brand_id",
                                                               "service_id") if r.get(k))
    to = f" по {r['valid_to']}" if r.get("valid_to") else ""
    return f"СК {r['kind']}: {who} — {r['mode']} {r['percent']:g} % с {r['valid_from']}{to}"


@router.get("/options")
def options(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    return S.options(db)


@router.get("/tree")
def tree(side: str = "agency", db: Session = Depends(get_db), user: User = Depends(VIEW)):
    try:
        return {"side": side, "items": S.tree(db, side)}
    except S.TermsError as e:
        _err(e)


# Партнёрская СК — во вкладке «Спец. условия» и по её праву (хендофф 27.10.2026): общие ручки правил — только основная.
PARTNER_ELSEWHERE = "Партнёрская СК правится во вкладке «Спец. условия»"


def _kind_of(db: Session, rule_id: int) -> Optional[str]:
    from app.agency_terms.models import SkRule
    r = db.get(SkRule, rule_id)
    return r.kind if r else None


def _save(db, payload: dict, user, rule_id: Optional[int] = None):
    try:
        r = S.save_rule(db, payload, user, rule_id)
    except S.TermsError as e:
        db.rollback()
        _err(e)
    log_action(db, user, "agency_terms_rule_save", "sk_rule", r.id, _rule_text(S.rule_dict(r)))
    db.commit()
    return S.rule_dict(r)


def _delete(db, rule_id: int, user):
    try:
        S.delete_rule(db, rule_id)
    except S.TermsError as e:
        db.rollback()
        _err(e)
    log_action(db, user, "agency_terms_rule_delete", "sk_rule", rule_id, f"Правило СК №{rule_id} удалено")
    db.commit()
    return {"ok": True}


@router.get("/rules")
def rules(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    return [r for r in S.all_rules(db) if r["kind"] == "основная"]


@router.post("/rules")
def rule_create(payload: RuleIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    if payload.kind != "основная":
        raise HTTPException(400, PARTNER_ELSEWHERE)
    return _save(db, payload.dict(), user)


@router.put("/rules/{rule_id}")
def rule_update(rule_id: int, payload: RuleIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    if payload.kind != "основная" or _kind_of(db, rule_id) == "партнёрская":
        raise HTTPException(400, PARTNER_ELSEWHERE)
    return _save(db, payload.dict(), user, rule_id)


@router.delete("/rules/{rule_id}")
def rule_delete(rule_id: int, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    if _kind_of(db, rule_id) == "партнёрская":
        raise HTTPException(400, PARTNER_ELSEWHERE)
    return _delete(db, rule_id, user)


@router.get("/special/partner")
def partner_rules(db: Session = Depends(get_db), user: User = Depends(SPECIAL_VIEW)):
    return [r for r in S.all_rules(db) if r["kind"] == "партнёрская"]


@router.post("/special/partner")
def partner_create(payload: RuleIn, db: Session = Depends(get_db), user: User = Depends(SPECIAL_EDIT)):
    return _save(db, {**payload.dict(), "kind": "партнёрская"}, user)


@router.put("/special/partner/{rule_id}")
def partner_update(rule_id: int, payload: RuleIn, db: Session = Depends(get_db), user: User = Depends(SPECIAL_EDIT)):
    if _kind_of(db, rule_id) != "партнёрская":
        raise HTTPException(404, "Партнёрское правило не найдено")
    return _save(db, {**payload.dict(), "kind": "партнёрская"}, user, rule_id)


@router.delete("/special/partner/{rule_id}")
def partner_delete(rule_id: int, db: Session = Depends(get_db), user: User = Depends(SPECIAL_EDIT)):
    if _kind_of(db, rule_id) != "партнёрская":
        raise HTTPException(404, "Партнёрское правило не найдено")
    return _delete(db, rule_id, user)


@router.get("/special/calc")
def special_calc(period: str, db: Session = Depends(get_db), user: User = Depends(SPECIAL_VIEW)):
    from app.agency_terms.special import calc_special
    try:
        return calc_special(db, period)
    except C.CalcError as e:
        _err(e)


@router.get("/calc")
def calc(period: str, agency_id: Optional[int] = None, advertiser_id: Optional[int] = None, entity_id: Optional[int] = None,
         contract_id: Optional[int] = None, mode: Optional[str] = None,
         db: Session = Depends(get_db), user: User = Depends(VIEW)):
    try:
        return C.calc(db, period, {"agency_id": agency_id, "advertiser_id": advertiser_id, "entity_id": entity_id,
                                   "contract_id": contract_id, "mode": mode})
    except C.CalcError as e:
        _err(e)


@router.get("/calc.xlsx")
def calc_xlsx(period: str, agency_id: Optional[int] = None, advertiser_id: Optional[int] = None,
              entity_id: Optional[int] = None, contract_id: Optional[int] = None, mode: Optional[str] = None,
              db: Session = Depends(get_db), user: User = Depends(VIEW)):
    from app.agency_terms import xlsx
    try:
        body = xlsx.export(db, period, {"agency_id": agency_id, "advertiser_id": advertiser_id, "entity_id": entity_id,
                                        "contract_id": contract_id, "mode": mode})
    except C.CalcError as e:
        _err(e)
    human = f"СК {period}.xlsx"
    return Response(content=body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=\"sk_{period}.xlsx\"; filename*=UTF-8''{quote(human)}"})


@router.post("/months/{period}/close")
def month_close(period: str, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    try:
        n = C.close_month(db, period, user)
    except C.CalcError as e:
        db.rollback()
        _err(e)
    log_action(db, user, "agency_terms_month_close", "sk_month", None, f"СК за {period}: месяц закрыт, строк снимка {n}")
    db.commit()
    return {"period": period, "rows": n}


@router.delete("/months/{period}")
def month_reopen(period: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    try:
        C.reopen_month(db, period)
    except C.CalcError as e:
        db.rollback()
        _err(e)
    log_action(db, user, "agency_terms_month_reopen", "sk_month", None, f"СК за {period}: месяц открыт заново, снимок снят")
    db.commit()
    return {"period": period, "reopened": True}


# ── спец. условия — скрытая вкладка ─────────────────────────────────────────────────────────────────

@router.get("/special")
def special(db: Session = Depends(get_db), user: User = Depends(SPECIAL_VIEW)):
    return [S.special_dict(s) for s in db.query(SkSpecialTerm).order_by(SkSpecialTerm.id).all()]


@router.post("/special")
def special_create(payload: SpecialIn, db: Session = Depends(get_db), user: User = Depends(SPECIAL_EDIT)):
    try:
        s = S.save_special(db, payload.dict(), user)
    except S.TermsError as e:
        db.rollback()
        _err(e)
    log_action(db, user, "agency_terms_special_save", "sk_special", s.id, f"Спец. условие №{s.id} сохранено")
    db.commit()
    return S.special_dict(s)


@router.put("/special/{sid}")
def special_update(sid: int, payload: SpecialIn, db: Session = Depends(get_db), user: User = Depends(SPECIAL_EDIT)):
    try:
        s = S.save_special(db, payload.dict(), user, sid)
    except S.TermsError as e:
        db.rollback()
        _err(e)
    log_action(db, user, "agency_terms_special_save", "sk_special", s.id, f"Спец. условие №{s.id} сохранено")
    db.commit()
    return S.special_dict(s)


@router.delete("/special/{sid}")
def special_delete(sid: int, db: Session = Depends(get_db), user: User = Depends(SPECIAL_EDIT)):
    s = db.get(SkSpecialTerm, sid)
    if s is None:
        raise HTTPException(404, "Условие не найдено")
    db.delete(s)
    log_action(db, user, "agency_terms_special_delete", "sk_special", sid, f"Спец. условие №{sid} удалено")
    db.commit()
    return {"ok": True}


# ── «Условия работы» ────────────────────────────────────────────────────────────────────────────────

class WorkIn(BaseModel):
    contract_id: Optional[int] = None
    agency_id: Optional[int] = None
    advertiser_id: Optional[int] = None
    brand_id: Optional[int] = None
    service_id: Optional[int] = None
    body: str
    mail_subject: Optional[str] = None
    commit_net: Optional[float] = None
    comment: Optional[str] = None
    valid_from: date
    valid_to: Optional[date] = None
    creatives_bonus: bool = False
    creatives_bonus_note: Optional[str] = None
    reports_bonus: bool = False
    reports_bonus_note: Optional[str] = None


@router.get("/work")
def work(db: Session = Depends(get_db), user: User = Depends(VIEW)):
    return S.all_work(db)


@router.get("/work/active")
def work_active(db: Session = Depends(get_db), user: User = Depends(MP_VIEW)):
    """Для плашки под брифом МП: все условия, подбор по сделке и периоду — на экране (бриф меняется на лету)."""
    return S.all_work(db)


def _work_save(db, payload: WorkIn, user, wid: Optional[int] = None):
    try:
        w = S.save_work(db, payload.dict(), user, wid)
    except S.TermsError as e:
        db.rollback()
        _err(e)
    log_action(db, user, "agency_terms_work_save", "sk_work_term", w.id, f"Условие работы: {w.body[:120]}")
    db.commit()
    return S.work_dict(w)


@router.post("/work")
def work_create(payload: WorkIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    return _work_save(db, payload, user)


@router.put("/work/{wid}")
def work_update(wid: int, payload: WorkIn, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    return _work_save(db, payload, user, wid)


@router.delete("/work/{wid}")
def work_delete(wid: int, db: Session = Depends(get_db), user: User = Depends(EDIT)):
    w = db.get(SkWorkTerm, wid)
    if w is None:
        raise HTTPException(404, "Условие не найдено")
    body = w.body
    db.delete(w)
    log_action(db, user, "agency_terms_work_delete", "sk_work_term", wid, f"Условие работы удалено: {body[:120]}")
    db.commit()
    return {"ok": True}

