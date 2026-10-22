# -*- coding: utf-8 -*-
"""Мастер-сделка: развилка «Отправить в ДО» (владелец 15.10.2026, схема docs/СХЕМА_контур_закрытия_еФарм.md).

Ключ пакета — доходный договор сделки и её финансовый месяц (`period_from`). Развилка на карточке:
своё ДС (новая мастер-сделка на одну сделку) · в открытую мастер-сделку того же договора и месяца · сделка уже в пакете.
При любом итоге — заморозка итоговой сверки, переход на следующую стадию по правилам требований и вход в конструктор закрытия."""
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.final_recon import closing as CL
from app.master_deal.models import MasterDeal, MasterDealItem

OPEN = ("черновик",)             # в пакет можно добавлять, пока он черновик (app/master_deal/status.py)
RECON_STAGE = "Итоговая сверка"


class MasterError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def period_of(deal) -> Optional[str]:
    return deal.period_from.strftime("%Y-%m") if deal.period_from else None


def item_of(db: Session, deal_id: int) -> Optional[MasterDealItem]:
    return db.query(MasterDealItem).filter(MasterDealItem.deal_id == deal_id).first()


def candidates(db: Session, deal, own=None) -> list:
    """Открытые мастер-сделки того же доходного договора и месяца — куда можно добавить сделку.
    `own` — область «свои»: только пакеты, все сделки которых свои; иначе присоединение запирало пакет для всех (аудит 21.10.2026)."""
    per = period_of(deal)
    if not (deal.ord_final_contract_id and per):
        return []
    rows = (db.query(MasterDeal).filter(MasterDeal.contract_id == deal.ord_final_contract_id, MasterDeal.period == per,
                                        MasterDeal.status.in_(OPEN)).order_by(MasterDeal.id).all())
    if own is not None:
        from app.master_deal import scope as SC
        rows = [m for m in rows if SC.all_in_scope(db, m, own)]
    counts = dict(db.execute(text("SELECT master_deal_id, count(*) FROM master_deal_items WHERE master_deal_id = ANY(:i) "
                                  "GROUP BY master_deal_id"), {"i": [m.id for m in rows] or [0]}).fetchall())
    return [{"id": m.id, "code": m.code, "deals": counts.get(m.id, 0)} for m in rows]


def _own_only(rows, own) -> list:
    """Соседи «своих»: чужие сделки с суммами сверки в модалке не показываются (аудит 21.10.2026)."""
    if own is None:
        return list(rows)
    ids = set(own or ())
    return [r for r in rows if r["sales_rep_id"] in ids or r["account_manager_id"] in ids]


def siblings(db: Session, deal, own=None) -> list:
    """Другие сделки того же доходного договора и месяца, ещё не в пакете — взять можно любую (владелец 15.10.2026);
    статус словами: «РК не завершена» / «сверка не завершена» / «сверка завершена». Дальше конструктора документов
    пакет не уйдёт, пока сверка не завершена у всех (`gate`)."""
    per = period_of(deal)
    if not (deal.ord_final_contract_id and per):
        return []
    rows = db.execute(text("""
        SELECT d.id, d.code, d.title, st.name AS stage, d.sales_rep_id, d.account_manager_id
          FROM sales_deals d LEFT JOIN sales_stages st ON st.id = d.our_stage_id
         WHERE d.ord_final_contract_id = :c AND to_char(d.period_from, 'YYYY-MM') = :p AND d.id <> :me
           AND NOT EXISTS (SELECT 1 FROM master_deal_items i WHERE i.deal_id = d.id)
           AND coalesce(st.is_lost, false) = false
         ORDER BY d.code"""), {"c": deal.ord_final_contract_id, "p": per, "me": deal.id}).mappings().all()
    from app.sales.models import SalesDeal
    out = []
    for r in _own_only(rows, own):
        d = db.get(SalesDeal, r["id"])
        st = deal_status(db, d)
        c = CL.compute(db, d)
        out.append({"id": r["id"], "code": r["code"], "title": r["title"], "stage": r["stage"], **st,
                    "total_net": c["total_net"], "verdict": c["verdict"]["text"]})
    return out


