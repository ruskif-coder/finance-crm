# -*- coding: utf-8 -*-
"""Удаление сделок — одни правила для реестра и для удаления воронки.

Решение владельца 23.09.2026 и аудит 3.H3 / 3.M9. Удаление сделки каскадом снимает
кампании, разнесения по приложениям, сборку запуска и историю стадий, а медиапланы
оставляет без сделки. Поэтому сделка с привязанной работой не удаляется ни из реестра, ни
вместе с воронкой: сначала отвязать — тогда удаление осознанное.

Два внешних ключа без каскада (комментарии и «продление от») роняли удаление с 500 —
`purge_links` снимает их явно.
"""
from __future__ import annotations


def holders(db, deal_ids) -> dict:
    """{id сделки: [что к ней привязано]} — пусто, если удалять можно."""
    from app.ad.models import AdCampaign
    from app.launch_prep.models import LaunchPrepTarget
    from app.sales.models import SalesDealAnnexAllocation, SalesMediaPlan
    ids = list(deal_ids or [])
    if not ids:
        return {}
    held: dict = {}
    for what, col in (("приложение к договору", SalesDealAnnexAllocation.deal_id),
                      ("кампания трафика", AdCampaign.deal_id),
                      ("медиаплан", SalesMediaPlan.deal_id),
                      ("сборка запуска", LaunchPrepTarget.deal_id)):
        for (did,) in db.query(col).filter(col.in_(ids)).distinct().all():
            held.setdefault(did, []).append(what)
    return held


def describe(db, held: dict) -> str:
    from app.sales.models import SalesDeal
    codes = {d.id: d.code or str(d.id) for d in
             db.query(SalesDeal).filter(SalesDeal.id.in_(list(held))).all()}
    return "; ".join(f"{codes.get(i, i)} — {', '.join(w)}" for i, w in sorted(held.items()))


def purge_links(db, deal_ids) -> None:
    """Внешние ключи без каскада: комментарии уходят со сделкой, ссылку «продление от» у
    ДРУГИХ сделок снимаем, а не удаляем сами сделки."""
    from app.sales.models import SalesDeal, SalesDealComment
    ids = list(deal_ids or [])
    if not ids:
        return
    db.query(SalesDealComment).filter(SalesDealComment.deal_id.in_(ids)).delete(
        synchronize_session=False)
    db.query(SalesDeal).filter(SalesDeal.prolonged_from_id.in_(ids)).update(
        {SalesDeal.prolonged_from_id: None}, synchronize_session=False)
