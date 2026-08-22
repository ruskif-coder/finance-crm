"""Резолверы получателей: превращают спецификацию из реестра/подписки в список user_id.

До реестра «кому слать» было зашито прямо в роутерах (media_plans.py). Теперь вызывающий
объявляет только факт события, а адресатов считает этот модуль — политику можно менять
в одном месте, не трогая бизнес-логику.

Спецификация получателя: {"type": "resolver"|"role"|"user", "value": ...}
"""
from typing import Iterable, List, Optional, Set

from sqlalchemy.orm import Session

from app.models import User, Role, RolePermission

# Глубина подъёма по дереву мастеров: страховка от кривой настройки master_id.
MAX_MASTER_DEPTH = 5


# ─────────────────────────── базовые выборки ───────────────────────────

def _active(db: Session, user_ids: Iterable[int]) -> List[int]:
    ids = {u for u in user_ids if u}
    if not ids:
        return []
    return [u.id for u in db.query(User).filter(User.id.in_(ids), User.is_active == 1).all()]


def by_role(db: Session, role_key: str) -> List[int]:
    role = db.query(Role).filter(Role.key == role_key).first()
    if not role:
        return []
    return [u.id for u in db.query(User).filter(User.role_id == role.id, User.is_active == 1).all()]


def mp_approvers(db: Session, ctx: dict) -> List[int]:
    """Кто может согласовывать медиапланы: право media_plans:approve + админы.
    Перенесено из media_plans._approver_user_ids без изменений в логике."""
    role_ids = [r.role_id for r in db.query(RolePermission)
                .filter(RolePermission.section == "media_plans",
                        RolePermission.can_approve == 1).all()]
    admin = db.query(Role).filter(Role.key == "admin").first()
    if admin:
        role_ids.append(admin.id)
    if not role_ids:
        return []
    return [u.id for u in db.query(User).filter(User.role_id.in_(role_ids),
                                                User.is_active == 1).all()]


def mp_stakeholders(db: Session, ctx: dict) -> List[int]:
    """Автор медиаплана и назначенные по нему ответственные (сейлз, аккаунт, трафик)."""
    p = ctx.get("media_plan")
    if p is None:
        return []
    return _active(db, [p.created_by, p.sales_rep_id, p.account_manager_id, p.traffic_manager_id])


def responsible(db: Session, ctx: dict) -> List[int]:
    """Ответственный по объекту: сейлз сделки, иначе аккаунт. Через sales_reps.user_id."""
    deal = ctx.get("deal")
    if deal is None:
        return []
    from app.sales.models import SalesRep
    rep_ids = [x for x in (deal.sales_rep_id, deal.account_manager_id) if x]
    if not rep_ids:
        return []
    rows = db.query(SalesRep).filter(SalesRep.id.in_(rep_ids)).all()
    return _active(db, [r.user_id for r in rows])


def sales_rep_of_deal(db: Session, ctx: dict) -> List[int]:
    """Продавец сделки — именно он, без аккаунта.

    Отдельно от `responsible`, который отдаёт обоих сразу: у сейлзовых событий
    (сделка ушла в бронь, сделка сорвалась) адресат один, и подмешивать туда аккаунта
    значит слать ему второе уведомление о том, что он и так видит в своей очереди."""
    deal = ctx.get("deal")
    if deal is None or not deal.sales_rep_id:
        return []
    from app.sales.models import SalesRep
    rep = db.query(SalesRep).filter(SalesRep.id == deal.sales_rep_id).first()
    return _active(db, [rep.user_id]) if rep else []


def sales_head(db: Session, ctx: dict) -> List[int]:
    """Руководитель отдела продаж — активные SalesRep с is_sales_head.

    Не через master_of_responsible: тот поднимается по дереву от ответственного и
    зависит от сделки, а здесь адресат один и тот же независимо от объекта."""
    from app.sales.models import SalesRep
    heads = db.query(SalesRep).filter(SalesRep.is_sales_head.is_(True),
                                      SalesRep.is_active.is_(True)).all()
    return _active(db, [h.user_id for h in heads])


