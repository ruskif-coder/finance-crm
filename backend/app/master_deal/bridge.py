# -*- coding: utf-8 -*-
"""Мост мастер-сделка → операция (владелец 20.10.2026: «при наличии счёта формируем операцию», «операция = счёт»).

Грань — комплект УПД: 1 УПД + 1 счёт = 1 операция (решение 10.08.2026). Рождается, когда 1С вернула номер счёта по комплекту
(`onec_invoice_no`); до подключения 1С номеров нет — мост молчит. Операция — «план поступлений» на сумму комплекта с НДС:
статья — выручки основной услуги комплекта (наибольшая сумма; маппинг «услуга → статья» в справочнике услуг), контрагент —
плательщик пакета (иначе — договора), наше юрлицо — договора, № ДС, основание к закрытию — в описание.
Повтор обновляет ту же операцию (ссылка на комплект), только пока она «план поступлений»: оплаченную или поправленную бухгалтером
в другой статус не трогаем."""
import logging
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app import own_company
from app.models import PLAN_INCOME

log = logging.getLogger("finance.master_deal")
PLANNED = PLAN_INCOME          # статус из словаря модели, не своей строкой: строчными он выпадал из сводок (09.11.2026)


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


def _has_parts(db: Session, op) -> bool:
    from app.models import Operation
    return db.query(Operation.id).filter(Operation.parent_operation_id == op.id).first() is not None


def _check_mismatch(db: Session, k, op) -> None:
    """Операцию мост не обновляет, а 1С дала другие сумму или № счёта — открыть «расхождение с 1С» (владелец 20.11.2026).
    Сумма — всей цепочки оплат (материнская + части): частично оплаченная хранит в себе только остаток."""
    from app import operation_issues as OI
    from app.final_recon.money import r2
    from app.models import Operation
    parts = db.query(func.coalesce(func.sum(Operation.income), 0)).filter(Operation.parent_operation_id == op.id).scalar()
    total = r2(float(op.income or 0) + float(parts or 0))
    diffs = []
    gross = k.onec_gross if k.onec_gross is not None else k.gross
    if gross is not None and abs(total - float(gross)) > 1:
        diffs.append(f"сумма {_money(total)} → {_money(float(gross))}")
    if (op.invoice or "") != (k.onec_invoice_no or ""):
        diffs.append(f"№ счёта {op.invoice or '—'} → {k.onec_invoice_no}")
    if diffs:
        OI.raise_issue(db, op, OI.MISMATCH, f"УПД № {k.upd_no} внесён в 1С заново, операция {op.status.lower()} — мост её не "
                       f"меняет: " + "; ".join(diffs) + ". Поправьте операцию или документы.", kit_id=k.id)


def _money(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ") + " ₽"


def sync_kit(db: Session, m, k):
    """Операция по счёту комплекта: создать или обновить. Нет счёта — None. Оплаченную не меняем."""
    from app.annex_tpl import document as tpl_doc
    from app.models import Contract, Operation
    from app.routers.operations import compute_vat_fact
    from app.sales.models import SalesAnnex
    from app import operation_issues as OI
    if not k.onec_invoice_no:
        return None
    op = db.query(Operation).filter(Operation.master_deal_upd_id == k.id).first()
    if op is not None:
        # документы внесены заново — «на переделке» снята, что бы ни было с цифрами дальше
        OI.close_kind(db, op.id, OI.REDO, "документы внесены в 1С заново")
    # оплачена, поправлена бухгалтером в другой статус или уже закрывается частями — мост её не трогает (частичная оплата:
    # у материнской остаток, перезапись полной суммой задвоила бы деньги); новые цифры 1С — проблемой «расхождение с 1С»
    if op is not None and (op.status != PLANNED or _has_parts(db, op)):
        _check_mismatch(db, k, op)
        return op
    a = db.get(SalesAnnex, k.annex_id)
    c = db.get(Contract, m.contract_id)
    model = tpl_doc.basis_model(db, a, c, [r[0] for r in db.execute(
        text("SELECT deal_id FROM sales_deal_annex_allocation WHERE annex_id = :a"), {"a": a.id})])
    basis = tpl_doc.upd_closing(model, k, a.rows, db)["text"] if model else None
    vat = float(a.vat_rate or 0)
    income = round(float(k.onec_gross if k.onec_gross is not None else (k.gross or 0)), 2)   # вернувшаяся из 1С сумма — факт (решение 42)
    # «Дата» операции у плана пустая (владелец 09.11.2026) — её ставит оплата; дата счёта — своё поле `invoice_date`
    fields = {"date": None, "status": PLANNED, "income": income, "expense": 0.0, "period": m.period,
              # НДС из 1С — тоже факт (решение 42, ревью 05.11.2026); до 1С — расчёт от ставки ДС
              "vat_rate": vat, "vat_fact": round(float(k.onec_vat), 2) if k.onec_vat is not None else compute_vat_fact(income, 0.0, vat),
              "article_id": _article(db, a, k),
              "counterparty_id": m.payer_counterparty_id or (c.counterparty_id if c else None),
              "own_company_id": own_company.for_contract_id(db, c), "ds_num": a.number, "invoice": k.onec_invoice_no,
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
