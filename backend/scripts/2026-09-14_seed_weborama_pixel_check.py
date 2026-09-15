# -*- coding: utf-8 -*-
"""Требование «пиксель Weborama получен» на входе в «В размещении».

Владелец 14.09.2026: разметку стадий под доп. параметр РК — делать; условием считается
подгрузка первой площадки, а она идёт после согласования баннера и получения ЕРИД. На
входе в «В размещении» уже стоят ровно эти три требования (`creatives_accepted`,
`placements_approved`, `erid_issued`) плюс `campaign_ready` — новое встаёт рядом.

БЕЗ ПРИВЯЗКИ К УСЛУГЕ, в отличие от разметки еФарма: условие применимости здесь —
сам доп. параметр (`{"weborama_pixel": true}`). Сделка, где пиксель не заказан, до
проверки не доходит вовсе, и значит одна строка разметки годится для всех услуг.

Запрет, а не предупреждение: выгрузка креативов в DSP к этому моменту и так отказывает
без пикселя (`dsp/provision._blocker`). Проверка делает тот же отказ видимым ЗАРАНЕЕ,
на карточке, а не в момент нажатия кнопки.

    docker exec finance_backend python -m scripts.2026-09-14_seed_weborama_pixel_check --dry-run
    docker exec finance_backend python -m scripts.2026-09-14_seed_weborama_pixel_check --commit
"""
import argparse
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import text

from app.database import SessionLocal
from app.sales.stage_checks import REGISTRY, SCOPE_KEYS

CHECK = "weborama_pixel"
STAGE = "В размещении"
SCOPE = {"weborama_pixel": True}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    write = args.commit and not args.dry_run

    db = SessionLocal()
    try:
        if CHECK not in REGISTRY:
            sys.exit(f"проверки «{CHECK}» нет в реестре — сперва код, потом разметка")
        bad = [k for k in SCOPE if k not in SCOPE_KEYS]
        if bad:
            sys.exit(f"ключей применимости нет в списке: {bad}")

        sid = db.execute(text("SELECT id FROM sales_stages WHERE name = :n"),
                         {"n": STAGE}).scalar()
        if sid is None:
            sys.exit(f"стадии «{STAGE}» нет в каталоге")

        exists = db.execute(text(
            "SELECT id FROM sales_stage_checks WHERE stage_id = :s AND check_key = :c"),
            {"s": sid, "c": CHECK}).first()
        if exists:
            print(f"уже размечено: «{STAGE}» ← {CHECK}")
        else:
            if write:
                db.execute(text("""
                    INSERT INTO sales_stage_checks (stage_id, check_key, is_blocking,
                                                    applies_when, sort_order)
                    VALUES (:s, :c, true, CAST(:w AS jsonb), 100)"""),
                    {"s": sid, "c": CHECK, "w": json.dumps(SCOPE, ensure_ascii=False)})
                db.commit()
            print(f"{'записано' if write else 'к записи'}: «{STAGE}» ← {CHECK} "
                  f"(запрет, применимо при {SCOPE})")

        rows = db.execute(text("""
            SELECT s.name, c.check_key, c.is_blocking
              FROM sales_stage_checks c JOIN sales_stages s ON s.id = c.stage_id
             WHERE s.id = :s ORDER BY c.sort_order, c.id"""), {"s": sid}).fetchall()
        print(f"\nвход в «{STAGE}» теперь требует:")
        for name, key, blocking in rows:
            print(f"  {key}{'!' if blocking else ''}")
        if not write:
            print("\nпрогон без записи — для записи добавьте --commit")
    finally:
        db.close()


if __name__ == "__main__":
    main()
