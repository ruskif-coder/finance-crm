# -*- coding: utf-8 -*-
"""Частота дня отчёта клиенту — от частоты медиаплана, для дней, УЖЕ зафиксированных (17.11.2026).

Зачем. До 17.11 частота дня пары «площадка × креатив» (`report_daily_coef.freq`) выбиралась от базы настроек SIMB ID
(4,0 ± 30 %) и МП не смотрела: у Ибуклина QZ9VNS в МП «до 3х», а в отчёте по неделям 4,4. Новые дни теперь фиксируются от
частоты МП (`report_coef.day_base`); этот скрипт один раз переписывает лежащие дни той же формулой, сохраняя случайную поправку
каждого дня: новая = старая ÷ 4,0 × частота МП × FLIGHT_SHARE. База 4,0 — единственная, что была (журнал: настройки SIMB ID
правились 05.10 и 07.10, частота оба раза 4,0 ± 30 %), поэтому старое число дня делится на неё точно.

Только РК, у сделки которых в последнем МП есть частота. Какие дни старые — по метке `computed_at`: зафиксированные ДО
выкладки нового кода (`--before`, момент выкладки). Переписанный день получает `computed_at = now()`, поэтому повторный запуск
его не трогает, а дни, зафиксированные после выкладки (уже от МП), не трогаются вовсе. Страховка — только дни в диапазоне
старой базы 2,80…5,20. Перед записью — копия строк в `/app/logs/report_coef_before_mp_<дата>.csv`.

    docker exec finance_backend python -m scripts.2026-11-17_report_coef_freq_from_mp --before="2026-11-17 19:00"          # сухо
    docker exec finance_backend python -m scripts.2026-11-17_report_coef_freq_from_mp --before="2026-11-17 19:00" --apply
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

OLD_BASE, OLD_LO, OLD_HI = 4.0, 2.80, 5.20
LOG_DIR = os.environ.get("LOG_DIR") or "/app/logs"


def main(apply: bool, before: str) -> None:
    db = SessionLocal()
    rows = db.execute(text("""
        SELECT k.id, k.creative_id, k.date, k.freq, c.id AS camp, d.id AS deal, d.code
          FROM report_daily_coef k
          JOIN ad_campaign_creative cr ON cr.id = k.creative_id
          JOIN ad_campaign c ON c.id = cr.campaign_id
          JOIN sales_deals d ON d.id = c.deal_id
         WHERE k.computed_at < CAST(:b AS timestamp)"""), {"b": before}).mappings().all()
    freq_of, todo = {}, []
    for r in rows:
        if r["deal"] not in freq_of:
            freq_of[r["deal"]] = deal_plan(db, r["deal"])["freq"]
        f = freq_of[r["deal"]]
        if not f:
            continue
        old = float(r["freq"])
        if not OLD_LO <= old <= OLD_HI:
            continue                                   # не от старой базы — не наш случай
        todo.append((r, round(max(0.01, old / OLD_BASE * f * FLIGHT_SHARE), 2)))
    by_code = {}
    for r, new in todo:
        a = by_code.setdefault(r["code"], [0, 0.0, 0.0, freq_of[r["deal"]]])
        a[0] += 1
        a[1] += float(r["freq"])
        a[2] += new
    for code, (n, o, nw, f) in sorted(by_code.items()):
        print(f"{code}: частота МП {f:g} · дней {n} · средняя частота дня {o / n:.2f} → {nw / n:.2f}")
    print(f"итого дней к переписи: {len(todo)}")
    if not apply or not todo:
        db.rollback()
        print("сухой прогон — ничего не записано" if not apply else "переписывать нечего")
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    path = os.path.join(LOG_DIR, f"report_coef_before_mp_{date.today():%Y-%m-%d}.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "creative_id", "date", "freq"])
        for r, _ in todo:
            w.writerow([r["id"], r["creative_id"], r["date"], r["freq"]])
    db.execute(text("""UPDATE report_daily_coef SET freq = :f, computed_at = now()
                         WHERE id = :i AND computed_at < CAST(:b AS timestamp)"""),
               [{"f": new, "i": r["id"], "b": before} for r, new in todo])
    db.commit()
    print(f"записано; копия прежних чисел — {path}")


if __name__ == "__main__":
    arg = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--before=")), None)
    if not arg:
        sys.exit("нужен --before=\"ГГГГ-ММ-ДД ЧЧ:ММ\" — момент выкладки кода, считающего частоту дня от МП")
    main("--apply" in sys.argv, arg)
