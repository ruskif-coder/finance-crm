# -*- coding: utf-8 -*-
"""«Темп размещения»: применить и снять буст — раскладка, лимиты в DSP, уведомление (08.10.2026).

Порядок на любое действие: замок долей РК (ставит вызывающий) → запись буста → пересчёт долей →
коммит → лимиты креативов в DSP. Лимиты уходят СРАЗУ, не ожидая ночного прогона: это и есть смысл
кнопки. Ночной `daily_shares` потом видит тот же буст и ничего не откатывает.

Площадки вне нашей DSP (Adfox) лимитов в DSP не имеют: им сервис отдаёт список «что поменять руками»
с новой суточной нормой — экран показывает его в окне результата, а событие уходит остальному трафику.
"""
import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.ad import boost, build
from app.ad.flight import PLACEMENT_RUNNING, flight_of
from app.ad.models import AdCampaign, AdCampaignPlacement
from app.audit import log_action
from app.bidder.facts import any_facts
from app.launch_prep import pub_rules

log = logging.getLogger("finance.dsp")


def _facts_of(db: Session, campaign_id: int) -> Optional[dict]:
    from app.bidder.facts import placement_facts
    got = placement_facts(db, [campaign_id])
    return got.get(campaign_id) if got is not None else None


def boostable_rest(db: Session, camp: AdCampaign):
    """(остаток РК, остаток тех, кого буст касается, их число, число запущенных «на фиксе», факт РК).

    Раскладка БЕЗ буста — иначе при действующем бусте остаток уже поднят. Свежего среза нет — остаток по
    последнему известному факту (как в самой раскладке с бустом)."""
    fresh = _facts_of(db, camp.id)
    _pls, out = build.campaign_layout(db, camp.id, facts=fresh, facts_given=True, with_boost=False)
    known = fresh if fresh is not None else any_facts(db, camp.id)
    running = [r for r in out["rows"] if r["status"] in PLACEMENT_RUNNING]
    free = [r for r in running if boost.boostable(r)]
    rest_free = sum(max(0.0, (r.get("plan_show") or 0) - known.get(r["id"], 0)) for r in free)
    fact = sum(known.values())
    return (max(0.0, (camp.plan_show or 0) - fact), rest_free, len(free), len(running) - len(free), fact)


def external_rows(db: Session, camp: AdCampaign, facts: Optional[dict]) -> list:
    """Запущенные площадки, у которых есть поверхности ВНЕ нашей DSP: что им поменять руками.

    `plan` — новый объём на остаток флайта, `per_day` — суточная норма на оставшиеся дни."""
    pls = (db.query(AdCampaignPlacement)
           .filter(AdCampaignPlacement.campaign_id == camp.id,
                   AdCampaignPlacement.status.in_(PLACEMENT_RUNNING)).all())
    modes = pub_rules.placement_modes(db, {(camp.deal_id, p.publisher_id) for p in pls})
    fl = flight_of(camp.date_start, camp.date_end)
    left = fl.left if fl else 0
    out = []
    for p in pls:
        m = modes.get((camp.deal_id, p.publisher_id)) or {}
        if m.get("mode") not in (pub_rules.MODE_EXTERNAL, pub_rules.MODE_MIXED):
            continue
        fact = (facts or {}).get(p.id, 0) or 0
        rest = max(0.0, (p.plan_show or 0) - fact)
        out.append({"placement_id": p.id, "publisher_id": p.publisher_id,
                    "surfaces": m.get("external", []), "plan": round(p.plan_show or 0),
                    "per_day": round(rest / left) if left else None})
    return out


def _publisher_names(db: Session, rows: list) -> list:
    from app.routers.traffic_dashboard import publisher_name
    return [{**r, "name": publisher_name(db, r["publisher_id"])} for r in rows]


def _sync(db: Session, camp: AdCampaign, client) -> dict:
    """Лимиты креативов в DSP по новому плану. Сбой не откатывает буст: он уже записан, ночной прогон
    дотянет лимиты; человеку сбой показывается в ответе."""
    if not camp.ms_campaign_xxhash:
        return {"campaign_id": camp.id, "updated": 0, "zero": [], "failed": [], "skipped": True}
    from app.dsp.limits import sync_limits
    try:
        from app.dsp.client import MsClient
        return sync_limits(db, camp, client or MsClient())
    except Exception as e:  # noqa: BLE001 — отчёт человеку, не падение ручки
        db.rollback()
        log.exception("РК %s: лимиты буста не ушли в DSP", camp.id)
        return {"campaign_id": camp.id, "updated": 0, "zero": [],
                "failed": [{"creative_id": None, "error": str(e)}]}


