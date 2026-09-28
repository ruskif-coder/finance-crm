# -*- coding: utf-8 -*-
"""Хранение съёма DSP: сырьё — в аналитическую базу, суточный срез — в основную.

Устроено как съём Weborama (`app/weborama/store.py`), и по тем же причинам:

* СЫРЬЁ КОММИТИТСЯ ПЕРВЫМ. Перекачать сырьё — это обращение к чужой системе, а
  пересобрать срез из уже лежащего сырья можно сколько угодно раз и без сети.
* ОБА ШАГА — АПСЕРТЫ (`uq_dsp_stat_raw`, `uq_ad_stat`). Окно перезабирает последние сутки
  по нескольку раз (DSP досчитывает задним числом), и прогон ЗАМЕЩАЕТ строку, а не
  добавляет к ней. Обратное выглядело бы как рост открутки.

СШИВКА «ХЕШ → ПЛОЩАДКА». Креатив в DSP заводится на каждую пару «площадка × креатив»
отдельно (`ad_campaign_creative.ms_creative_xxhash`), поэтому факт площадки за сутки =
сумма её креативов. Хеш в нашей строке меняется при перевыгрузке, но старый не теряется:
каждый удачный `Creative.add` лежит в журнале с `local_ref = cr<id строки>`. Карта —
текущие хеши плюс история журнала; без истории показы до перевыгрузки ушли бы в
«не разнесено».

ОСТАТОК. Итог кампании от DSP минус сумма разнесённого по площадкам. Больше нуля — в
кампании крутится креатив, которого мы не заводили (руками в кабинете). Он ложится строкой
без площадки: тогда итог РК у нас равен итогу в кабинете, а экран видит, что разнести не
удалось.

НОЛЬ = ОТСУТСТВИЕ СТРОКИ. Сутки без показов строку не пишут, а прежнюю — снимают. Строка с
нулём говорила бы «факт есть», и экраны считали бы её днём открутки.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text

from app.ad.stat_sources import OWN
from app.dsp import stats as S
from app.dsp.client import MsError

log = logging.getLogger("finance.dsp")

SOURCE = "dsp"
assert SOURCE in OWN, "источник DSP — наш счётчик, он обязан входить в факт"

# Сколько последних суток перезабирать (DSP досчитывает задним числом). Столько же
# суток после конца флайта РК остаётся в сборе — последний прогон и есть финальная сверка.
WINDOW_DAYS = 3


@dataclass
class Target:
    """РК в сборе и её отрезок дней."""
    campaign_id: int
    ms_campaign: str
    start: date
    end: date


@dataclass
class HashMap:
    """хеш креатива → (РК, площадка); хеш кампании → РК."""
    creatives: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    campaigns: Dict[str, int] = field(default_factory=dict)

    def creatives_of(self, campaign_ids) -> List[str]:
        ids = set(campaign_ids)
        return [h for h, (c, _) in self.creatives.items() if c in ids]


def _ts(day: date) -> str:
    """Сутки DSP — московские (даты он отдаёт в Europe/Moscow)."""
    return f"{day.isoformat()} 00:00:00+03:00"


# ── что собирать ───────────────────────────────────────────────────────────
def cursors(dsp_db, hashes) -> Dict[str, date]:
    if not hashes:
        return {}
    rows = dsp_db.execute(text(
        "SELECT ms_campaign_xxhash, (last_pulled_ts AT TIME ZONE 'Europe/Moscow')::date "
        "FROM dsp_sync_cursor WHERE ms_campaign_xxhash = ANY(:h) AND last_pulled_ts IS NOT NULL"),
        {"h": list(hashes)}).all()
    return {r[0].upper(): r[1] for r in rows}


def window_for(start: date, end: date, today: date, cursor: Optional[date]) -> Optional[tuple]:
    """Отрезок дней, который надо (пере)забрать у РК, или None.

    Верх — вчера: сегодняшние сутки не закрыты, частичная строка выглядела бы на экране
    как «сегодня открутили мало». Низ — последние `WINDOW_DAYS` суток до курсора (досчёт),
    без курсора — старт флайта. РК, у которой флайт кончился больше `WINDOW_DAYS` суток
    назад и всё забрано, из сбора выходит.
    """
    yesterday = today - timedelta(days=1)
    if start > yesterday:
        return None
    if today > end + timedelta(days=WINDOW_DAYS + 1) and cursor and cursor >= end:
        return None
    hi = min(yesterday, end)
    lo = start if cursor is None else max(start, min(cursor + timedelta(days=1),
                                                     hi - timedelta(days=WINDOW_DAYS - 1)))
    return (lo, hi) if lo <= hi else None


def targets(db, dsp_db, today: date, campaign_id: Optional[int] = None,
            start: Optional[date] = None, end: Optional[date] = None) -> List[Target]:
    """РК с хешем кампании в DSP и флайтом. Явный отрезок (`--from/--to`) — как есть."""
    sql = ("SELECT id, ms_campaign_xxhash, date_start, date_end FROM ad_campaign "
           "WHERE coalesce(ms_campaign_xxhash, '') <> '' "
           "AND date_start IS NOT NULL AND date_end IS NOT NULL")
    params = {}
    if campaign_id is not None:
        sql += " AND id = :c"
        params["c"] = campaign_id
    rows = db.execute(text(sql), params).all()
    cur = cursors(dsp_db, [r[1].upper() for r in rows])
    out = []
    for cid, xx, ds, de in rows:
        if start and end:
            # Ручной отрезок тоже не заходит за вчера: неполные сутки на экране выглядят
            # как «сегодня открутили мало».
            lo = max(ds, start)
            hi = min(de + timedelta(days=WINDOW_DAYS), end, today - timedelta(days=1))
            win = (lo, hi) if lo <= hi else None
        else:
            win = window_for(ds, de, today, cur.get(xx.upper()))
        if win:
            out.append(Target(cid, xx.upper(), win[0], win[1]))
    return out


# ── карта хешей ────────────────────────────────────────────────────────────
def hash_map(db, dsp_db, campaign_ids, *, contour: str, partner: Optional[str]) -> HashMap:
    """Текущие хеши из наших строк + прежние из журнала (перевыгрузки).

    Журнал берётся только своего контура и своего клиента кабинета: хеш, заведённый под
    другим клиентом (28.09.2026 — боевые РК под демо-клиентом), этому кабинету не
    принадлежит, и его показы — не наши.
    """
    m = HashMap()
    if not campaign_ids:
        return m
    ids = list(campaign_ids)
    for cid, xx in db.execute(text(
            "SELECT id, ms_campaign_xxhash FROM ad_campaign WHERE id = ANY(:ids)"),
            {"ids": ids}).all():
        if xx:
            m.campaigns[xx.upper()] = cid
    rows = db.execute(text(
        "SELECT id, campaign_id, placement_id, ms_creative_xxhash FROM ad_campaign_creative "
        "WHERE campaign_id = ANY(:ids)"), {"ids": ids}).all()
    by_ref = {f"cr{r[0]}": (r[1], r[2]) for r in rows}
    for _, cid, pid, xx in rows:
        if xx:
            m.creatives[xx.upper()] = (cid, pid)
    if by_ref:
        hist = dsp_db.execute(text(
            "SELECT DISTINCT local_ref, ms_xxhash FROM dsp_send_log "
            "WHERE contour = :ct AND method = 'Creative.add' AND ok "
            "AND ms_xxhash IS NOT NULL AND local_ref = ANY(:refs) "
            "AND (request->'params'->>'partner_xxhash') IS NOT DISTINCT FROM :px"),
            {"ct": contour, "refs": list(by_ref), "px": partner}).all()
        for ref, xx in hist:
            m.creatives.setdefault(xx.upper(), by_ref[ref])
    return m


# ── сырьё ──────────────────────────────────────────────────────────────────
_RAW_SQL = text("""
    INSERT INTO dsp_stat_raw (ts, ms_campaign_xxhash, ms_source_key, ms_creative_xxhash,
                              shows, clicks, spend, imported_at)
    VALUES (CAST(:ts AS timestamptz), :camp, NULL, :cr, :shows, :clicks, :spend, now())
    ON CONFLICT ON CONSTRAINT uq_dsp_stat_raw DO UPDATE SET
        shows = EXCLUDED.shows, clicks = EXCLUDED.clicks, spend = EXCLUDED.spend,
        imported_at = now()
