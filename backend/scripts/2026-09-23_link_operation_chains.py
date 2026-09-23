# -*- coding: utf-8 -*-
"""Разметить цепочки частичных оплат, заведённые руками до 23.09.2026.

Зачем. До кнопки «Частичная оплата» плановую операцию закрывали по частям вручную:
копия с полученной суммой — «оплачено», исходная — план на остаток. Связи между ними не
было, и в данных остались группы операций с одинаковыми № ДС и Счётом. Миграция
`2026-09-23_operation_parent.sql` завела поле связи; этот скрипт проставляет его старым
цепочкам.

Правило разметки — `app.operation_chains.plan_backfill` (там же почему именно так):
группа = № ДС + Счёт + КОНТРАГЕНТ; корень — единственная плановая операция группы, а если
цепочка уже погашена — заведённая раньше всех. Группы, где решить нечем (две плановых,
приход вместе с расходом), НЕ трогаются — они печатаются списком для ручной разметки.
Группы, где хоть что-то уже связано, не трогаются тоже.

Без `--apply` только показывает, что собирается сделать. Повторный прогон безопасен:
размеченные группы пропускаются.

    docker exec finance_backend python -m scripts.2026-09-23_link_operation_chains
    docker exec finance_backend python -m scripts.2026-09-23_link_operation_chains --apply
"""
import sys

# Реестр моделей целиком: у операции внешние ключи на пользователей и контрагентов, и без
# их моделей SQLAlchemy падает на commit — уже ПОСЛЕ печати списка, то есть вывод
# выглядел бы как успех (так случилось со скриптом 21.09.2026).
import app.models  # noqa: F401
import app.notify.models  # noqa: F401
from app.database import SessionLocal
from app.models import Counterparty, Operation
from app.operation_chains import amount, plan_backfill


def _line(op, cp_name, mark=""):
    return (f"    #{op.id:<6} {op.status:<17} {amount(op):>14,.2f}  "
            f"{(op.date.isoformat() if op.date else '—'):<10}  {cp_name}{mark}").replace(",", " ")


def main(apply: bool) -> int:
    db = SessionLocal()
    try:
        ops = (db.query(Operation)
               .filter(Operation.ds_num.isnot(None), Operation.invoice.isnot(None),
                       Operation.counterparty_id.isnot(None)).all())
        by_id = {o.id: o for o in ops}
        names = {c.id: c.name for c in db.query(Counterparty).all()}
        plan = plan_backfill(ops)
        links, unclear = plan["links"], plan["unclear"]

        roots = {}
        for part, root in links.items():
            roots.setdefault(root, []).append(part)
        print(f"Цепочек к разметке: {len(roots)}, частей: {len(links)}")
        for root, parts in sorted(roots.items()):
            r = by_id[root]
            print(f"\n  № ДС «{r.ds_num}» / счёт «{r.invoice}»")
            print(_line(r, names.get(r.counterparty_id, '?'), "   ← материнская"))
            for p in sorted(parts):
                print(_line(by_id[p], names.get(by_id[p].counterparty_id, '?')))

        if unclear:
            print(f"\nОставлено для ручной разметки: {len(unclear)}")
            for (cp, ds, inv), ids, why in unclear:
                print(f"  № ДС «{ds}» / счёт «{inv}», {names.get(cp, '?')}: {ids} — {why}")

        if not apply:
            print("\nСухой прогон: ничего не записано. Запись — с флагом --apply.")
            return 0
        if not links:
            print("\nЗаписывать нечего.")
            return 0

        for part, root in links.items():
            by_id[part].parent_operation_id = root
        db.commit()

        # Успех — по базе, а не по отсутствию исключения: сверяем, что связь легла.
        done = (db.query(Operation.id)
                .filter(Operation.id.in_(list(links)), Operation.parent_operation_id.isnot(None))
                .count())
        if done != len(links):
            print(f"\nОШИБКА: связано {done} из {len(links)} — проверьте журнал базы.")
            return 1
        print(f"\nЗаписано: {done} частей в {len(roots)} цепочках.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv[1:]))
