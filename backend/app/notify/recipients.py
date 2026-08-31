"""Резолверы получателей: превращают спецификацию из реестра/подписки в список user_id.

До реестра «кому слать» было зашито прямо в роутерах (media_plans.py). Теперь вызывающий
объявляет только факт события, а адресатов считает этот модуль — политику можно менять
в одном месте, не трогая бизнес-логику.

Спецификация получателя: {"type": "resolver"|"role"|"staff_group"|"user", "value": ...}

`staff_group` появился 31.08.2026 и нужен там, где адресат — КОНТУР, а не конкретная роль:
ролей в контуре бывает несколько (рядовой и мастер), и главное — ключ роли вида
`role_<id>` у каждой установки свой. Событие, адресованное `role_121`, на проде не нашло
бы никого и не сказало бы об этом ни слова.
"""
from typing import Iterable, List, Optional, Set

from sqlalchemy.orm import Session

from app.models import User, Role

# Глубина подъёма по дереву мастеров: страховка от кривой настройки master_id.
MAX_MASTER_DEPTH = 5


# ─────────────────────────── базовые выборки ───────────────────────────

def _active(db: Session, user_ids: Iterable[int]) -> List[int]:
    ids = {u for u in user_ids if u}
    if not ids:
        return []
    return [u.id for u in db.query(User).filter(User.id.in_(ids), User.is_active == 1).all()]


def by_staff_group(db: Session, group: str) -> List[int]:
    """Все активные люди контура: и рядовые, и мастера.

    Признак стабилен между установками, в отличие от `roles.key`: `staff_group`
    проставляется миграцией по смыслу роли, а не по номеру строки.
    """
    ids = [r.id for r in db.query(Role).filter(Role.staff_group == group).all()]
    if not ids:
        return []
    return [u.id for u in db.query(User).filter(User.role_id.in_(ids),
                                                User.is_active == 1).all()]


def by_role(db: Session, role_key: str) -> List[int]:
    role = db.query(Role).filter(Role.key == role_key).first()
    if not role:
        return []
    return [u.id for u in db.query(User).filter(User.role_id == role.id, User.is_active == 1).all()]


# Резолверы `mp_approvers` (роли с правом media_plans:approve) и `mp_stakeholders`
# (автор + ответственные) удалены 30.08.2026 вместе со стейт-машиной согласования МП:
# согласующих больше нет как роли в процессе. Автор плана по-прежнему адресуем —
# `mp_author` ниже.


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
    "mp_author": mp_author,
    "responsible": responsible,
    "account_manager": account_manager,
    "sales_rep_of_deal": sales_rep_of_deal,
    "sales_head": sales_head,
    "year_plan_owner": year_plan_owner,
    "master_of_responsible": master_of_responsible,
}

# Что резолвер ждёт в `ctx`. Объявлено списком, а не только в теле функции, потому что
# ошибка здесь МОЛЧАЛИВАЯ: резолвер не находит своего ключа, возвращает пустой список,
# адресатов нет, событие уходит в никуда — ни исключения, ни строки в журнале отправок.
#
# Так и случилось: шесть событий контура креативов и трафика адресованы аккаунту сделки,
# а вызовы передавали `ctx={"deal_id": deal.id}` вместо `ctx={"deal": deal}`. Площадка
# нажимала «на доработку», вердикт ложился в базу и в журнал кабинета, а аккаунт не
# узнавал об этом никогда. Нашлось 31.08.2026 не приборами, а тем, что владелец нажал
# кнопку и спросил, где теперь искать результат.
#
# Значение — ОБЪЕКТ, а не идентификатор: резолверу нужны поля (`deal.account_manager_id`),
# и лишний поход в базу за уже загруженной строкой здесь ни к чему.
#
# Прибор, который держит соответствие: `backend/tests/test_notify_ctx.py`.
RESOLVER_CTX = {
    "mp_author": "media_plan",          # SalesMediaPlan
    "responsible": "deal",              # SalesDeal
    "account_manager": "deal",          # SalesDeal
    "sales_rep_of_deal": "deal",        # SalesDeal
    "year_plan_owner": "rep_id",        # int — id SalesRep владельца плана
    "master_of_responsible": "deal",    # SalesDeal
    # "sales_head" и роль/пользователь в получателях контекста не читают вовсе.
}

RESOLVER_LABELS = {
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
        elif t == "staff_group":
            ids = by_staff_group(db, v)
        elif t == "user":
            ids = _active(db, [v])
        else:
            ids = []
        for uid in ids:
            if uid not in seen:
                seen.add(uid)
                out.append(uid)
    return out
