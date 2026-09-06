"""Крон: порождение РК и доезд новых площадок-кандидатов (этап 3a).

Владелец 02.09.2026: РК заводится автоматически (при открытии дашборда и кнопкой), а новые
площадки «подключаются по мере согласования креативов» — их доезд ловит этот прогон.
Идемпотентно: добавляет недостающее, статусы существующих площадок не трогает.

    docker exec finance_backend python -m scripts.2026-09-02_sync_ad_campaigns
    docker exec finance_backend python -m scripts.2026-09-02_sync_ad_campaigns --dry-run

Крон на сервере (после выкладки, с разрешения владельца):
    0 6 * * * docker exec finance_backend python -m scripts.2026-09-02_sync_ad_campaigns
"""
import argparse

import app.models  # noqa: F401 — регистрирует users в Base.metadata
import app.launch_prep.models  # noqa: F401 — launch_prep_* (FK из ad.models)

from app.ad import build  # noqa: E402
from app.database import SessionLocal  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="показать, но не записывать")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        res = build.sync_all(db, commit=not args.dry_run)
        if args.dry_run:
            db.rollback()
        print(f"{'[dry-run] ' if args.dry_run else ''}"
              f"РК: создано {res['created']}, обновлено {res['updated']}, "
              f"без медиаплана {res['no_media_plan']} (из {res['deals']} сделок "
              f"на {res['stages']} стадиях)")
        print(f"Площадки: кандидатов {res['placement_candidates']}, "
              f"добавлено {res['placements_added']}, без веса {res['placements_without_weight']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
