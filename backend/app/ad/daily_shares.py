# -*- coding: utf-8 -*-
"""Ночной пересчёт объёмов РК и лимитов креативов в DSP. Ставится в cron.

    docker exec finance_backend python -m app.ad.daily_shares --dry-run
    docker exec finance_backend python -m app.ad.daily_shares     (крон 02:00 UTC — после сбора статистики DSP)

Что делает (владелец 27.09.2026):
  1. веса площадок во всех незавершённых РК — из балансировщика, объёмы пересчитываются
     (`build.refresh_weights`). Заодно на шестой день флайта само переключается удержание
     долей: до этого объём делят все площадки в работе, дальше — только запущенные;
  2. лимиты заведённых в DSP креативов догоняют их долю (`dsp.limits.sync_limits`).

Без этого прогона правило «первые пять дней» сработало бы только при следующем нажатии
трафика: сохранённые планы площадок — снимок, сами по календарю не меняются.

ПРОГОН С ОТКАЗАМИ — НЕ УСПЕХ: итог печатает число креативов, чей лимит не ушёл, и
завершается с кодом 1, чтобы крон это видел.
"""
import argparse
import logging
import sys

from app.database import SessionLocal

log = logging.getLogger("finance.dsp")


def run(dry_run: bool = False, client=None, campaign_ids=None) -> dict:
    from app.ad import build
    from app.ad.models import AdCampaign

    from app.bidder import journal
    # Журнал — справка, не условие работы (ревью 05.10.2026): нет таблицы (бэкенд выложен
    # раньше миграции) — пересчёт и лимиты всё равно идут.
    run_id = None
    if not dry_run:
        try:
            run_id = journal.start()
        except Exception:  # noqa: BLE001
            log.exception("журнал биддера: прогон не заведён")
    db = SessionLocal()
    try:
        shares = build.refresh_weights(db, commit=not dry_run, campaign_ids=campaign_ids)
        if dry_run:
            db.rollback()
            return {"shares": shares, "limits": [], "failed": 0, "dry_run": True}
        q = (db.query(AdCampaign)
             .filter(AdCampaign.ms_campaign_xxhash.isnot(None),
                     (AdCampaign.status.is_(None))
                     | (~AdCampaign.status.in_(build.CAMPAIGN_CLOSED))))
        if campaign_ids is not None:
            q = q.filter(AdCampaign.id.in_(list(campaign_ids)))
        camps = q.all()
        limits = []
        if camps:
            from app.dsp.client import MsClient
            from app.dsp.limits import sync_limits
            c = client or MsClient()
            for camp in camps:
                # Сбой одной РК (не только ответ DSP — любая ошибка) не должен оставить
                # остальные РК со старыми лимитами до следующей ночи.
                try:
                    limits.append(sync_limits(db, camp, c))
                except Exception as e:  # noqa: BLE001 — отчёт прогона, дальше следующая РК
                    db.rollback()
                    log.exception("РК %s: лимиты не подтянуты", camp.id)
                    limits.append({"campaign_id": camp.id, "updated": 0, "zero": [],
                                   "failed": [{"creative_id": None, "error": str(e)}]})
        failed = sum(len(x["failed"]) for x in limits)
        from app.ad.stat_sources import fact_as_of
        if run_id is not None:
            try:
                journal.finish(run_id, shares, limits, failed,
                               fact_as_of(db) if shares.get("by_fact") else None,
                               [f for x in limits for f in x["failed"]])
            except Exception:  # noqa: BLE001
                log.exception("журнал биддера: прогон %s не закрыт", run_id)
        return {"shares": shares, "limits": limits, "failed": failed, "dry_run": False,
                "run_id": run_id}
    finally:
        db.close()


def _report(out: dict) -> str:
    s = out["shares"]
    upd = sum(x["updated"] for x in out["limits"])
    zero = sum(len(x.get("zero") or []) for x in out["limits"])
    return (f"РК пересчитано: {s['campaigns']}, весов сменилось: {s['weights_changed']}; "
            f"лимитов в DSP обновлено: {upd}, не ушло: {out['failed']}"
            + (f", креативов с нулевой долей (лимит не менялся): {zero}" if zero else "")
            + ("" if s.get("by_fact", True) else
               "; статистики DSP за вчера нет — объёмы по весам, без факта")
            + (" (пробный прогон, ничего не записано)" if out.get("dry_run") else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Ночной пересчёт объёмов РК и лимитов DSP")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    res = run(dry_run=a.dry_run)
    print(_report(res))
    sys.exit(1 if res["failed"] else 0)
