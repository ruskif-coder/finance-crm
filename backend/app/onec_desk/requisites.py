# -*- coding: utf-8 -*-
"""Реквизиты сторон в УПД 1С против наших карточек (владелец 12.11.2026: «проверял бы реквизиты из УПД и наши — и как-то
информировал: расходится, дополнить»).

«расходится» — у нас другое значение (ИНН, КПП, наименование, адрес): ошибка либо в 1С, либо в нашей карточке, и документы
клиенту уйдут с одними реквизитами, а наш учёт — с другими. «дополнить» — в 1С значение есть, у нас пусто: карточку надо
заполнить (в том числе расчётный счёт продавца из УПД, которого нет среди счетов нашего юрлица).
Сравнение без оформления: регистр, кавычки, пробелы и форма «ООО/АО/ИП» в начале или конце названия не считаются различием."""
import re
from typing import Optional

WHO = (("seller", "продавец"), ("buyer", "покупатель"))
FORMS = r"(ооо|оао|зао|пао|ао|ип|нко|ано|фгуп|гуп|муп)"


LONG = (("общество с ограниченной ответственностью", "ооо"), ("публичное акционерное общество", "пао"),
        ("акционерное общество", "ао"), ("индивидуальный предприниматель", "ип"))


def _name(s: Optional[str]) -> str:
    t = (s or "").lower()
    for long_, short in LONG:            # 1С пишет форму полностью, у нас — сокращённо (ревью 12.11.2026)
        t = t.replace(long_, short)
    t = re.sub(r"[«»“”„\"']", " ", t)
    t = re.sub(rf"^\s*{FORMS}\s+|\s+{FORMS}\s*$", " ", t.strip())
    return re.sub(r"\s+", " ", t).strip()


def _addr(s: Optional[str]) -> str:
    return re.sub(r"[\s,.]+", " ", (s or "").lower()).strip()


def _plain(s: Optional[str]) -> str:
    return (s or "").strip()


FIELDS = (("наименование", "name", _name), ("ИНН", "inn", _plain), ("КПП", "kpp", _plain), ("адрес", "address", _addr))


def diff(onec: dict, ours: dict) -> list:
    """→ [{who, field, kind: расходится|дополнить, onec, ours}] — только то, что требует внимания."""
    out = []
    for key, who in WHO:
        a, b = onec.get(key) or {}, ours.get(key) or {}
        for label, f, norm in FIELDS:
            x, y = a.get(f), b.get(f)
            if not _plain(x):
                continue
            if not _plain(y):
                out.append({"who": who, "field": label, "kind": "дополнить", "onec": x, "ours": None})
            elif norm(x) != norm(y):
                out.append({"who": who, "field": label, "kind": "расходится", "onec": x, "ours": y})
        bank = a.get("bank")
        if key == "seller" and bank and bank.get("account") and bank["account"] not in (b.get("accounts") or []):
            out.append({"who": who, "field": "расчётный счёт", "kind": "дополнить", "onec": bank["account"], "ours": None})
    return out
