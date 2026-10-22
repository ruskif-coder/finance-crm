# -*- coding: utf-8 -*-
"""Мост мастер-сделка → операция (владелец 20.10.2026: «при наличии счёта формируем операцию», «операция = счёт»).

Грань — комплект УПД: 1 УПД + 1 счёт = 1 операция (решение 10.08.2026). Рождается, когда 1С вернула номер счёта по комплекту
(`onec_invoice_no`); до подключения 1С номеров нет — мост молчит. Операция — «план поступлений» на сумму комплекта с НДС:
статья — выручки основной услуги комплекта (наибольшая сумма; маппинг «услуга → статья» в справочнике услуг), контрагент —
плательщик пакета (иначе — договора), наше юрлицо — договора, № ДС, основание к закрытию — в описание.
Повтор обновляет ту же операцию (ссылка на комплект), только пока она «план поступлений»: оплаченную или поправленную бухгалтером
в другой статус не трогаем."""
import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("finance.master_deal")
PLANNED = "план поступлений"


def main_service(rows: list) -> Optional[str]:
    """Основная услуга комплекта — базовая строка с наибольшей суммой; допы услугу не задают."""
    by: dict = {}
    for r in rows or []:
        if r.get("kind") == "base" and r.get("position"):
            by[r["position"]] = by.get(r["position"], 0.0) + float(r.get("amount") or 0)
    return max(by, key=by.get) if by else None


def _kit_rows(annex, k) -> list:
    rows = list(annex.rows or [])
    if k.brand:
        rows = [r for r in rows if (r.get("brand") or "") == k.brand] or rows
    if k.service:
        rows = [r for r in rows if (r.get("position") or "") == k.service] or rows
    return rows


def _article(db: Session, annex, k) -> Optional[int]:
    name = main_service(_kit_rows(annex, k))
    if name:
        a = db.execute(text("SELECT revenue_article_id FROM sales_services WHERE name = :n"), {"n": name}).scalar()
        if a:
            return a
    # Только допы (или услуга без статьи) — статья услуги сделки комплекта
    return db.execute(text("""SELECT s.revenue_article_id FROM sales_deal_annex_allocation x JOIN sales_deals d ON d.id = x.deal_id
                               JOIN sales_services s ON s.id = d.service_id
                              WHERE x.annex_id = :a AND s.revenue_article_id IS NOT NULL ORDER BY x.deal_id LIMIT 1"""),
                      {"a": annex.id}).scalar()


def sync_kit(db: Session, m, k):
    """Операция по счёту комплекта: создать или обновить. Нет счёта — None. Оплаченную не меняем."""
    from app.annex_tpl import document as tpl_doc
    from app.models import Contract, Operation
    from app.routers.operations import compute_vat_fact
    from app.sales.models import SalesAnnex
    if not k.onec_invoice_no:
        return None
    op = db.query(Operation).filter(Operation.master_deal_upd_id == k.id).first()
    if op is not None and op.status != PLANNED:      # оплачена или поправлена бухгалтером в другой статус — мост её не трогает
        return op
    a = db.get(SalesAnnex, k.annex_id)
    c = db.get(Contract, m.contract_id)
    model = (tpl_doc.model_of(db, a, c, [r[0] for r in db.execute(
        text("SELECT deal_id FROM sales_deal_annex_allocation WHERE annex_id = :a"), {"a": a.id})]) or {}).get("model") or {}
    basis = tpl_doc.upd_closing(model, k, a.rows)["text"] if model else None
    vat = float(a.vat_rate or 0)
    income = round(float(k.gross or 0), 2)
    fields = {"date": k.onec_invoice_date or date.today(), "status": PLANNED, "income": income, "expense": 0.0, "period": m.period,
              "vat_rate": vat, "vat_fact": compute_vat_fact(income, 0.0, vat), "article_id": _article(db, a, k),
              "counterparty_id": m.payer_counterparty_id or (c.counterparty_id if c else None),
              "own_company_id": c.own_company_id if c else None, "ds_num": a.number, "invoice": k.onec_invoice_no,
              "invoice_date": k.onec_invoice_date, "description": basis, "master_deal_upd_id": k.id}
    if op is None:
        op = Operation(**fields)
        db.add(op)
    else:
        for key, v in fields.items():
            setattr(op, key, v)
    db.flush()
    return op


def sync_package(db: Session, m) -> list:
    """Все комплекты пакета со счетами — для ответа 1С (спринт 6): вызвать после записи номеров. Сбой по одному не роняет остальные."""
    from app.master_deal.models import MasterDealUpd
    out = []
    for k in db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id).order_by(MasterDealUpd.upd_no):
        try:
            with db.begin_nested():                      # сбой одного комплекта откатывает только его, сессия живая
                op = sync_kit(db, m, k)
            if op is not None:
                out.append(op.id)
        except Exception:  # noqa: BLE001
            log.exception("%s: операция по УПД № %s не сформирована", m.code, k.upd_no)
    return out
