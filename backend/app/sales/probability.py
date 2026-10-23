# -*- coding: utf-8 -*-
"""Вероятность сделки — одно правило для «Статусов продаж», реестра и дашборда продаж (владелец 23.10.2026).

Хранится светофор `sales_deals.probability_color` (green — факт, orange — средняя, grey — низкая). Не задан — показываем
по стадии (Бронь — средняя, раньше — низкая), в базу при этом не пишем: «только показ». Сделка в работе (после Брони)
— всегда «факт»: это ПИШЕТСЯ (при переходе — `stage_move.apply_move`, старые — миграцией 2026-10-23) и правке не
поддаётся ни в «Статусах», ни в дашборде, ни в реестре."""
from typing import Optional

# После Брони проект запущен: сделка в «факте» и не двигается (владелец 21.10.2026).
IN_WORK = ("launch_prep", "launch", "closing", "closing_fact", "archive")
LIGHTS = ("green", "orange", "grey")
FACT = "green"


def in_work(stage_key: Optional[str]) -> bool:
    return stage_key in IN_WORK


def effective(light: Optional[str], stage_key: Optional[str], lost: bool = False) -> Optional[str]:
    """Цвет, который видит человек. None — у сорвавшейся: в суммы она не идёт.
    Двойник на клиенте — `frontend/lib/salesStatus.colOf` (колонка при переносе до сохранения): менять вместе."""
    if lost:
        return None
    if in_work(stage_key):
        return FACT
    if light in LIGHTS:
        return light
    return "orange" if stage_key == "booking" else "grey"
