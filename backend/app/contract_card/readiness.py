# -*- coding: utf-8 -*-
"""Готовность договора к ДС и СК по договору (макет карточки договора, владелец 28.10.2026).

Проверки — те же условия, на которых ДС собирается и подтверждается: подписанты сторон (`signers.party_of`), реквизиты сторон,
есть по какому шаблону собрать (основной, именованный или базовый формата — владелец: «ок»), условие СК, канал выдачи, срок договора
с учётом пролонгации. У каждой проверки `target` — куда вести человека, если красная."""
import re
from datetime import date
from typing import List, Optional

from app.agency_terms import rules as RL

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_RU = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})")


def end_date(text: Optional[str]) -> Optional[date]:
    s = (text or "").strip()
    m = _ISO.match(s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = _RU.match(s)
    return date(int(m[3]), int(m[2]), int(m[1])) if m else None


def term_check(end_text: Optional[str], prolongation: Optional[str], on: date) -> dict:
    """Срок договора на дату `on`: дата окончания ещё не прошла; прошла — покрыта автопролонгацией; срок текстом («бессрочно») — годен."""
    s = (end_text or "").strip()
    if not s:
        return {"ok": False, "text": "срок договора не указан"}
    end = end_date(s)
    if end is None:
        return {"ok": True, "text": f"срок: {s}"}
    if end >= on:
        return {"ok": True, "text": f"действует до {end:%d.%m.%Y}"}
    if "авто" in (prolongation or "").lower():
        return {"ok": True, "text": f"срок до {end:%d.%m.%Y}, продлевается: пролонгация {prolongation}"}
    return {"ok": False, "text": f"срок истёк {end:%d.%m.%Y}, пролонгации нет"}


def sk_summary(rules: List[dict], contract_id: int, agency_ids, advertiser_ids, on: date) -> Optional[dict]:
    """Основная СК договора: самое точное действующее правило на договор с его агентством / рекламодателем (бренд и услуга не заданы).
    `brand_rules` — сколько действующих правил основной СК с брендом действуют внутри этого договора/агентства/рекламодателя."""
    keys = [{"contract_id": contract_id, "agency_id": a} for a in agency_ids] or []
    keys += [{"contract_id": contract_id, "advertiser_id": v} for v in advertiser_ids]
    keys = keys or [{"contract_id": contract_id}]
    best = None
    for k in keys:
        r = RL.pick(rules, k, on, RL.MAIN)
        if r and (best is None or RL.specificity(r) > RL.specificity(best)):
            best = r
    if best is None:
        return None
    scope = "договор" if best.get("contract_id") else "агентство" if best.get("agency_id") else "рекламодатель"
    mine = lambda r: (r.get("contract_id") == contract_id or r.get("agency_id") in set(agency_ids)  # noqa: E731
                      or r.get("advertiser_id") in set(advertiser_ids))
    brand = [r for r in rules if r["kind"] == RL.MAIN and r.get("brand_id") is not None and RL.active(r, on) and mine(r)]
    return {"id": best["id"], "percent": best["percent"], "mode": best.get("mode"), "scope": scope, "brand_rules": len(brand),
            "agency_id": best.get("agency_id"), "advertiser_id": best.get("advertiser_id")}


def _item(key, label, ok, text, target=None) -> dict:
    return {"key": key, "label": label, "ok": bool(ok), "text": text, "target": target}


def _signer(p: dict) -> dict:
    miss = [m for m in p["missing"] if "подписант" in m or "полномочий" in m or "доверенност" in m]
    who = "заказчика" if p["side"] == "заказчик" else "исполнителя"
    return _item(f"signer_{p['side']}", f"Подписант {who}", not miss,
                 ", ".join(miss) if miss else "должность, основание, срок доверенности — в порядке", f"signer:{p['side']}")


def _requisites(parties: List[dict]) -> dict:
    gaps = []
    for p in parties:
        cp = p.get("counterparty") or {}
        need = [n for n, k in (("ИНН", "inn"), ("КПП", "kpp"), ("ОГРН", "ogrn"), ("адрес", "address")) if not (cp.get(k) or "").strip()]
        if not cp:
            gaps.append(f"{p['side']}: юрлицо не указано")
        elif need:
            gaps.append(f"{p['side']}: нет {', '.join(need)}")
    bad = next((p for p in parties if p.get("counterparty") and any(g.startswith(p["side"]) for g in gaps)), None)
    return _item("requisites", "Реквизиты сторон", not gaps, "; ".join(gaps) if gaps else "ИНН, КПП, ОГРН и адрес у обеих сторон",
                 f"counterparty:{bad['counterparty']['id']}" if bad else None)


def checks(db, c, parties: List[dict], sk: Optional[dict], on: date) -> List[dict]:
    from app.annex_tpl import service as S
    tpl = S.resolve_for_contract(db, c)["template"]
    out = [_signer(p) for p in parties] + [_requisites(parties)]
    out.append(_item("template", "Шаблон ДС", tpl is not None,
                     f"по умолчанию — «{tpl.title}»" if tpl else "у договора нет шаблона: не указан формат или формату не назначен базовый",
                     "templates"))
    out.append(_item("sk", "Условие СК", sk is not None,
                     f"{sk['percent']:g} % · {sk['mode']} · на {sk['scope']}" if sk else "правила СК на договор, агентство или рекламодателя нет",
                     "sk"))
    out.append(_item("channel", "Канал выдачи", bool((c.issue_channel or "").strip()), c.issue_channel or "не задан: ЭДО или бумага", "edit"))
    t = term_check(c.end_date_text, c.prolongation, on)
    out.append(_item("term", "Срок договора", t["ok"], t["text"], "edit"))
    return out
