# -*- coding: utf-8 -*-
"""Починка данных: «в размещении» там, где ничего не запущено.

До 18.09.2026 это состояние ставилось кнопкой на карточке сделки. Один и тот же факт —
«идёт ли размещение» — имели право утверждать два места, и они разошлись: карточка
говорила о размещении по площадке, у которой РК не собрана, сама площадка ждёт запуска,
а срок не наступил.

Писатель теперь один — запуск площадки в дашборде трафика. Этот прогон приводит в
соответствие то, что успели наставить руками: пары, объявленные размещёнными, у которых
площадка в РК НЕ запущена, откатываются на «ерид получен». Обратный ход разрешён только
здесь и только потому, что исправляется неверная запись, а не отменяется решение.

    docker exec finance_backend python -m scripts.2026-09-18_fix_placed_without_launch --dry-run
    docker exec finance_backend python -m scripts.2026-09-18_fix_placed_without_launch --apply
"""
import argparse

import app.models  # noqa: F401 — регистрирует users в Base.metadata
import app.launch_prep.models  # noqa: F401
import app.sales.models  # noqa: F401
import app.ad.models  # noqa: F401

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402

RUNNING = ("запущен", "пауза")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT t.id, t.deal_id, t.publisher_id, p.name AS publisher,
                   pl.status AS placement_status
              FROM launch_prep_target t
              JOIN sales_publishers p ON p.id = t.publisher_id
              LEFT JOIN ad_campaign c ON c.deal_id = t.deal_id
              LEFT JOIN ad_campaign_placement pl
                     ON pl.campaign_id = c.id AND pl.publisher_id = t.publisher_id
             WHERE t.state = 'в размещении' AND t.archived_at IS NULL
        """)).mappings().all()

        bad = [r for r in rows if (r["placement_status"] or "") not in RUNNING]
        print(f"объявлено размещёнными: {len(rows)}, из них без запуска: {len(bad)}")
        for r in bad:
            print(f"  сделка {r['deal_id']} · {r['publisher']} · "
                  f"площадка в РК: {r['placement_status'] or 'нет строки'}")
        if bad and args.apply:
            db.execute(text("UPDATE launch_prep_target SET state = 'ерид получен' "
                            "WHERE id = ANY(:ids)"), {"ids": [r["id"] for r in bad]})
            db.commit()
            print(f"откатано: {len(bad)}")
        elif bad:
            print("это показ; чтобы применить — --apply")
    finally:
        db.close()


if __name__ == "__main__":
    main()
