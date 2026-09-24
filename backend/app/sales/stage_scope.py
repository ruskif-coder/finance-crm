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
    # Сделка стоит на стадии основной цепочки, неприменимой к её услуге: реестр так
    # ставит сознательно (решение владельца 24.09.2026), и так выходит при смене услуги
    # посреди пути. Следующая — ближайшая применимая ВПЕРЕДИ; первая стадия цепочки
    # отправила бы сделку в начало обычной кнопкой (ревью этапа 7, 24.09.2026).
    if cur in catalog.flow:
        after = catalog.flow[catalog.flow.index(cur) + 1:]
        return next((catalog.by_id[s] for s in after if s in chain), None)
    return catalog.by_id[chain[0]] if chain else None


# ── Видимость блоков карточки ────────────────────────────────────────────────
#
# Ключ блока совпадает с `id` секции на карточке сделки (frontend/pages/sales/deals/[id]).
# Значение — как понять, что внутри УЖЕ ЧТО-ТО ЕСТЬ: непустой блок не прячется никогда,
# даже если его стадия ещё не наступила. Спрятанные данные не просто невидимы — их
# невозможно найти: человек считает, что их нет, и заводит второй раз.

BLOCK_KEYS = ("head", "mp", "ord", "traffic-brief", "campaign-extra", "creatives",
              "campaign", "docs")

# Подписи для экрана настройки. Живут рядом с ключами, а не во фронте: список блоков —
# свойство карточки, и разойтись эти два перечня не должны.
BLOCK_LABELS = {
    "head": "Шапка сделки",
    "mp": "Медиаплан",
    "ord": "ОРД",
    "traffic-brief": "Цели и особенности РК",
    "campaign-extra": "Доп. параметры РК",
    "creatives": "Креативы",
    "campaign": "Рекламная кампания",
    "docs": "Документы",
}


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
    if key == "campaign-extra":
        # «Непусто» = параметр отличается от умолчания, то есть его кто-то осознанно
        # включил. Пока параметр один; когда их станет несколько, условие станет ИЛИ по
        # ним — и останется одним выражением, а не проверкой в каждом месте вывода.
        return bool(getattr(deal, "weborama_pixel", False))
    if key == "docs":
        # Блок документов наполняется ТРЕМЯ разными способами, и «загруженный файл» —
        # только один из них. Медиаплан лежит своей строкой, а ДС считается готовой по
        # ВЫПУЩЕННОМУ приложению — файла у него больше нет вовсе (`sales/deals/[id].js`,
        # `docsReady`). Считать непустоту по одним файлам значило бы объявить пустой
        # сделку с выпущенной ДС и планом — то есть спрятать ровно то, что уже собрано.
        return bool(db.execute(text("""
            SELECT 1 WHERE EXISTS (SELECT 1 FROM sales_deal_files WHERE deal_id = :d)
                       OR EXISTS (SELECT 1 FROM sales_media_plans WHERE deal_id = :d)
                       OR EXISTS (SELECT 1 FROM sales_deal_annex_allocation a
                                  JOIN sales_annexes x ON x.id = a.annex_id
                                  WHERE a.deal_id = :d AND x.no IS NOT NULL)
            """), {"d": deal.id}).first())
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


def blocks_markup(db, catalog) -> list:
    """Разметка блоков ДЛЯ ЭКРАНА настройки: по одной строке на блок.

    В таблице ключ — пара (стадия, блок), то есть строк на блок может быть несколько. Но
    читаются они правилом «виден НАЧИНАЯ с самой ранней» (`visible_blocks`), поэтому все
    строки, кроме первой, не значат ничего. Экран показывает то, что действительно
    работает, — одну стадию, — и сохранение приводит таблицу к этому же виду.

    `stage_id = None` — «виден всегда» (правило 3: нет строки — нет ограничения).
    """
    rows = db.execute(text(
        "SELECT stage_id, block_key FROM sales_stage_blocks")).fetchall()
    order = {s.id: i for i, s in enumerate(catalog.stages)}
    first: dict = {}
    for sid, key in rows:
        pos = order.get(sid)
        if pos is None:          # стадия удалена из каталога — строка уже ничего не значит
            continue
        if key not in first or pos < first[key][0]:
            first[key] = (pos, sid)
    return [{"key": k, "label": BLOCK_LABELS.get(k, k),
             "stage_id": first.get(k, (None, None))[1]} for k in BLOCK_KEYS]


def save_blocks_markup(db, pairs: dict) -> None:
    """Переписать разметку: {block_key: stage_id | None}. Вызывается внутри чужой
    транзакции — `commit` остаётся за вызывающим, чтобы сохранение каталога и блоков
    было одним действием, а не двумя с разной судьбой."""
    db.execute(text("DELETE FROM sales_stage_blocks"))
    for key, sid in pairs.items():
        if sid is None:
            continue
        db.execute(text(
            "INSERT INTO sales_stage_blocks (stage_id, block_key) VALUES (:s, :b)"),
            {"s": sid, "b": key})
