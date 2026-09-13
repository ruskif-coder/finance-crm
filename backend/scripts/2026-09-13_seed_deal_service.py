# -*- coding: utf-8 -*-
"""Разовый засев `sales_deals.service_id` (миграция 2026-09-13_deal_service.sql).

Правило владельца 13.09.2026: услуга сделки — ПЕРВАЯ услуга её медиаплана. Колонка
новая, поэтому у всех сделок она пуста; здесь проставляем её задним числом.

Два источника, строго по убыванию доверия:

1. **Первая строка плана** — то самое правило. Единственный источник, которому доверяем
   без оговорок.
2. **`product` по имени** — для сделок БЕЗ плана (их большинство: планы в системе только
   у 35 из 920). Строка приехала из Битрикса, и это догадка, а не правило, — поэтому
   сопоставляем только при ТОЧНОМ совпадении с именем в справочнике услуг. «DSP OLV
   (не предлагать)» и прочий мусор из Битрикса в справочник не попадёт и останется
   неразобранным, что честнее приблизительного матча.

Не сматчилось — оставляем NULL. Это не ошибка: к сделке без услуги применяются только
общие требования стадий, без привязки к услуге.

Повторный запуск безопасен: трогаем только сделки с пустым `service_id`. Уже
проставленное не перезаписываем — сделку могли поправить руками после первого прогона.

    docker exec finance_backend python -m scripts.2026-09-13_seed_deal_service --dry-run
    docker exec finance_backend python -m scripts.2026-09-13_seed_deal_service --commit
"""
import argparse

from sqlalchemy import text

from app.database import SessionLocal


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="записать (без флага — только показать)")
    ap.add_argument("--dry-run", action="store_true", help="явная форма прогона без записи")
    args = ap.parse_args()
    write = args.commit and not args.dry_run

    db = SessionLocal()
    try:
        total = db.execute(text("SELECT count(*) FROM sales_deals")).scalar()
        empty = db.execute(text(
            "SELECT count(*) FROM sales_deals WHERE service_id IS NULL")).scalar()

        # 1. По первой строке плана.
        by_plan = db.execute(text("""
            WITH first_row AS (
                SELECT DISTINCT ON (p.deal_id) p.deal_id, r.position
                  FROM sales_media_plans p
                  JOIN sales_media_plan_rows r ON r.plan_id = p.id
                 WHERE p.deal_id IS NOT NULL
                 ORDER BY p.deal_id, p.version DESC, r.sort_order
            )
            SELECT d.id, s.id AS service_id, s.name
              FROM sales_deals d
              JOIN first_row f ON f.deal_id = d.id
              JOIN sales_services s ON s.name = btrim(f.position)
             WHERE d.service_id IS NULL
        """)).fetchall()

        # 2. По строке product — только для сделок БЕЗ плана.
        by_product = db.execute(text("""
            SELECT d.id, s.id AS service_id, s.name
              FROM sales_deals d
              JOIN sales_services s ON s.name = btrim(d.product)
             WHERE d.service_id IS NULL
               AND NOT EXISTS (SELECT 1 FROM sales_media_plans p WHERE p.deal_id = d.id)
        """)).fetchall()

        print(f"сделок всего: {total}, без услуги: {empty}")
        print(f"  по первой строке плана: {len(by_plan)}")
        print(f"  по строке product:      {len(by_product)}")

        seen = {r[0] for r in by_plan}
        pairs = list(by_plan) + [r for r in by_product if r[0] not in seen]
        rest = empty - len(pairs)
        print(f"  останется без услуги:   {rest}")

        spread: dict = {}
        for _, _, name in pairs:
            spread[name] = spread.get(name, 0) + 1
        for name, n in sorted(spread.items(), key=lambda kv: -kv[1]):
            print(f"    {name}: {n}")

        if not write:
            print("\nпрогон без записи — для записи добавьте --commit")
            return

        for deal_id, service_id, _ in pairs:
            db.execute(text("UPDATE sales_deals SET service_id = :s WHERE id = :d"),
                       {"s": service_id, "d": deal_id})
        db.commit()
        left = db.execute(text(
            "SELECT count(*) FROM sales_deals WHERE service_id IS NULL")).scalar()
        print(f"\nзаписано: {len(pairs)}; без услуги осталось: {left}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
