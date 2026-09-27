# -*- coding: utf-8 -*-
"""Лимиты креативов в DSP догоняют план РК (владелец 27.09.2026).

План площадки меняется после выгрузки: запустили часть площадок, закончилось удержание
первых пяти дней, поправили индекс в балансировщике, отклонили креатив. Лимит креатива в
DSP ставится при выгрузке и сам не меняется — без этого модуля DSP крутил бы по плану дня
выгрузки. Раз в сутки (`app/ad/daily_shares`) доля каждого заведённого креатива
сравнивается с последним отправленным лимитом и расходящиеся правятся `Creative.edit`.

Раз в сутки, а не на каждое событие: суточный темп раскладывает пейсер DSP, и
перераспределение действует со следующего суточного плана (`ad/flight`). Сеть на каждое
нажатие трафика ничего не ускорила бы.

Лимит `total` — за весь срок, не остаток (память dsp-api). Креатив без доли (отклонён,
не участвует в раскладке) не трогаем: ноль в DSP означает «без лимита», а не «не крутить».
"""
import logging

from sqlalchemy.orm import Session

from app.ad.build import creative_plans
from app.ad.models import AdCampaign, AdCampaignCreative
from app.dsp.client import MsError

log = logging.getLogger("finance.dsp")


def sync_limits(db: Session, camp: AdCampaign, client) -> dict:
    """Подтянуть лимиты заведённых креативов РК. Сбой одного не останавливает остальных."""
    plans = creative_plans(db, camp)
    updated, failed, zero = 0, [], []
    crs = (db.query(AdCampaignCreative)
           .filter(AdCampaignCreative.campaign_id == camp.id,
                   AdCampaignCreative.ms_creative_xxhash.isnot(None)).all())
    for cr in crs:
        want = plans.get(cr.id)
        if want == 0:
            # Доля обнулилась у уже заведённого креатива. Отправить 0 нельзя (в DSP это
            # «без лимита»), молчать тоже — он продолжит крутить по старому лимиту. Отдаём
            # в отчёт прогона, решает трафик: пауза или другой заданный объём.
            zero.append(cr.id)
            continue
        if want is None:
            continue
        want = int(want)
        ref = f"cr{cr.id}"
        if client.last_sent_show_limit(ref) == want:
            continue
        try:
            client.creative_edit(cr.ms_creative_xxhash,
                                 {"limits": {"show": {"total": want}}}, local_ref=ref)
            updated += 1
        except MsError as e:
            log.warning("лимит креатива %s не обновлён: %s", cr.id, e)
            failed.append({"creative_id": cr.id, "error": str(e)})
    if zero:
        log.warning("РК %s: у заведённых креативов %s доля стала нулевой — лимит не менялся",
                    camp.id, zero)
    return {"campaign_id": camp.id, "updated": updated, "failed": failed, "zero": zero}
