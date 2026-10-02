# -*- coding: utf-8 -*-
"""Разовая правка таргетинга по площадке (`source`) у кампаний, уже заведённых в DSP
(правка DSP 02.10.2026, владелец: «переписать что уже загружено»).

Было: `items{key: {is_checked, bid_start}}` — без `bid_rate`, DSP читал коэффициент как 0.
Надо: `bid_rate: 1` в каждом пункте, ставка `bid_start` — как была.

Источник истины — текущее состояние в DSP (`Targeting.getUserSetting`), а не наш журнал:
переотправляется ровно то, что там стоит, с добавленным `bid_rate`. Список кампаний — из
журнала отправок (все xxhash, которым мы когда-либо слали `source`).

По умолчанию — пробный прогон: только читает. Запись — `--apply`. Повтор безопасен:
пункты с `bid_rate` уже не трогаются.

    docker exec finance_backend python -m scripts.2026-10-02_dsp_source_bid_rate [--apply]
"""
import sys

from sqlalchemy import text

import app.main  # noqa: F401
from app.dsp.client import MsClient, MsError
from app.dsp.db import dsp_engine


def _items(got) -> dict:
    """Пункты из ответа getUserSetting: бывает {items:{…}} или {targeting_data:{items:{…}}}."""
    if not isinstance(got, dict):
        return {}
    data = got.get("targeting_data") if isinstance(got.get("targeting_data"), dict) else got
    items = data.get("items")
    return items if isinstance(items, dict) else {}


def _invert(got) -> bool:
    if not isinstance(got, dict):
        return False
    data = got.get("targeting_data") if isinstance(got.get("targeting_data"), dict) else got
    return bool(data.get("is_invert_mode"))


def fixed(items: dict) -> dict:
    """Те же пункты, у каждого `bid_rate: 1`, если его нет или он 0."""
    return {k: {**v, "bid_rate": 1} if not (v or {}).get("bid_rate") else v
            for k, v in items.items()}


def main():
    apply = "--apply" in sys.argv
    with dsp_engine().connect() as c:
        hashes = [h for (h,) in c.execute(text(
            "SELECT DISTINCT request->'params'->>'xxhash' FROM dsp_send_log "
            "WHERE method = 'Targeting.setUserSetting' "
            "AND request->'params'->>'target_key' = 'source' ORDER BY 1"))]
    cl = MsClient()
    todo = done = 0
    for h in hashes:
        try:
            got = cl.targeting_get(h, "source")
        except MsError as e:
            print(f"{h}: не прочитан — {e}")
            continue
        items = _items(got)
        new = fixed(items)
        if not items:
            print(f"{h}: таргетинга по площадке нет — пропуск")
            continue
        if new == items:
            print(f"{h}: уже с bid_rate — ок")
            continue
        todo += 1
        print(f"{h}: {items} → {new}")
        if apply:
            try:
                cl.targeting_set(h, "source", new, is_invert_mode=_invert(got))
                done += 1
            except MsError as e:
                print(f"{h}: НЕ записан — {e}")
    print(f"кампаний: {len(hashes)}, к правке: {todo}, записано: {done}"
          + ("" if apply else " (пробный прогон, запись — --apply)"))


if __name__ == "__main__":
    main()
