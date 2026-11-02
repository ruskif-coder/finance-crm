# -*- coding: utf-8 -*-
"""ДС на старте — через конструктор закрытия (владелец 02.11.2026; задумано 16.10: «кнопка “Создать” поведёт на промежуточный
конструктор закрытия»).

Кнопка «Создать» в карточке сделки заводит мастер-сделку `issued_at_start`:
  · одна сделка — один ДС, к пакету никто не присоединяется (владелец: «не участвует в объединении»);
  · со «Сборки» (МП зафиксирован) и до итоговой сверки — дальше ДС закрытия делается «Отправить в ДО»;
  · договор — доходный договор сделки (блок ОРД), как у любой мастер-сделки, а не последний договор плательщика;
  · раскладка — по медиаплану, без сверки; ДС — первичный (`issue_kind='primary'`); «Подтвердить ДС» → «ждём закрытия».
На итоговой сверке «Отправить в ДО» находит сделку в этом же пакете и возвращает его в черновик — стартовая фаза кончилась,
дальше пакет закрывается по факту (`to_annex.create`: первичный ДС не у клиента — пересборка с тем же номером; у клиента
и не подписан — стоп; подписан — УПД по факту к нему)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.master_deal import service as MS
from app.master_deal import status as ST
from app.master_deal.models import MasterDeal, MasterDealItem


def why_not(db: Session, deal) -> Optional[str]:
    """Почему по этой сделке нельзя выпустить ДС на старте; None — можно."""
    from app.sales import plan_lock
    from app.sales.catalog import Catalog
    cat = Catalog(db)
    cur = cat.by_id.get(deal.our_stage_id)
    if cur is not None and (getattr(cur, "is_lost", False) or getattr(cur, "is_terminal", False)):
        return f"Сделка на «{cur.name}» — ДС на старте не выпускается"
    if not plan_lock.stage_locks_plan(cat, deal.our_stage_id):
        return "ДС на старте — со «Сборки»: медиаплан к этому моменту зафиксирован"
    order = {x.id: i for i, x in enumerate(cat.stages)}
    recon = next((x for x in cat.stages if x.name == MS.RECON_STAGE), None)
    if recon is not None and order.get(deal.our_stage_id, -1) >= order[recon.id]:
        return f"Сделка на «{cur.name}» — ДС закрытия делается кнопкой «Отправить в ДО»"
    if not deal.ord_final_contract_id:
        return "У сделки не выбран доходный договор — выберите его в блоке ОРД карточки сделки"
    if not deal.period_from:
        return "У сделки нет периода — финансовый месяц нужен пакету"
    return None


def start(db: Session, deal, user) -> MasterDeal:
    """Завести пакет со стартовым ДС для сделки или вернуть уже заведённый. Отказ — MasterError с текстом для человека."""
    it = MS.item_of(db, deal.id)
    if it is not None:
        m = db.get(MasterDeal, it.master_deal_id)
        if m.issued_at_start:
            return m
        raise MS.MasterError(409, f"Сделка уже в мастер-сделке {m.code} — ДС делается там")
    why = why_not(db, deal)
    if why:
        raise MS.MasterError(409, why)
    m = MasterDeal(code=MS._new_code(db), contract_id=deal.ord_final_contract_id, period=MS.period_of(deal),
                   payer_counterparty_id=deal.payer_counterparty_id, created_by=getattr(user, "id", None), issued_at_start=True)
    db.add(m)
    db.flush()
    db.add(MasterDealItem(master_deal_id=m.id, deal_id=deal.id, added_by=getattr(user, "id", None)))
    db.flush()
    return m


def closing_started(db: Session, m) -> bool:
    """Сделку пакета уже отправили в ДО (сверка заморожена) — стартовая фаза кончилась."""
    return bool(db.execute(text("""SELECT 1 FROM master_deal_items i JOIN final_recon_deals r ON r.deal_id = i.deal_id
                                    WHERE i.master_deal_id = :m AND r.sent_at IS NOT NULL LIMIT 1"""), {"m": m.id}).first())


def in_start_phase(db: Session, m) -> bool:
    return bool(getattr(m, "issued_at_start", False)) and not closing_started(db, m)


def status_after_confirm(db: Session, m) -> str:
    """Куда уходит пакет, когда все его ДС подтверждены: стартовый — ждать закрытия, обычный — ждать УПД из 1С."""
    return ST.WAIT_CLOSE if in_start_phase(db, m) else ST.WAIT_1C


def reopen_for_closing(db: Session, m) -> None:
    """«Отправить в ДО» по сделке стартового пакета: пакет возвращается в черновик и дальше закрывается по факту.
    ДС на старте ещё не подтверждён — закрытие не начинаем: черновик старта сначала подтверждают или возвращают в раскладку."""
    if m.status == ST.AGREE:
        raise MS.MasterError(409, f"В пакете {m.code} неподтверждённый ДС на старте — подтвердите его или верните в раскладку")
    if m.status == ST.WAIT_CLOSE:
        m.status, m.updated_at = ST.DRAFT, datetime.utcnow()
