# -*- coding: utf-8 -*-
"""Откат частоты дня отчёта клиенту к значениям до 17.11.2026 (решение владельца 21.11.2026).

Зачем. 17.11 вместе с выкладкой v2.7.60 частота дня пары «площадка × креатив» стала браться из медиаплана,
и тот же прогон переписал частоту у всех уже лежавших дней (25 475 строк) — поэтому отчёты за прошлые недели,
уже отправленные клиентам, при новой выгрузке показывали другие уники и охват. Здесь обратное: дни до 17.11
получают прежнюю частоту, дни с 17.11 остаются на частоте МП.

Откуда берётся «прежняя» частота:
  1. из копии, которую сделал пересчёт 17.11 — `/app/logs/report_coef_before_mp_2026-11-18.csv` (25 475 строк);
  2. для строк, которых в копии нет (день появился уже после пересчёта, например поздно приехал факт Adfox),
     обратной формулой: было = стало / (частота МП × FLIGHT_SHARE) × 4,0 (база SIMB ID до 17.11).

Повторный запуск безопасен: сделанные id записываются в маркер `/app/logs/report_coef_reverted_ids.csv`,
и второй прогон их не трогает. Без маркера формула применилась бы к уже откаченной строке второй раз
(3,10 → 4,51 на сухом прогоне 21.11.2026 — ровно этот случай).

    docker exec finance_backend python -m scripts.2026-11-21_report_coef_revert               # сухо
    docker exec finance_backend python -m scripts.2026-11-21_report_coef_revert --apply       # запись
    docker exec finance_backend python -m scripts.2026-11-21_report_coef_revert --mark-only   # только маркер
"""
import csv
import os
import sys
from datetime import date

import app.model_registry  # noqa: F401
from sqlalchemy import text

from app.ad.build import deal_plan
from app.ad.report_coef import FLIGHT_SHARE
from app.database import SessionLocal

CUT = date(2026, 11, 17)
OLD_BASE = 4.0
SRC = "/app/logs/report_coef_before_mp_2026-11-18.csv"
LOG_DIR = os.environ.get("LOG_DIR") or "/app/logs"
MARK = os.path.join(LOG_DIR, "report_coef_reverted_ids.csv")


def load_mark() -> set:
    if not os.path.exists(MARK):
        return set()
    with open(MARK, encoding="utf-8") as fh:
        return {int(r["id"]) for r in csv.DictReader(fh)}


def main(apply: bool, mark_only: bool) -> None:
    old = {}
    if os.path.exists(SRC):
        with open(SRC, encoding="utf-8") as fh:
            old = {(int(r["creative_id"]), r["date"]): float(r["freq"]) for r in csv.DictReader(fh)}
    done = load_mark()

    db = SessionLocal()
    cur = db.execute(text("""
        SELECT k.id, k.creative_id, k.date, k.freq, d.id AS deal, d.code
          FROM report_daily_coef k
          JOIN ad_campaign_creative cr ON cr.id = k.creative_id
          JOIN ad_campaign c ON c.id = cr.campaign_id
          JOIN sales_deals d ON d.id = c.deal_id
         ORDER BY k.date, k.id""")).mappings().all()

    freq_of, todo, by_formula = {}, [], []
    for r in cur:
        if r["date"] >= CUT or r["id"] in done:
            continue
        o = old.get((r["creative_id"], r["date"].isoformat()))
        if o is not None:
            if abs(o - float(r["freq"])) > 1e-9:
                todo.append((r["id"], o, r["creative_id"], r["date"]))
            continue
        if r["deal"] not in freq_of:
            freq_of[r["deal"]] = deal_plan(db, r["deal"])["freq"]
        f = freq_of[r["deal"]]
        if not f:
            continue                      # частоты МП нет — восстановить нечем, строка остаётся как есть
        back = max(0.01, round(float(r["freq"]) / (f * FLIGHT_SHARE) * OLD_BASE, 2))
        todo.append((r["id"], back, r["creative_id"], r["date"]))
        by_formula.append((r["code"], r["date"].isoformat(), float(r["freq"]), back))

    print(f"к правке: {len(todo)} (из копии {len(todo) - len(by_formula)}, обратной формулой {len(by_formula)}); "
          f"в маркере уже {len(done)}")
    for c, d, n, b in by_formula[:5]:
        print(f"  {c} {d}: {n:.2f} -> {b:.2f}")

    if not todo:
        print("править нечего")
        return
    if not apply and not mark_only:
        db.rollback()
        print("сухой прогон — ничего не записано")
        return

    os.makedirs(LOG_DIR, exist_ok=True)
    if apply:
        path = os.path.join(LOG_DIR, f"report_coef_before_revert_{date.today():%Y-%m-%d}.csv")
        by_id = {r["id"]: r for r in cur}
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "creative_id", "date", "freq"])
            for i, _, _, _ in todo:
                r = by_id[i]
                w.writerow([r["id"], r["creative_id"], r["date"], r["freq"]])
        db.execute(text("""UPDATE report_daily_coef SET freq = :f, computed_at = now()
                             WHERE id = :i AND date < :cut"""),
                   [{"f": f, "i": i, "cut": CUT} for i, f, _, _ in todo])
        db.commit()
        print(f"записано {len(todo)} строк; копия прежних чисел — {path}")

    with open(MARK, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if not done:
            w.writerow(["id"])
        for i, _, _, _ in todo:
            w.writerow([i])
    print(f"маркер дополнен: {len(done) + len(todo)} id в {MARK}")


if __name__ == "__main__":
    main("--apply" in sys.argv, "--mark-only" in sys.argv)
