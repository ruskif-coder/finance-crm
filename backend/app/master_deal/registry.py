# -*- coding: utf-8 -*-
"""Реестр мастер-сделок («Финансы → Мастер-сделки»): одной выборкой, без пересчёта сверки — суммы из комплектов УПД (есть после
раскладки) или пусто. Эффективность — только с правом и только у пакетов с раскладкой."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.master_deal import scope as SC
from app.master_deal import status as MST
from app.master_deal import to_annex as TA

_ROWS = text("""
    SELECT m.id, m.code, m.status, m.period, c.contract_number, c.contract_date, cp.name, pay.name,
           coalesce(u.name, u.email),
           (SELECT count(*) FROM master_deal_items i WHERE i.master_deal_id = m.id),
           (SELECT sum(net) FROM master_deal_upds x WHERE x.master_deal_id = m.id),
           (SELECT sum(gross) FROM master_deal_upds x WHERE x.master_deal_id = m.id),
           m.created_at,
           (SELECT array_agg(DISTINCT a.name ORDER BY a.name) FROM master_deal_items i JOIN sales_deals d ON d.id = i.deal_id
              JOIN sales_advertisers a ON a.id = d.advertiser_id WHERE i.master_deal_id = m.id),
           (SELECT array_agg(DISTINCT b.name ORDER BY b.name) FROM master_deal_items i JOIN sales_deals d ON d.id = i.deal_id
              JOIN sales_brands b ON b.id = d.brand_id WHERE i.master_deal_id = m.id)
      FROM master_deals m
      LEFT JOIN contracts c ON c.id = m.contract_id
      LEFT JOIN counterparties cp ON cp.id = c.counterparty_id
      LEFT JOIN counterparties pay ON pay.id = m.payer_counterparty_id
      LEFT JOIN users u ON u.id = m.created_by
     ORDER BY m.period DESC, m.code DESC""")


def row_efficiency(db: Session, m) -> dict:
    from app.final_recon import closing as CL
    from app.master_deal import efficiency as EF
    from app.sales.models import SalesDeal
    ids = [r[0] for r in db.execute(text("SELECT deal_id FROM master_deal_items WHERE master_deal_id = :m"), {"m": m.id})]
    return EF.total([EF.row(d.code, CL.compute(db, d), EF.estimate(db, d.id)) for d in (db.get(SalesDeal, i) for i in ids)])


def _iso(v, **kw):
    return v.isoformat(**kw) if v else None


def rows(db: Session, user) -> list:
    """Строки реестра. Сверка сделки — один раз за запрос (`CL.memo`, аудит 21.10.2026)."""
    from app.final_recon import closing as CL
    with CL.memo(db):
        return _rows(db, user)


def _rows(db: Session, user) -> list:
    from app.master_deal.models import MasterDeal
    own = SC.own_reps(db, user)
    fin = SC.can_finance(db, user)
    out = []
    for r in db.execute(_ROWS).all():
        m = db.get(MasterDeal, r[0])
        if not SC.all_in_scope(db, m, own):            # как карточка: суммы и эффективность всего пакета (аудит 21.10.2026)
            continue
        out.append({"code": r[1], "status": r[2], "status_label": MST.label(db, m), "todo": MST.todo(db, m), "period": r[3],
                    "contract": {"number": r[4], "date": _iso(r[5])}, "counterparty": r[6], "payer": r[7], "built_by": r[8],
                    "deals": r[9], "net": round(r[10], 2) if r[10] is not None else None,
                    "gross": round(r[11], 2) if r[11] is not None else None,
                    "ds": [a["number"] for a in TA.annexes_of(db, m)], "created_at": _iso(r[12], timespec="seconds"),
                    "advertisers": list(r[13] or []), "brands": list(r[14] or []),
                    "contract_id": m.contract_id, "step": MST.row_step(db, m),
                    # канал — отдельной колонкой (хендофф v2): бумажный по факту пакет остаётся бумажным, иначе — из договора
                    "channel": MST.PAPER if MST.is_paper(db, m) else MST.channel_of(db, m),
                    **({"efficiency": row_efficiency(db, m)} if fin and r[10] is not None else {})})
    return out
