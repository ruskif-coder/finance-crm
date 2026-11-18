# -*- coding: utf-8 -*-
"""Правка медиаплана сразу тянет за собой систему (владелец 18.11.2026: «все правки МП — даты, период, услуги, объёмы, цены —
сразу меняют всё по системе, без обновления при открытии»).

Здесь — то, что держит КОПИЮ данных медиаплана и раньше от него отставало:

  · `snapshot_rows` + `carry_fact_entries` — факт, введённый аккаунтом в итоговой сверке, привязан к id строки МП
    (`final_recon_fact_entries.mp_row_id`), а сохранение МП пересоздаёт строки с новыми id (`_write_children`, и новая
    версия — тоже новые строки). Без переноса введённый факт терялся: сверка показывала пустые поля;
  · `follow_period` — получатели сборки запуска хранят период на момент добавления (`launch_prep_target.period_from/to`), и
    он важнее живого периода сделки в срочности трафика, зависших парах и выгрузке внешних каналов. Двигаем вместе со сделкой
    тех, у кого период был равен прежнему периоду сделки; суженный руками (продление внутри месяца) не трогаем.

Пересчёт РК и лимитов DSP — `app.ad.volumes_now.replan_now`, его зовут все пути записи МП.
"""
from collections import defaultdict
from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session


def _key(position, model, inventory, fmt) -> tuple:
    return ((position or "").strip().lower(), (model or "").strip().upper(), (inventory or "").strip().lower(),
            (fmt or "").strip().lower())


def snapshot_rows(db: Session, plan_id: Optional[int]) -> List[Tuple[int, tuple]]:
    """[(id строки, ключ)] в порядке строк — до того, как строки перепишут."""
    if not plan_id:
        return []
    from app.sales.models import SalesMediaPlanRow
    rows = (db.query(SalesMediaPlanRow).filter(SalesMediaPlanRow.plan_id == plan_id)
            .order_by(SalesMediaPlanRow.sort_order, SalesMediaPlanRow.id).all())
    return [(r.id, _key(r.position, r.model, r.inventory, r.format)) for r in rows]


def carry_fact_entries(db: Session, deal_id: Optional[int], old: List[Tuple[int, tuple]], new_plan_id: int) -> int:
    """Перевесить введённый факт со старых строк на новые. Сопоставление — по смыслу строки (услуга, модель, поверхность,
    формат), среди одинаковых — по порядку. Строку убрали из МП — её факт остаётся висеть (это решение аккаунта, не наше).
    → сколько записей перевешено."""
    if not deal_id or not old:
        return 0
    from app.final_recon.models import FinalReconFactEntry
    entries = {e.mp_row_id: e for e in db.query(FinalReconFactEntry).filter(FinalReconFactEntry.deal_id == deal_id).all()}
    if not any(rid in entries for rid, _ in old):
        return 0
    db.flush()                                     # новые строки должны получить id (autoflush в проекте выключен)
    queue = defaultdict(list)
    for rid, k in snapshot_rows(db, new_plan_id):
        queue[k].append(rid)
    moved = 0
    for rid, k in old:
        e = entries.get(rid)
        if e is None or not queue[k]:
            continue
        new_id = queue[k].pop(0)
        if new_id != rid:
            e.mp_row_id = new_id
            moved += 1
    return moved


def follow_period(db: Session, deal_id: int, old_from: Optional[date], old_to: Optional[date],
                  new_from: Optional[date], new_to: Optional[date]) -> int:
    """Период получателей сборки — за периодом сделки, если он был равен прежнему периоду сделки. → сколько сдвинуто."""
    if (old_from, old_to) == (new_from, new_to) or new_from is None:
        return 0
    from app.launch_prep.models import LaunchPrepTarget
    rows = (db.query(LaunchPrepTarget).filter(LaunchPrepTarget.deal_id == deal_id,
                                              LaunchPrepTarget.period_from == old_from,
                                              LaunchPrepTarget.period_to == old_to).all())
    for t in rows:
        t.period_from, t.period_to = new_from, new_to
    return len(rows)


def refresh_drafts(db: Session, deal_id: Optional[int], user=None) -> None:
    """Черновые ДС пакета сделки — сразу из МП (владелец 18.11.2026: до ЭДО документы обновляются сразу, после «ушло в ЭДО» —
    только отзывом по кнопке). Правила, что можно трогать, — в `master_deal.sync_rows` (неподтверждённый ДС, не у клиента);
    раньше это делалось только при открытии карточки пакета или ДС."""
    if not deal_id:
        return
    from app.master_deal import sync_rows as SR
    from app.master_deal.models import MasterDeal, MasterDealItem
    m = (db.query(MasterDeal).join(MasterDealItem, MasterDealItem.master_deal_id == MasterDeal.id)
         .filter(MasterDealItem.deal_id == deal_id).first())
    SR.on_open(db, m, user)


def follow_plan_change(db: Session, deal_ids, user=None) -> None:
    """После записи МП (сохранение, правка из реестра, привязка/отвязка, удаление, сдвиг месяца): план РК и лимиты DSP, черновые
    ДС пакета. Каждая часть не роняет запись — она уже сделана; ночные прогоны остаются страховкой."""
    import logging
    from app.ad.volumes_now import replan_now
    for deal_id in {d for d in (deal_ids if isinstance(deal_ids, (list, set, tuple)) else [deal_ids]) if d}:
        replan_now(db, deal_id)
        try:
            refresh_drafts(db, deal_id, user)
        except Exception:  # noqa: BLE001
            db.rollback()
            logging.getLogger(__name__).exception("сделка %s: черновые ДС из МП не обновлены", deal_id)