def deal_status(db: Session, deal) -> dict:
    """Готовность сделки к документам пакета: done — сверка зафиксирована («Отправить в ДО» нажато)."""
    from app.sales.catalog import Catalog
    st = CL.compute(db, deal)
    if st["frozen"]:
        return {"state": "done", "status": "сверка завершена"}
    cat = Catalog(db)
    cur = cat.by_id.get(deal.our_stage_id)
    recon = next((x for x in cat.stages if x.name == RECON_STAGE), None)
    order = {x.id: i for i, x in enumerate(cat.stages)}
    if cur and recon and order.get(cur.id, -1) < order.get(recon.id, -1):
        return {"state": "rk", "status": "РК не завершена"}
    if st["confirmed"]:
        return {"state": "ready", "status": "сверка готова"}
    return {"state": "recon", "status": "сверка не завершена"}


def gate(db: Session, m) -> dict:
    """Пакет дальше конструктора документов — только когда сверка завершена у всех сделок."""
    from app.sales.models import SalesDeal
    wait = []
    for it in db.query(MasterDealItem).filter(MasterDealItem.master_deal_id == m.id):
        d = db.get(SalesDeal, it.deal_id)
        st = deal_status(db, d)
        if st["state"] != "done":
            wait.append({"code": d.code, **st})
    return {"ok": not wait, "wait": wait}


def _taken(db: Session, deal, m, user) -> None:
    from app.notify.master_deal import deal_taken
    deal_taken(db, deal, m, user)


def attach(db: Session, deal, m, user) -> None:
    """Прикрепить сделку к пакету без перехода и заморозки — её сверка закончится позже, своей кнопкой."""
    if item_of(db, deal.id):
        raise MasterError(409, f"{deal.code} уже в пакете")
    db.add(MasterDealItem(master_deal_id=m.id, deal_id=deal.id, added_by=getattr(user, "id", None)))
    m.updated_at = datetime.utcnow()
    db.flush()
    _taken(db, deal, m, user)


def fork(db: Session, deal, own=None) -> dict:
    """Что показать в модалке «Отправить в ДО». `own` — область «свои» пользователя (None — все)."""
    me = {"code": deal.code, "title": deal.title}
    it = item_of(db, deal.id)
    if it:
        m = db.get(MasterDeal, it.master_deal_id)
        return {"deal": me, "in_master": {"id": m.id, "code": m.code, "status": m.status}, "candidates": []}
    why = None
    if not deal.ord_final_contract_id:
        why = "У сделки не выбран доходный договор — он ключ пакета (блок ОРД)"
    elif not deal.period_from:
        why = "У сделки нет периода — финансовый месяц ключ пакета"
    return {"deal": me, "in_master": None, "candidates": candidates(db, deal, own), "blocked": why,
            "siblings": [] if why else siblings(db, deal, own),
            "contract_id": deal.ord_final_contract_id, "period": period_of(deal)}


def _new_code(db: Session) -> str:
    n = db.execute(text("SELECT nextval('master_deal_no_seq')")).scalar()
    return f"M-{int(n):04d}"


def create(db: Session, deal, user) -> MasterDeal:
    m = MasterDeal(code=_new_code(db), contract_id=deal.ord_final_contract_id, period=period_of(deal),
                   payer_counterparty_id=deal.payer_counterparty_id, created_by=getattr(user, "id", None))
    db.add(m)
    db.flush()
    return m


