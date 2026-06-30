"""
Привязка существующих строк Contract к реестру контрагентов через
Contract.counterparty_id (FK-колонка, добавляется отдельно через
add_contract_counterparty_fk.sql перед запуском этого скрипта).

Алгоритм сопоставления — тот же, что и в sync_contracts.py: normalize_inn /
normalize_name / build_indexes импортируются оттуда напрямую, а не
переписываются. Сперва пробуем сопоставить по ИНН, если не вышло — по
названию. Никакого нечёткого (fuzzy) сопоставления — риск перепутать
контрагентов в финансовых данных того не стоит (см. CLAUDE.md): при 0 или
>1 кандидатах строка не трогается и уходит в отчёт на ручной разбор через
раздел «Договоры» (там теперь есть привязка к реестру через выпадающий список).

Для каждой однозначно сопоставленной строки:
  - Contract.counterparty_id = id найденного контрагента (сама привязка,
    цель этой миграции);
  - Contract.counterparty_name / Contract.inn дополнительно перезаписываются
    на канонические значения из Counterparty — тот же эффект, что и у
    sync_contracts.py, но теперь подкреплён настоящей связью, а не только
    текстовым совпадением.

Строки, у которых counterparty_id уже заполнен (например, договоры,
созданные через обновлённый UI после деплоя — там привязка обязательна),
не трогаются и не попадают в выборку.

Запуск:
    docker exec finance_backend python -m app.link_contracts_to_counterparties            # dry-run
    docker exec finance_backend python -m app.link_contracts_to_counterparties --apply     # применить

link_contracts_to_counterparties.bat сам применяет ALTER TABLE (добавляет
counterparty_id), прогоняет dry-run, печатает отчёт, спрашивает
подтверждение, делает pg_dump и только потом запускает --apply.
"""
import sys

from app.database import SessionLocal
from app.models import Contract, Counterparty
from app.sync_contracts import normalize_inn, normalize_name, build_indexes


def link_contracts(db):
    counterparties = db.query(Counterparty).all()
    by_inn, by_name = build_indexes(counterparties)

    contracts = db.query(Contract).filter(Contract.counterparty_id.is_(None)).all()

    linked_rows = []
    ambiguous_rows = []
    not_found_rows = []

    for c in contracts:
        inn_n = normalize_inn(c.inn)
        name_n = normalize_name(c.counterparty_name)
        candidates = []
        via = None
        if inn_n and inn_n in by_inn:
            candidates = by_inn[inn_n]
            via = "ИНН"
        elif name_n and name_n in by_name:
            candidates = by_name[name_n]
            via = "название"

        if len(candidates) > 1:
            ambiguous_rows.append((c.id, c.counterparty_name, c.inn, via, len(candidates)))
            continue
        if len(candidates) == 0:
            not_found_rows.append((c.id, c.counterparty_name, c.inn))
            continue

        match = candidates[0]
        old_name, old_inn = c.counterparty_name, c.inn
        c.counterparty_id = match.id
        c.counterparty_name = match.name
        c.inn = match.inn or c.inn
        linked_rows.append((c.id, old_name, old_inn, match.id, match.name, match.inn, via))

    return {
        "linked": linked_rows,
        "ambiguous": ambiguous_rows,
        "not_found": not_found_rows,
        "total_unlinked_before": len(contracts),
    }


def print_report(result, apply_mode):
    print("=" * 78)
    print("Привязка Contract.counterparty_id к реестру контрагентов")
    print("=" * 78)
    print(f"Непривязанных строк до запуска: {result['total_unlinked_before']}")
    print()
    print(f"Привязано: {len(result['linked'])}")
    for cid, old_name, old_inn, cp_id, cp_name, cp_inn, via in result["linked"]:
        print(f"  #{cid}: \"{old_name}\" / ИНН {old_inn}  ->  Counterparty #{cp_id} \"{cp_name}\" / ИНН {cp_inn}  (совпадение по {via})")
    print(f"Неоднозначно (>1 кандидата, не трогали): {len(result['ambiguous'])}")
    for cid, name, inn, via, n in result["ambiguous"]:
        print(f"  #{cid}: \"{name}\" / ИНН {inn} — {n} кандидатов по {via}")
    print(f"Не найдено в реестре контрагентов (не трогали): {len(result['not_found'])}")
    for cid, name, inn in result["not_found"]:
        print(f"  #{cid}: \"{name}\" / ИНН {inn}")

    print()
    print("=" * 78)
    if apply_mode:
        print("Изменения ЗАПИСАНЫ в базу.")
    else:
        print("DRY RUN — изменения НЕ записаны. Запустите с --apply, чтобы применить.")
    print("Неоднозначные и не найденные строки нужно привязать вручную через раздел «Договоры».")
    print("=" * 78)


def main():
    apply_mode = "--apply" in sys.argv
    db = SessionLocal()
    try:
        result = link_contracts(db)
        print_report(result, apply_mode)
        if apply_mode:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
