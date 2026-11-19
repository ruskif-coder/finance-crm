# -*- coding: utf-8 -*-
"""Привести старые номера ДС в операциях к правилу «ДС № N» / «ПР № N» (владелец 18.11.2026, `app/ds_label.py`).

Новые записи приводит валидатор модели; этот скрипт — один раз для того, что уже лежит в базе (`доп.12`, `прил 64`,
«Дополнительное соглашение № 12» …). Записи без номера после слова («пени», «заявка 3», голое число) не трогаются.

    docker exec finance_backend python -m scripts.2026-11-18_ds_num_short            # сухой прогон: сколько и примеры
    docker exec finance_backend python -m scripts.2026-11-18_ds_num_short --apply    # записать; прежние значения — в CSV

Повторный запуск безопасен: уже короткие номера не меняются (0 к записи).
"""
import csv
import os
import sys
from collections import Counter
from app.timez import msk_now

import app.model_registry  # noqa: F401 — регистрирует все таблицы
from sqlalchemy import text

from app.database import SessionLocal
from app.ds_label import short


def main(apply: bool) -> None:
    db = SessionLocal()
    rows = db.execute(text("SELECT id, ds_num FROM operations WHERE ds_num IS NOT NULL AND ds_num <> ''")).fetchall()
    changes = [(r.id, r.ds_num, short(r.ds_num)) for r in rows if short(r.ds_num) != r.ds_num]
    kinds = Counter(new.split(' ')[0] for _, _, new in changes)
    print(f"номеров всего: {len(rows)}; к записи: {len(changes)} ({dict(kinds)})")
    for i, old, new in changes[:15]:
        print(f"  #{i}: {old!r} → {new!r}")
    if not apply or not changes:
        print("сухой прогон — ничего не записано" if not apply else "записывать нечего")
        return
    os.makedirs('/app/logs', exist_ok=True)
    path = f"/app/logs/ds_num_before_short_{msk_now():%Y-%m-%d_%H%M}.csv"
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        csv.writer(fh).writerows([('id', 'ds_num_before', 'ds_num_after'), *changes])
    for i, _, new in changes:
        db.execute(text("UPDATE operations SET ds_num = :v WHERE id = :i"), {'v': new, 'i': i})
    db.commit()
    print(f"записано: {len(changes)}; прежние значения — {path}")


if __name__ == '__main__':
    main('--apply' in sys.argv)
