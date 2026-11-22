# -*- coding: utf-8 -*-
"""Человеческий текст деталей журнала (макет design_handoff_journal, 16.11.2026).

Переписываются только известные шаблоны — те, что реально встречаются в журнале (замер 16.11: параметры таргетинга,
раскладка мастер-сделки, массовые правки со списком id, статус / дата / банк, связь с Битриксом, закодированные адреса).
Всё прочее остаётся как записано: лучше сырой текст, чем выдуманный (макет, допущение 5). Запись в базе не меняется —
переписывается только показ и выгрузка.
"""
import re
from urllib.parse import unquote

_TARGETING = {"interests": "интересы", "buys": "покупки", "audience": "аудитория", "behavior": "поведение",
              "competitors": "конкуренты"}
_TARGETING_RX = re.compile(r"\b(" + "|".join(_TARGETING) + r"):")
_IDS_RX = re.compile(r"\bids=\[([^\]]*)\]")
_FIELD = {"status": "статус", "date": "дата", "bank": "банк"}
_FIELD_RX = re.compile(r"\b(status|date|bank)=([^,;]+)")
_DATE_RX = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_MASTER = {"ours": "основная — наша запись", "bx": "основная — из Битрикса"}
_URL_RX = re.compile(r"https?://\S+")
_LAYOUT_RX = re.compile(r"((?:\w+=(?:True|False|hide|show|zero|separate|together|fold|\[[^\]]*\])(?:, )?){3,})")


def _layout(m) -> str:
    kv = dict(p.split("=", 1) for p in m.group(1).split(", ") if "=" in p)
    out = []
    if "addons_mode" in kv:
        out.append({"separate": "допы отдельным ДС", "together": "допы в общем ДС",
                    "fold": "допы в стоимости базовой услуги"}.get(kv["addons_mode"], kv["addons_mode"]))
    elif "addons_separate" in kv:
        out.append("допы отдельным ДС" if kv["addons_separate"] == "True" else "допы в общем ДС")
    if "bonus_addons" in kv:
        out.append("бонусные допы скрыты" if kv["bonus_addons"] == "hide" else "бонусные допы показаны")
    ds = [w for k, w in (("ds_by_brand", "брендам"), ("ds_by_service", "услугам")) if kv.get(k) == "True"]
    if ds:
        out.append("ДС по " + " и ".join(ds))
    upd = [w for k, w in (("upd_by_brand", "брендам"), ("upd_by_service", "услугам")) if kv.get(k) == "True"]
    if upd:
        out.append("УПД по " + " и ".join(upd))
    moved = kv.get("moved", "[]").strip("[]").strip()
    if moved:
        out.append(f"перенесено строк: {len([x for x in moved.split(',') if x.strip()])}")
    return ", ".join(out) or m.group(1)


def _field(m) -> str:
    val = m.group(2).strip()
    d = _DATE_RX.match(val)
    if d:
        val = f"{d.group(3)}.{d.group(2)}.{d.group(1)}"
    return f"{_FIELD[m.group(1)]} {val}"


def humanize(action: str, raw) -> str:
    if not raw:
        return ""
    s = str(raw)
    s = _TARGETING_RX.sub(lambda m: _TARGETING[m.group(1)] + ":", s)
    s = _IDS_RX.sub(lambda m: f"записей: {len([x for x in m.group(1).split(',') if x.strip()])}", s)
    if action == "master_deal_settings":
        s = _LAYOUT_RX.sub(_layout, s)
    s = _FIELD_RX.sub(_field, s)
    s = re.sub(r"\bmaster=(ours|bx)\b", lambda m: _MASTER[m.group(1)], s)
    s = _URL_RX.sub(lambda m: unquote(m.group(0)), s)
    return s
