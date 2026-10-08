# -*- coding: utf-8 -*-
"""«Темп размещения» (08.10.2026): остаток РК временно поднят на X % на N дней.

DSP принимает на креатив только итог за весь флайт и сам равномерно раскладывает его по дням
(`uniform_pro`), поэтому «поднять суточный лимит» — это временно поднять итог, а потом вернуть.
Дни не трогаем: сокращать нечего, и флайт остаётся прежним.

  · множитель стоит на ОСТАТКЕ (план минус факт) и только у запущенных площадок без заданного
    объёма — пауза, ждущие, выбывшие и «на фиксе» остаются как были;
  · план самой РК (`AdCampaign.plan_show`) не меняется: клиентские отчёты и выгрузки прежние;
  · после последнего дня буста ночной прогон закрывает его (`expire_due`), и раскладка снова идёт по
    исходному плану. Показы, накрученные за время буста, уже в факте — остаток и суточная норма
    ниже сами, отдельного «возврата» объёма нет;
  · «день» = сутки после сегодняшних: сегодняшний уже отчитан (так считает весь `ad/flight`),
    объём же в DSP меняется сразу.

Раскладка читает буст в ОДНОМ месте — `build.campaign_layout` (её же зовут ночной пересчёт и
страница «Биддер»), поэтому ночью буст не откатывается раньше срока.
"""
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.ad.flight import PLACEMENT_RUNNING, Flight
from app.ad.models import AdCampaign, AdCampaignBoost

MAX_PCT = 100


class BoostError(ValueError):
    """Буст завести нельзя; текст — человеку."""


def window(fl: Optional[Flight], pct, days, today: date) -> Tuple[date, date]:
    """(первый, последний день) буста или `BoostError`. Дни проверяются до конца флайта."""
    if not isinstance(pct, int) or isinstance(pct, bool) or not 1 <= pct <= MAX_PCT:
        raise BoostError(f"Процент — целое число от 1 до {MAX_PCT}")
    if not isinstance(days, int) or isinstance(days, bool) or days < 1:
        raise BoostError("Дней — целое число, не меньше одного")
    if fl is None:
        raise BoostError("У РК не заданы даты флайта")
    if fl.done <= 0:
        raise BoostError("РК ещё не стартовала: поднимать пока нечего")
    if fl.left <= 0:
        raise BoostError("Флайт закончился: нет дней, на которые можно поднять")
    if days > fl.left:
        raise BoostError(f"Дней до конца флайта — {fl.left}, а нужно {days}. Выберите не больше")
    return today, today + timedelta(days=days)


def active(db: Session, campaign_id: int) -> Optional[AdCampaignBoost]:
    return (db.query(AdCampaignBoost)
            .filter(AdCampaignBoost.campaign_id == campaign_id,
                    AdCampaignBoost.ended_at.is_(None)).first())


def is_live(b: Optional[AdCampaignBoost], today: Optional[date] = None) -> bool:
    """Действует ли буст в этот день: открыт и день внутри окна. После последнего дня — нет, даже
    если ночной прогон его ещё не закрыл: раскладка не должна держать объём дольше срока."""
    today = today or date.today()
    return bool(b and b.ended_at is None and b.starts_on <= today <= b.until)


def boostable(row) -> bool:
    """Касается ли буст площадки: запущена, без заданного объёма, не выбыла (правила 25.09 и 05.10.2026)."""
    return row.get("status") in PLACEMENT_RUNNING and not row.get("fixed") and not row.get("settled")


def boost_rows(rows, facts: Optional[dict], pct: int):
    """Раскладка РК с бустом → (новые строки, добавка к плану РК).

    Буст — на ОСТАТКЕ ПЛОЩАДКИ: план' = план + (план − факт) × pct/100, и только у тех, кого он касается
    (`boostable`). Остальные строки не трогаются — их доли и планы остаются как в раскладке без буста
    (раньше добавка уходила в общий пул и делилась по весам и на паузу, и на ждущих).

    ПОТОЛОК ДОЛИ буст не зажимает намеренно: он — явная команда трафика («принудительно поднять»), а подъём
    на один и тот же процент остатка у всех касаемых площадок сохраняет их доли друг относительно друга, то
    есть то равновесие, которое потолок и стережёт. Зажатие же делало бы буст бесполезным там, где запущена
    одна-две площадки (потолок у них и так поднят до равной доли). `facts` — факт по площадкам с начала РК
    (None — не знаем, остаток от всего плана площадки)."""
    out, extra = [], 0
    for r in rows:
        if not boostable(r):
            out.append(r)
            continue
        base = r.get("plan_show") or 0
        fact = (facts or {}).get(r["id"], 0) or 0
        new = round(base + max(0.0, base - fact) * pct / 100.0)    # остаток × (1 + pct), не ниже прежнего плана
        extra += new - base
        out.append({**r, "plan_show": new, "boosted": new != base})
    return out, extra


def effective_pct(rest: float, rest_free: float, pct: float) -> float:
    """pct, пересчитанный на ВЕСЬ остаток РК: график рисует норму РК целиком, а поднимается только часть."""
    return pct * rest_free / rest if rest > 0 else 0.0


def start(db: Session, camp: AdCampaign, pct, days, *, user_id: Optional[int],
          facts: Optional[dict], today: Optional[date] = None) -> AdCampaignBoost:
    """Завести буст; действующий закрывается («заменён»). Коммит — на вызывающем."""
    from app.ad.flight import flight_of
    today = today or date.today()
    starts_on, until = window(flight_of(camp.date_start, camp.date_end, today), pct, days, today)
    prev = active(db, camp.id)
    if prev:
        end(db, prev, "заменён")
        db.flush()   # уникальный индекс «один активный на РК» — старый закрыт до вставки нового
    fact_total = sum((facts or {}).values())
    rest = max(0, round((camp.plan_show or 0) - fact_total))
    b = AdCampaignBoost(campaign_id=camp.id, pct=pct, days=days, starts_on=starts_on, until=until,
                        rest_at_start=rest, created_by=user_id)
    db.add(b)
    db.flush()
    return b


def end(db: Session, b: AdCampaignBoost, reason: str) -> None:
    b.ended_at = datetime.utcnow()
    b.ended_reason = reason


def expire_due(db: Session, today: Optional[date] = None) -> list:
    """Закрыть истёкшие буста и буст окончившихся РК. Возвращает закрытые (для события)."""
    from app.ad.build import CAMPAIGN_CLOSED
    today = today or date.today()
    closed = []
    q = (db.query(AdCampaignBoost, AdCampaign.status)
         .join(AdCampaign, AdCampaign.id == AdCampaignBoost.campaign_id)
         .filter(AdCampaignBoost.ended_at.is_(None)))
    for b, status in q.all():
        if b.until < today:
            end(db, b, "истёк")
        elif status in CAMPAIGN_CLOSED:
            end(db, b, "РК окончена")
        else:
            continue
        closed.append(b)
    return closed


def boosted_days(b: Optional[AdCampaignBoost]) -> Optional[tuple]:
    """(первый день, последний день, pct) для графика; None — буста нет."""
    return (b.starts_on, b.until, b.pct) if b and b.ended_at is None else None