def _notify(db: Session, camp: AdCampaign, key: str, title: str, body: str, actor) -> None:
    from app.notify.bus import emit
    from app.routers.traffic_dashboard import rk_label
    try:
        emit(db, key, title=title, body=body, link=f"/traffic/dashboard?rk={camp.id}",
             entity_type="ad_campaign", entity_id=camp.id, actor=actor)
        db.commit()
    except Exception:  # noqa: BLE001 — уведомление справка: буст уже применён
        db.rollback()
        log.exception("%s: уведомление о бусте не отправлено", rk_label(db, camp.id))


def _ext_text(ext: list) -> str:
    return "; ".join(f"{e['name']} — {e['per_day']:,} в сутки".replace(",", " ")
                     for e in ext if e.get("per_day") is not None)


def apply(db: Session, camp: AdCampaign, pct: int, days: int, user, client=None,
          today: Optional[date] = None) -> dict:
    """Включить буст. Замок долей РК взят вызывающим. Ошибку ввода даёт `boost.BoostError`."""
    from app.routers.traffic_dashboard import rk_label
    facts = _facts_of(db, camp.id)
    b = boost.start(db, camp, pct, days, user_id=getattr(user, "id", None), facts=facts, today=today)
    changes = build.recompute_shares(db, camp.id)
    log_action(db, user, "ad_boost_start", "ad_campaign", camp.id,
               f"{rk_label(db, camp.id)}: остаток +{pct} % на {days} дн. (до {b.until:%d.%m})")
    limits = _sync(db, camp, client)
    ext = _publisher_names(db, external_rows(db, camp, facts))
    if ext:
        _notify(db, camp, "traffic_boost_started", f"Темп размещения: {rk_label(db, camp.id)}",
                f"Остаток поднят на {pct} % до {b.until:%d.%m}. Измените лимиты Adfox: {_ext_text(ext)}",
                user)
    return {"boost": view(b), "changes": len(changes), "limits": limits, "external": ext}


def cancel(db: Session, camp: AdCampaign, user, client=None) -> dict:
    """Снять буст досрочно: исходный план возвращается сразу."""
    from app.routers.traffic_dashboard import rk_label
    b = boost.active(db, camp.id)
    if not b:
        raise boost.BoostError("Активного буста нет")
    boost.end(db, b, "снят")
    changes = build.recompute_shares(db, camp.id)
    log_action(db, user, "ad_boost_cancel", "ad_campaign", camp.id,
               f"{rk_label(db, camp.id)}: буст +{b.pct} % снят досрочно")
    limits = _sync(db, camp, client)
    facts = _facts_of(db, camp.id)
    ext = _publisher_names(db, external_rows(db, camp, facts))
    if ext:
        _notify(db, camp, "traffic_boost_ended", f"Темп размещения снят: {rk_label(db, camp.id)}",
                f"Верните лимиты Adfox: {_ext_text(ext)}", user)
    return {"boost": None, "changes": len(changes), "limits": limits, "external": ext}


def notify_ended(db: Session, ended: list) -> None:
    """Ночной прогон закрыл истёкшие бусты: событие трафику — вернуть лимиты Adfox. Лимиты в DSP
    уже догнал сам прогон (`sync_limits` идёт следом)."""
    from app.routers.traffic_dashboard import rk_label
    for b in ended:
        camp = db.get(AdCampaign, b.campaign_id)
        if camp is None:
            continue
        ext = _publisher_names(db, external_rows(db, camp, _facts_of(db, camp.id)))
        body = f"Буст +{b.pct} % закончился ({b.ended_reason})."
        if ext:
            body += f" Верните лимиты Adfox: {_ext_text(ext)}"
        _notify(db, camp, "traffic_boost_ended", f"Темп размещения закончен: {rk_label(db, camp.id)}",
                body, None)


def view(b) -> Optional[dict]:
    if b is None:
        return None
    return {"id": b.id, "pct": b.pct, "days": b.days, "starts_on": b.starts_on, "until": b.until,
            "rest_at_start": b.rest_at_start}
