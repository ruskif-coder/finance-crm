# -*- coding: utf-8 -*-
"""Открепить псевдоагентство «НЕТ» (владелец 28.10.2026: «да»): сделки с агентством «НЕТ» → без агентства, связки «НЕТ ↔ юрлицо»
снять. Для системы «НЕТ» — обычное агентство, и прямые сделки делились на два вида («без агентства» и «агентство НЕТ»): правила СК по
умолчанию заводились на оба, и у договора выходило два правила на одно условие. Запускать ДО `2026-10-27_agency_terms_defaults`.
Само агентство «НЕТ» не удаляется (на него могут ссылаться правила и история) — только перестаёт быть чьим-то агентством.

    docker exec finance_backend python -m scripts.2026-10-28_detach_pseudo_agency            # пробно: что изменится
    docker exec finance_backend python -m scripts.2026-10-28_detach_pseudo_agency --apply    # записать (с журналом действий)
"""
import argparse

import app.model_registry  # noqa: F401
from sqlalchemy import text

from app.audit import log_action
from app.database import SessionLocal

NAME = "НЕТ"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    db = SessionLocal()
    try:
        ag = db.execute(text("SELECT id FROM sales_agencies WHERE btrim(name) = :n"), {"n": NAME}).scalars().all()
        if len(ag) != 1:
            print(f"агентств «{NAME}» найдено {len(ag)} — ожидалось ровно одно, ничего не делаю")
            return
        aid = ag[0]
        deals = db.execute(text("SELECT id, code FROM sales_deals WHERE agency_id = :a ORDER BY id"), {"a": aid}).all()
        links = db.execute(text("SELECT ac.id, c.name FROM sales_agency_counterparties ac JOIN counterparties c ON c.id = ac.counterparty_id "
                                "WHERE ac.agency_id = :a ORDER BY ac.id"), {"a": aid}).all()
        rules = db.execute(text("SELECT count(*) FROM sk_rules WHERE agency_id = :a"), {"a": aid}).scalar()
        print(f"агентство «{NAME}» id={aid}: сделок {len(deals)}, связок с юрлицами {len(links)}, правил СК на нём {rules}")
        print("  сделки:", ", ".join(c for _, c in deals) or "—")
        print("  юрлица:", ", ".join(n for _, n in links) or "—")
        if not a.apply:
            print("пробный прогон — ничего не записано; запись — с --apply")
            return
        db.execute(text("UPDATE sales_deals SET agency_id = NULL WHERE agency_id = :a"), {"a": aid})
        db.execute(text("DELETE FROM sales_agency_counterparties WHERE agency_id = :a"), {"a": aid})
        db.commit()
        log_action(db, None, "detach_pseudo_agency", "agency", aid,
                   f"«{NAME}»: сделок без агентства {len(deals)} ({', '.join(c for _, c in deals)}); снято связок с юрлицами {len(links)}")
        left = db.execute(text("SELECT (SELECT count(*) FROM sales_deals WHERE agency_id = :a) + "
                               "(SELECT count(*) FROM sales_agency_counterparties WHERE agency_id = :a)"), {"a": aid}).scalar()
        print(f"записано; осталось привязок к «{NAME}»: {left}. Правила СК на «{NAME}» ({rules}) не трогал — сделкам они больше не подходят")
    finally:
        db.close()


if __name__ == "__main__":
    main()
