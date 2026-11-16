# -*- coding: utf-8 -*-
"""Старые версии медиаплана у сделок на терминальной стадии (владелец 15.11.2026: «храним последнюю версию»).

Сделка ушла в «Архив успешных», «не случилась» или «сорвалась» — медиаплан больше не меняется, а черновые версии копятся.
Оставляем старшую версию каждой группы (`group_id` — один МП сделки, их может быть несколько), остальные удаляем вместе со
строками и допами (каскад в базе). Версию, по строкам которой введён факт (`final_recon_fact_entries.mp_row_id`, без FK),
не трогаем: на ней стоит сверка.

Удаление живёт ТОЛЬКО здесь, а не в app/ (16.11.2026, страж `test_no_destructive_sql_anywhere_in_app`): запускается по слову
владельца, сначала сухим прогоном. Автоматического удаления при переводе в терминальную стадию нет.

Запуск:
    docker exec finance_backend python -m scripts.2026-11-15_mp_terminal_prune            # показать
    docker exec finance_backend python -m scripts.2026-11-15_mp_terminal_prune --apply    # удалить
"""
import sys

import app.model_registry  # noqa: F401 — все модели: иначе ORM не разрешит FK
from sqlalchemy import text

from app.database import SessionLocal


def prune_old_versions(db, deal_id: int) -> list:
    """Удалить все версии МП сделки, кроме старшей в каждой группе. Возвращает id удалённых. Без commit."""
    db.flush()
    ids = [i for (i,) in db.execute(text("""
        SELECT p.id FROM sales_media_plans p
         WHERE p.deal_id = :d
           AND p.version < (SELECT max(q.version) FROM sales_media_plans q
                             WHERE q.deal_id = p.deal_id AND q.group_id IS NOT DISTINCT FROM p.group_id)
           AND NOT EXISTS (SELECT 1 FROM final_recon_fact_entries f JOIN sales_media_plan_rows r ON r.id = f.mp_row_id
                            WHERE r.plan_id = p.id)
         ORDER BY p.id"""), {"d": deal_id})]
    if ids:
        db.execute(text("DELETE FROM sales_media_plans WHERE id = ANY(:i)"), {"i": ids})
    return ids


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        deals = db.execute(text("""
            SELECT d.id, d.code, s.name FROM sales_deals d JOIN sales_stages s ON s.id = d.our_stage_id
             WHERE s.is_terminal AND (SELECT count(*) FROM sales_media_plans p WHERE p.deal_id = d.id) > 1
             ORDER BY d.id""")).all()
        total = []
        for did, code, stage in deals:
            gone = prune_old_versions(db, did)
            if gone:
                print(f"{code:<8} {stage:<24} удаляются версии: {', '.join(map(str, gone))}")
                total += gone
        print(f"\nВсего версий к удалению: {len(total)}")
        if apply:
            db.commit()
            print("Готово: удалены.")
        else:
            db.rollback()
            print("СУХОЙ ПРОГОН — ничего не изменено. Для удаления: --apply")
    finally:
        db.close()


if __name__ == "__main__":
    main("--apply" in sys.argv)
