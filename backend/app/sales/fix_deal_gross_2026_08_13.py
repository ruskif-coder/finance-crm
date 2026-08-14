"""Разовый фикс: пересчёт суммы С НДС у сделок, где импорт из Битрикса принёс мусор.

Причина. amount_with_vat приходит из стандартного поля opportunity, amount — из
отдельного поля «до НДС» (см. bitrix/deal_sync.py). opportunity заполнен лишь у 85
сделок из 1065, тогда как «до НДС» — у 1019, то есть достоверна именно сумма без НДС.
У семи сделок opportunity оказался невозможным: 0, либо меньше суммы без НДС, либо
втрое больше. Пересчитываем gross = net × (1 + SALES_VAT_RATE), как это делает конвейер
годового плана; net не трогаем.

Запуск (сначала бэкап!):
    docker exec finance_backend python -m app.sales.fix_deal_gross_2026_08_13 --apply
Без --apply печатает план и ничего не пишет.
"""
import sys

from app.database import SessionLocal
from app.sales.models import SalesDeal
from app.routers.year_plan import SALES_VAT_RATE

# Верхняя граница правдоподобия: gross не может быть меньше net и не может превышать
# net более чем на треть (ставка 22 % + запас на округления и старые ставки).
MAX_K = 1.31


def anomalies(db):
    rows = (db.query(SalesDeal)
            .filter(SalesDeal.amount.isnot(None), SalesDeal.amount != 0,
                    SalesDeal.amount_with_vat.isnot(None)).all())
    return [d for d in rows
            if d.amount_with_vat < d.amount - 1 or d.amount_with_vat > d.amount * MAX_K]


def main(apply: bool):
    db = SessionLocal()
    try:
        bad = anomalies(db)
        if not bad:
            print("Аномалий нет.")
            return
        for d in bad:
            new = round(d.amount * (1 + SALES_VAT_RATE), 2)
            print(f"{d.code or d.id}: net={d.amount} gross={d.amount_with_vat} -> {new}")
            if apply:
                d.amount_with_vat = new
        if apply:
            db.commit()
            print(f"Обновлено сделок: {len(bad)}")
        else:
            print(f"Всего к правке: {len(bad)}. Запустить с --apply, чтобы применить.")
    finally:
        db.close()


if __name__ == "__main__":
    main("--apply" in sys.argv)
