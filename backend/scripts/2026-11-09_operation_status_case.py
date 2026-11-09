# -*- coding: utf-8 -*-
"""Статус операции мимо словаря из-за регистра → в словарь (09.11.2026).

Мост мастер-сделки писал «план поступлений» строчными: на проде 21 операция за октябрь (16,3 млн с НДС). Финотчёт «по начислению»
их видит, а дебиторка, карточки контрагента/договора, дашборд руководителя и напоминания сравнивают статус буквально — и не видят.
Код моста исправлен; этот скрипт приводит уже записанные строки. Трогает ТОЛЬКО статус и только там, где он отличается от
словарного одним регистром; прочие странные статусы перечисляет, но не меняет.

    docker exec finance_backend python -m scripts.2026-11-09_operation_status_case            # сухо
    docker exec finance_backend python -m scripts.2026-11-09_operation_status_case --apply

Повторный запуск ничего не делает.
"""
import sys

from sqlalchemy import text

from app.models import OPERATION_STATUSES


def run(db, apply: bool = False) -> dict:
    """fix — строки, где статус отличается от словарного только регистром/пробелами; other — прочие мимо словаря (не трогаем)."""
    rows = db.execute(text("SELECT id, status, period, income, invoice, master_deal_upd_id FROM operations "
                           "WHERE status <> ALL(:d) ORDER BY id"), {"d": list(OPERATION_STATUSES)}).mappings().all()
    rep = {"fix": [], "other": []}
    for r in rows:
        want = (r["status"] or "").strip().upper()
        item = {**dict(r), "to": want}
        (rep["fix"] if want in OPERATION_STATUSES else rep["other"]).append(item)
    if apply:
        for it in rep["fix"]:
            db.execute(text("UPDATE operations SET status = :s WHERE id = :i"), {"s": it["to"], "i": it["id"]})
        db.flush()
    return rep


def main(argv=None) -> int:
    from app.database import SessionLocal
    argv = list(sys.argv[1:] if argv is None else argv)
    apply = "--apply" in argv
    db = SessionLocal()
    try:
        rep = run(db, apply=apply)
        if apply:
            db.commit()
    finally:
        db.close()
    total = sum(float(x["income"] or 0) for x in rep["fix"])
    print(("ПРИМЕНЕНО" if apply else "СУХОЙ ПРОГОН — ничего не записано")
          + f": к правке {len(rep['fix'])} на {total:,.0f} ₽ дохода".replace(",", " ") + f", прочих мимо словаря {len(rep['other'])}")
    for x in rep["fix"]:
        print(f"  #{x['id']:<6} {x['period'] or '—':<8} счёт {x['invoice'] or '—':<8} «{x['status']}» → «{x['to']}»"
              + (f"  (мост, комплект {x['master_deal_upd_id']})" if x["master_deal_upd_id"] else ""))
    for x in rep["other"]:
        print(f"  НЕ ТРОГАЮ #{x['id']} «{x['status']}» — статуса нет в словаре")
    if not apply and rep["fix"]:
        print("Для применения добавьте --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
