# -*- coding: utf-8 -*-
"""События креативов — только где матрица учёта по услугам требует креативы (владелец 14.11.2026).

Правило одно с дашбордом аккаунта: внешний запуск (`account_turn.external_launch` — контур аккаунта, и матрица не требует ни
креативов, ни ЕРИД) не согласует баннер с площадками и не проходит проверку трафика. Поэтому ни «площадка молчит», ни «трафик
вернул креатив», ни «ЕРИД выпущен» по такой сделке не уходят: на копии прода 14.11 по OLV висело 7 «площадка молчит» по старым
парам. Включили креативы для услуги в матрице — события снова идут, правка кода не нужна.

Проверка стоит в двух местах одного потока: в `bus.emit` (события по действию) и в сканере до записи состояния (по расписанию)."""
from typing import Optional

CREATIVE_EVENTS = {"creative_set_sent", "creative_verdict", "traffic_rework", "creative_silence", "traffic_silence",
                   "creative_erid_failed", "creative_erid_issued"}


def allowed_for(event_key: str, flow: str, applies) -> bool:
    """Чистая часть: событие `event_key` для сделки с циклом `flow` и применимыми пунктами матрицы `applies`."""
    from app.sales.account_turn import external_launch
    return event_key not in CREATIVE_EVENTS or not external_launch(flow, applies)


def allowed(db, event_key: str, ctx: Optional[dict]) -> bool:
    """Без сделки в контексте решать нечем — пропускаем (адресаты всё равно читают сделку из ctx)."""
    if event_key not in CREATIVE_EVENTS:
        return True
    deal = (ctx or {}).get("deal")
    if deal is None or db is None:
        return True
    from app.final_recon import flow
    from app.sales.models import SalesStageCheck
    from app.sales.stage_checks import applicable_keys
    return allowed_for(event_key, flow.of_deal(db, deal), applicable_keys(db.query(SalesStageCheck).all(), deal))