""")


def save_raw(dsp_db, pull: S.DayPull, hmap: HashMap) -> int:
    """Строка на креатив (под хешем его кампании) и строка на кампанию (креатив NULL)."""
    camp_of = {cid: xx for xx, cid in hmap.campaigns.items()}
    n = 0
    for xx, v in pull.creatives.items():
        cid = hmap.creatives.get(xx, (None, None))[0]
        camp = camp_of.get(cid)
        if not camp:
            continue
        dsp_db.execute(_RAW_SQL, {"ts": _ts(pull.day), "camp": camp, "cr": xx,
                                  "shows": v.shows, "clicks": v.clicks, "spend": v.spend})
        n += 1
    for xx, v in pull.campaigns.items():
        dsp_db.execute(_RAW_SQL, {"ts": _ts(pull.day), "camp": xx, "cr": None,
                                  "shows": v.shows, "clicks": v.clicks, "spend": v.spend})
        n += 1
    dsp_db.commit()
    return n


def remember(dsp_db, campaign_hash: str, day: date) -> None:
    """Курсор РК: докуда забрано. Сдвигается только вперёд и только после удачи."""
    dsp_db.execute(text("""
        INSERT INTO dsp_sync_cursor (ms_campaign_xxhash, last_pulled_ts, updated_at)
        VALUES (:h, CAST(:ts AS timestamptz), now())
        ON CONFLICT (ms_campaign_xxhash) DO UPDATE SET
            last_pulled_ts = GREATEST(dsp_sync_cursor.last_pulled_ts, EXCLUDED.last_pulled_ts),
            updated_at = now()
    """), {"h": campaign_hash, "ts": _ts(day)})
    dsp_db.commit()


# ── срез в основную базу ───────────────────────────────────────────────────
_UPSERT = text("""
    INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks, source,
                                  imported_at)
    VALUES (:c, :p, :d, :shows, :clicks, :src, now())
    ON CONFLICT ON CONSTRAINT uq_ad_stat DO UPDATE SET
        shows = EXCLUDED.shows, clicks = EXCLUDED.clicks, imported_at = now()
