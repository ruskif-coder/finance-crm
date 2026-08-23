"""Одноразовый бэкфилл vat_rate_income/expense и default_article_income/expense_id
по фактическим операциям (2026-07-16, см. add_vat_article_defaults.sql и models.py).

Правила:
- НДС: ставка из САМОЙ СВЕЖЕЙ операции направления (по date, потом по id) — не самая
  частая, потому что «смешанные» ставки в истории почти всегда пара 20/22 (переход
  ставки НДС 20→22%), и частотный выбор утянул бы устаревшие 20%.
- Статья: самая частая по направлению (разнобой маленький: 26 контрагентов на расходе,
  3 на приходе — им ставится самая частая, спорные печатаются в отчёт для ручной правки).
- Уже заполненные вручную значения НЕ перезаписываются (idempotent, можно перезапускать).

Запуск: docker exec finance_backend python -m scripts.backfill_vat_articles
"""
from sqlalchemy import text
from app.database import SessionLocal


def main():
    db = SessionLocal()
    try:
        # --- НДС: последняя операция каждого направления ---
        vat_rows = db.execute(text("""
            SELECT DISTINCT ON (counterparty_id, dir) counterparty_id, dir, vat_rate
            FROM (
                SELECT counterparty_id,
                       CASE WHEN income > 0 THEN 'income' ELSE 'expense' END AS dir,
                       vat_rate, date, id
                FROM operations
                WHERE counterparty_id IS NOT NULL
            ) t
            ORDER BY counterparty_id, dir, date DESC, id DESC
        """)).fetchall()

        # --- Статья: самая частая по направлению ---
        art_rows = db.execute(text("""
            SELECT DISTINCT ON (counterparty_id, dir) counterparty_id, dir, article_id, cnt
            FROM (
                SELECT counterparty_id,
                       CASE WHEN income > 0 THEN 'income' ELSE 'expense' END AS dir,
                       article_id, COUNT(*) AS cnt
                FROM operations
                WHERE counterparty_id IS NOT NULL AND article_id IS NOT NULL
                GROUP BY 1, 2, 3
            ) t
            ORDER BY counterparty_id, dir, cnt DESC, article_id
        """)).fetchall()

        # --- Спорные статьи (несколько вариантов) — в отчёт ---
        mixed_art = db.execute(text("""
            SELECT c.name, t.dir, COUNT(*) AS variants
            FROM (
                SELECT counterparty_id,
                       CASE WHEN income > 0 THEN 'income' ELSE 'expense' END AS dir,
                       article_id
                FROM operations
                WHERE counterparty_id IS NOT NULL AND article_id IS NOT NULL
                GROUP BY 1, 2, 3
            ) t JOIN counterparties c ON c.id = t.counterparty_id
            GROUP BY c.name, t.dir HAVING COUNT(*) > 1
            ORDER BY c.name
        """)).fetchall()

        vat_updated = art_updated = skipped = 0

        for cid, direction, rate in vat_rows:
            col = "vat_rate_income" if direction == "income" else "vat_rate_expense"
            res = db.execute(text(
                f"UPDATE counterparties SET {col} = :rate WHERE id = :cid AND {col} IS NULL"
            ), {"rate": rate, "cid": cid})
            if res.rowcount:
                vat_updated += 1
            else:
                skipped += 1

        for cid, direction, article_id, _cnt in art_rows:
            col = "default_article_income_id" if direction == "income" else "default_article_expense_id"
            res = db.execute(text(
                f"UPDATE counterparties SET {col} = :aid WHERE id = :cid AND {col} IS NULL"
            ), {"aid": article_id, "cid": cid})
            if res.rowcount:
                art_updated += 1

        db.commit()

        print(f"НДС: заполнено {vat_updated} значений (пропущено уже заполненных: {skipped})")
        print(f"Статьи: заполнено {art_updated} значений")
        if mixed_art:
            print("\nКонтрагенты с несколькими статьями по направлению (поставлена самая частая, проверьте вручную):")
            for name, direction, variants in mixed_art:
                print(f"  {name} [{direction}]: {variants} вариантов")
    finally:
        db.close()


if __name__ == "__main__":
    main()
