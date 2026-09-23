# -*- coding: utf-8 -*-
"""Фиксация медиаплана на стадии «Сборка» — одно правило на все места записи.

РЕШЕНИЕ ВЛАДЕЛЬЦА 23.09.2026. После перевода сделки в «Сборку» («Готовятся к старту»,
`stage_key = launch_prep`) медиаплан фиксируется: правки больше не принимаются, КРОМЕ ДАТ
ЗАПУСКА (`date_from` / `date_to`). Мастер править может — с записью в журнал. При
переводе человек видит об этом уведомление ДО нажатия.

ЗАЧЕМ. На «Сборке» по плану уже собирают размещение: площадки, объёмы, креативы,
приложение к договору. Любое сохранение плана возит его сумму и реквизиты в сделку
(`_sync_deal_from_plan`), и до этого решения ничто не мешало переписать сумму сделки,
по которой уже подписан документ (аудит 23.09.2026, 3.H4). Прежняя «фиксация»
(`_plan_is_sealed`) защищала только историю версий — правка рождала новую версию и всё
равно переписывала сделку.

ГРАНИЦА — ПОЗИЦИЯ В КАТАЛОГЕ, а не имя и не номер стадии. Всё, что в каталоге стоит на
месте «Сборки» и дальше, — зафиксировано, включая «Сделка сорвалась» (она идёт после
«Брони») и архив. «Сделка не случилась» стоит в песочнице, до «Сборки», — план там не
фиксируется: сделки не было, фиксировать нечего. Переименуют стадию или вставят новую —
граница поедет вместе с `stage_key`.
"""
from __future__ import annotations

from typing import Optional

LOCK_STAGE_KEY = "launch_prep"

NOTICE = ("После перевода сделки в стадию сборки медиаплан фиксируется и больше "
          "недоступен для правок (кроме дат запуска)")

# Поля, которые остаются открытыми на зафиксированном плане.
OPEN_FIELDS = ("date_from", "date_to")


def _position(cat, stage_id) -> Optional[int]:
    for i, s in enumerate(cat.stages):
        if s.id == stage_id:
            return i
    return None


def lock_position(cat) -> Optional[int]:
    """Место «Сборки» в каталоге. None — стадии с таким ключом нет (фиксация выключена)."""
    for i, s in enumerate(cat.stages):
        if getattr(s, "stage_key", None) == LOCK_STAGE_KEY:
            return i
    return None


def stage_locks_plan(cat, stage_id) -> bool:
    """Сделка на этой стадии держит свой медиаплан зафиксированным?"""
    if not stage_id:
        return False
    lock, pos = lock_position(cat), _position(cat, stage_id)
    return lock is not None and pos is not None and pos >= lock


def crosses_lock(cat, from_stage_id, to_stage_id) -> bool:
    """Этот переход ФИКСИРУЕТ план: из открытой стадии — в зафиксированную."""
    return stage_locks_plan(cat, to_stage_id) and not stage_locks_plan(cat, from_stage_id)


def deal_locks_plan(db, deal_id) -> bool:
    """Сделка по id — держит ли она план зафиксированным. Нет сделки — нет фиксации."""
    if not deal_id:
        return False
    from app.sales.catalog import Catalog
    from app.sales.models import SalesDeal
    deal = db.query(SalesDeal).filter(SalesDeal.id == deal_id).first()
    return bool(deal and stage_locks_plan(Catalog(db), deal.our_stage_id))
