# -*- coding: utf-8 -*-
"""Состояние площадки во ВНЕШНИХ системах: Weborama и DSP.

Одна точка на три потребителя — карточку сделки, сводную по креативам и дашборд трафика.
Второй расчёт того же состояния разошёлся бы с первым, и спор «у меня пиксель есть, а у
тебя нет» разрешить было бы нечем.

**Состояние ВЫЧИСЛЯЕТСЯ, а не хранится.** Отдельное поле-статус — это третья копия правды
рядом с фактом (`weborama_refs`, `weborama_pixel`, `ms_creative_xxhash`), и она обязательно
разойдётся. Тот же принцип, что у публичного состояния получателя в стадии сборки: свёртка
считается, второго поля под неё нет намеренно.

**Считается ПАЧКОЙ.** Реестр трафика показывает 57 РК в одном ответе; расчёт по одной РК за
раз дал бы под двести запросов на экран. Батчи здесь того же вида, что `_placements_of` и
`_creatives_all` в дашборде, и появились по той же причине.
"""
from typing import Dict, Iterable, List

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ad.models import AdCampaign, AdCampaignCreative, AdCampaignPlacement

# Значения. «—» и «нет» — РАЗНЫЕ вещи, и путать их дорого: «нет» зовёт нажать кнопку,
# «—» говорит, что делать нечего. Площадка, которая крутит сама (`is_direct`, те самые
# 10%), не идёт ни в DSP, ни в Weborama.
NOT_NEEDED = "—"
MISSING = "нет"
REGISTERED = "заведён"
READY = "есть"
RUNNING = "крутится"
UNKNOWN = "неизвестно"

# Состояния, которые считаются «сделано» при подсчёте покрытия.
DONE_WEBORAMA = (READY,)
DONE_DSP = (REGISTERED, RUNNING)


def totals(states) -> Dict[str, dict]:
    """Покрытие по РК: «сделано из нужных» отдельно по каждой системе.

    Знаменатель — только те площадки, которым это НУЖНО: крутящие сами («—») не считаются
    ни в числителе, ни в знаменателе, иначе итог никогда не сойдётся и перестанет
    что-либо значить.
    """
    out = {"weborama": {"done": 0, "need": 0}, "dsp": {"done": 0, "need": 0}}
    for row in (states.values() if isinstance(states, dict) else states):
        for key, done_states in (("weborama", DONE_WEBORAMA), ("dsp", DONE_DSP)):
            st = (row.get(key) or {}).get("state")
            if not st or st == NOT_NEEDED:
                continue
            out[key]["need"] += 1
            if st in done_states:
                out[key]["done"] += 1
    return out


def _state_of(p: AdCampaignPlacement, refs: dict, hung: set,
              crs: List[AdCampaignCreative], dsp_hung=frozenset()) -> dict:
    """Состояние ОДНОЙ площадки. Единственное место, где эти правила записаны."""
    if p.is_direct:
        # Крутит сама — внешние системы её не касаются вовсе.
        return {"weborama": {"state": NOT_NEEDED, "why": "площадка крутит сама"},
                "dsp": {"state": NOT_NEEDED, "why": "площадка крутит сама"}}

    if p.id in hung:
        wb = {"state": UNKNOWN,
              "why": "попытка не завершилась — исход неизвестен, повторять нельзя"}
    elif p.weborama_pixel:
        wid = refs.get(p.id, ("", ""))[0]
        wb = {"state": READY, "id": wid, "why": f"вставка {wid}" if wid else "пиксель получен"}
    elif p.id in refs:
        wid = refs[p.id][0]
        wb = {"state": REGISTERED, "id": wid,
              "why": f"вставка {wid} заведена, пиксель ещё не получен"}
    else:
        wb = {"state": MISSING, "why": "вставка в Weborama не заведена"}

    with_hash = [c for c in crs if c.ms_creative_xxhash]
    # Заведение креатива ушло без ответа — не «нет»: повтор заперт до сверки с кабинетом,
    # и без этой буквы человек жал бы «DSP» и получал отказ, не понимая почему.
    if any(f"cr{c.id}" in dsp_hung for c in crs if not c.ms_creative_xxhash):
        ds = {"state": UNKNOWN,
              "why": "заведение креатива осталось без ответа — сверьтесь с кабинетом "
                     "(окно кнопки «DSP»)"}
    elif p.status == "запущен" and with_hash:
        ds = {"state": RUNNING, "why": f"креативов в кабинете DSP: {len(with_hash)}"}
    elif with_hash:
        ds = {"state": REGISTERED, "why": f"креативов заведено: {len(with_hash)}"}
    elif crs:
        ds = {"state": MISSING, "why": f"креативов в очереди: {len(crs)}, ни одного в DSP"}
    else:
        ds = {"state": MISSING, "why": "креативов на площадке нет"}
    return {"weborama": wb, "dsp": ds}


