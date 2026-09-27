"""Объёмы по площадкам против плана РК — одна проверка на все экраны (владелец 27.09.2026).

Объём задаётся аккаунтом у каждого креатива на паре «креатив × площадка»
(`launch_prep_set_target.plan_show`). Площадка получает в РК сумму объёмов своих креативов
(`ad/flight.distribute`). Против плана РК (последний медиаплан сделки) три уровня:

  · ok    — в пределах половины плана;
  · warn  — сумма площадки больше 50 % плана: предупреждение, без блокировки — слишком
            много на одной площадке;
  · over  — больше 100 % плана: у площадки или В СУММЕ по всем. Блокируются дальнейшие
            действия — отправка трафику, «Изменить стадию», запуск РК и площадок, — и
            аккаунт с трафиком получают уведомление.

При вводе объём больше плана не пропускается; превышение появляется, когда объёмы уже
вписаны, а план в медиаплане потом уменьшили. Проверка читается из ОДНОЙ функции —
блок креатива, требования перехода, дашборд трафика и все запреты сходятся.
"""
from typing import Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

WARN_SHARE = 0.5

# Какой объём ДЕРЖИТ план РК — одно условие на все подсчёты (ревью 27.09.2026).
# Креатив, отклонённый площадкой, плана не держит: раскладка РК его не считает
# (`ad/build.PLACEMENT_FIXED_SQL`), и проверка, считавшая его, запирала сделку лишним
# объёмом — отклонили креатив на 600 тысяч, дали столько же доработке, и при плане в
# миллион выходило «превышено». Неотправленный креатив держит: объём вписывают до
# отправки, и проверить его надо именно тогда.
HOLDS_PLAN = """NOT EXISTS (
    SELECT 1 FROM launch_prep_pair pr
      JOIN ad_campaign_creative cc ON cc.pair_id = pr.id
     WHERE pr.set_id = st.set_id AND pr.target_id = st.target_id
       AND cc.status = :rejected)"""


def _fmt(n) -> str:
    return f"{int(round(n)):,}".replace(",", " ")


def _rejected() -> str:
    from app.ad.flight import CREATIVE_REJECTED
    return CREATIVE_REJECTED


def evaluate(plan: Optional[float], by_publisher: Dict[int, float]) -> dict:
    """Уровни по площадкам и общий вердикт — из чисел, без базы.

    План округляется до целых, как у проверки при вводе (`launch_prep._rk_plan`): у CPC
    показы выводятся из кликов через CTR и бывают дробными, и объём, принятый при вводе
    против 100 000, иначе оказывался «больше плана» 99 999,6 и запирал сделку."""
    plan = int(round(plan)) if plan else None
    total = sum(v or 0 for v in by_publisher.values())
    rows = {}
    for pid, v in by_publisher.items():
        v = v or 0
        level = "ok"
        if plan:
            if v > plan:
                level = "over"
            elif v > plan * WARN_SHARE:
                level = "warn"
        rows[pid] = {"sum": int(round(v)), "level": level,
                     "share": round(v / plan, 4) if plan else None}
    over_by = int(round(total - plan)) if plan and total > plan else 0
    blocked = bool(plan) and (over_by > 0 or any(r["level"] == "over" for r in rows.values()))
    message = None
    if blocked:
        message = (f"Объёмы по площадкам превышают план РК на {_fmt(max(over_by, 0))} показов "
                   f"(распределено {_fmt(total)} из {_fmt(plan)}) — уменьшите их в блоке креатива"
                   if over_by > 0 else
                   "Объём одной из площадок больше плана РК — уменьшите его в блоке креатива")
    return {"plan": int(round(plan)) if plan else None, "total": int(round(total)),
            "over_by": over_by, "blocked": blocked, "message": message,
            "by_publisher": rows}


