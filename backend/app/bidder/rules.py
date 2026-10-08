# -*- coding: utf-8 -*-
"""Правила распределения объёма РК — чистые функции, в базу не ходят (см. `app/bidder`).

`capped_shares` переехал сюда из `app/ad/flight` 05.10.2026; `flight` его реэкспортирует,
чтобы старые импорты не сломались.
"""
from typing import Optional


def capped_shares(weights: dict, cap: Optional[float], capless=frozenset()) -> dict:
    """Доли по весам с потолком (владелец 30.09.2026, балансировщик вариант «A + D»).

    `weights` — {ключ: вес}, `cap` — предел доли одной площадки в тех же единицах (0…1),
    `capless` — ключи, которых потолок не касается (ручной индекс перекрывает всё).
    Излишек сверх потолка уходит остальным пропорционально их весам («заливка»), пока
    никто не выше потолка. Невыполнимый потолок (площадок меньше, чем 1/cap) поднимается
    до равной доли — иначе часть объёма повисла бы ни на ком.
    """
    total = sum(float(w) for w in weights.values() if w) or 0.0
    if not total:
        return {k: 0.0 for k in weights}
    share = {k: (float(w) / total if w else 0.0) for k, w in weights.items()}
    if not cap or cap >= 1:
        return share
    live = [k for k, w in weights.items() if w]
    # Невыполнимый потолок поднимаем до равной доли СРЕДИ ПОДЧИНЁННЫХ ему: площадки с
    # ручным индексом держат свою долю по весу и в подъёме не участвуют.
    capped = [k for k in live if k not in capless]
    free_share = 1.0 - sum(share[k] for k in live if k in capless)
    c = max(float(cap), free_share / len(capped)) if capped else 1.0
    out = {k: 0.0 for k in weights}
    for _ in range(len(live) + 1):
        free = [k for k in live if k not in out or out[k] == 0.0]
        placed = sum(v for v in out.values())
        w_free = sum(float(weights[k]) for k in free)
        if not free or not w_free:
            break
        cur = {k: (1.0 - placed) * float(weights[k]) / w_free for k in free}
        over = [k for k in free if k not in capless and cur[k] > c + 1e-12]
        if not over:
            out.update(cur)
            break
        for k in over:
            out[k] = c
    return out


def floor_to_fact(pool: float, weights: dict, facts: dict, cap_abs: Optional[float] = None,
                  capless=frozenset()) -> dict:
    """Объёмы площадок из общего `pool` по весам, но НЕ НИЖЕ их факта (владелец 05.10.2026).

    `weights` — {ключ: вес}, `facts` — {ключ: показов уже открутила}, `cap_abs` — потолок
    одной площадки в ПОКАЗАХ (не в доле: пул меняется на каждом шаге, а предел — нет).
    Площадка, которой по весам досталось меньше факта, получает ровно факт и выходит из
    дележа; остаток пула заново делится между остальными. Факт больше пула — остальным 0,
    в минус не уходим. Возвращает {ключ: объём} (float).
    """
    fixed: dict = {}
    for _ in range(len(weights) + 1):
        free = {k: w for k, w in weights.items() if k not in fixed}
        left = max(0.0, float(pool) - sum(fixed.values()))
        cap = (cap_abs / left) if (cap_abs and left) else None
        sh = capped_shares(free, cap, capless) if free else {}
        amt = {k: left * sh.get(k, 0.0) for k in free}
        below = [k for k in free if float(facts.get(k) or 0) > amt[k] + 1e-9]
        if not below:
            return {**fixed, **amt}
        for k in below:
            fixed[k] = float(facts[k])
    return {k: fixed.get(k, 0.0) for k in weights}


