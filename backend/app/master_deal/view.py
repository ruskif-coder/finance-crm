# -*- coding: utf-8 -*-
"""Карточка мастер-сделки — одна сборка для экрана пакета, расхлопа реестра и ответа каждой ручки после действия.
`deals` — сделки пакета, уже проверенные на область видимости пользователя (их отбирает роутер)."""
from typing import Optional

from sqlalchemy.orm import Session

from app.master_deal import docs as MDOC
from app.master_deal import scope as SC
from app.master_deal import service as MS
from app.master_deal import start as SP
from app.master_deal import status as MST
from app.master_deal import to_annex as TA


def _who(db: Session, uid) -> Optional[str]:
    from app.models import User
    u = db.get(User, uid) if uid else None
    return (u.name or u.email) if u else None


def _at(v):
    return v.isoformat(timespec="seconds") if v else None


def issue(db: Session, m) -> dict:
    """Выставление: канал договора, бумага ли пакет, сводка подписи по документам, когда документы последний раз уходили
    клиенту и срок ожидания подписанных. Отметки — у документов (`docs`), не у пакета (02.11.2026)."""
    from app.master_deal import issue as IS
    return {"channel": MST.channel_of(db, m), "paper": MST.is_paper(db, m), "summary": IS.state(db, m),
            "rejected": IS.rejected(db, m), "last_sent_at": _at(IS.last_sent_at(db, m)), "due_days": IS.due_days(db),
            "start": {"issued_at_start": bool(m.issued_at_start), "phase": SP.in_start_phase(db, m)}}


def _deals(db: Session, deals: list, fin: bool, special: bool = False, plan_only: bool = False) -> tuple:
    from app.final_recon import closing as CL
    from app.master_deal import efficiency as EF
    from app.sales.catalog import Catalog
    from app.sales import annex as annex_mod
    from app.sales.models import SalesService
    cat = Catalog(db)
    ids = {d.service_id for d in deals if d.service_id}
    svc = {s.id: s.name for s in db.query(SalesService).filter(SalesService.id.in_(ids or [0]))}
    out, eff = [], []
    for d in deals:
        st = CL.compute(db, d, plan_only=plan_only)      # ДС на старте — суммы по МП, как раскладка (02.11.2026)
        if fin:
            eff.append(EF.row(d.code, st, EF.estimate(db, d.id)))
        stg = cat.by_id.get(d.our_stage_id)
        out.append({"id": d.id, "code": d.code, "title": d.title, "stage": stg.name if stg else None,
                    "brand": annex_mod.deal_brand(db, [d.id]), "service": svc.get(d.service_id),
                    "verdict": st["verdict"], "mode": st["mode"], "total_net": st["total_net"], "total_gross": st["total_gross"],
                    "price": MDOC.deal_price(db, d.id), **MS.deal_status(db, d)})
    if not fin:
        return out, None
    res = {"rows": eff, "total": EF.total(eff)}
    return out, (EF.with_full(db, deals, res) if special else res)


def card(db: Session, m, user, deals: list) -> dict:
    from app.master_deal import layout as LY
    from app.master_deal import package as PK
    from app.master_deal import primary as PR
    from app.models import Contract, Counterparty
    c = db.get(Contract, m.contract_id)
    payer = db.get(Counterparty, m.payer_counterparty_id) if m.payer_counterparty_id else None
    start = SP.in_start_phase(db, m)
    out_deals, eff = _deals(db, deals, SC.can_finance(db, user), SC.can_special(db, user), plan_only=start)
    lay = LY.layout(db, m)
    issued_list = PK.issued(db, m.contract_id)
    return {
        "id": m.id, "code": m.code, "status": m.status, "period": m.period,
        # Вид документа по договору — панели сборки: выбирается при первой сборке со стартовым номером (31.10.2026).
        "contract": {"id": c.id, "number": c.contract_number, "date": c.contract_date,
                     "annex_word": getattr(c, "annex_word", None)} if c else None,
        "payer": {"id": payer.id, "name": payer.name, "inn": payer.inn} if payer else None,
        "deals": out_deals, "deals_total_net": round(sum((d["total_net"] or 0) for d in out_deals), 2),
        **({"efficiency": eff} if eff is not None else {}),
        # Пакет со стартовым ДС — одна сделка, без объединения (02.11.2026): кандидатов ему не предлагаем.
        "candidates": [] if m.issued_at_start else PK.candidates(db, m), "settings": LY.settings_of(m),
        "issued_at_start": bool(m.issued_at_start),
        "saved": {"by": _who(db, m.saved_by), "at": m.updated_at} if m.saved_by else None,
        "start_no": m.start_no, "issued": issued_list, "last_issued": max((x["no"] for x in issued_list), default=None),
        "issued_ds": PK.issued_ds(db, m), "prev": PK.prev(db, m), "layout": lay,
        # На старте сверку не ждут — ДС на план (02.11.2026); плашка «пока сверка не завершена» ему не про то.
        "gate": {"ok": True, "wait": []} if start else MS.gate(db, m),
        "annexes": TA.annexes_of(db, m), "upds": TA.upds_of(db, m), "primary": None if start else PR.info(db, m, lay["total_gross"]),
        "to_annex_why": TA.ready(db, m) if m.status == MST.DRAFT else [],
        "issue": issue(db, m), "docs": MDOC.build(db, m), "events": MDOC.events(db, m),
        "sequence": list(MST.sequence(db, m)), "step": MST.row_step(db, m), "status_label": MST.label(db, m),
        "todo": MST.todo(db, m), "status_actions": MST.actions(db, m, user), "statuses": list(MST.STATUSES),
    }
