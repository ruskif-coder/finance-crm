# -*- coding: utf-8 -*-
"""«Дата» у плана поступлений моста → пусто (владелец 09.11.2026: «дата операции должна быть пустой», «есть отдельное поле дата
счёта»).

Мост мастер-сделки вписывал дату счёта из 1С и в «Дату» операции, и в «Дату счёта». У ручных планов поступлений «Дата» пустая —
её ставит оплата. Код моста исправлен; скрипт стирает «Дату» у уже записанных планов моста. Не трогает: дату счёта, оплаченные
операции моста, ручные операции.

    docker exec finance_backend python -m scripts.2026-11-09_bridge_plan_date_empty            # сухо
    docker exec finance_backend python -m scripts.2026-11-09_bridge_plan_date_empty --apply

Повторный запуск ничего не делает.
"""
import sys

from sqlalchemy import text

from app.models import PLAN_INCOME


def run(db, apply: bool = False) -> list:
    """Планы поступлений моста с заполненной «Датой»; при apply — дата стирается."""
    rows = [dict(r) for r in db.execute(text(
        "SELECT id, period, date, invoice, invoice_date, income, master_deal_upd_id FROM operations "
        "WHERE master_deal_upd_id IS NOT NULL AND status = :s AND date IS NOT NULL ORDER BY id"), {"s": PLAN_INCOME}).mappings()]
    if apply and rows:
        db.execute(text("UPDATE operations SET date = NULL WHERE id = ANY(:i)"), {"i": [r["id"] for r in rows]})
        db.flush()
    return rows


def main(argv=None) -> int:
    from app.database import SessionLocal
    argv = list(sys.argv[1:] if argv is None else argv)
    apply = "--apply" in argv
    db = SessionLocal()
    try:
        rows = run(db, apply=apply)
        if apply:
            db.commit()
    finally:
        db.close()
    print(("ПРИМЕНЕНО" if apply else "СУХОЙ ПРОГОН — ничего не записано") + f": планов моста с датой операции {len(rows)}")
    for x in rows:
        print(f"  #{x['id']:<6} {x['period'] or '—':<8} счёт {x['invoice'] or '—':<8} дата {x['date']} → пусто"
              f"  (дата счёта {x['invoice_date']} остаётся)")
    if not apply and rows:
        print("Для применения добавьте --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
