# -*- coding: utf-8 -*-
"""Лента журнала действий (макет design_handoff_journal, 16.11.2026): два источника одним потоком.

Сотрудники — `audit_log`; кабинеты паблишеров — `cabinet_log`, только действия самих площадок (сторона «площадка»,
решение владельца 16.11.2026: наши уведомления площадкам — не их активность, они остаются на экране кабинетов).
Фильтры складываются по «И»: контур → период → кто → поиск → раздел → действие. Счётчики фильтров (`facets`) считает
сервер по тем же фильтрам, кроме собственного: у пина раздела — без фильтра раздела и действия, у списка «Кто» — без «кто».
Время в базе — UTC, дни выбирают по Москве: граница сдвигается на пояс (как в прежнем журнале).
"""
from dataclasses import dataclass, replace
from datetime import date, datetime, time as dt_time, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.journal import details as dt
from app.journal import sections as sc
from app.timez import MSK_OFFSET

PUB_SIDE = "площадка"


@dataclass(frozen=True)
class Query:
    contour: str = "staff"            # staff | cabinet | all
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    actor: Optional[str] = None       # «staff:12» | «cabinet:5»
    q: Optional[str] = None
    section: Optional[str] = None
    action: Optional[str] = None
    offset: int = 0
    limit: int = 200


_STAFF = ("SELECT 'staff' AS src, a.id, a.created_at AS at, a.user_id AS actor_id, a.user_name AS actor_name, "
          "CAST(NULL AS text) AS site, a.action, a.entity_type, a.entity_id, a.details FROM audit_log a")
_CAB = ("SELECT 'cabinet' AS src, l.id, l.created_at AS at, l.account_id AS actor_id, l.actor_name AS actor_name, "
        "p.domain AS site, l.action, l.entity_type, l.entity_id, l.subject AS details FROM cabinet_log l "
        "LEFT JOIN sales_publishers p ON p.id = l.publisher_id")


def _pat(q: str) -> str:
    return "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _known_actions(db: Session, src: str) -> list:
    if src == "staff":
        return db.execute(text("SELECT DISTINCT action FROM audit_log")).scalars().all()
    return db.execute(text("SELECT DISTINCT action FROM cabinet_log WHERE actor_side = :s"), {"s": PUB_SIDE}).scalars().all()


def _branch(db: Session, src: str, f: Query, p: dict, known: dict) -> Optional[str]:
    """SQL одного источника с фильтрами `f`, или None — источник отключён фильтром."""
    if f.contour not in ("all", src):
        return None
    pre = "a" if src == "staff" else "l"
    where = [f"{pre}.actor_side = :side"] if src == "cabinet" else []
    p["side"] = PUB_SIDE
    if f.date_from:
        p["dfrom"] = datetime.combine(f.date_from, dt_time()) - timedelta(hours=MSK_OFFSET)
        where.append(f"{pre}.created_at >= :dfrom")
    if f.date_to:
        p["dto"] = datetime.combine(f.date_to + timedelta(days=1), dt_time()) - timedelta(hours=MSK_OFFSET)
        where.append(f"{pre}.created_at < :dto")
    if f.actor:
        kind, _, aid = f.actor.partition(":")
        if kind != src or not aid.isdigit():
            return None
        p[f"actor_{src}"] = int(aid)
        where.append(f"{pre}.{'user_id' if src == 'staff' else 'account_id'} = :actor_{src}")
    if f.q and f.q.strip():
        p["pat"] = _pat(f.q)
        ql = f.q.strip().lower()
        p[f"qkeys_{src}"] = [k for k in known[src] if ql in sc.label_of(src, k).lower()]
        if src == "staff":
            p["qdeals"] = db.execute(text("SELECT id FROM sales_deals WHERE code ILIKE :pat ESCAPE '\\'"), p).scalars().all()
            where.append("(a.user_name ILIKE :pat ESCAPE '\\' OR a.details ILIKE :pat ESCAPE '\\' OR a.action = ANY(:qkeys_staff) "
                         "OR (a.entity_type = 'sales_deal' AND a.entity_id = ANY(:qdeals)))")
        else:
            where.append("(l.actor_name ILIKE :pat ESCAPE '\\' OR l.subject ILIKE :pat ESCAPE '\\' OR p.domain ILIKE :pat ESCAPE '\\' "
                         "OR l.action = ANY(:qkeys_cabinet))")
    keys = None
    if f.section:
        keys = [k for k in known[src] if sc.section_of(src, k) == f.section]
    if f.action:
        keys = [k for k in (keys if keys is not None else known[src]) if k == f.action]
    if keys is not None:
        if not keys:
            return None
        p[f"keys_{src}"] = keys
        where.append(f"{pre}.action = ANY(:keys_{src})")
    base = _STAFF if src == "staff" else _CAB
    return base + (" WHERE " + " AND ".join(where) if where else "")