def year_plan_owner(db: Session, ctx: dict) -> List[int]:
    """Сейлз, которому принадлежит строка/план года. ctx: {"rep_id": <SalesRep.id>}.

    Через rep_id, а не через сделку: события годового плана рождаются до сделок либо
    вовсе из-за их отсутствия («месяц запланирован, сделок нет»)."""
    rep_id = ctx.get("rep_id")
    if not rep_id:
        return []
    from app.sales.models import SalesRep
    rep = db.query(SalesRep).filter(SalesRep.id == rep_id).first()
    return _active(db, [rep.user_id]) if rep else []


def mp_author(db: Session, ctx: dict) -> List[int]:
    """Только автор медиаплана. Для брошенного черновика остальные ответственные
    ни при чём: план им ещё не показывали."""
    p = ctx.get("media_plan")
    return _active(db, [p.created_by]) if p is not None else []


def account_manager(db: Session, ctx: dict) -> List[int]:
    deal = ctx.get("deal")
    if deal is None or not deal.account_manager_id:
        return []
    from app.sales.models import SalesRep
    rep = db.query(SalesRep).filter(SalesRep.id == deal.account_manager_id).first()
    return _active(db, [rep.user_id]) if rep else []


def master_of_responsible(db: Session, ctx: dict) -> List[int]:
    """Мастер ответственного — подъём по дереву sales_reps.master_id с защитой от цикла.
    Если master_id не заполнен (а он пока не заполнен ни у кого), падаем на запасной
    вариант: активные представители с флагом is_sales_head."""
    deal = ctx.get("deal")
    from app.sales.models import SalesRep
    start = None
    if deal is not None:
        start = deal.sales_rep_id or deal.account_manager_id
    if start:
        seen: Set[int] = set()
        cur = db.query(SalesRep).filter(SalesRep.id == start).first()
        depth = 0
        while cur is not None and cur.master_id and depth < MAX_MASTER_DEPTH:
            if cur.master_id in seen:          # цикл в дереве — молча прекращаем подъём
                break
            seen.add(cur.master_id)
            cur = db.query(SalesRep).filter(SalesRep.id == cur.master_id).first()
            depth += 1
        if cur is not None and cur.id != start:
            return _active(db, [cur.user_id])
    heads = db.query(SalesRep).filter(SalesRep.is_sales_head.is_(True),
                                      SalesRep.is_active.is_(True)).all()
    return _active(db, [h.user_id for h in heads])


RESOLVERS = {
    "mp_approvers": mp_approvers,
    "mp_stakeholders": mp_stakeholders,
    "mp_author": mp_author,
    "responsible": responsible,
    "account_manager": account_manager,
    "sales_rep_of_deal": sales_rep_of_deal,
    "sales_head": sales_head,
    "year_plan_owner": year_plan_owner,
    "master_of_responsible": master_of_responsible,
}

RESOLVER_LABELS = {
    "mp_approvers": "Согласующие МП",
    "mp_stakeholders": "Автор и ответственные по МП",
    "mp_author": "Автор МП",
    "responsible": "Ответственный",
    "account_manager": "Аккаунт сделки",
    "sales_rep_of_deal": "Сейлз сделки",
    "sales_head": "Руководитель отдела продаж",
    "year_plan_owner": "Сейлз годового плана",
    "master_of_responsible": "Мастер ответственного",
}


def resolve(db: Session, specs: Iterable[dict], ctx: Optional[dict] = None) -> List[int]:
    """Спецификации получателей → список user_id без дублей, только активные."""
    ctx = ctx or {}
    out: List[int] = []
    seen: Set[int] = set()
    for spec in specs or []:
        t, v = (spec or {}).get("type"), (spec or {}).get("value")
        if t == "resolver":
            ids = RESOLVERS[v](db, ctx) if v in RESOLVERS else []
        elif t == "role":
            ids = by_role(db, v)
        elif t == "user":
            ids = _active(db, [v])
        else:
            ids = []
        for uid in ids:
            if uid not in seen:
                seen.add(uid)
                out.append(uid)
    return out