def send(db: Session, deal, user, *, target: str, master_id: Optional[int] = None, check_ready: bool = True) -> dict:
    """«Отправить в ДО»: target = new (своё ДС) | join (в мастер-сделку `master_id`) | existing (уже в пакете).

    Порядок: проверки → переход стадии по правилам требований → заморозка сверки → пакет. Отказ перехода — ничего не меняет."""
    from app.sales import stage_move
    from app.sales.catalog import Catalog

    from app.master_deal import scope as SC
    f = fork(db, deal, SC.own_reps(db, user) if user is not None else None)
    if f.get("in_master"):
        target = "existing"
    elif f.get("blocked"):
        raise MasterError(409, f["blocked"])
    if target not in ("new", "join", "existing"):
        raise MasterError(400, "Куда отправить: своё ДС или в мастер-сделку")

    cat = Catalog(db)
    cur = cat.by_id.get(deal.our_stage_id)
    first_send = not (CL.compute(db, deal)["frozen"])
    # Кнопка живёт на «Итоговой сверке»; повторный вход (сделка уже отправлена) — только в конструктор, без перехода.
    if first_send and not CL.compute(db, deal)["confirmed"]:
        raise MasterError(409, "Сначала подтвердите сверку")
    if first_send and (not cur or cur.name != RECON_STAGE):
        raise MasterError(409, f"«Отправить в ДО» — со стадии «{RECON_STAGE}», а сделка на «{cur.name if cur else '—'}»")
    nxt = stage_move.next_stage(db, deal, cat) if first_send else None
    moved = None
    if nxt is not None:
        plan = stage_move.plan_move(db, deal, nxt, cat)
        if not stage_move.may_move(plan):
            raise MasterError(409, stage_move.refusal_text(plan))
    try:
        state = CL.freeze(db, deal, user)
    except CL.ClosingError as e:
        raise MasterError(e.status, e.message)

    if target == "existing":
        m = db.get(MasterDeal, f["in_master"]["id"])
    elif target == "join":
        m = db.get(MasterDeal, master_id) if master_id else None
        if not m or m.id not in {c["id"] for c in f["candidates"]}:
            raise MasterError(409, "Эта мастер-сделка не подходит: другой договор, месяц или она уже не на сборке")
    else:
        m = create(db, deal, user)
    if target != "existing":
        db.add(MasterDealItem(master_deal_id=m.id, deal_id=deal.id, added_by=getattr(user, "id", None)))
        _taken(db, deal, m, user)
        m.updated_at = datetime.utcnow()
        db.flush()

    if nxt is not None:
        res = stage_move.apply_move(db, deal, nxt, user, reason="Отправить в ДО", catalog=cat)
        moved = nxt.name if res.get("moved") else None
    from app.notify import closing as CN
    if first_send:
        CN.deal_sent(db, deal, m, user)
    if check_ready and first_send:       # из `send_with` — после всех доп. сделок; повторный вход (сделка уже отправлена) — тишина
        CN.ready_check(db, m)
    return {"master": {"id": m.id, "code": m.code}, "moved_to": moved, "closing": state, "first_send": first_send}


def send_with(db: Session, deal, extra: list, user, *, target: str, master_id: Optional[int] = None) -> dict:
    """«Отправить в ДО» сразу с доп. сделками того же договора и месяца (владелец 15.10.2026): взять можно любую — на сверке она
    отправляется целиком, иначе прикрепляется. Всё или ничего:
    отказ по любой сделке поднимается наверх, и вызывающий откатывает весь пакет."""
    out = send(db, deal, user, target=target, master_id=master_id, check_ready=False)
    from app.master_deal import scope as SC
    allowed = {x["id"]: x for x in siblings(db, deal, SC.own_reps(db, user) if user is not None else None)}
    m = db.get(MasterDeal, out["master"]["id"])
    added, first = [], out["first_send"]
    for x in extra:
        sib = allowed.get(x.id)
        if not sib:
            raise MasterError(409, f"{x.code}: другой договор или месяц, или уже в пакете")
        if sib["state"] == "ready":          # сверка подтверждена — отправляется целиком: заморозка и переход
            first = send(db, x, user, target="join", master_id=m.id, check_ready=False)["first_send"] or first
        else:                                # РК идёт или сверка не подтверждена — только прикрепляем; закончит своя кнопка
            attach(db, x, m, user)
        added.append(x.code)
    if first:                                # «собрана» — один раз, когда весь набор этого действия уже в пакете (ревью 21.10.2026)
        from app.notify import closing as CN
        CN.ready_check(db, m)
    return {**out, "added": added}
