# -*- coding: utf-8 -*-
"""Окно контрагента — сборка ответа (форма `sampleReadiness` дизайнера, но `kinds: list` вместо `kind`).

Вид юрлица не один: ДПД МЕДИА — и агентство, и площадка, поэтому блоки — объединение блоков всех его видов.
Блок отдаётся только при праве `view` своего раздела и вместе со своими проверками: без права нет ни данных, ни алертов,
ни их доли в счётчиках (как в карточке договора, `contract_card/service.card`).
"""
import re
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Contract, Counterparty
from app.permissions import get_permissions_for_user
from app.readiness import contracts as RC
from app.readiness import history as H
from app.readiness import market as M
from app.readiness import party as P
from app.sales.models import (SalesAdvertiser, SalesAdvertiserCounterparty, SalesAgencyCounterparty, SalesBrand,
                              SalesPublisherCounterparty)
from app.timez import msk_now

# Блок → раздел прав. Тот же состав, что `BLOCKS` во `frontend/components/readiness/readinessSchema.js`.
SECTIONS = {"cp": "counterparties", "sg": "counterparties", "ct": "contracts", "tpl": "annex_templates",
            "ag": "dir_agencies", "ad": "dir_advertisers", "sk": "sk_terms", "ord": "ord"}
ORDER = list(SECTIONS)
# Рекламодатели — только у плательщика: агентство и рекламодатель независимы (владелец 04.11.2026).
MARKET = {"ag": {"agency"}, "ad": {"direct"}, "sk": {"agency", "direct"}, "ord": {"agency", "direct"}}
KIND_LABELS = {"contractor": "подрядчик", "agency": "агентство", "direct": "прямой рекламодатель", "publisher": "площадка"}
SOON_DAYS = 60
_DMY = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def kinds_of(db: Session, cp) -> List[str]:
    out = []
    for kind, model in (("agency", SalesAgencyCounterparty), ("direct", SalesAdvertiserCounterparty),
                        ("publisher", SalesPublisherCounterparty)):
        if db.query(model.id).filter(model.counterparty_id == cp.id).first():
            out.append(kind)
    return out or ["contractor"]


def blocks_for(kinds: List[str]) -> List[str]:
    return [b for b in ORDER if b not in MARKET or MARKET[b] & set(kinds)]


def _checks(db: Session, cp, kinds: List[str], blocks: List[str], on: date) -> List[dict]:
    out = []
    if "cp" in blocks:
        out += P.cp_checks(db, cp, on, kinds)
    if "sg" in blocks:
        out += P.sg_checks(db, cp, on)
    if "ct" in blocks:
        out += RC.ct_checks(db, cp, on)
    if "tpl" in blocks:
        out += RC.tpl_checks(db, cp)
    if {"ad", "sk", "ord"} & set(blocks):
        out += [c for c in M.checks(db, cp, on) if c["block"] in blocks]
    return out


def _subject(c: dict) -> str:
    s = c.get("subject") or c["title"].split(":")[0]
    return "договору " + s[len("договор "):] if s.startswith("договор ") else s     # «ДС по договору 103», не «по договор»


def headline(checks: List[dict]) -> str:
    bad = [c for c in checks if c["sev"] == "bad"]
    doc = [c for c in bad if c["block"] in ("ct", "tpl")]
    if doc:
        return f"ДС по {_subject(doc[0])} сейчас не собрать"
    erid = [c for c in bad if c["block"] in ("ad", "ord")]
    if erid:
        return f"ЕРИД по {_subject(erid[0])} не выпустится"
    if checks:
        return "документы соберутся"
    return "всё готово к документам и ОРД"


def _dmy(text: Optional[str]) -> Optional[date]:
    m = _DMY.search(text or "")
    try:
        return date(int(m[3]), int(m[2]), int(m[1])) if m else None
    except ValueError:
        return None


