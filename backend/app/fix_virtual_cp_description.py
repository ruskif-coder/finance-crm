"""
fix_virtual_cp_description.py

Для всех операций, у которых контрагент в статусе «виртуальный»:
  - description пусто/NULL  → записывает название контрагента
  - description заполнено   → ставит название контрагента первым, затем
                               через ' | ' существующее описание

Идемпотентно: если description уже начинается с названия контрагента —
строка пропускается, чтобы скрипт можно было запустить повторно без двойного
добавления.

Запуск:
    docker exec finance_backend python -m app.fix_virtual_cp_description
    docker exec finance_backend python -m app.fix_virtual_cp_description --apply
"""
import sys
import os
sys.path.insert(0, '/app')

from app.database import SessionLocal
from app.models import Operation, Counterparty


def main():
    apply_mode = "--apply" in sys.argv
    db = SessionLocal()
    try:
        rows = (
            db.query(Operation, Counterparty)
            .join(Counterparty, Operation.counterparty_id == Counterparty.id)
            .filter(Counterparty.status == 'виртуальный')
            .order_by(Counterparty.name, Operation.id)
            .all()
        )

        print("=" * 78)
        print("Перенос названия виртуального контрагента в поле «Описание»")
        print("=" * 78)
        print(f"Операций с виртуальным контрагентом: {len(rows)}")
        print()

        to_change = []
        skipped = 0

        for op, cp in rows:
            old_desc = (op.description or '').strip()

            # Идемпотентность: уже начинается с имени контрагента — пропускаем
            if old_desc.startswith(cp.name):
                skipped += 1
                continue

            new_desc = f"{cp.name} | {old_desc}" if old_desc else cp.name
            to_change.append((op, cp.name, old_desc, new_desc))

        print(f"Пропущено (уже содержат имя): {skipped}")
        print(f"Будет изменено: {len(to_change)}")
        print()

        for op, cp_name, old_desc, new_desc in to_change:
            old_show = repr(old_desc) if old_desc else '(пусто)'
            new_show = repr(new_desc)
            print(f"  #{op.id:>6}  [{cp_name}]")
            print(f"           было: {old_show}")
            print(f"          стало: {new_show}")

        print()
        print("=" * 78)
        if apply_mode:
            for op, cp_name, old_desc, new_desc in to_change:
                op.description = new_desc
            db.commit()
            print(f"ПРИМЕНЕНО: изменено {len(to_change)} операций.")
        else:
            db.rollback()
            print("DRY RUN — ничего не записано.")
            print("Запустите с --apply, чтобы применить.")
        print("=" * 78)

    finally:
        db.close()


if __name__ == "__main__":
    main()
