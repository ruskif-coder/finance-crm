"""
Синхронизация раздела «Договоры» со справочником контрагентов + выгрузка
неактивных контрагентов.

Делает два шага в одной транзакции:

  1. Стандартизация: для каждой существующей строки Contract ищет контрагента
     в Counterparty — сперва по ИНН (после нормализации: убираем все
     нечисловые символы, чиним артефакт Excel "1234567890.0" -> "1234567890"),
     если не нашли — по названию (lower + схлопнутые пробелы + без кавычек).
     При ОДНОЗНАЧНОМ совпадении counterparty_name/inn в Contract
     перезаписываются на канонические значения из Counterparty. Если по ключу
     подходит больше одного контрагента — строка уходит в отчёт "неоднозначно"
     без изменений. Если совпадений вообще нет — в отчёт "не найдено", тоже
     без изменений. Никакого нечёткого (fuzzy) сопоставления нет — риск
     перепутать контрагентов в финансовых данных того не стоит; такие строки
     остаются на ручной разбор.

  2. Выгрузка неактивных контрагентов: для каждого Counterparty, у которого
     есть хотя бы одна операция со статусом ОПЛАЧЕНО и дата последней такой
     операции раньше 01.01.2025, и который ещё не представлен в Contracts
     (по ИНН/названию после шага 1) — добавляется новая строка Contract с
     заполненными только counterparty_name и inn (остальные поля пустые) и
     служебной отметкой в note с датой последней оплаты. Контрагенты без
     единой операции ОПЛАЧЕНО не считаются — нет даты, с которой сравнивать.

Запуск:
    docker exec finance_backend python -m app.sync_contracts            # dry-run, только отчёт
    docker exec finance_backend python -m app.sync_contracts --apply    # применить изменения

sync_contracts.bat сам гоняет dry-run, спрашивает подтверждение, делает
pg_dump и только потом запускает --apply (см. CLAUDE.md про бэкап перед
любым деструктивным изменением).
"""
import sys
from datetime import date

from sqlalchemy import func

from app.database import SessionLocal
from app.models import Contract, Counterparty, Operation

CUTOFF = date(2025, 1, 1)