def expiring(data: dict, blocks: List[str], on: date) -> List[dict]:
    """Лента «истекает в 60 дней»: доверенности, основные правила СК, сроки договоров. `info` — продлится сам."""
    till = on + timedelta(days=SOON_DAYS)
    out = []

    def add(d, title, tone, hint, fix):
        if d and on <= d <= till:
            out.append({"date": f"{d:%d.%m.%Y}", "days": (d - on).days, "title": title, "tone": tone, "hint": hint, "fix": fix})
    if "sg" in blocks:
        for s in data["signers"]:
            if not s["archived"]:
                add(s["poa_until"], f"доверенность · {s['name'] or 'подписант'}", "warn",
                    "после этой даты подписант не сможет подписывать ДС", {"block": "sg", "ref": s["id"], "action": "new_poa"})
    if "sk" in blocks:
        for r in data["sk"]:
            if r.get("kind") == "основная":
                add(r.get("valid_to"), f"СК · правило {r.get('percent', 0):g} %", "warn",
                    "основное правило — после срока сделки пойдут без СК", {"block": "sk", "ref": r["id"]})
    if "ct" in blocks:
        for c in data["contracts"]:
            auto = "авто" in (c["prolongation"] or "").lower()
            add(_dmy(c["valid_until"]), f"{c['number'] or c['id']} · срок", "info" if auto else "warn",
                "пролонгация авто — продлится сам" if auto else "без пролонгации — после срока размещения без основания",
                {"block": "ct", "ref": c["id"], "field": "valid_until"})
    return sorted(out, key=lambda x: x["days"])


def _points(data: dict, blocks: List[str], kinds: List[str]) -> int:
    """Сколько пунктов проверено — для «ок» в сводке (`total − горит − скоро`). Пункты — те, что разбирают
    `party`/`contracts`/`market`; по числу их условий на единицу данных."""
    n = {"cp": 6 + ("publisher" in kinds), "sg": 1 + sum(1 for s in data.get("signers", []) if s["poa_until"]),
         "ct": 10 * len(data.get("contracts", [])), "tpl": len(data.get("contracts", [])),
         "ag": 0, "ad": sum(1 + sum(b["active"] for b in a["brands"]) for a in data.get("advertisers", [])),
         "sk": len(data.get("contracts", [])) + len(data.get("sk", [])),
         "ord": len((data.get("ord") or {}).get("contracts", [])) + len((data.get("ord") or {}).get("initial", []))}
    return sum(n[b] for b in blocks)


def _data(db: Session, cp, blocks: List[str]) -> dict:
    # Шапка окна (имя, ИНН, статус) — всегда: без права на контрагентов блока «Юрлицо» нет, но окно чьё-то (ревью 05.11).
    out: Dict = {"counterparty": {"id": cp.id, "name": cp.name, "inn": cp.inn, "kpp": cp.kpp, "status": cp.status}}
    if "cp" in blocks:
        c = P.cp_data(db, cp)
        out["banks"] = c.pop("banks")
        out["counterparty"] = c
    if "sg" in blocks:
        out["signers"] = P.sg_data(db, cp)
    if "ct" in blocks:
        out["contracts"] = RC.ct_data(db, cp)
    if "tpl" in blocks:
        out["templates"] = RC.tpl_data(db, cp)["templates"]
    if "ag" in blocks:
        out["agency"] = M.ag_data(db, cp)
    if "ad" in blocks:
        out["advertisers"] = M.ad_data(db, cp)
    if "sk" in blocks:
        out["sk"] = M.sk_data(db, cp)
    if "ord" in blocks:
        out["ord"] = M.ord_data(db, cp)
    return out


def _signer_options(db: Session, cp_id: Optional[int]) -> List[dict]:
    from app.signers import service as SG
    if not cp_id:
        return []
    return [{"id": s.id, "label": f"{s.director_name} — {s.signer_position}" if s.signer_position else s.director_name}
            for s in SG.list_of(db, cp_id) if s.director_name]


def options(db: Session, cp) -> dict:
    """Списки выбора подписантов договора: заказчика — подписанты этого юрлица, нашего — нашего юрлица
    (`own_company.sole`, юрлицо у нас одно; со вторым список станет по договору)."""
    from app import own_company
    us = own_company.sole(db)
    return {"signers": _signer_options(db, cp.id), "ourSigners": _signer_options(db, us.id if us else None)}


