# -*- coding: utf-8 -*-
"""Отзыв креатива у площадки до запуска её размещения (владелец 28.09.2026).

Решения владельца:

* граница — РАЗМЕЩЕНИЕ ЭТОЙ ПЛОЩАДКИ, а не РК целиком: пока оно не запущено, отзыв
  возможен, даже если креатив уже выгружен в DSP;
* отзывать можно и то, что площадка уже согласовала;
* отзывает мастер аккаунтов (и админ) — тот же предикат, что снимает «саморекламу»;
* площадке — уведомление с причиной, сразу;
* вернуть отозванное нельзя: заново — перезагрузкой креатива по обычной процедуре
  (новый комплект), и тогда у площадки появится новая задача, а не воскресшая старая.

ОТЗЫВ — СВОЙСТВО ПАРЫ, А НЕ ВЕРДИКТ. Вердикт пишет площадка; отзываем мы. Строка проверки
площадки остаётся как была: по ней видно, что площадка успела сказать до отзыва.

ЧТО ОТЗЫВ ТЯНЕТ ЗА СОБОЙ:

* задача уходит из кабинета площадки (`pub.task_v1` отбрасывает отозванные пары);
* креатив РК — «отклонён» (ручной статус, синк его не перетрёт): не делит объём, не
  уходит в DSP, не держит площадку «у площадки»;
* пара выходит из порога ЕРИД (`active_pairs`);
* получатель, у которого согласованной была только эта пара, возвращается в
  «согласование»;
* креатив, уже заведённый в DSP, переводится там в архив — по нему больше ничего не
  должно открутиться. Сбой DSP отзыв НЕ откатывает: решение записано, а экран говорит,
  что в DSP креатив остался, и почему.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("finance.launch_prep")

# Дальше этих состояний получатель уже в эфире или позади — отзывать поздно.
PLACED_STATES = ("в размещении", "завершён", "сверка завершена", "архив")
# Ручные статусы размещения в РК — запуск или то, что бывает только после него.
# Площадка уже запускалась — это ручные статусы площадки (Н-2: копия расходилась бы).
from app.ad.flight import PLACEMENT_MANUAL as PLACEMENT_STARTED  # noqa: E402
from app.dsp import client as ds  # noqa: E402
# Состояния получателя, которые держались на согласованной паре.
AGREED_STATES = ("согласован", "ерид получен", "заведён в DSP")
REASON_MAX = 500


KIND_WITHDRAW = "отзыв"
KIND_DECLINE = "отказ в правках"


class WithdrawError(ValueError):
    """Отзыв невозможен — текст для человека."""


def _platform_verdict(db: Session, pair_id: int) -> Optional[str]:
    return db.execute(text(
        "SELECT verdict FROM launch_prep_review WHERE pair_id = :p AND kind = 'площадка'"),
        {"p": pair_id}).scalar()


def _placement(db: Session, target):
    """Размещение площадки в РК этой сделки — или None, если РК ещё не собрана."""
    from app.ad.models import AdCampaign, AdCampaignPlacement
    return (db.query(AdCampaignPlacement)
            .join(AdCampaign, AdCampaign.id == AdCampaignPlacement.campaign_id)
            .filter(AdCampaign.deal_id == target.deal_id,
                    AdCampaignPlacement.publisher_id == target.publisher_id).first())


def blocker(db: Session, pair, target) -> Optional[str]:
    """Почему отозвать нельзя, или None. Одна функция для кнопки и для ручки."""
    if pair.withdrawn_at:
        return "креатив у этой площадки уже отозван"
    if not pair.sent_at:
        return "площадке креатив ещё не уходил — он у трафика"
    if _platform_verdict(db, pair.id) == "отказ":
        return "площадка уже отказалась — отзывать нечего"
    if target.state in PLACED_STATES:
        return "размещение уже запущено — отзыв возможен только до запуска"
    pl = _placement(db, target)
    if pl is not None and pl.status in PLACEMENT_STARTED:
        return "размещение уже запущено — отзыв возможен только до запуска"
    return None


def _creative_row(db: Session, pair, target):
    from app.ad.models import AdCampaignCreative
    pl = _placement(db, target)
    if pl is None:
        return None
    return (db.query(AdCampaignCreative)
            .filter(AdCampaignCreative.placement_id == pl.id,
                    AdCampaignCreative.root_set_id == pair.set_id).first())


def _rollback_target_state(db: Session, pair, target) -> None:
    """Согласованной у получателя была только эта пара — назад в «согласование»."""
    from app.launch_prep.models import LaunchPrepPair
    if target.state not in AGREED_STATES:
        return
    db.flush()
    other = (db.query(LaunchPrepPair)
             .filter(LaunchPrepPair.target_id == target.id, LaunchPrepPair.id != pair.id,
                     LaunchPrepPair.agreed_at.isnot(None),
                     LaunchPrepPair.withdrawn_at.is_(None)).first())
    if other is None:
        target.state = "согласование"


def _archive_in_dsp(xxhash: str, ref: str, client=None) -> dict:
    from app.dsp.client import PROD, MsClient, MsError
    try:
        c = client or MsClient(contour=PROD)
        c.creative_set_status(xxhash, ds.ARCHIVE, local_ref=ref)
        return {"state": "archived", "xxhash": xxhash}
    except (MsError, ValueError) as e:
        log.warning("Отзыв %s: креатив %s в DSP не архивирован: %s", ref, xxhash, e)
        return {"state": "error", "xxhash": xxhash, "why": str(e)[:300]}


def _tell_publisher(db: Session, pair, s, target, reason: str) -> dict:
    """Площадке — сразу и с причиной. Сбой рассылки отзыв не отменяет."""
    from app.notify.outward import notify_publisher
    from app.launch_prep.erid_service import _deal_brand_name, deal_period_text
    from app.sales.models import SalesDeal, SalesPublisher

    pub = db.get(SalesPublisher, target.publisher_id)
    deal = db.get(SalesDeal, target.deal_id)
    if pub is None or deal is None:
        return {"status": "skip"}
    brand = _deal_brand_name(db, deal)
    period = deal_period_text(deal)
    context = " · ".join(x for x in ((pub.domain or pub.name), brand, period) if x)
    try:
        return notify_publisher(
            db, "креатив отозван", pub.id,
            title="Креатив отозван",
            body=f"Мы отозвали этот материал. Причина: {reason}. Размещать его не нужно — "
                 "если будет замена, она придёт отдельной задачей.",
            facts=[("комплект", f"№{s.no}"), ("причина", reason)],
            context=context, link="/", entity_type="launch_prep_pair", entity_id=pair.id,
            values={"бренд": brand, "период": period})
    except Exception as e:                                   # noqa: BLE001
        db.rollback()
        log.warning("Площадке %s не ушло «креатив отозван»: %s", pub.id, e)
        return {"status": "error", "why": str(e)[:200]}


def withdraw(db: Session, pair_id: int, user, reason: str, dsp_client=None,
             kind: str = KIND_WITHDRAW) -> dict:
    """Отозвать. Порядок: запись у нас → коммит → DSP → площадке.

    Своё записываем ПЕРВЫМ: отказ DSP или почты не должен оставить креатив «у площадки»,
    когда решение уже принято. Остальное — последствия, их исход возвращается в ответе.
    """
    from app.ad import build
    from app.audit import log_action
    from app.launch_prep.models import LaunchPrepCreativeSet, LaunchPrepPair, LaunchPrepTarget

    reason = (reason or "").strip()
    if not reason:
        raise WithdrawError("укажите причину — её увидит площадка")
    if len(reason) > REASON_MAX:
        raise WithdrawError(f"причина длиннее {REASON_MAX} символов")
    from app.notify.outward.send import has_amount
    if has_amount(reason):
        # Причину увидит площадка; наших сумм ей не пишем никогда (правило 16.09.2026,
        # аудит 01.10.2026, К-1). Отказ, а не молчаливая подмена: человек должен знать,
        # что именно уйдёт.
        raise WithdrawError("в причине сумма — площадке деньги не пишем, сформулируйте без неё")
    pair = db.get(LaunchPrepPair, pair_id)
    if pair is None:
        raise LookupError("пара не найдена")
    target = db.get(LaunchPrepTarget, pair.target_id)
    s = db.get(LaunchPrepCreativeSet, pair.set_id)
    why = blocker(db, pair, target)
    if why:
        raise WithdrawError(why)
    # Отказ в правках (владелец 30.09.2026) — ответ на ЗАПРОС ПРАВОК площадки: без него
    # отказывать не в чем. Последствия — те же, что у отзыва: из ротации РК, из порога
    # ЕРИД, из DSP; площадке — то же письмо с нашим ответом.
    if kind == KIND_DECLINE and _platform_verdict(db, pair.id) != "на доработку":
        raise WithdrawError("площадка не просила правок — отказывать не в чем")

    pair.withdrawn_at = datetime.utcnow()
    pair.withdrawn_by = getattr(user, "id", None)
    pair.withdraw_reason = reason
    pair.withdraw_kind = kind
    row = _creative_row(db, pair, target)
    xxhash = (row.ms_creative_xxhash or "").strip() if row is not None else ""
    if row is not None:
        row.status = "отклонён"
    _rollback_target_state(db, pair, target)
    db.commit()
    build.sync_deal_quietly(db, target.deal_id)

    dsp = (_archive_in_dsp(xxhash, f"cr{row.id}", dsp_client) if xxhash
           else {"state": "none"})
    mail = _tell_publisher(db, pair, s, target, reason)
    action = "creative_rework_declined" if kind == KIND_DECLINE else "creative_withdrawn"
    verb = "правки площадки не приняты" if kind == KIND_DECLINE else "отозван у площадки"
    log_action(db, user, action, "launch_prep_pair", pair.id,
               f"комплект №{s.no} {verb} #{target.publisher_id}: {reason}"
               + (f"; DSP: {dsp['state']}" if xxhash else ""))
    return {"pair_id": pair.id, "withdrawn_at": pair.withdrawn_at, "dsp": dsp,
            "publisher_notified": (mail or {}).get("status")}