# ── правила — для страницы «Биддер» ─────────────────────────────────────────
# Текст правил живёт рядом с кодом, который их исполняет: поменял правило — поменяй
# строку здесь, страница покажет новое без правки фронта.
RULES = [
    {"title": "Веса — из балансировщика",
     "text": "Объём РК делится между площадками пропорционально их индексу в балансировщике. "
             "Ручной индекс перекрывает расчётный. Нет индекса — площадка в раскладке не участвует.",
     "since": "02.09.2026"},
    {"title": "Потолок доли",
     "text": "Одна площадка не получает больше заданной доли плана РК; излишек расходится по "
             "остальным пропорционально весам. Площадка с ручным индексом потолку не подчиняется.",
     "since": "30.09.2026"},
    {"title": "Заданный объём",
     "text": "Площадка с объёмом, введённым по её креативам, получает ровно его; остальное "
             "делится по весам.",
     "since": "25.09.2026"},
    {"title": "Первые 5 дней — удержание долей",
     "text": "До старта и первые 5 дней РК объём делят все площадки в работе, включая ещё не "
             "запущенные. Факт в эти дни не учитывается. С 6-го дня делят запущенные и на паузе.",
     "since": "27.09.2026"},
    {"title": "Пауза держит долю",
     "text": "Площадка на паузе сохраняет свою долю; после снятия паузы пересчитывается обычным порядком.",
     "since": "05.10.2026"},
    {"title": "Выбывшая площадка — план = факт",
     "text": "Площадка вне раскладки (завершена или снят индекс), которая уже открутила, держит "
             "план, равный открученному. Остальным уходит только неоткрученное — РК не перекручивает.",
     "since": "05.10.2026"},
    {"title": "План не ниже факта",
     "text": "Если по весам или по заданному объёму площадке выходит меньше уже открученного "
             "(например, подключилась новая), её план = факт, разница расходится по остальным.",
     "since": "05.10.2026"},
    {"title": "Факт — DSP + ADFOX, за вчера",
     "text": "Факт берётся из нашего счётчика (DSP и загруженный ADFOX), Weborama не входит. "
             "Статистики за вчера нет — раскладка по весам, без факта.",
     "since": "05.10.2026"},
    {"title": "Темп размещения — временный подъём остатка",
     "text": "Трафик поднимает остаток РК на X % на N дней: остаток каждой запущенной площадки (план минус "
             "факт) растёт на X %. Не затрагиваются площадки с заданным объёмом, на паузе, ещё не "
             "запущенные и выбывшие. Подъём на один процент у всех касаемых площадок сохраняет их доли друг относительно друга, поэтому потолок доли его не зажимает. После последнего дня ночной пересчёт "
             "возвращает объём к исходному, дни флайта не меняются, план самой РК не меняется.",
     "since": "08.10.2026"},
    {"title": "Исполнение — лимиты креативов в DSP",
     "text": "Ночной пересчёт раздаёт план площадки её креативам и правит лимиты в DSP (лимит на "
             "весь срок). Суточный темп раскладывает пейсер DSP.",
     "since": "27.09.2026"},
]

REASONS = {
    "settled": "вне раскладки — план = факт",
    "out": "не в раскладке",
    "fixed": "заданный объём",
    "no_weight": "нет индекса в балансировщике",
    "floored": "поднята до факта",
    "capped": "упёрлась в потолок",
    "weight": "по весу",
    "boost": "поднят «темпом размещения»",
}


def explain(row: dict, fact, facts_used: bool, cap_abs: Optional[float]) -> dict:
    """Почему у площадки такой план — код и подпись (`REASONS`). Порядок проверок важен:
    выбывшая и заданный объём перекрывают вес, «до факта» — потолок."""
    plan = row.get("plan_show")
    if row.get("boosted"):
        code = "boost"
    elif row.get("settled"):
        code = "settled"
    elif not row.get("in_plan"):
        code = "out"
    elif row.get("fixed"):
        code = "fixed"
    elif row.get("no_weight"):
        code = "no_weight"
    elif facts_used and fact and plan is not None and plan <= round(float(fact)):
        code = "floored"
    elif cap_abs and plan is not None and not row.get("capless") and plan >= round(cap_abs) - 1:
        code = "capped"
    else:
        code = "weight"
    return {"code": code, "label": REASONS[code]}
