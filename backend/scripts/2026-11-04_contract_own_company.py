# -*- coding: utf-8 -*-
"""Наше юрлицо у договоров, где оно пустое (владелец 04.11.2026).

Договоры, заведённые через реестр и «Добавить данные», создавались без `own_company_id` — поля в форме нет, а
создание его не ставило (с 04.11.2026 ставит, `routers/contracts.py`). Документы при этом печатались с юрлицом (брали
единственное наше), а мост мастер-сделки в операции — нет. Ставим то же единственное наше юрлицо, что подставляли
документы (`own_company.sole`). Наших юрлиц не ровно одно — отказ: угадывать нельзя.

Сухой прогон по умолчанию, запись — `--apply`:
    docker exec finance_backend python -m scripts.2026-11-04_contract_own_company [--apply]
"""
import argparse

import app.model_registry  # noqa: F401
from app import own_company
from app.audit import log_action
from app.database import SessionLocal
from app.models import Contract


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    db = SessionLocal()
    try:
        ours = own_company.sole(db)
        if ours is None:
            print("Отказ: наших юрлиц не ровно одно — какое ставить, не решить без владельца")
            return 1
        rows = db.query(Contract).filter(Contract.own_company_id.is_(None)).order_by(Contract.id).all()
        print(f"Договоров без нашего юрлица: {len(rows)}; ставим id {ours.id}")
        for c in rows:
            print(f"  договор {c.id} № {c.contract_number or '—'} от {c.contract_date or '—'}")
        if not a.apply:
            print("Сухой прогон — ничего не записано. Запись: --apply")
            db.rollback()
            return 0
        for c in rows:
            c.own_company_id = ours.id
        db.flush()
        if rows:
            log_action(db, None, "contracts_own_company_backfill", "contract", None,
                       f"наше юрлицо проставлено у {len(rows)} договоров: {', '.join(str(c.id) for c in rows)}")
        db.commit()
        print(f"Записано: {len(rows)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
