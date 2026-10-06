# -*- coding: utf-8 -*-
"""Журнал ночных прогонов биддера (владелец 05.10.2026; таблицы — миграция
2026-10-05_bidder_run.sql, без ORM-моделей: пишет и читает только этот модуль).

Пишет `app/ad/daily_shares` своей сессией: строка прогона заводится ДО расчёта и
закрывается после, поэтому оборванный прогон виден пустым `finished_at`, а не пропадает.
Пробный прогон (`--dry-run`) в журнал не пишется.
"""
import json
from typing import Optional

from sqlalchemy import text

from app.database import SessionLocal


def start() -> int:
    db = SessionLocal()
    try:
        rid = db.execute(text("INSERT INTO bidder_run DEFAULT VALUES RETURNING id")).scalar()
        db.commit()
        return rid
    finally:
        db.close()


def finish(run_id: int, shares: dict, limits: list, failed: int,
           fact_as_of=None, errors: Optional[list] = None, checks: Optional[list] = None) -> None:
    changes = shares.get("changes") or []
    db = SessionLocal()
    try:
        db.execute(text("""
            UPDATE bidder_run SET finished_at = now(), by_fact = :bf, fact_as_of = :fa,
                   campaigns = :c, plans_changed = :pc, limits_updated = :lu,
                   limits_failed = :lf, errors = CAST(:e AS jsonb),
                   checks = CAST(:ck AS jsonb)
             WHERE id = :id"""), {
            "id": run_id, "bf": shares.get("by_fact"), "fa": fact_as_of,
            "c": shares.get("campaigns"), "pc": len(changes),
            "lu": sum(x.get("updated", 0) for x in limits), "lf": failed,
            "e": json.dumps(errors or [], ensure_ascii=False, default=str),
            "ck": json.dumps(checks or [], ensure_ascii=False, default=str)})
        if changes:
            db.execute(text("""
                INSERT INTO bidder_run_change
                       (run_id, campaign_id, placement_id, plan_before, plan_after, reason)
                VALUES (:r, :campaign_id, :placement_id, :plan_before, :plan_after, :reason)"""),
                [{"r": run_id, **c} for c in changes])
        db.commit()
    finally:
        db.close()


RUNNING_FOR = "1 hour"   # незакрытый прогон моложе часа — «идёт», старше — «оборвался»


def runs(db, limit: int = 60, run_id: Optional[int] = None) -> list:
    """Прогоны, новые сверху. Время — по Москве строкой (база пишет UTC, а экран и крон
    говорят в МСК — как журнал действий), `state` — идёт / оборвался / ок / с ошибками."""
    rows = db.execute(text(f"""
        SELECT id, by_fact, fact_as_of, campaigns, plans_changed, limits_updated,
               limits_failed, errors, checks,
               (started_at + interval '3 hours')::date AS run_day_msk,
               to_char(started_at + interval '3 hours', 'YYYY-MM-DD HH24:MI') AS started_msk,
               CASE WHEN finished_at IS NOT NULL THEN
                        CASE WHEN coalesce(limits_failed, 0) > 0
                               OR jsonb_path_exists(coalesce(checks, '[]'), '$[*] ? (@.level == "error")')
                               THEN 'ошибки'
                             WHEN jsonb_path_exists(coalesce(checks, '[]'), '$[*] ? (@.level == "warning")')
                               THEN 'предупреждения'
                             ELSE 'ок' END
                    WHEN started_at > (now() AT TIME ZONE 'UTC') - interval '{RUNNING_FOR}' THEN 'идёт'
                    ELSE 'оборвался' END AS state
          FROM bidder_run WHERE (CAST(:id AS integer) IS NULL OR id = :id)
         ORDER BY id DESC LIMIT :n"""), {"n": limit, "id": run_id}).mappings().all()
    return [dict(r) for r in rows]


def changes_of(db, run_id: int) -> list:
    rows = db.execute(text("""
        SELECT ch.campaign_id, d.code, ch.placement_id, coalesce(sp.domain, sp.name) AS site,
               ch.plan_before, ch.plan_after, ch.reason
          FROM bidder_run_change ch
          JOIN ad_campaign c ON c.id = ch.campaign_id
          JOIN sales_deals d ON d.id = c.deal_id
          LEFT JOIN ad_campaign_placement p ON p.id = ch.placement_id
          LEFT JOIN sales_publishers sp ON sp.id = p.publisher_id
         WHERE ch.run_id = :r ORDER BY d.code, site"""), {"r": run_id}).mappings().all()
    return [dict(r) for r in rows]


def last_state(db) -> Optional[str]:
    """Состояние последнего ЗАКРЫТОГО прогона — для тревоги на переходе."""
    r = runs(db, limit=50)
    done = [x for x in r if x["state"] not in ("идёт", "оборвался")]
    return done[0]["state"] if done else None


def run(db, run_id: int) -> Optional[dict]:
    """Один прогон по номеру (ревью 06.10.2026: поиск в 500 последних давал 404 старым)."""
    r = runs(db, limit=1, run_id=run_id)
    return r[0] if r else None