def volumes_by_deal(db: Session, deal_ids) -> Dict[int, Dict[int, float]]:
    """То же пачкой на страницу: {deal_id: {publisher_id: показы}} — одним запросом."""
    if not deal_ids:
        return {}
    out: Dict[int, Dict[int, float]] = {}
    for d, pid, v in db.execute(text("""
        SELECT cs.deal_id, t.publisher_id, sum(st.plan_show)
          FROM launch_prep_set_target st
          JOIN launch_prep_creative_set cs ON cs.id = st.set_id
          JOIN launch_prep_target t ON t.id = st.target_id
         WHERE cs.deal_id = ANY(:d) AND st.plan_show IS NOT NULL AND """ + HOLDS_PLAN + """
         GROUP BY cs.deal_id, t.publisher_id"""),
            {"d": list(deal_ids), "rejected": _rejected()}).all():
        if v:
            out.setdefault(d, {})[pid] = float(v)
    return out


def deal_volumes(db: Session, deal_id: int) -> Dict[int, float]:
    """Сумма заданных объёмов по площадкам сделки: {publisher_id: показы}."""
    rows = db.execute(text("""
        SELECT t.publisher_id, sum(st.plan_show)
          FROM launch_prep_set_target st
          JOIN launch_prep_creative_set cs ON cs.id = st.set_id
          JOIN launch_prep_target t ON t.id = st.target_id
         WHERE cs.deal_id = :d AND st.plan_show IS NOT NULL AND """ + HOLDS_PLAN + """
         GROUP BY t.publisher_id"""), {"d": deal_id, "rejected": _rejected()}).all()
    return {pid: float(v) for pid, v in rows if v}


def others_total(db: Session, deal_id: int, set_id: int, target_id: int) -> float:
    """Сумма объёмов сделки, кроме пары «креатив × площадка» (set_id, target_id) — для
    проверки при вводе: замена своего же значения не считается дважды."""
    return float(db.execute(text("""
        SELECT COALESCE(SUM(st.plan_show), 0) FROM launch_prep_set_target st
          JOIN launch_prep_creative_set cs ON cs.id = st.set_id
         WHERE cs.deal_id = :d AND NOT (st.set_id = :s AND st.target_id = :t)
           AND """ + HOLDS_PLAN),
        {"d": deal_id, "s": set_id, "t": target_id, "rejected": _rejected()}).scalar() or 0)


def guard(db: Session, deal_id: int) -> None:
    """Запрет действия, пока объёмы превышают план РК: 400 с объяснением, что делать.

    Стоит в отправке трафику, «Изменить стадию», запуске РК и площадки, выгрузке в DSP.
    """
    from fastapi import HTTPException
    st = check(db, deal_id)
    if st["blocked"]:
        raise HTTPException(status_code=400, detail=st["message"])


def notify_if_newly_blocked(db: Session, deal_id, before: Optional[dict], actor) -> bool:
    """Уведомление аккаунту и трафику, когда превышение ПОЯВИЛОСЬ (было в норме — стало
    больше плана). На каждом сохранении плана с уже висящим превышением не шумит.
    Сбой уведомления не отменяет уже сохранённое. True — отправили."""
    import logging
    if not deal_id:
        return False
    try:
        after = check(db, deal_id)
        if not after["blocked"] or (before and before.get("blocked")):
            return False
        from app.notify.bus import emit
        from app.sales.deal_label import deal_label
        from app.sales.models import SalesDeal
        deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
        if deal is None:
            return False
        emit(db, "volumes_over_plan",
             title=f"Объёмы превышают план РК: {deal_label(deal)}",
             body=after["message"], link=f"/sales/deals/{deal.code or deal.id}",
             entity_type="sales_deal", entity_id=deal.id, actor=actor, ctx={"deal": deal})
        db.commit()
        return True
    except Exception as e:                                  # noqa: BLE001
        db.rollback()
        logging.getLogger("finance.volumes").warning(
            "Уведомление о превышении объёмов по сделке %s не ушло: %s", deal_id, e)
        return False


def check(db: Session, deal_id: int) -> dict:
    """Состояние объёмов сделки против плана РК."""
    from app.ad import build as ad_build
    plan = (ad_build.deal_plan(db, deal_id) or {}).get("plan_show")
    return evaluate(plan, deal_volumes(db, deal_id))