def states_by_campaign(db: Session, campaign_ids: Iterable[int]) -> Dict[int, Dict[int, dict]]:
    """`{campaign_id: {placement_id: состояние}}` — четырьмя запросами на любое число РК."""
    ids = [int(i) for i in campaign_ids]
    if not ids:
        return {}
    pls = (db.query(AdCampaignPlacement)
           .filter(AdCampaignPlacement.campaign_id.in_(ids)).all())
    pl_ids = [p.id for p in pls] or [0]

    # Заведённые вставки Weborama — по площадке. `weborama_refs.local_id` для вида
    # `insertion` указывает на площадку РК.
    refs = {r[0]: (r[1], r[2]) for r in db.execute(text("""
        SELECT local_id, wcm_id, label FROM weborama_refs
         WHERE kind = 'insertion' AND local_id = ANY(:ids)
    """), {"ids": pl_ids}).all()}

    # Незакрытые попытки: вызов ушёл, ответ не вернулся. Показываем отдельно — повторять
    # такое автоматически нельзя, объект в чужой системе мог создаться.
    hung = {r[0] for r in db.execute(text("""
        SELECT DISTINCT local_id FROM weborama_submissions
         WHERE kind = 'insertion' AND finished_at IS NULL AND local_id = ANY(:ids)
    """), {"ids": pl_ids}).all()}

    crs: Dict[int, list] = {}
    for c in (db.query(AdCampaignCreative)
              .filter(AdCampaignCreative.campaign_id.in_(ids)).all()):
        crs.setdefault(c.placement_id, []).append(c)

    # Зависшие заведения креативов DSP — одним запросом к журналу на все РК. Журнал
    # недоступен — пусто: экран не падает, а повтор запирает сама выгрузка.
    from app.dsp.client import MsClient
    no_hash = [f"cr{c.id}" for lst in crs.values() for c in lst
               if not (c.ms_creative_xxhash or "").strip()]
    dsp_hung = MsClient().unknown_refs("Creative.add", "creative", no_hash) if no_hash else set()

    out: Dict[int, Dict[int, dict]] = {i: {} for i in ids}
    for p in pls:
        out[p.campaign_id][p.id] = _state_of(p, refs, hung, crs.get(p.id, []), dsp_hung)
    return out


def totals_by_campaign(db: Session, campaign_ids: Iterable[int]) -> Dict[int, dict]:
    """Покрытие по каждой РК списком — для строк реестра трафика."""
    return {cid: totals(st) for cid, st in states_by_campaign(db, campaign_ids).items()}


def states_by_placement(db: Session, campaign_id: int) -> Dict[int, dict]:
    """То же состояние, но ключом площадки РК — для расхлопа дашборда."""
    return states_by_campaign(db, [campaign_id]).get(campaign_id, {})


def external_states(db: Session, deal_id: int) -> Dict[int, dict]:
    """`{publisher_id: {"weborama": {...}, "dsp": {...}}}` по всем площадкам РК сделки.

    Пусто, если РК ещё не собрана: это не ошибка, а «спрашивать пока нечего».
    """
    camp = db.query(AdCampaign).filter(AdCampaign.deal_id == deal_id).first()
    if not camp:
        return {}
    by_pl = states_by_campaign(db, [camp.id]).get(camp.id, {})
    pls = (db.query(AdCampaignPlacement)
           .filter(AdCampaignPlacement.campaign_id == camp.id).all())
    return {p.publisher_id: by_pl[p.id] for p in pls if p.id in by_pl}


__all__ = ["external_states", "states_by_placement", "states_by_campaign",
           "totals", "totals_by_campaign",
           "NOT_NEEDED", "MISSING", "REGISTERED", "READY", "RUNNING", "UNKNOWN"]