def _union(db: Session, f: Query, known: dict) -> tuple:
    p: dict = {}
    parts = [b for b in (_branch(db, "staff", f, p, known), _branch(db, "cabinet", f, p, known)) if b]
    return (" UNION ALL ".join(parts) if parts else None), p


def _deal_codes_of_pairs(db: Session, pair_ids: list) -> dict:
    if not pair_ids:
        return {}
    rows = db.execute(text("SELECT p.id, d.code FROM launch_prep_pair p JOIN launch_prep_creative_set s ON s.id = p.set_id "
                           "JOIN sales_deals d ON d.id = s.deal_id WHERE p.id = ANY(:i)"), {"i": pair_ids}).all()
    return {i: c for i, c in rows if c}


def _objects(db: Session, rows) -> dict:
    from app.audit_objects import describe
    staff = describe(db, [(r.entity_type, r.entity_id) for r in rows if r.src == "staff"])
    pairs = _deal_codes_of_pairs(db, [r.entity_id for r in rows if r.entity_type == "launch_prep_pair" and r.entity_id])
    out = {}
    for r in rows:
        o = staff.get((r.entity_type, r.entity_id)) if r.src == "staff" else None
        label = (o or {}).get("label") or (r.details if r.src == "cabinet" else None)
        href = (o or {}).get("href")
        code = href.rsplit("/", 1)[-1] if href and href.startswith("/sales/deals/") else pairs.get(r.entity_id) if r.entity_type == "launch_prep_pair" else None
        if code and label and label.startswith(code):
            label = label[len(code):].lstrip(" ·")
        out[(r.src, r.id)] = {"label": label, "href": href, "code": code} if (label or code) else None
    return out


def _item(r, obj) -> dict:
    sec = sc.section_of(r.src, r.action)
    return {
        "id": f"{r.src}:{r.id}", "at": r.at,
        "actor": {"id": f"{r.src}:{r.actor_id}" if r.actor_id else None, "name": r.actor_name, "kind": r.src, "site": r.site},
        "action": r.action, "action_label": sc.label_of(r.src, r.action), "section": sec,
        "object": obj, "details": "" if r.src == "cabinet" else dt.humanize(r.action, r.details),
    }


def fetch(db: Session, f: Query) -> dict:
    known = {"staff": _known_actions(db, "staff"), "cabinet": _known_actions(db, "cabinet")}
    sql, p = _union(db, f, known)
    items, total = [], 0
    if sql:
        total = db.execute(text(f"SELECT count(*) FROM ({sql}) u"), p).scalar() or 0
        rows = db.execute(text(f"SELECT * FROM ({sql}) u ORDER BY at DESC, src, id DESC OFFSET :off LIMIT :lim"),
                          {**p, "off": max(f.offset, 0), "lim": max(min(f.limit, 500), 1)}).all()
        objs = _objects(db, rows)
        items = [_item(r, objs.get((r.src, r.id))) for r in rows]
    return {"items": items, "total": total, "has_more": f.offset + len(items) < total, "facets": facets(db, f, known)}


def facets(db: Session, f: Query, known: dict) -> dict:
    """Счётчики фильтров: разделы и действия — без фильтра раздела/действия; «кто» — без фильтра «кто»;
    контуры — всего записей в каждом, без фильтров."""
    sections: dict = {}
    actions: dict = {}
    sql, p = _union(db, replace(f, section=None, action=None), known)
    if sql:
        for src, action, n in db.execute(text(f"SELECT src, action, count(*) FROM ({sql}) u GROUP BY 1, 2"), p).all():
            sid = sc.section_of(src, action)
            sections[sid] = sections.get(sid, 0) + n
            if f.section == sid:
                actions[action] = {"label": sc.label_of(src, action), "n": n}
    actors = []
    sql, p = _union(db, replace(f, actor=None), known)
    if sql:
        for src, aid, name, site, n in db.execute(text(f"SELECT src, actor_id, actor_name, site, count(*) FROM ({sql}) u "
                                                       "WHERE actor_id IS NOT NULL GROUP BY 1, 2, 3, 4 ORDER BY 3"), p).all():
            actors.append({"id": f"{src}:{aid}", "name": name, "kind": src, "site": site, "count": n})
    contours = {
        "staff": db.execute(text("SELECT count(*) FROM audit_log")).scalar() or 0,
        "cabinet": db.execute(text("SELECT count(*) FROM cabinet_log WHERE actor_side = :s"), {"s": PUB_SIDE}).scalar() or 0,
    }
    contours["all"] = contours["staff"] + contours["cabinet"]
    return {"sections": sections, "actions": actions, "actors": actors, "contours": contours,
            "section_list": [{"id": s.id, "title": s.title, "color": s.color} for s in sc.SECTIONS]}
