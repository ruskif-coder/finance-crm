# -*- coding: utf-8 -*-
"""Готовность маркировки — одно правило на всю систему (владелец 02.10.2026).

ЕРИД ОРД выдаёт сразу, а регистрация в ЕРИР идёт асинхронно:

    Created → RegistrationRequired → Registering → Active
                                               ↘ RegistrationError

ГОТОВ маркер при `Active` или `Registering`: креатив уже передан в реестр. На
`RegistrationRequired` он стоит в очереди ОРД и ещё может кончиться отказом — с 05.10.2026
ВРЕМЕННО тоже считается готовым (см. READY_STATUSES). Чужой маркер
(самореклама — его выпускает площадка в своём ОРД) нашего статуса не имеет и готов сразу.

Два вопроса, которые легко спутать:
  * «маркер ВЫДАН» — `set.erid` не пуст. Им живут запреты необратимого: не удалить
    комплект, не выпустить второй раз, искать по маркеру;
  * «маркер ГОТОВ» — эта функция. Ею живёт всё, что пускает рекламу дальше: стадия
    «ЕРИД выпущен», площадки «ерид получен», маркер в РК и в DSP, пиксель Weborama,
    ступень ОРД «Креативы», паспорт для внешних площадок.

До 02.10 вторым вопросом задавался только DSP (копия нацеливания), остальные отвечали
первым — и три комплекта прода в RegistrationRequired были «готовы» на одном экране и
«не готовы» на другом. Читать — только отсюда.
"""
from typing import Optional

# ВРЕМЕННО готов и `RegistrationRequired` (владелец 05.10.2026): ОРД держал 11 комплектов в
# очереди 3–5 дней, трафики не могли запускать. Маркер выдан — пускаем; риск, что ОРД потом
# откажет в регистрации, владелец принял. Вернуть строгое правило — убрать статус отсюда.
READY_STATUSES = ("Active", "Registering", "RegistrationRequired")
OWN_SOURCE = "наш"


def _marker(s) -> str:
    return (getattr(s, "erid", None) or "").strip()


def erid_ready(s) -> bool:
    """Маркер комплекта можно пускать в работу."""
    if not _marker(s):
        return False
    if (getattr(s, "erid_source", None) or OWN_SOURCE) != OWN_SOURCE:
        return True
    return getattr(s, "ord_status", None) in READY_STATUSES


def ready_erid(s) -> Optional[str]:
    """Маркер, если он готов, иначе None."""
    return _marker(s) if erid_ready(s) else None


def ready_sql(alias: str) -> str:
    """То же правило условием SQL над `launch_prep_creative_set` под псевдонимом `alias`.
    Тест `test_erid_readiness` сверяет его с `erid_ready` на всех случаях."""
    statuses = ", ".join(f"'{x}'" for x in READY_STATUSES)
    return (f"(coalesce(trim({alias}.erid), '') <> '' AND "
            f"(coalesce({alias}.erid_source, '{OWN_SOURCE}') <> '{OWN_SOURCE}' "
            f"OR {alias}.ord_status IN ({statuses})))")


def waiting_text(s) -> str:
    """Почему выданный маркер ещё не готов — словами для экрана."""
    return (f"ЕРИД {_marker(s)} выдан, ждёт регистрации в ЕРИР "
            f"(статус ОРД {getattr(s, 'ord_status', None) or 'не получен'})")


def is_direct(deal) -> bool:
    """Прямой рекламодатель (02.10.2026): изначальный договор = доходный, отдельного нет."""
    return bool(getattr(deal, "ord_direct_advertiser", False))