def normalize_inn(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.endswith(".0"):
        head = s[:-2]
        if head.isdigit():
            s = head
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits or None


def normalize_name(raw):
    if raw is None:
        return None
    s = raw.strip().lower()
    for ch in ('«', '»', '"', "'", '“', '”', '`'):
        s = s.replace(ch, '')
    s = " ".join(s.split())
    return s or None


def build_indexes(counterparties):
    by_inn = {}
    by_name = {}
    for cp in counterparties:
        inn_n = normalize_inn(cp.inn)
        if inn_n:
            by_inn.setdefault(inn_n, []).append(cp)
        name_n = normalize_name(cp.name)
        if name_n:
            by_name.setdefault(name_n, []).append(cp)
    return by_inn, by_name


def standardize_contracts(db):
    counterparties = db.query(Counterparty).all()
    by_inn, by_name = build_indexes(counterparties)
    contracts = db.query(Contract).all()

    changed_rows = []
    ambiguous_rows = []
    not_found_rows = []
    matched_unchanged = 0

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
        new_inn = match.inn or c.inn
        if c.counterparty_name == match.name and c.inn == new_inn:
            matched_unchanged += 1
            continue
        c.counterparty_name = match.name
        c.inn = new_inn
        changed_rows.append((c.id, old_name, old_inn, match.name, new_inn, via))

    return {
        "changed": changed_rows,
        "ambiguous": ambiguous_rows,
        "not_found": not_found_rows,
        "matched_unchanged": matched_unchanged,
    }


def find_dormant_counterparties(db):
    last_op = (
        db.query(
            Operation.counterparty_id.label("cid"),
            func.max(Operation.date).label("last_date"),
        )
        .filter(Operation.counterparty_id.isnot(None), Operation.status == "ОПЛАЧЕНО")
        .group_by(Operation.counterparty_id)
        .subquery()
    )
    rows = (
        db.query(Counterparty, last_op.c.last_date)
        .join(last_op, Counterparty.id == last_op.c.cid)
        .filter(last_op.c.last_date < CUTOFF)
        .order_by(last_op.c.last_date)
        .all()
    )
    return rows


def export_dormant(db, dormant_rows):
    existing = db.query(Contract).all()
    existing_inns = {normalize_inn(c.inn) for c in existing if normalize_inn(c.inn)}
    existing_names = {normalize_name(c.counterparty_name) for c in existing if normalize_name(c.counterparty_name)}

    added_rows = []
    skipped_rows = []

    for cp, last_date in dormant_rows:
        inn_n = normalize_inn(cp.inn)
        name_n = normalize_name(cp.name)
        if (inn_n and inn_n in existing_inns) or (name_n and name_n in existing_names):
            skipped_rows.append((cp.id, cp.name, cp.inn, last_date))
            continue
        note = (
            f"Без операций со статусом ОПЛАЧЕНО с {last_date.strftime('%d.%m.%Y')}"
            " — выгружено автоматически (неактивен на 01.01.2025)"
        )
        if cp.status == "виртуальный":
            note += "; внимание: контрагент помечен как виртуальный"
        db.add(Contract(counterparty_name=cp.name, inn=cp.inn, note=note))
        if inn_n:
            existing_inns.add(inn_n)
        if name_n:
            existing_names.add(name_n)
        added_rows.append((cp.id, cp.name, cp.inn, last_date, cp.status))

    return added_rows, skipped_rows


def print_report(std_result, added_rows, skipped_rows, apply_mode):
    print("=" * 78)
    print("ШАГ 1. Стандартизация существующих строк Contract по базе контрагентов")
    print("=" * 78)
    print(f"Изменено строк: {len(std_result['changed'])}")
    for cid, old_name, old_inn, new_name, new_inn, via in std_result["changed"]:
        print(f"  #{cid}: \"{old_name}\" / ИНН {old_inn}  ->  \"{new_name}\" / ИНН {new_inn}  (совпадение по {via})")
    print(f"Совпало, без изменений: {std_result['matched_unchanged']}")
    print(f"Неоднозначно (>1 кандидата, не трогали): {len(std_result['ambiguous'])}")
    for cid, name, inn, via, n in std_result["ambiguous"]:
        print(f"  #{cid}: \"{name}\" / ИНН {inn} — {n} кандидатов по {via}")
    print(f"Не найдено в справочнике контрагентов (не трогали): {len(std_result['not_found'])}")
    for cid, name, inn in std_result["not_found"]:
        print(f"  #{cid}: \"{name}\" / ИНН {inn}")

    print()
    print("=" * 78)
    print("ШАГ 2. Выгрузка контрагентов без операций ОПЛАЧЕНО с 01.01.2025")
    print("=" * 78)
    print(f"Новых строк в Contracts: {len(added_rows)}")
    for cid, name, inn, last_date, status in added_rows:
        flag = "  [виртуальный]" if status == "виртуальный" else ""
        print(f"  + \"{name}\" / ИНН {inn} — последняя оплата {last_date.strftime('%d.%m.%Y')}{flag}")
    print(f"Уже представлены в Contracts (пропущено): {len(skipped_rows)}")
    for cid, name, inn, last_date in skipped_rows:
        print(f"  = \"{name}\" / ИНН {inn} — последняя оплата {last_date.strftime('%d.%m.%Y')}")

    print()
    print("=" * 78)
    if apply_mode:
        print("Изменения ЗАПИСАНЫ в базу.")
    else:
        print("DRY RUN — изменения НЕ записаны. Запустите с --apply, чтобы применить.")
    print("=" * 78)


def main():
    apply_mode = "--apply" in sys.argv
    db = SessionLocal()
    try:
        std_result = standardize_contracts(db)
        dormant_rows = find_dormant_counterparties(db)
        db.flush()
        added_rows, skipped_rows = export_dormant(db, dormant_rows)

        print_report(std_result, added_rows, skipped_rows, apply_mode)

        if apply_mode:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
