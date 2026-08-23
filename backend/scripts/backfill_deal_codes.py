"""Одноразовый бэкфилл: присвоить code всем сделкам без метки. Идемпотентно (только WHERE code IS NULL).

Запуск: docker exec finance_backend python -m scripts.backfill_deal_codes
"""
import app.models  # noqa: F401 — регистрирует связанные таблицы (counterparties и т.п.)
from app.database import SessionLocal
from app.sales.models import SalesDeal
from app.sales.deal_code import assign_code


def main():
    db = SessionLocal()
    try:
        rows = db.query(SalesDeal).filter(SalesDeal.code.is_(None)).all()
        print(f"Сделок без метки: {len(rows)}")
        done = 0
        for d in rows:
            assign_code(db, d)
            done += 1
            if done % 200 == 0:
                db.commit()
                print(f"  … {done}")
        db.commit()
        print(f"Готово: присвоено меток — {done}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