""")
_DELETE = text(
    "DELETE FROM ad_campaign_stat WHERE campaign_id = :c "
    "AND placement_id IS NOT DISTINCT FROM :p AND date = :d AND source = 'dsp'")


def _put(db, cid, pid, day, shows, clicks) -> bool:
    args = {"c": cid, "p": pid, "d": day}
    if shows > 0 or clicks > 0:
        db.execute(_UPSERT, {**args, "src": SOURCE, "shows": shows, "clicks": clicks})
        return True
    db.execute(_DELETE, args)
    return False


def push_daily(db, dsp_db, hmap: HashMap, targets_: List[Target]) -> dict:
    """Суточный срез ИЗ СЫРЬЯ → `ad_campaign_stat`, `source = 'dsp'`.

    Из сырья, а не из ответа: срез пересобирается за любой прошлый отрезок без вызова
    наружу, и результат не зависит от того, что пришло в последний раз."""
    written = 0
    unassigned: Dict[int, int] = {}
    for t in targets_:
        raw = dsp_db.execute(text("""
            SELECT (ts AT TIME ZONE 'Europe/Moscow')::date AS day, ms_creative_xxhash AS cr,
                   shows, clicks
              FROM dsp_stat_raw
             WHERE ms_campaign_xxhash = :h AND ms_source_key IS NULL
               AND ts BETWEEN CAST(:a AS timestamptz) AND CAST(:b AS timestamptz)
        """), {"h": t.ms_campaign, "a": _ts(t.start), "b": _ts(t.end)}).mappings().all()
        per_day: Dict[date, Dict[int, list]] = {}
        totals: Dict[date, tuple] = {}
        for r in raw:
            if r["cr"] is None:
                totals[r["day"]] = (r["shows"], r["clicks"])
                continue
            hit = hmap.creatives.get(r["cr"].upper())
            if not hit or hit[0] != t.campaign_id:
                continue
            acc = per_day.setdefault(r["day"], {}).setdefault(hit[1], [0, 0])
            acc[0] += r["shows"]
            acc[1] += r["clicks"]
        placements = {pid for c, pid in hmap.creatives.values() if c == t.campaign_id}
        placements |= {pid for d in per_day.values() for pid in d}
        day = t.start
        while day <= t.end:
            spread = per_day.get(day, {})
            for pid in placements:
                # Нет ни одной строки сырья по площадке за сутки — замера нет, и прежнее
                # число не трогаем: «не спросили» не значит «не крутила».
                if pid in spread:
                    s, k = spread[pid]
                    written += _put(db, t.campaign_id, pid, day, s, k)
            if day in totals:
                rest_s = totals[day][0] - sum(v[0] for v in spread.values())
                rest_k = totals[day][1] - sum(v[1] for v in spread.values())
                if rest_s < 0 or rest_k < 0:
                    log.warning("dsp stat: РК %s %s — разнесено больше итога кампании "
                                "(%s / %s)", t.campaign_id, day, rest_s, rest_k)
                    rest_s = rest_k = 0
                written += _put(db, t.campaign_id, None, day, rest_s, rest_k)
                if rest_s > 0:
                    unassigned[t.campaign_id] = unassigned.get(t.campaign_id, 0) + rest_s
            day += timedelta(days=1)
    db.commit()
    return {"written": written, "unassigned": unassigned}


# ── прогон целиком ─────────────────────────────────────────────────────────
def sync(db, dsp_db, client, today: date, *, campaign_id: Optional[int] = None,
         start: Optional[date] = None, end: Optional[date] = None) -> dict:
    """Вызовы → сырьё → срез → курсоры. Итог — то, по чему прогон оценивается без базы.

    Кампания, не вернувшаяся в ответе, — ошибка прогона, а не ноль: её курсор не
    сдвигается, и следующий прогон заберёт эти сутки снова.
    """
    tg = targets(db, dsp_db, today, campaign_id, start, end)
    hmap = hash_map(db, dsp_db, [t.campaign_id for t in tg],
                    contour=client.contour, partner=client.partner_xxhash)
    days: Dict[date, List[Target]] = {}
    for t in tg:
        d = t.start
        while d <= t.end:
            days.setdefault(d, []).append(t)
            d += timedelta(days=1)

    raw_rows = shows = 0
    missing_cr: set = set()
    failed: Dict[str, str] = {}
    errors: List[str] = []
    for day in sorted(days):
        ts_ = days[day]
        # Сутки изолированы: отказ DSP на одних (таймаут пачки, один плохой хеш) не
        # роняет остальные. У задетых РК курсор не сдвигается — следующий прогон повторит.
        try:
            pull = S.pull_day(client, day, hmap.creatives_of([t.campaign_id for t in ts_]),
                              [t.ms_campaign for t in ts_])
        except MsError as e:
            errors.append(f"{day}: {str(e)[:200]}")
            for t in ts_:
                failed.setdefault(t.ms_campaign, day.isoformat())
            continue
        raw_rows += save_raw(dsp_db, pull, hmap)
        shows += sum(v.shows for v in pull.campaigns.values())
        missing_cr.update(pull.missing_creatives)
        for h in pull.missing_campaigns:
            failed.setdefault(h, day.isoformat())
    # Курсор двигает только плановый прогон. Ручной добор отрезка в середине флайта
    # сдвинул бы его вперёд, и дни до отрезка ночной прогон больше не забрал бы никогда.
    planned = not (start and end)
    for t in tg:
        if planned and t.ms_campaign not in failed:
            remember(dsp_db, t.ms_campaign, t.end)
    pushed = push_daily(db, dsp_db, hmap, tg)
    out = {"campaigns": len(tg), "days": len(days), "raw_rows": raw_rows, "shows": shows,
           "creatives": len(hmap.creatives), "missing_creatives": sorted(missing_cr),
           "failed_campaigns": failed, "errors": errors[:20], **pushed}
    log.info("DSP съём: %s", out)
    return out
