# -*- coding: utf-8 -*-
"""История блока окна контрагента — «было → стало» из журнала действий (`audit_log`), новые сверху.

Своего журнала окно не ведёт: строки пишут существующие ручки. Блок — набор сущностей журнала: юрлицо и подписанты —
контрагент (подписанты — по действию `*signer*`), договоры и выбор шаблона — его договоры, агентство, рекламодатели с
брендами, правила СК. Подробности вида «поле: было → стало» разбираются на строки; «—» — пусто.
"""
import re
from typing import List, Optional, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import AuditLog, Contract
from app.timez import to_msk

_CHANGE = re.compile(r"^(?P<what>.+?): (?P<before>.*?) → (?P<after>.*)$")
_EMPTY = ("—", "-", "")
LIMIT = 30


def _empty(v: str) -> Optional[str]:
    v = v.strip()
    return None if v in _EMPTY else v


def parse(details: Optional[str]) -> List[Tuple[str, Optional[str], Optional[str]]]:
    """`(what, from, to)` по каждой части «поле: было → стало»; без стрелки — вся строка в `what`."""
    parts = [p.strip() for p in (details or "").split("; ") if p.strip()]
    changes = [m for m in (_CHANGE.match(p) for p in parts) if m]
    if not changes:
        return [((details or "").strip() or "изменено", None, None)]
    return [(m["what"], _empty(m["before"]), _empty(m["after"])) for m in changes]


def _filters(db: Session, cp_id: int, block: str) -> list:
    from app.readiness import market as M
    from app.models import Counterparty
    is_signer = AuditLog.action.ilike("%signer%")
    if block in ("cp", "sg"):
        own = and_(AuditLog.entity_type == "counterparty", AuditLog.entity_id == cp_id)
        return [and_(own, is_signer if block == "sg" else ~is_signer)]
    if block in ("ct", "tpl", "ord"):
        ids = [i for (i,) in db.query(Contract.id).filter(Contract.counterparty_id == cp_id)]
        if not ids:
            return []
        on = and_(AuditLog.entity_type == "contract", AuditLog.entity_id.in_(ids))
        # события ОРД тоже пишутся на договор — в «Договорах» их нет: видны только с правом ОРД (ревью 05.11)
        pick = {"ct": and_(~AuditLog.action.ilike("annex%"), ~AuditLog.action.ilike("ord%")), "tpl": AuditLog.action == "annex_tpl_choice",
                "ord": AuditLog.action.ilike("ord%")}[block]
        return [and_(on, pick)]
    cp = db.get(Counterparty, cp_id)
    if block == "ag":
        ids = M._agency_ids(db, cp)
        return [and_(AuditLog.entity_type == "sales_agency", AuditLog.entity_id.in_(ids))] if ids else []
    if block == "ad":
        advs = M.ad_data(db, cp)
        brands = [b["id"] for a in advs for b in a["brands"]]
        out = [and_(AuditLog.entity_type == "sales_advertiser", AuditLog.entity_id.in_([a["id"] for a in advs]))] if advs else []
        return out + ([and_(AuditLog.entity_type == "sales_brand", AuditLog.entity_id.in_(brands))] if brands else [])
    if block == "sk":
        ids = [r["id"] for r in M.sk_data(db, cp)]
        return [and_(AuditLog.entity_type == "sk_rule", AuditLog.entity_id.in_(ids))] if ids else []
    return []


def of_block(db: Session, cp_id: int, block: str, limit: int = LIMIT) -> List[dict]:
    where = _filters(db, cp_id, block)
    if not where:
        return []
    out = []
    for a in (db.query(AuditLog).filter(or_(*where)).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
              .limit(limit).all()):
        at = f"{to_msk(a.created_at):%d.%m.%Y %H:%M}" if a.created_at else ""
        for what, before, after in parse(a.details):
            out.append({"at": at, "who": a.user_name or "система", "what": what, "from": before, "to": after})
    return out[:limit]
