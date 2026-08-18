# -*- coding: utf-8 -*-
"""CLI-обёртка над модулем app.sales.bitrix.deal_import.
Запуск: python import_new_deals.py [commit]  (без 'commit' — dry-run).
Логика/правила — в модуле, здесь только запуск и вывод отчёта."""
import sys
from app.database import SessionLocal
import app.models  # noqa: F401 — регистрирует counterparties для резолва FK в standalone-процессе
from app.sales.bitrix.deal_import import import_new_deals

if __name__ == "__main__":
    commit = "commit" in sys.argv
    db = SessionLocal()
    try:
        rep = import_new_deals(db, commit=commit)
    finally:
        db.close()
    print("anchor=%(anchor_bitrix_id)s fetched=%(fetched)s to_insert=%(to_insert)s "
          "skip_untracked=%(skipped_untracked)s skip_existing=%(skipped_existing)s "
          "inserted=%(inserted)s" % rep)
    if not commit:
        print("DRY-RUN — ничего не записано (запусти с 'commit' для записи)")
