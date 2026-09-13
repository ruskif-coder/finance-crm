# -*- coding: utf-8 -*-
"""Хранение съёма Weborama: сырьё в аналитическую базу, суточный срез — в основную.

РАЗДЕЛЕНИЕ НА ДВА ШАГА НЕ КОСМЕТИЧЕСКОЕ. Сырьё пишется и коммитится ПЕРВЫМ, срез
отдаётся вторым. Порядок такой потому, что шаги стоят разного: перекачать сырьё — это
обращение к чужой системе с ограниченным окном выдачи, а пересобрать срез из уже
лежащего сырья можно сколько угодно раз. Если второй шаг упадёт, первый останется, и
следующий прогон доложит срез без единого вызова наружу.

ЧТО ДЕЛАЕТ СРЕЗ ИДЕМПОТЕНТНЫМ. Окно съёма перекрывает трое суток назад (Weborama
дозаливает задним числом), то есть одни и те же сутки приезжают по нескольку раз. Оба
шага — апсерты по ограничению: `uq_wcm_stat_daily` в сырье и `uq_ad_stat` в основной
базе. Ни один прогон не добавляет строку к уже существующей, он её ЗАМЕЩАЕТ. Обратное
поведение росло бы само собой и выглядело бы как рост открутки.

ЧЕГО ЭТОТ МОДУЛЬ НЕ ДЕЛАЕТ. Не угадывает соответствие «их вставка → наша площадка».
Соответствие берётся только из `weborama_refs` — реестра, который заполняется, когда
вставку заводим МЫ. Сопоставлять по имени нельзя: замер 12.09.2026 показал, что 233
вставки из 452 названы по старой схеме (`espumizan-aptechestvo`), где вторая часть —
сокращение, а не домен, и подбор по трёхбуквенным кодам площадок «находит» совпадения
внутри чужих слов. Цена ошибки тут прямая — чужие показы на чужой площадке.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional

from sqlalchemy import text

from app.ad.stat_sources import VERIFIER
from app.weborama import stats as S

log = logging.getLogger("finance.weborama")

SOURCE = "weborama"
assert SOURCE in VERIFIER, "источник обязан быть объявлен измерителем, иначе попадёт в факт"


def save_raw(dsp_db, account_id: str, pull: S.WcmPull) -> int:
    """Сырьё в `wcm_stat_daily`. Возвращает число записанных строк."""
    if not pull.rows:
        return 0
    sql = text("""
        INSERT INTO wcm_stat_daily (day, account_id, insertion_id, label,
                                    impression, click, metrics, imported_at)
        VALUES (:day, :acc, :ins, :label, :imp, :clk, CAST(:metrics AS JSONB), now())
        ON CONFLICT ON CONSTRAINT uq_wcm_stat_daily DO UPDATE SET
            label       = EXCLUDED.label,
            impression  = EXCLUDED.impression,
            click       = EXCLUDED.click,
            metrics     = EXCLUDED.metrics,
            imported_at = now()
    """)
    for r in pull.rows:
        dsp_db.execute(sql, {"day": r.day, "acc": str(account_id), "ins": r.insertion_id,
                             "label": r.label, "imp": r.impression, "clk": r.click,
                             "metrics": json.dumps(r.metrics, ensure_ascii=False)})
    dsp_db.commit()
    return len(pull.rows)


def remember(dsp_db, account_id: str, *, pull: Optional[S.WcmPull] = None,
             error: Optional[str] = None) -> None:
    """Курсор: докуда забрали и чем закончилось.

    Пишется и на удаче, и на отказе. Прогон, который молча не состоялся, с экрана
    неотличим от прогона, который ничего не нашёл, — а это разные вещи.
    """
    dsp_db.execute(text("""
        INSERT INTO wcm_sync_cursor (account_id, last_pulled_day, last_run_at,
                                     last_rows, last_absent, last_error, updated_at)
        VALUES (:acc, :day, now(), :rows, :absent, :err, now())
        ON CONFLICT (account_id) DO UPDATE SET
            last_pulled_day = COALESCE(EXCLUDED.last_pulled_day,
                                       wcm_sync_cursor.last_pulled_day),
            last_run_at = now(), last_rows = EXCLUDED.last_rows,
            last_absent = EXCLUDED.last_absent, last_error = EXCLUDED.last_error,
            updated_at = now()
    """), {"acc": str(account_id),
           "day": pull.end if pull else None,
           "rows": len(pull.rows) if pull else None,
           "absent": ", ".join(pull.absent_metrics) if pull and pull.absent_metrics else None,
           "err": error})
    dsp_db.commit()


def _mapping(db, account_id: str) -> dict:
    """их вставка → (наша площадка, её РК). Только из реестра, без догадок."""
    rows = db.execute(text("""
        SELECT r.wcm_id, p.id AS placement_id, p.campaign_id
          FROM weborama_refs r
          JOIN ad_campaign_placement p ON p.id = r.local_id
         WHERE r.kind = 'insertion' AND r.account_id = :acc
    """), {"acc": str(account_id)}).mappings().all()
    return {str(r["wcm_id"]): (r["placement_id"], r["campaign_id"]) for r in rows}


def push_daily(db, dsp_db, account_id: str, start: date, end: date) -> dict:
    """Суточный срез из сырья → `ad_campaign_stat` с `source='weborama'`.

    Считается ИЗ СЫРЬЯ, а не из ответа: тогда срез можно пересобрать за любой прошлый
    отрезок, не трогая чужой API, и результат не зависит от того, что было в последнем
    вызове.
    """
    mapping = _mapping(db, account_id)
    raw = dsp_db.execute(text("""
        SELECT day, insertion_id, impression, click
          FROM wcm_stat_daily
         WHERE account_id = :acc AND day BETWEEN :a AND :b
    """), {"acc": str(account_id), "a": start, "b": end}).mappings().all()

    written = skipped = 0
    unmatched_imp = 0
    sql = text("""
        INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks,
                                      source, imported_at)
        VALUES (:c, :p, :d, :shows, :clicks, :src, now())
        ON CONFLICT ON CONSTRAINT uq_ad_stat DO UPDATE SET
            shows = EXCLUDED.shows, clicks = EXCLUDED.clicks, imported_at = now()
    """)
    for r in raw:
        hit = mapping.get(str(r["insertion_id"]))
        if not hit:
            skipped += 1
            unmatched_imp += r["impression"] or 0
            continue
        placement_id, campaign_id = hit
        db.execute(sql, {"c": campaign_id, "p": placement_id, "d": r["day"],
                         "shows": r["impression"] or 0, "clicks": r["click"] or 0,
                         "src": SOURCE})
        written += 1
    db.commit()
    return {"written": written, "skipped": skipped,
            "unmatched_impressions": unmatched_imp, "mapped_insertions": len(mapping)}


def sync(db, dsp_db, client, account_id: str, *, start: Optional[date] = None,
         end: Optional[date] = None) -> dict:
    """Полный съём: вызов → сырьё → срез → курсор.

    Возвращает то, по чему прогон можно оценить НЕ ЗАГЛЯДЫВАЯ В БАЗУ: сколько строк,
    сколько показов, сошлась ли контрольная сумма, какие метрики промолчали и сколько
    показов осталось неприцепленными. Последнее — не мелочь: пока реестр соответствий
    пуст, неприцепленным остаётся ВСЁ, и прогон, отчитавшийся «успешно», не положил бы
    на дашборд ни одного числа.
    """
    if start is None or end is None:
        start, end = S.window()
    try:
        pull = S.pull(client, start, end)
    except Exception as e:                                  # noqa: BLE001 — нужен любой
        remember(dsp_db, account_id, error=repr(e)[:500])
        raise

    saved = save_raw(dsp_db, account_id, pull)
    remember(dsp_db, account_id, pull=pull)
    pushed = push_daily(db, dsp_db, account_id, start, end)

    out = {"start": start.isoformat(), "end": end.isoformat(),
           "rows": saved, "impressions": pull.impressions,
           "their_total": pull.grand_total, "discrepancy": pull.discrepancy,
           "absent_metrics": list(pull.absent_metrics), "ok": pull.ok()}
    out.update(pushed)
    log.info("Weborama съём %s..%s: %s", start, end, out)
    return out
