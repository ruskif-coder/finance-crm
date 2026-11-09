# -*- coding: utf-8 -*-
"""«Ещё не дошли» — объём закрытия, которого бухгалтер пока не видит (владелец 09.11.2026: «все что после итоговой сверки»).

Сделки закрываемого месяца на стадии «Итоговая сверка» и дальше по цепочке, документы которых ещё не у бухгалтера: сверка не
отправлена в ДО (сделки нет в пакете или она в стартовом пакете «ждём закрытия») — «на сверке»; пакет в черновике — «черновик»;
пакет на согласовании ДС — «согласование». С «ждём 1С» заявка уже в очереди бухгалтера и здесь не считается. Самореклама
считается: она площадок, клиенту за неё выставляем (владелец 09.11.2026). Месяц сделки — месяц `period_from`, как у пакета (`master_deal.service.period_of`)."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.master_deal import status as ST
from app.master_deal.service import RECON_STAGE

BUCKETS = ("recon", "draft", "agree")
_OF_STATUS = {ST.DRAFT: "draft", ST.AGREE: "agree"}


def _stages_from_recon(db: Session) -> list[int]:
    from app.sales.catalog import Catalog
    cat = Catalog(db)
    flow = [cat.by_id[i] for i in cat.flow]
    at = next((n for n, s in enumerate(flow) if s.name == RECON_STAGE), None)
    return [] if at is None else [s.id for s in flow[at:]]


def upstream(db: Session, month: str) -> dict:
    stages = _stages_from_recon(db)
    rows = db.execute(text("""
        SELECT d.id, d.code, d.title, s.name AS stage, m.code AS package, m.status AS package_status,
               coalesce(cp.name, d.payer_name) AS client, r.name AS account
          FROM sales_deals d
          JOIN sales_stages s ON s.id = d.our_stage_id
          LEFT JOIN master_deal_items i ON i.deal_id = d.id
          LEFT JOIN master_deals m ON m.id = i.master_deal_id
          LEFT JOIN counterparties cp ON cp.id = d.counterparty_id
          LEFT JOIN sales_reps r ON r.id = d.account_manager_id
         WHERE to_char(d.period_from, 'YYYY-MM') = :month AND d.our_stage_id = ANY(:stages)
           AND (m.id IS NULL OR m.status IN (:draft, :agree, :wait_close))
         ORDER BY m.code NULLS FIRST, d.code"""),
        {"month": month, "stages": stages, "draft": ST.DRAFT, "agree": ST.AGREE, "wait_close": ST.WAIT_CLOSE}).all()
    deals = [{"deal_id": x.id, "code": x.code, "title": x.title, "stage": x.stage, "client": x.client, "account": x.account,
              "package": x.package if x.package_status in _OF_STATUS else None,
              "bucket": _OF_STATUS.get(x.package_status, "recon")} for x in rows]
    counts = {b: sum(1 for x in deals if x["bucket"] == b) for b in BUCKETS}
    packages = {b: len({x["package"] for x in deals if x["bucket"] == b and x["package"]}) for b in ("draft", "agree")}
    return {"month": month, "total": len(deals), "counts": counts, "packages": packages, "deals": deals}
