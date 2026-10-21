# -*- coding: utf-8 -*-
"""Первичный ДС пакета на закрытии (владелец 16.10.2026).

ДС бывает выпущен на старте на план («первичный», `issue_kind='primary'`). На закрытии:
  · НЕ подписан — важен только его номер: этот же ДС пересобирается по факту из раскладки (номер и дата прежние; подтверждённый
    перезамораживается), дальше он — ДС «по факту»; ДС допов (n-01) создаётся рядом с тем же номером;
  · подписан — ДС не трогаем (юридический документ на план), комплекты УПД идут по факту и привязываются к нему; расхождение
    «ДС … · закрываем … · недокрут …» показывается, не блокирует.
Подпись перепроверяется непосредственно перед действием (`annex_signed.signed_state`: ЭДО → файл ДС → нет данных)."""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.master_deal import service as MS
from app.master_deal.models import MasterDeal


def primary_of(db: Session, m: MasterDeal):
    """Первичный ДС, на который сделки пакета были выпущены на старте; None — нет. Разные первичные ДС у сделок пакета — отказ."""
    from app.sales.models import SalesAnnex
    ids = [r[0] for r in db.execute(text("""
        SELECT DISTINCT a.id FROM sales_annexes a
          JOIN sales_deal_annex_allocation al ON al.annex_id = a.id
          JOIN master_deal_items i ON i.deal_id = al.deal_id AND i.master_deal_id = :m
         WHERE a.issue_kind = 'primary' AND (a.master_deal_id IS NULL OR a.master_deal_id = :m)"""), {"m": m.id})]
    if len(ids) > 1:
        raise MS.MasterError(409, "У сделок пакета разные первичные ДС — соберите их отдельными мастер-сделками")
    return db.get(SalesAnnex, ids[0]) if ids else None


def info(db: Session, m: MasterDeal, layout_gross: Optional[float]) -> Optional[dict]:
    """Что показать на раскладке: первичный ДС, подписан ли (и чем), его сумма против суммы закрытия."""
    from app.sales import annex_signed
    try:
        p = primary_of(db, m)
    except MS.MasterError as e:
        return {"error": e.message}
    if p is None:
        return None
    st = annex_signed.signed_state(db, p)
    gross = float(p.total_amount or 0)
    return {"id": p.id, "number": p.number or "черновик без номера", "confirmed": p.no is not None, "gross": gross,
            "signed": st["signed"], "source": st["source_label"], "signed_at": st["at"], "conflict": st["conflict"],
            "closing_gross": layout_gross, "diff": round((layout_gross or 0) - gross, 2) if layout_gross is not None else None,
            "branch": "signed" if st["signed"] else "rebuild"}
