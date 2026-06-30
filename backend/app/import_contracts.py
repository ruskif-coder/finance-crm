"""
Единоразовый импорт «Реестр договоров.xlsx» в таблицу contracts.

Запуск (после того как файл скопирован в контейнер, см. CLAUDE.md):
    docker exec finance_backend python -m app.import_contracts

Источник: F:\\finance\\contracts_import.xlsx (исходно "Реестр договоров.xlsx",
переименован в ASCII-имя — .bat-скрипты в этом проекте должны оставаться чистым
ASCII, см. CLAUDE.md). 85 строк, лист "Лист1".
Сопоставление колонок — см. комментарии в Contract (app/models.py).
Договоры хранятся как плоский справочник без FK на Counterparty — ИНН и
название контрагента — обычный текст (осознанное решение, см. CLAUDE.md).

Идемпотентность: если в таблице contracts уже есть строки, импорт пропускается,
чтобы повторный запуск не создавал дублей.
"""
import datetime
import openpyxl
import pandas as pd
from app.database import SessionLocal
from app.models import Contract

SOURCE_PATH = "/app/contracts_import.xlsx"
SHEET_NAME = "Лист1"


def clean_text(x):
    """Строка -> схлопнуть пробелы/переводы строк; число -> str(); пусто -> None."""
    if x is None:
        return None
    if isinstance(x, str):
        s = " ".join(x.split())
        return s or None
    return str(x).strip() or None


def parse_contract_date(raw):
    """Возвращает (date|None, заметка|None). Заметка уходит в Contract.note,
    если в файле дата указана, но не распознаётся (опечатки вроде '10.09.1015')."""
    if raw is None:
        return None, None
    if isinstance(raw, datetime.datetime):
        return raw.date(), None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None, None
        try:
            parsed = pd.to_datetime(s, dayfirst=True)
            return parsed.date(), None
        except Exception:
            return None, f"Дата договора в исходном файле не распознана: {s}"
    return None, None


def format_end_date(raw):
    """ДАТА ОКОНЧАНИЯ ДОГОВОРА хранится как текст (формат в файле непостоянный)."""
    if raw is None:
        return None
    if isinstance(raw, datetime.datetime):
        return raw.strftime("%d.%m.%Y")
    return clean_text(raw)


def main():
    db = SessionLocal()
    existing = db.query(Contract).count()
    if existing:
        print(f"В таблице contracts уже есть {existing} строк(и) — импорт отменён во избежание дублей.")
        db.close()
        return

    wb = openpyxl.load_workbook(SOURCE_PATH, data_only=True)
    ws = wb[SHEET_NAME]
    rows = list(ws.iter_rows(values_only=True))[1:]  # пропускаем строку заголовков

    created = 0
    skipped = 0
    for row in rows:
        # Пустая строка — нет ни номера договора, ни ИНН, ни названия контрагента
        if row[1] is None and row[4] is None and row[5] is None:
            skipped += 1
            continue

        contract_date, date_note = parse_contract_date(row[3])

        contract = Contract(
            contract_number=clean_text(row[1]),
            contract_date=contract_date,
            inn=clean_text(row[4]),
            counterparty_name=clean_text(row[5]),
            marketing_name=clean_text(row[6]),
            cooperation_format=clean_text(row[7]),
            services=clean_text(row[8]),
            end_date_text=format_end_date(row[9]),
            prolongation=clean_text(row[10]),
            payment_form=clean_text(row[11]),
            payment_term=clean_text(row[12]),
            note=date_note,
        )
        db.add(contract)
        created += 1

    db.commit()
    db.close()
    print(f"Импортировано договоров: {created} (пропущено пустых строк: {skipped})")


if __name__ == "__main__":
    main()
