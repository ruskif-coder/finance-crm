# -*- coding: utf-8 -*-
"""Сравнение двух версий шаблона по `id` пункта. Результат — список `[знак, название, описание, было?, стало?]`.

Знаки: `+` добавлен, `−` убран, `~` изменён текст или название, `🔒` обязательность, `↳` подпункт/основной,
`↕` перемещён, `≡` версия базы принята без изменения текста (кастомный «оставил свой»).
"""
from typing import List


def diff(prev: List[dict], nxt: List[dict]) -> list:
    a = [b for b in prev if not b.get("sys")]
    b = [x for x in nxt if not x.get("sys")]
    ia, ib = {x["id"]: x for x in a}, {x["id"]: x for x in b}
    out = []
    for x in b:
        if x["id"] not in ia:
            out.append(["+", x["title"], "добавлен пункт"])
    for x in a:
        if x["id"] not in ib:
            out.append(["−", x["title"], "пункт убран"])
    order_a = [x["id"] for x in a if x["id"] in ib]
    order_b = [x["id"] for x in b if x["id"] in ia]
    for x in b:
        p = ia.get(x["id"])
        if p is None:
            continue
        if (p.get("text") or "") != (x.get("text") or ""):
            out.append(["~", x["title"], "изменён текст", p.get("text"), x.get("text")])
        if p.get("title") != x.get("title"):
            out.append(["~", x["title"], f"было «{p.get('title')}»"])
        if bool(p.get("req")) != bool(x.get("req")):
            out.append(["🔒", x["title"], "стал обязательным" if x.get("req") else "обязательность снята"])
        if bool(p.get("sub")) != bool(x.get("sub")):
            out.append(["↳", x["title"], "стал подпунктом" if x.get("sub") else "стал основным пунктом"])
        if order_a.index(x["id"]) != order_b.index(x["id"]):
            out.append(["↕", x["title"], "перемещён"])
    return out
