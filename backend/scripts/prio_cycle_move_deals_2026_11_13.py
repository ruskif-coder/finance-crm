# -*- coding: utf-8 -*-
"""Разово: сделки приоритезации, ещё не дошедшие до итоговой сверки, — на воронку «Приоритезация» (свой цикл, 13.11.2026).

Старые сделки услуги (до модуля приоритезации) шли полным циклом через Pharm и уже на закрывающих — их не трогаем. Тем, кто уже на
«Готовятся к старту» и дальше, сразу заводится РК (носитель факта из статистики сервиса) — иначе до ночного прогона факту некуда лечь.

    docker exec finance_backend python -m scripts.prio_cycle_move_deals_2026_11_13            # показать
    docker exec finance_backend python -m scripts.prio_cycle_move_deals_2026_11_13 --apply    # записать
"""
import sys

from sqlalchemy import text

import app.model_registry  # noqa: F401 — все таблицы для внешних ключей
from app.ad import build
from app.database import SessionLocal
from app.final_recon import flow
from app.sales.catalog import Catalog
from app.sales.models import SalesDeal

BEFORE_RECON = ("МП Подготовка", "МП Отправлено", "Бронь", "Готовятся к старту", "В размещении")


def main(apply: bool) -> int:
    db = SessionLocal()
    try:
        pid = db.execute(text("SELECT id FROM sales_pipelines WHERE name = 'Приоритезация'")).scalar()
        if pid is None:
            print("нет воронки «Приоритезация» — сначала миграция 2026-11-13_prio_cycle.sql")
            return 1
        cat = Catalog(db)
        deals = db.execute(text("""
            SELECT d.id FROM sales_deals d JOIN sales_services s ON s.id = d.service_id JOIN sales_stages st ON st.id = d.our_stage_id
             WHERE s.name = 'Приоритезация' AND st.name = ANY(:st) ORDER BY d.id"""), {"st": list(BEFORE_RECON)}).scalars().all()
        for did in deals:
            d = db.get(SalesDeal, did)
            was = flow.of_deal(db, d)
            d.realization_pipeline_id = pid
            db.flush()
            flow.reset(db)
            stage = cat.by_id.get(d.our_stage_id)
            rk = None
            if stage is not None and stage.id in build.assembly_stage_ids(db):
                rk = build.ensure_campaign_on_move(db, d, stage)
            print(f"{d.code} «{stage.name if stage else '—'}»: {was} → {flow.of_deal(db, d)}"
                  + (f"; РК: {rk}" if rk else ""))
        print(f"итого сделок: {len(deals)}" + ("" if apply else " (без --apply ничего не записано)"))
        db.commit() if apply else db.rollback()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