def _last_change(db: Session, cp_id: int, blocks: List[str]) -> dict:
    out = {}
    for b in blocks:
        rows = H.of_block(db, cp_id, b, limit=1)
        if rows:
            out[b] = f"изменено {rows[0]['at'][:10]} · {rows[0]['who']}"
    return out


def build(db: Session, cp_id: int, user) -> Optional[dict]:
    cp = db.get(Counterparty, cp_id)
    if cp is None:
        return None
    perms = get_permissions_for_user(db, user)
    can = lambda s, a: bool((perms.get(s) or {}).get(a))  # noqa: E731
    on = msk_now().date()
    kinds = kinds_of(db, cp)
    blocks = [b for b in blocks_for(kinds) if can(SECTIONS[b], "view")]
    data = _data(db, cp, blocks)
    checks = _checks(db, cp, kinds, blocks, on)
    sections = sorted({SECTIONS[b] for b in blocks_for(kinds)})
    return {
        "mode": "check", "kinds": kinds, "blocks": blocks, **data, "checks": checks,
        "total": _points(data, blocks, kinds) or len(checks), "headline": headline(checks),
        "expiring": expiring(data, blocks, on), "today": f"{on:%d.%m.%Y}",
        "currentUser": {"id": user.id, "name": user.name},
        "permissions": {"view": [s for s in sections if can(s, "view")], "edit": [s for s in sections if can(s, "edit")]},
        "lastChange": _last_change(db, cp.id, blocks),
        "options": options(db, cp) if "ct" in blocks else {"signers": [], "ourSigners": []},
    }


def build_many(db: Session, ids: List[int]) -> Dict[int, dict]:
    """`{bad, warn}` по каждому — для значка в реестре; все блоки, как у админа."""
    on = msk_now().date()
    out = {}
    for cp in db.query(Counterparty).filter(Counterparty.id.in_(list(ids) or [0])).all():
        kinds = kinds_of(db, cp)
        cs = _checks(db, cp, kinds, blocks_for(kinds), on)
        out[cp.id] = {"bad": sum(c["sev"] == "bad" for c in cs), "warn": sum(c["sev"] == "warn" for c in cs)}
    return out


def lookup(db: Session, inn: str, kpp: Optional[str] = None, see_advertisers: bool = True) -> dict:
    """Дубли при заведении: юрлица с тем же ИНН (`exact` — и КПП тот же; другой КПП — филиал) и рекламодатели с ним."""
    inn = (inn or "").strip()
    if len(inn) < 10:
        return {"counterparties": [], "advertisers": []}
    cps = db.query(Counterparty).filter(Counterparty.inn == inn).order_by(Counterparty.id).all()
    n_ct = dict(db.query(Contract.counterparty_id, func.count(Contract.id))
                .filter(Contract.counterparty_id.in_([c.id for c in cps] or [0])).group_by(Contract.counterparty_id).all())
    want = (kpp or "").strip()
    rows = [{"id": c.id, "inn": c.inn, "kpp": c.kpp, "name": c.name, "exact": bool(want) and (c.kpp or "") == want,
             "info": " · ".join([", ".join(KIND_LABELS[k] for k in kinds_of(db, c)), _plural_contracts(n_ct.get(c.id, 0))])}
            for c in cps]
    # Рекламодатели — только с правом на их справочник (ревью 05.11.2026): иначе поиск дублей показывал их всем с «Добавить данные».
    advs = db.query(SalesAdvertiser).filter(SalesAdvertiser.inn == inn).order_by(SalesAdvertiser.id).all() if see_advertisers else []
    n_br = dict(db.query(SalesBrand.advertiser_id, func.count(SalesBrand.id))
                .filter(SalesBrand.advertiser_id.in_([a.id for a in advs] or [0])).group_by(SalesBrand.advertiser_id).all())
    return {"counterparties": sorted(rows, key=lambda r: not r["exact"]),
            "advertisers": [{"id": a.id, "inn": a.inn, "name": a.short_name or a.name,
                             "info": f"брендов: {n_br.get(a.id, 0)}"} for a in advs]}


def _plural_contracts(n: int) -> str:
    word = "договор" if n % 10 == 1 and n % 100 != 11 else (
        "договора" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "договоров")
    return f"{n} {word}"

