# -*- coding: utf-8 -*-
"""Проверки перехода стадий для цикла «приоритезация» (13.11.2026). Регистрируются в общем реестре `sales/stage_checks` —
там только импорт этого модуля. Разметка (на каких стадиях, для какого цикла) — миграция 2026-11-13_prio_cycle.sql."""
from sqlalchemy import text

from app.sales.stage_checks import Ctx, Result, _not_yet, _ok, register

RUNNING = ("идёт", "остановлено")       # площадка хоть раз запущена


def _placements(c: Ctx) -> list:
    return c._once("prio_placements", lambda: c.db.execute(text("""
        SELECT pp.id, sp.name, pp.status, pp.camp_id, pp.fact_source
          FROM prio_placements pp JOIN prio_requests r ON r.id = pp.request_id
          JOIN sales_publishers sp ON sp.id = pp.publisher_id
         WHERE r.deal_id = :d ORDER BY sp.name"""), {"d": c.deal.id}).mappings().all())


@register("prio_live", "Хотя бы одна площадка запущена в приоритезации",
          "Запустите согласованную площадку в блоке «Приоритезация» — сделка перейдёт сама")
def _prio_live(c: Ctx) -> Result:
    rows = _placements(c)
    if any(r["status"] in RUNNING for r in rows):
        return _ok()
    return _not_yet("ни одна площадка не запущена" if rows else "площадок в запросе нет")


@register("prio_fact_complete", "Факт есть по всем запущенным площадкам",
          "Итоговая сверка, блок «Приоритезация»: факт из статистики сервиса или загрузите итоговый файл площадки")
def _prio_fact_complete(c: Ctx) -> Result:
    """Факт площадки — снимки статистики сервиса (`prio_stat_raw` по её camp_id) или загруженный итоговый файл (`fact_source`
    «файл» ставится только когда файл записал её дни). Незапущенные площадки факта не требуют."""
    missing = []
    for r in _placements(c):
        if r["status"] not in RUNNING:
            continue
        if r["fact_source"] == "файл":
            continue
        has = r["camp_id"] and c.db.execute(text("SELECT 1 FROM prio_stat_raw WHERE camp_id = :c LIMIT 1"),
                                            {"c": r["camp_id"]}).first()
        if not has:
            missing.append(r["name"])
    return _ok() if not missing else _not_yet(f"нет факта: {', '.join(missing)}")
