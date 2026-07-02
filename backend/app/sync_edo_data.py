"""
sync_edo_data.py
================
Synchronizes KPP and EDO identifier from an EDO export CSV into the counterparties table.

Rules:
  - Matches DB counterparties to CSV rows by INN (exact match).
  - Updates kpp if DB value is NULL/empty and CSV has a non-empty value.
  - Updates edo_id with the most recent EDO identifier from CSV (by status-change date).
  - Does NOT create new counterparties.
  - Safe to re-run (idempotent).

Usage (inside container):
  docker exec finance_backend python /app/app/sync_edo_data.py /app/app/counteragents.csv

CSV must be UTF-8 with BOM or plain UTF-8, semicolon-separated.
"""

import sys
import csv
import os
import io
from datetime import datetime

# ---- load env so SQLAlchemy can connect ----
sys.path.insert(0, "/app")
os.environ.setdefault("POSTGRES_SERVER", "db")
os.environ.setdefault("POSTGRES_USER", "finance_user")
os.environ.setdefault("POSTGRES_DB", "finance")

from app.database import SessionLocal
from app.models import Counterparty
from sqlalchemy.orm import Session

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "/app/app/counteragents.csv"


def parse_date(s: str):
    """Parse 'DD.MM.YYYY HH:MM:SS' or return epoch for sorting."""
    try:
        return datetime.strptime(s.strip(), "%d.%m.%Y %H:%M:%S")
    except Exception:
        return datetime.min


def load_csv(path: str) -> dict:
    """
    Returns dict: inn -> {kpp, edo_id, name, date}
    When the same INN appears multiple times, keeps the entry with the LATEST status date.
    """
    records = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            inn = (row.get("ИНН") or "").strip()
            if not inn:
                continue
            kpp      = (row.get("КПП") or "").strip()
            edo_id   = (row.get("Идентификатор участника ЭДО") or "").strip()
            name     = (row.get("Название организации") or "").strip()
            date_str = (row.get("Дата изменения статуса") or "").strip()
            dt = parse_date(date_str)

            existing = records.get(inn)
            if existing is None or dt > existing["date"]:
                records[inn] = {"kpp": kpp, "edo_id": edo_id, "name": name, "date": dt}
    return records


def main():
    print(f"\n=== sync_edo_data.py ===")
    print(f"CSV: {CSV_PATH}\n")

    csv_by_inn = load_csv(CSV_PATH)
    print(f"CSV: {len(csv_by_inn)} unique INNs loaded\n")

    db: Session = SessionLocal()
    try:
        counterparties = db.query(Counterparty).filter(
            Counterparty.inn.isnot(None),
            Counterparty.inn != ""
        ).all()
        print(f"DB: {len(counterparties)} counterparties with non-empty INN\n")

        updated_kpp   = 0
        updated_edo   = 0
        not_in_csv    = []

        for cp in counterparties:
            inn = (cp.inn or "").strip()
            csv_row = csv_by_inn.get(inn)

            if csv_row is None:
                not_in_csv.append(f"  {cp.name} (ИНН {inn})")
                continue

            changed = False

            # Update KPP only if DB value is empty
            if not (cp.kpp or "").strip() and csv_row["kpp"]:
                print(f"  [KPP]    {cp.name}: '' -> '{csv_row['kpp']}'")
                cp.kpp = csv_row["kpp"]
                updated_kpp += 1
                changed = True

            # Update EDO id (always sync to most-recent from CSV)
            if csv_row["edo_id"] and (cp.edo_id or "").strip() != csv_row["edo_id"]:
                print(f"  [EDO]    {cp.name}: '{cp.edo_id or ''}' -> '{csv_row['edo_id']}'")
                cp.edo_id = csv_row["edo_id"]
                updated_edo += 1
                changed = True

        db.commit()

        print(f"\n--- Results ---")
        print(f"  KPP updated  : {updated_kpp}")
        print(f"  EDO updated  : {updated_edo}")
        print(f"  Not in CSV   : {len(not_in_csv)}")

        if not_in_csv:
            print("\nCounterparties in DB but NOT found in CSV:")
            for line in not_in_csv:
                print(line)

        print("\nDone.")
    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
