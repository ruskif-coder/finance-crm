# -*- coding: utf-8 -*-
"""Применимость стадии к услуге и видимость блоков карточки.

Две таблицы разметки, которые до 13.09.2026 существовали схемой и моделью, но не имели
НИ ОДНОГО читателя: `sales_stage_services` и `sales_stage_blocks`. Пустая таблица при этом
неотличима от «механизм работает, просто разметки нет» — самый тихий вид недоделки,
поэтому обе прочитаны здесь.

## Общее правило обеих

**Нет строк — прежнее поведение.** Стадия без записей в `sales_stage_services` применима
ко всем услугам; блок без записей в `sales_stage_blocks` виден всегда. Иначе накат
миграции молча выключил бы половину лестницы и половину карточки.
"""
from typing import Optional

from sqlalchemy import text


# ── Применимость стадии к услуге ─────────────────────────────────────────────

def stage_services(db) -> dict:
    """{stage_id: {service_id, …}} — только для стадий, у которых разметка ЕСТЬ.

    Стадии, которой нет в этом словаре, применимы ко всем услугам: отсутствие записи и
    есть «ограничений нет»."""
    rows = db.execute(text(
        "SELECT stage_id, service_id FROM sales_stage_services")).fetchall()
    out: dict = {}
    for sid, svc in rows:
        out.setdefault(sid, set()).add(svc)
    return out


def stage_applies(stage_id: int, deal, marks: dict) -> bool:
    """Применима ли стадия к услуге этой сделки.

    Сделка БЕЗ услуги проходит любую стадию: «услуга не определена» — это незнание, а не
    основание выкинуть сделку из лестницы. Иначе 217 сделок без услуги потеряли бы часть
    пути молча, и понять это по экрану было бы нечем."""
    allowed = marks.get(stage_id)
    if not allowed:
        return True
    svc = getattr(deal, "service_id", None)
    if svc is None:
        return True
    return svc in allowed


def flow_for(deal, catalog, marks: dict) -> list:
    """Цепочка стадий ИМЕННО ЭТОЙ сделки: неприменимые к её услуге выброшены.

    Терминальные в цепочку не входят и здесь — они ветвящиеся исходы, а не ступени."""
    return [sid for sid in catalog.flow
            if stage_applies(sid, deal, marks)]


def next_for(deal, catalog, marks: dict):
    """Следующая ПРИМЕНИМАЯ стадия. Неприменимые проскакиваются.

    У сделки на ТЕРМИНАЛЕ следующей нет — возвращаем None. `Catalog.next_of` здесь
    отдаёт первую стадию цепочки, и до 13.09.2026 это означало, что карточка сорванной
    сделки писала «следующая: МП Подготовка», кнопка «двинуть» без выбора цели вела
    туда же, движением назад это не считалось (терминал вне `flow`, `is_before` всегда
    False) — и любой сейлз воскрешал сорванную сделку обычным нажатием, без права
    мастера и без следа. Выход из терминала — решение, а не шаг вперёд.

    Пустая стадия (`our_stage_id` NULL) — другое дело: сделке надо куда-то встать,
    отдаём первую применимую."""
    chain = flow_for(deal, catalog, marks)
    cur = deal.our_stage_id
    if cur in chain:
        i = chain.index(cur)
        return catalog.by_id[chain[i + 1]] if i + 1 < len(chain) else None
    if cur is not None and getattr(catalog.by_id.get(cur), "is_terminal", False):
        return None
    return catalog.by_id[chain[0]] if chain else None


# ── Видимость блоков карточки ────────────────────────────────────────────────
#
# Ключ блока совпадает с `id` секции на карточке сделки (frontend/pages/sales/deals/[id]).
# Значение — как понять, что внутри УЖЕ ЧТО-ТО ЕСТЬ: непустой блок не прячется никогда,
# даже если его стадия ещё не наступила. Спрятанные данные не просто невидимы — их
# невозможно найти: человек считает, что их нет, и заводит второй раз.

BLOCK_KEYS = ("head", "mp", "ord", "traffic-brief", "creatives", "campaign", "docs")


def _has_content(db, deal, key: str) -> bool:
    if key == "head":
        return True          # шапку не прячем никогда: на ней имя и стадия
    if key == "mp":
        return bool(db.execute(text(
            "SELECT 1 FROM sales_media_plans WHERE deal_id = :d LIMIT 1"),
            {"d": deal.id}).first())
    if key == "ord":
        return bool(deal.ord_initial_contract_id or deal.ord_final_contract_id)
    if key == "traffic-brief":
        return bool((getattr(deal, "traffic_brief", None) or "").strip())
    if key == "creatives":
        return bool(db.execute(text(
            "SELECT 1 FROM launch_prep_creative_set WHERE deal_id = :d LIMIT 1"),
            {"d": deal.id}).first())
    if key == "campaign":
        return bool(db.execute(text(
            "SELECT 1 FROM ad_campaign WHERE deal_id = :d LIMIT 1"),
            {"d": deal.id}).first())
    if key == "docs":
        return bool(db.execute(text(
            "SELECT 1 FROM sales_deal_files WHERE deal_id = :d LIMIT 1"),
            {"d": deal.id}).first())
    return True


def visible_blocks(db, deal, catalog, marks: Optional[dict] = None) -> dict:
    """{block_key: True/False} — какие блоки карточки показывать этой сделке.

    Три правила, и каждое закрывает свой способ потерять работу:

    1. **Появился — больше не исчезает.** Блок виден начиная со своей стадии, а не только
       на ней: иначе движение вперёд прятало бы заполненное, и это читается как «данные
       потерялись».
    2. **Непустое не прячем никогда** — см. комментарий к `_has_content`.
    3. **Нет разметки — виден всегда**: накат миграции не должен обнулить ничью карточку,
       а новый блок не должен пропасть оттого, что его забыли разметить.
    """
    rows = db.execute(text(
        "SELECT stage_id, block_key FROM sales_stage_blocks")).fetchall()
    by_block: dict = {}
    for sid, key in rows:
        by_block.setdefault(key, set()).add(sid)

    # Позиция стадии в ПОЛНОМ порядке каталога (включая терминальные): «начиная с» надо
    # уметь сравнивать и для сделки, ушедшей в архив.
    order = {s.id: i for i, s in enumerate(catalog.stages)}
    cur_pos = order.get(deal.our_stage_id, -1)

    out = {}
    for key in BLOCK_KEYS:
        stages = by_block.get(key)
        if not stages:
            out[key] = True                      # правило 3
            continue
        first = min((order.get(s, 10 ** 6) for s in stages), default=10 ** 6)
        out[key] = cur_pos >= first or _has_content(db, deal, key)   # правила 1 и 2
    return out
