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
               coalesce(cp.name, d.payer_name) AS client, r.name AS account,
               coalesce(d.amount_with_vat, d.amount) AS gross,
               concat_ws(' / ', coalesce(ad.short_name, ad.name), b.name) AS brand,
               (SELECT max(h.at) FROM sales_deal_stage_history h WHERE h.deal_id = d.id AND h.to_stage_id = d.our_stage_id) AS stage_since
          FROM sales_deals d
          JOIN sales_stages s ON s.id = d.our_stage_id
          LEFT JOIN master_deal_items i ON i.deal_id = d.id
          LEFT JOIN master_deals m ON m.id = i.master_deal_id
          LEFT JOIN counterparties cp ON cp.id = d.counterparty_id
          LEFT JOIN sales_reps r ON r.id = d.account_manager_id
          LEFT JOIN sales_advertisers ad ON ad.id = d.advertiser_id
          LEFT JOIN sales_brands b ON b.id = d.brand_id
         WHERE to_char(d.period_from, 'YYYY-MM') = :month AND d.our_stage_id = ANY(:stages)
           AND (m.id IS NULL OR m.status IN (:draft, :agree, :wait_close))
         ORDER BY m.code NULLS FIRST, d.code"""),
        {"month": month, "stages": stages, "draft": ST.DRAFT, "agree": ST.AGREE, "wait_close": ST.WAIT_CLOSE}).all()
    deals = [{"deal_id": x.id, "code": x.code, "title": x.title, "stage": x.stage, "client": x.client, "account": x.account,
              "gross": float(x.gross) if x.gross is not None else None, "brand": x.brand or None,
              "stage_since": x.stage_since.isoformat(timespec="seconds") if x.stage_since else None,
              "package": x.package if x.package_status in _OF_STATUS else None,
              "bucket": _OF_STATUS.get(x.package_status, "recon")} for x in rows]
    counts = {b: sum(1 for x in deals if x["bucket"] == b) for b in BUCKETS}
    packages = {b: len({x["package"] for x in deals if x["bucket"] == b and x["package"]}) for b in ("draft", "agree")}
    return {"month": month, "total": len(deals), "counts": counts, "packages": packages, "deals": deals}


# Прогноз «Ещё в пути» (хендофф 09.11.2026): «на сверке» и «черновик» — работа на нашей стороне («сверка»), «согласование» — у клиента
FORECAST_STAGE = {"recon": "сверка", "draft": "сверка", "agree": "согласование"}


def not_arrived(up: dict) -> dict:
    """Строки прогноза в контракте хендоффа (`data.not_arrived.items`); счётчики и сумму считает экран (`forecastOf`)."""
    return {"items": [{"code": x["code"], "buyer": x.get("client") or "", "brand": x.get("brand") or "", "account": x.get("account") or "",
                       "stage": FORECAST_STAGE[x["bucket"]], "gross": round(float(x.get("gross") or 0), 2),
                       "stage_since": x.get("stage_since")} for x in up.get("deals") or []]}
