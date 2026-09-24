# -*- coding: utf-8 -*-
"""Суточный съём статистики Weborama. Ставится в cron рядом с досылкой уведомлений.

    docker exec finance_backend python -m app.weborama.daily --dry-run
    docker exec finance_backend python -m app.weborama.daily
    docker exec finance_backend python -m app.weborama.daily --from 2026-08-01 --to 2026-09-12

Раз в сутки — решение владельца 10.09.2026: тем же темпом обновляется дашборд, и
сравнивать наш счётчик с верификатором надо в этом же ритме.

ОКНО ШИРЕ ОДНОГО ДНЯ НАМЕРЕННО. Weborama дозаливает данные задним числом, поэтому каждый
прогон перезабирает последние трое суток, а не только вчерашние. Оба шага записи —
апсерты, поэтому перезабор ничего не удваивает.

ПРОГОН, КОТОРЫЙ НИЧЕГО НЕ ПРИЦЕПИЛ, — НЕ УСПЕХ. Пока реестр `weborama_refs` пуст,
сырьё ложится, а на дашборд не попадает ни одно число: соответствия «их вставка → наша
площадка» берутся только из реестра, а он заполняется, когда вставку заводим МЫ. Поэтому
итог прогона печатается с числом неприцепленных показов, а не словом «готово».
"""
import argparse
import sys
from datetime import date, datetime

from app.database import SessionLocal
from app.weborama import stats as S
from app.weborama import store
from app.weborama.client import WcmClient, WcmError



def _day(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _account(db) -> str:
    """Аккаунт — ТОТ ЖЕ, в котором заводятся вставки: настройка `weborama_account_id`.

    До 23.09.2026 съём брал его из переменной `WEBORAMA_DEMO_ACCOUNT_ID`, а заведение —
    из настройки. Разойдись они, съём шёл в чужой аккаунт и честно докладывал «легло 0»;
    пустая переменная роняла крон (аудит, 4.M6). Место у аккаунта одно.
    """
    from app.weborama import provision

    return provision.account_id(db)


def run(account_id=None, *, start=None, end=None, dry_run: bool = False) -> dict:
    from app.dsp.db import DspSessionLocal

    if not account_id:
        probe = SessionLocal()
        try:
            account_id = _account(probe)
        finally:
            probe.close()
    if DspSessionLocal is None:
        raise RuntimeError("DSP_DATABASE_URL не задан — сырьё складывать некуда")

    if start is None or end is None:
        start, end = S.window()

    client = WcmClient(account_id)
    db, dsp_db = SessionLocal(), DspSessionLocal()
    try:
        if dry_run:
            pull = S.pull(client, start, end)
            out = {"start": start.isoformat(), "end": end.isoformat(),
                   "rows": len(pull.rows), "impressions": pull.impressions,
                   "their_total": pull.grand_total, "discrepancy": pull.discrepancy,
                   "absent_metrics": list(pull.absent_metrics), "ok": pull.ok(),
                   "dry_run": True}
        else:
            out = store.sync(db, dsp_db, client, account_id, start=start, end=end)
        return out
    finally:
        db.close(); dsp_db.close()


def _report(out: dict) -> str:
    def n(v):
        return f"{v:,}".replace(",", " ")

    parts = [f"Weborama {out['start']}..{out['end']}: строк {out['rows']}, "
             f"показов {n(out['impressions'])}"]
    if out.get("discrepancy"):
        parts.append(f"РАСХОЖДЕНИЕ с их итогом {out['discrepancy']:+}")
    if out.get("absent_metrics"):
        parts.append("НЕ ПРИШЛИ метрики: " + ", ".join(out["absent_metrics"]))
    if out.get("dry_run"):
        parts.append("СУХОЙ ПРОГОН, ничего не записано")
    else:
        parts.append(f"на дашборд легло {out['written']}, "
                     f"без соответствия {out['skipped']} "
                     f"({n(out['unmatched_impressions'])} показов)")
        if not out.get("mapped_insertions"):
            parts.append("реестр соответствий ПУСТ — ни одно число на дашборд не попало")
    return "; ".join(parts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Суточный съём статистики Weborama")
    ap.add_argument("--dry-run", action="store_true", help="снять и сверить, не записывая")
    ap.add_argument("--from", dest="since", type=_day, help="начало отрезка YYYY-MM-DD")
    ap.add_argument("--to", dest="until", type=_day, help="конец отрезка YYYY-MM-DD")
    a = ap.parse_args()
    try:
        print(_report(run(start=a.since, end=a.until, dry_run=a.dry_run)))
    except (WcmError, RuntimeError) as e:
        print(f"Съём Weborama не состоялся: {e}", file=sys.stderr)
        sys.exit(1)
