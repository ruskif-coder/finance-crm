"""Разовый сид our_stage_id для сделок (read-side флип: our_stage — мастер денег).

Заполняет SalesDeal.our_stage_id ТОЛЬКО там, где сейчас NULL (существующие
привязки, в т.ч. ручные перемещения через move_deal, НЕ трогает). Резолв — через
OurStageResolver (привязка стадии к Битриксу → мост по stage_key). Не сматчилось
→ остаётся NULL («требует разбора»).

Идемпотентно: повторный запуск ничего лишнего не делает. По умолчанию dry-run.

Запуск на сервере (после деплоя кода и применения привязок):
  docker exec finance_backend python -m app.seed_our_stage          # предпросмотр
  docker exec finance_backend python -m app.seed_our_stage --commit  # запись
"""
import sys
from app.database import SessionLocal
from app.sales.models import SalesDeal
from app.sales.stage_resolve import OurStageResolver


def main(commit: bool):
    db = SessionLocal()
    try:
        resolver = OurStageResolver(db)
        nulls = db.query(SalesDeal).filter(SalesDeal.our_stage_id.is_(None)).all()
        filled = still_null = 0
        for d in nulls:
            sid = resolver.resolve(d.pipeline, d.bitrix_stage)
            if sid is not None:
                d.our_stage_id = sid
                filled += 1
            else:
                still_null += 1
        total = db.query(SalesDeal).count()
        print(f"Всего сделок: {total}; было NULL: {len(nulls)}; "
              f"сматчилось: {filled}; остаётся NULL (требуют разбора): {still_null}")
        if commit:
            db.commit()
            print("Записано.")
        else:
            db.rollback()
            print("DRY-RUN (без записи). Повторить с --commit для записи.")
    finally:
        db.close()


if __name__ == "__main__":
    main(commit="--commit" in sys.argv)
