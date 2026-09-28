# -*- coding: utf-8 -*-
"""Суточный съём статистики DSP. Ставится в cron сервера: 04:30 МСК (01:30 UTC).

    docker exec finance_backend python -m app.dsp.stat_daily --dry-run
    docker exec finance_backend python -m app.dsp.stat_daily
    docker exec finance_backend python -m app.dsp.stat_daily --campaign 45 --from 2026-10-01 --to 2026-10-05

Раз в сутки — решение владельца 27.09.2026. Окно — последние трое суток плюс догон по
курсору: DSP досчитывает задним числом, а оба шага записи — апсерты, поэтому перезабор
ничего не удваивает. Сегодняшние сутки не забираются: они не закрыты.

Кабинет — боевой клиент (`dsp_partner_xxhash` в админке, иначе `DSP_PARTNER_XXHASH`):
ровно тот, под которым заводятся РК. Демо-кабинет не собирается — там только нацеливание
и проверки.

ПРОГОН, КОТОРЫЙ ЧТО-ТО НЕ ЗАБРАЛ, — НЕ УСПЕХ. Кампания, не вернувшаяся в ответе,
печатается поимённо и роняет код возврата: крон с ошибкой виден, молчаливый ноль — нет.
"""
import argparse
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.database import SessionLocal
from app.dsp import stat_store as store
from app.dsp import stats as S
from app.dsp.client import PROD, MsClient, MsError


def _day(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def today_msk() -> date:
    return datetime.now(ZoneInfo("Europe/Moscow")).date()


LAST_RUN_KEY = "dsp_stat_last"


def record(out: dict | None = None, error: str | None = None) -> None:
    """Итог боевого прогона — для экрана «Статус системы» (`check_dsp_stats`).

    Пишется и на удаче, и на отказе: крон, который молча не состоялся, с экрана
    неотличим от крона, который ничего не нашёл."""
    import json

    from sqlalchemy import text
    out = out or {}
    value = json.dumps({
        "at": datetime.utcnow().isoformat(timespec="seconds"),
        "campaigns": out.get("campaigns", 0), "shows": out.get("shows", 0),
        "failed": [f"{h} с {d}" for h, d in (out.get("failed_campaigns") or {}).items()][:20],
        "unassigned": out.get("unassigned") or {},
        "missing_creatives": len(out.get("missing_creatives") or []),
        "error": ((error or "; ".join(out.get("errors") or []))[:300]) or None,
    }, ensure_ascii=False)
    db = SessionLocal()
    try:
        db.execute(text("INSERT INTO company_settings (key, value) VALUES (:k, :v) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
                   {"k": LAST_RUN_KEY, "v": value})
        db.commit()
    finally:
        db.close()


def run(*, campaign_id=None, start=None, end=None, dry_run: bool = False,
        client=None) -> dict:
    from app.dsp.db import DspSessionLocal

    if DspSessionLocal is None:
        raise RuntimeError("DSP_DATABASE_URL не задан — сырьё складывать некуда")
    if (start is None) != (end is None):
        raise RuntimeError("--from и --to задаются вместе")
    client = client or MsClient(contour=PROD)
    if not client.partner_xxhash:
        raise RuntimeError("не задан клиент кабинета DSP (админка или DSP_PARTNER_XXHASH)")
    db, dsp_db = SessionLocal(), DspSessionLocal()
    try:
        today = today_msk()
        if not dry_run:
            return store.sync(db, dsp_db, client, today, campaign_id=campaign_id,
                              start=start, end=end)
        tg = store.targets(db, dsp_db, today, campaign_id, start, end)
        hmap = store.hash_map(db, dsp_db, [t.campaign_id for t in tg],
                              contour=client.contour, partner=client.partner_xxhash)
        # Сухой прогон спрашивает только вчерашние сутки — проверить доступ и ответ, не
        # обходя всё окно и ничего не записывая.
        probe = None
        if tg:
            day = max(t.end for t in tg)
            live = [t for t in tg if t.start <= day <= t.end]
            pull = S.pull_day(client, day, hmap.creatives_of([t.campaign_id for t in live]),
                              [t.ms_campaign for t in live])
            probe = {"day": day.isoformat(),
                     "shows": sum(v.shows for v in pull.campaigns.values()),
                     "missing_campaigns": pull.missing_campaigns,
                     "missing_creatives": pull.missing_creatives}
        return {"dry_run": True, "campaigns": len(tg), "creatives": len(hmap.creatives),
                "windows": {t.campaign_id: f"{t.start}..{t.end}" for t in tg},
                "probe": probe}
    finally:
        db.close()
        dsp_db.close()


def _report(out: dict) -> str:
    if out.get("dry_run"):
        return (f"DSP СУХОЙ ПРОГОН: РК в сборе {out['campaigns']}, креативов {out['creatives']}, "
                f"окна {out['windows']}; проба {out['probe']}")
    parts = [f"DSP: РК {out['campaigns']}, суток {out['days']}, строк сырья {out['raw_rows']}, "
             f"показов {out['shows']}, строк среза {out['written']}"]
    if out.get("unassigned"):
        parts.append(f"НЕ РАЗНЕСЕНО по площадкам (показов по РК): {out['unassigned']}")
    if out.get("missing_creatives"):
        parts.append(f"нет данных по креативам: {', '.join(out['missing_creatives'])}")
    if out.get("failed_campaigns"):
        parts.append(f"НЕ ЗАБРАНЫ кампании (с суток): {out['failed_campaigns']}")
    if out.get("errors"):
        parts.append("отказы DSP: " + "; ".join(out["errors"]))
    return "; ".join(parts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Суточный съём статистики DSP")
    ap.add_argument("--dry-run", action="store_true", help="проверить доступ, ничего не писать")
    ap.add_argument("--campaign", type=int, help="id РК у нас")
    ap.add_argument("--from", dest="since", type=_day, help="начало отрезка YYYY-MM-DD")
    ap.add_argument("--to", dest="until", type=_day, help="конец отрезка YYYY-MM-DD")
    a = ap.parse_args()
    # Итог на экран состояния — только у планового прогона: ручной добор отрезка или
    # сухая проверка не должны выдавать себя за ночной крон.
    planned = not (a.dry_run or a.campaign or a.since)
    try:
        res = run(campaign_id=a.campaign, start=a.since, end=a.until, dry_run=a.dry_run)
    except Exception as e:  # noqa: BLE001 — любой отказ обязан дойти до экрана состояния
        if planned:
            try:
                record(error=str(e) if isinstance(e, (MsError, RuntimeError)) else repr(e))
            except Exception:  # noqa: BLE001 — база недоступна: останется «нет прогона 30 ч»
                pass
        print(f"Съём DSP не состоялся: {e!r}", file=sys.stderr)
        sys.exit(1)
    if planned:
        record(res)
    print(_report(res))
    if res.get("failed_campaigns"):
        sys.exit(2)
