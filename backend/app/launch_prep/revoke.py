"""Отзыв согласования площадкой — из кабинета (владелец 29.09.2026).

Площадка, уже согласовавшая креатив, может до запуска своего размещения передумать:
это ЗАПРОС АККАУНТУ НА ПЕРЕДЕЛКУ БАННЕРА ПО СТАНДАРТНОЙ ПРОЦЕДУРЕ. То есть её вердикт
становится «на доработку» с причиной — ровно как если бы она ответила так сразу, — и
дальше работает обычная переделка: аккаунт перезагружает креатив новым комплектом.

Отличие от нашего отзыва (withdraw.py): там решаем МЫ и пара уходит насовсем; здесь
отвечает площадка, пара остаётся с её новым ответом. Граница по времени — одна на оба
(`withdraw.blocker`): пока размещение площадки не запущено.

ЧТО ТЯНЕТ ЗА СОБОЙ, и где это держится:
* вердикт «на доработку» → креатив РК уходит из рабочих при синке (`chain_status`), не
  делит объём и не уходит в DSP;
* `agreed_at` снимается → пара выходит из порога ЕРИД и из «согласовано» у матрицы;
* получатель, у которого согласованной была только эта пара, — назад в «согласование»;
* креатив, уже заведённый в DSP, — в архив там (сбой DSP отзыв не откатывает);
* событие «ответ площадки» — аккаунту и менеджеру паблишеров (профили уведомлений).
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.launch_prep import withdraw as W

log = logging.getLogger("finance.launch_prep")
PREFIX = "Отзыв согласования"


class RevokeError(ValueError):
    """Отозвать согласование нельзя — текст для площадки."""


def blocker(db: Session, pair, target) -> Optional[str]:
    if W._platform_verdict(db, pair.id) != "ок":
        return "креатив ещё не согласован — отзывать нечего"
    return W.blocker(db, pair, target)


def revoke(db: Session, pair_id: int, reason: str, author_name: str,
           author_email: Optional[str] = None, dsp_client=None) -> dict:
    from datetime import datetime

    from app.ad import build
    from app.audit import log_action
    from app.launch_prep.models import (LaunchPrepCreativeSet, LaunchPrepPair,
                                        LaunchPrepReview, LaunchPrepTarget)
    from app.notify import emit
    from app.sales.models import SalesDeal

    reason = (reason or "").strip()
    if not reason:
        raise RevokeError("укажите, что поправить в баннере — это увидит аккаунт")
    if len(reason) > W.REASON_MAX:
        raise RevokeError(f"причина длиннее {W.REASON_MAX} символов")
    pair = db.get(LaunchPrepPair, pair_id)
    if pair is None:
        raise LookupError("задание не найдено")
    target = db.get(LaunchPrepTarget, pair.target_id)
    s = db.get(LaunchPrepCreativeSet, pair.set_id)
    why = blocker(db, pair, target)
    if why:
        raise RevokeError(why)

    rec = (db.query(LaunchPrepReview)
           .filter(LaunchPrepReview.pair_id == pair.id, LaunchPrepReview.kind == "площадка").first())
    rec.verdict = "на доработку"
    rec.reason = f"{PREFIX}: {reason}"
    rec.decided_by = author_name
    rec.decided_email = (author_email or "").strip() or None
    rec.decided_at = datetime.utcnow()
    rec.source = "кабинет"
    pair.agreed_at = None
    row = W._creative_row(db, pair, target)
    W._rollback_target_state(db, pair, target)
    db.commit()

    build.sync_deal_quietly(db, target.deal_id)
    dsp = {"state": "none"}
    if row is not None and (row.ms_creative_xxhash or "").strip():
        dsp = W._archive_in_dsp(row.ms_creative_xxhash, f"cr{row.id}", dsp_client)

    deal = db.get(SalesDeal, target.deal_id)
    log_action(db, None, "creative_pair_verdict", "sales_deal", deal.id,
               f"комплект №{s.no}: отзыв согласования площадкой ({author_name}): {reason}")
    from app.sales.deal_label import deal_label
    emit(db, "creative_verdict",
         title=f"Площадка отозвала согласование · {deal_label(deal)}",
         body=(f"Комплект №{s.no}: {reason}. Нужна переделка баннера по обычной процедуре"
               # Сбой DSP отзыв не откатывает — но молчать о нём нельзя: креатив мог
               # остаться живым в кабинете DSP (ревью 29.09.2026).
               + (f". ВНИМАНИЕ: креатив в DSP не переведён в архив — {dsp.get('why')}"
                  if dsp.get("state") == "error" else "")),
         link=f"/sales/deals/{deal.code or deal.id}",
         entity_type="sales_deal", entity_id=deal.id, actor=None, ctx={"deal": deal})
    db.commit()
    return {"verdict": rec.verdict, "dsp": dsp, "deal_id": deal.id}
