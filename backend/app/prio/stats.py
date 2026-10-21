# -*- coding: utf-8 -*-
"""Суточная статистика системы приоритезации (владелец 19.10.2026: «хранить дельту между суточными данными при запросах»).

Разработчик подтвердил: разбивка по camp_id есть, сутки — при date_start = date_end, даты МСК. Окно — последние `WINDOW` суток:
день перезабирается несколько ночей и может дорасти. Каждый снимок дня хранится (`prio_stat_raw`) с дельтой к предыдущему
снимку того же дня; в факт РК (`ad_campaign_stat`, источник `prio`) идёт последний снимок — апсертом, как у DSP.
Отрицательная дельта (система уменьшила день) — не отрицательный день: факт = снимок, а в отчёт — «уменьшилось».

Формат ответа `stats-all-summary` в доке не описан — разбор терпимый (ищет camp_id и показы/клики под разными именами);
сверить на первой пробе с токеном."""
import logging
import sys
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

import app.model_registry  # noqa: F401 — крон отдельным процессом: все таблицы для внешних ключей
from app.database import SessionLocal
from app.prio import models as M

log = logging.getLogger("finance.prio")
WINDOW = 3
SOURCE = "prio"
_SHOW = ("impressions", "imp", "shows", "show", "views")
_CLICK = ("clicks", "clk", "click")
_TYPES = ("search", "catalog", "context")


def _num(d: dict, keys) -> Optional[int]:
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return int(round(float(d[k])))
            except (TypeError, ValueError):
                return None
    return None


def parse(body: Any) -> dict:
    """Ответ → {camp_id: {"shows", "clicks", "by_type"}}. Список строк или словарь по camp_id — оба вида."""
    if isinstance(body, dict):
        items = body.get("stats") or body.get("campaigns") or body.get("data") or body.get("items")
        if items is None:
            items = [dict(v, camp_id=k) for k, v in body.items() if isinstance(v, dict) and str(k).isdigit()]
    else:
        items = body
    out = {}
    for it in items or []:
        if not isinstance(it, dict) or it.get("camp_id") is None:
            continue
        by = {t: {"shows": _num(it[t], _SHOW), "clicks": _num(it[t], _CLICK)} for t in _TYPES if isinstance(it.get(t), dict)}
        shows = _num(it, _SHOW)
        clicks = _num(it, _CLICK)
        if shows is None and by:
            shows = sum(v["shows"] or 0 for v in by.values())
        if clicks is None and by:
            clicks = sum(v["clicks"] or 0 for v in by.values())
        out[int(it["camp_id"])] = {"shows": shows or 0, "clicks": clicks or 0, "by_type": by or None}
    return out


def save_snapshot(db: Session, camp_id: int, day: date, v: dict) -> M.PrioStatRaw:
    prev = (db.query(M.PrioStatRaw).filter_by(camp_id=camp_id, day=day)
            .order_by(M.PrioStatRaw.pulled_at.desc(), M.PrioStatRaw.id.desc()).first())
    row = M.PrioStatRaw(camp_id=camp_id, day=day, shows=v["shows"], clicks=v["clicks"], by_type=v.get("by_type"),
                        delta_shows=(v["shows"] - prev.shows) if prev else None,
                        delta_clicks=(v["clicks"] - prev.clicks) if prev else None, pulled_at=datetime.utcnow())
    db.add(row)
    db.flush()
    return row


_UPSERT = text("""
    INSERT INTO ad_campaign_stat (campaign_id, placement_id, date, shows, clicks, source, imported_at)
    VALUES (:c, :p, :d, :s, :k, 'prio', now())
    ON CONFLICT ON CONSTRAINT uq_ad_stat DO UPDATE SET shows = EXCLUDED.shows, clicks = EXCLUDED.clicks, imported_at = now()
""")


def target_of(db: Session, camp_id: int) -> Optional[tuple]:
    """camp_id → (РК сделки, площадка РК) для факта; площадки в РК нет — строка на РК целиком."""
    row = db.execute(text("""
        SELECT c.id, (SELECT ap.id FROM ad_campaign_placement ap WHERE ap.campaign_id = c.id AND ap.publisher_id = pp.publisher_id
                       ORDER BY ap.id LIMIT 1)
          FROM prio_placements pp JOIN prio_requests r ON r.id = pp.request_id
          JOIN ad_campaign c ON c.deal_id = r.deal_id
         WHERE pp.camp_id = :c ORDER BY c.id LIMIT 1"""), {"c": camp_id}).first()
    return (row[0], row[1]) if row else None


def pull(db: Session, client, days: Iterable[date], *, commit: bool = True) -> dict:
    """`commit=False` — для тестов: в транзакции, которую откатывает вызывающий (иначе тест оставит строки на стенде)."""
    known = {r[0] for r in db.execute(text("SELECT camp_id FROM prio_placements WHERE camp_id IS NOT NULL"))}
    out = {"days": 0, "snapshots": 0, "written": 0, "shrunk": [], "unknown": set(), "no_rk": set()}
    for day in days:
        got = parse(client.stats(day.isoformat(), day.isoformat()))
        out["days"] += 1
        # Несколько РК системы могут лечь в одну строку факта (у РК сделки нет строки этой площадки → строка «РК целиком»):
        # складываем за сутки и пишем ОДИН раз — иначе вторая площадка затирала первую (найдено прогоном по шагам 19.10).
        acc: dict = {}
        for camp_id, v in got.items():
            if camp_id not in known:
                out["unknown"].add(camp_id)
                continue
            snap = save_snapshot(db, camp_id, day, v)
            out["snapshots"] += 1
            if snap.delta_shows is not None and snap.delta_shows < 0:
                out["shrunk"].append(f"{camp_id} {day}: {snap.delta_shows}")
            tgt = target_of(db, camp_id)
            if not tgt:
                out["no_rk"].add(camp_id)
                continue
            cur = acc.setdefault(tgt, [0, 0])
            cur[0] += v["shows"]
            cur[1] += v["clicks"]
        for (cid, pid), (shows, clicks) in acc.items():
            db.execute(_UPSERT, {"c": cid, "p": pid, "d": day, "s": shows, "k": clicks})
            out["written"] += 1
    if commit:
        db.commit()
    else:
        db.flush()
    out["unknown"], out["no_rk"] = sorted(out["unknown"]), sorted(out["no_rk"])
    return out


def window(today: date, n: int = WINDOW) -> list:
    return [today - timedelta(days=i) for i in range(n, 0, -1)]


def _report(o: dict) -> str:
    parts = [f"Приоритезация: суток {o['days']}, снимков {o['snapshots']}, строк факта {o['written']}"]
    if o["shrunk"]:
        parts.append("день уменьшился: " + "; ".join(o["shrunk"]))
    if o["unknown"]:
        parts.append(f"РК без нашей площадки запроса: {o['unknown']}")
    if o["no_rk"]:
        parts.append(f"нет РК сделки для факта: {o['no_rk']}")
    return "; ".join(parts)


if __name__ == "__main__":
    from app.dsp.stat_daily import today_msk
    from app.prio.client import PrioApiError, PrioClient
    s = SessionLocal()
    try:
        from app.prio import autostop
        c = PrioClient()
        print(_report(pull(s, c, window(today_msk()))))
        print(autostop.report(autostop.run(s, c)))
    except PrioApiError as e:
        print(f"Сбор приоритезации не состоялся: {e}", file=sys.stderr)
        from app.notify import prio as N
        s.rollback()
        N.stat_failed(s, e)
        sys.exit(1)
    finally:
        s.close()
