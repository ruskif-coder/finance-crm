# -*- coding: utf-8 -*-
"""Пересчёт объёмов РК «сейчас», по событию, а не ночью (владелец 08.10.2026).

Одна функция — `refresh_volumes_now(db, deal_id)`: её зовёт согласование площадки («ок»), запуск площадки и
(позже) автоматическая цепочка заведения. Что она делает:

  1. пересобирает площадки и доли РК (`build.sync_deal`) — тот же расчёт, что ночью;
  2. если РК уже выгружена в DSP — сразу переписывает лимиты её креативов (`dsp.limits.sync_limits`): раньше
     они доезжали только ночью, и на оперативном старте креатив стоял со старым лимитом до утра;
  3. считает «объём, если стартует сейчас» для согласованных, но не запущенных площадок — их показывает паспорт
     с пометкой «предварительно». Это ЛЕТУЧЕЕ число: в базу оно не пишется, у остальных площадок объём не
     меняется, пока эта не запущена (правило «после 5-го дня делят только запущенные и на паузе» цело).

Сбой функции НЕ роняет вызвавшее действие: вердикт и старт уже записаны, ночной прогон остаётся страховкой.
"""
import logging

from sqlalchemy.orm import Session

from app.ad import build
from app.ad.flight import PLACEMENT_READY
from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement

log = logging.getLogger("finance.ad")


def push_limits(db: Session, camp: AdCampaign, client=None) -> dict:
    """Лимиты креативов РК в DSP по текущим планам. Нет выгрузки в DSP или сбой — отчёт, не исключение."""
    if not camp.ms_campaign_xxhash:
        return {"campaign_id": camp.id, "updated": 0, "zero": [], "failed": [], "skipped": True}
    try:
        from app.dsp.client import MsClient
        from app.dsp.limits import sync_limits
        return sync_limits(db, camp, client or MsClient())
    except Exception as e:  # noqa: BLE001 — отчёт, ночной прогон повторит
        db.rollback()
        log.exception("РК %s: лимиты по событию не ушли в DSP", camp.id)
        return {"campaign_id": camp.id, "updated": 0, "zero": [],
                "failed": [{"creative_id": None, "error": str(e)}]}


def preview_plans(db: Session, camp: AdCampaign) -> dict:
    """{creative_id: показы} для креативов согласованных, но НЕ запущенных площадок без записанного плана.

    Расчёт — раскладка РК, в которой эти площадки считаются запущенными (`campaign_layout(assume_running=…)`),
    и деление плана площадки между её креативами (`creative_plans`). Пусто: таких площадок нет (в первые
    5 дней согласованные уже входят в раскладку и план у них записан)."""
    waiting = [p for p in db.query(AdCampaignPlacement)
               .filter(AdCampaignPlacement.campaign_id == camp.id,
                       AdCampaignPlacement.status == PLACEMENT_READY).all() if not p.plan_show]
    if not waiting:
        return {}
    ids = {p.id for p in waiting}
    _pls, out = build.campaign_layout(db, camp.id, assume_running=ids)
    extra = {r["id"]: r["plan_show"] for r in out["rows"] if r["id"] in ids and r["plan_show"]}
    if not extra:
        return {}
    mine = {cid for (cid,) in db.query(AdCampaignCreative.id)
            .filter(AdCampaignCreative.campaign_id == camp.id,
                    AdCampaignCreative.placement_id.in_(list(extra)))}
    plans = build.creative_plans(db, camp, extra_plans=extra)
    return {cid: v for cid, v in plans.items() if cid in mine and v}


def refresh_volumes_now(db: Session, deal_id: int, *, client=None, sync_dsp: bool = True) -> dict:
    """Пересобрать РК сделки и сразу обновить лимиты в DSP. Не падает: в ответе `error` или итог."""
    camp = db.query(AdCampaign).filter(AdCampaign.deal_id == deal_id).first()
    if camp is None:
        return {"skipped": "нет РК"}
    try:
        res = build.sync_deal(db, deal_id)          # коммитит; тот же расчёт, что ночью
    except Exception as e:  # noqa: BLE001
        db.rollback()
        log.warning("Пересборка РК сделки %s по событию не удалась: %s", deal_id, e)
        return {"error": str(e)}
    out = {"campaign_id": camp.id, **res}
    if sync_dsp:
        out["limits"] = push_limits(db, camp, client)
    return out


def preview_note() -> str:
    return "предварительно — площадка ещё не запущена"
