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
import app.model_registry  # noqa: F401 — крон отдельным процессом: все таблицы для внешних ключей

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
        limit_errors = [f for x in limits for f in x["failed"]]
        # Ручной прогон по части РК (`campaign_ids`) не проверяет и не тревожит по всем
        # остальным и не становится «предыдущим» для ночного (ревью 06.10.2026).
        full = _SCOPE_ALL(campaign_ids)
        checks = _checks(db, shares, limit_errors) if full else []
        prev = None
        if run_id is not None:
            try:
                prev = journal.last_state(db) if full else None
                journal.finish(run_id, shares, limits, failed,
                               fact_as_of(db) if shares.get("by_fact") else None,
                               limit_errors, checks)
            except Exception:  # noqa: BLE001
                log.exception("журнал биддера: прогон %s не закрыт", run_id)
            if full:
                try:
                    _alert_if_worse(db, prev, checks)
                except Exception:  # noqa: BLE001
                    db.rollback()
                    log.exception("биддер: тревога о прогоне %s не отправлена", run_id)
        return {"shares": shares, "limits": limits, "failed": failed, "dry_run": False,
                "run_id": run_id, "checks": checks}
    finally:
        db.close()


def _SCOPE_ALL(campaign_ids) -> bool:   # noqa: N802 — подменяется в тестах
    return campaign_ids is None


def _checks(db, shares: dict, limit_errors: list) -> list:
    """Проверки прогона (`app/bidder/checks`). Сбой проверки не роняет прогон — он
    сам становится строкой-ошибкой: молчащий прибор хуже упавшего."""
    from app.bidder import checks as K
    from app.dsp.stat_daily import today_msk
    try:
        dsp_error = None
        try:
            from app.dsp.db import DspSessionLocal
            dsp = DspSessionLocal() if DspSessionLocal else None
        except Exception as e:  # noqa: BLE001
            dsp, dsp_error = None, type(e).__name__
        try:
            g = K.gather(db, dsp, today_msk())
        finally:
            if dsp is not None:
                dsp.close()
        out = K.evaluate(g["campaigns"], bool(shares.get("by_fact")), g["slice_vs_raw"],
                         limit_errors, today_msk())
        # Базы DSP нет — сверка пропущена, и это должно быть видно, а не молча «всё ок».
        dsp_error = dsp_error or g.get("dsp_error")
        return out + [K.dsp_unavailable(dsp_error)] if dsp_error else out
    except Exception as e:  # noqa: BLE001
        db.rollback()
        log.exception("биддер: проверки прогона не выполнены")
        return [{"level": "error", "code": "checks_failed", "title": "Проверки не выполнены",
                 "count": 1, "examples": [str(e)[:200]]}]


def _alert_if_worse(db, prev_state, checks: list) -> None:
    """Тревога владельцу и мастерам трафика — только когда прогон стал хуже предыдущего."""
    from app.bidder import checks as K
    now = K.state_of(checks)
    if not K.should_alert(prev_state, now):
        return
    from app.notify.bus import emit
    body = "; ".join(f"{c['title']}: {c['count']}" + (f" ({c['examples'][0]})" if c["examples"] else "")
                     for c in checks)
    emit(db, "cron_bidder_failed", title=f"Биддер: {now}", body=body[:600],
         link="/traffic/bidder", entity_type="cron", entity_id=2, actor=None)
    db.commit()


def _report(out: dict) -> str:
    s = out["shares"]
    upd = sum(x["updated"] for x in out["limits"])
    zero = sum(len(x.get("zero") or []) for x in out["limits"])
    return (f"РК пересчитано: {s['campaigns']}, весов сменилось: {s['weights_changed']}; "
            f"лимитов в DSP обновлено: {upd}, не ушло: {out['failed']}"
            + (f", креативов с нулевой долей (лимит не менялся): {zero}" if zero else "")
            + ("" if s.get("by_fact", True) else
               "; статистики DSP за вчера нет — объёмы по весам, без факта")
            + "".join(f"\n  [{c['level']}] {c['title']}: {c['count']}"
                      + (f" — {', '.join(c['examples'][:3])}" if c["examples"] else "")
                      for c in out.get("checks") or [])
            + (" (пробный прогон, ничего не записано)" if out.get("dry_run") else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Ночной пересчёт объёмов РК и лимитов DSP")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    res = run(dry_run=a.dry_run)
    print(_report(res))
    sys.exit(1 if res["failed"] else 0)
