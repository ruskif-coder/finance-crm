# -*- coding: utf-8 -*-
"""Проверки ночного прогона биддера и разбор изменений (владелец 06.10.2026: «мне бы эти
статусы и возможные ошибки в лог биддера»).

То, что 06.10 проверялось руками после первого ночного прогона, прогон проверяет сам и
пишет в `bidder_run.checks` (миграция 2026-10-06_bidder_run_checks.sql):

  ошибка        сумма планов площадок ≠ плану РК сверх округления; план площадки меньше
                уже открученного; наш срез DSP за вчера ≠ сырью DSP; лимит не ушёл в DSP;
  предупреждение после удержания долей у РК нет ни одной площадки в раскладке (как 9HT4V9
                06.10 — с причиной: не выгружена, нет креативов); статистики за вчера нет.

`evaluate` чистая — данные собирает `gather`. Тревога — на переходе «нормально → плохо»
(`should_alert`), как у автовыпуска ЕРИД: каждую ночь одно и то же — не новость.
"""
from datetime import date, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import text

from app.ad.flight import HOLD_DAYS, flight_of, holds

ERROR, WARNING = "error", "warning"
STATES = ("ок", "предупреждения", "ошибки")
EXAMPLES = 10


def _check(level, code, title, examples) -> dict:
    return {"level": level, "code": code, "title": title, "count": len(examples),
            "examples": examples[:EXAMPLES]}


def evaluate(campaigns: list, by_fact: bool, slice_vs_raw: Optional[Tuple[int, int]],
             limit_errors: list, today: date) -> List[dict]:
    """`campaigns` — [{code, plan_show, date_start, date_end, status, in_dsp, creatives,
    plans: [план площадки], facts: [факт той же площадки]}]."""
    out, over, under, below, empty = [], [], [], [], []
    for c in campaigns:
        plans = [p for p in c["plans"] if p]
        fl = flight_of(c.get("date_start"), c.get("date_end"), today)
        # Флайт кончился или без дат — сумму и факт не проверяем: РК закрывается сверкой, а
        # лёгкий перекрут DSP в конце флайта давал бы «ошибки» каждую ночь (ревью 06.10.2026).
        live = fl is not None and not fl.is_over
        if live and plans and c.get("plan_show"):
            # Округление: каждая площадка ±0,5 показа — допуск по числу площадок.
            # Больше плана — перекрут, ошибка. Меньше — часть плана некуда поставить (06.10.2026,
            # 6KZUTN: одна площадка с заданным объёмом на треть плана) — предупреждение.
            diff = sum(plans) - c["plan_show"]
            msg = (f"{c['code']}: планы {round(sum(plans))} при плане РК {round(c['plan_show'])}"
                   f" ({'+' if diff > 0 else '−'}{round(abs(diff))})")
            if diff > len(plans):
                over.append(msg)
            elif -diff > len(plans):
                under.append(msg)
        for p, f in zip(c["plans"], c["facts"]):
            # Только площадки в раскладке: у вне раскладки плана нет, и сравнивать нечего.
            if live and p and f and p < f:
                below.append(f"{c['code']}: план {round(p)} < открученного {f}")
        if c.get("plan_show") and not plans and live and not holds(fl):
            why = [c.get("status") or "без статуса"]
            if not c.get("in_dsp"):
                why.append("не выгружена в DSP")
            if not c.get("creatives"):
                why.append("нет креативов")
            empty.append(f"{c['code']} ({'; '.join(why)})")
    if over:
        out.append(_check(ERROR, "sum_mismatch", "Сумма планов площадок больше плана РК — перекрут",
                          over))
    if below:
        out.append(_check(ERROR, "below_fact", "План площадки меньше уже открученного", below))
    # Без свежей статистики сверять нечего — это уже предупреждение «stale».
    if by_fact and slice_vs_raw is not None and slice_vs_raw[0] != slice_vs_raw[1]:
        out.append(_check(ERROR, "slice_vs_raw", "Срез DSP за вчера не сходится с сырьём DSP",
                          [f"в срезе {slice_vs_raw[0]}, в сырье {slice_vs_raw[1]}"]))
    if limit_errors:
        out.append(_check(ERROR, "limits_failed", "Лимиты не ушли в DSP",
                          [f"креатив {e.get('creative_id') or '—'}: {e.get('error')}"[:200]
                           for e in limit_errors]))
    if under:
        out.append(_check(WARNING, "plan_unassigned",
                          "План РК распределён не полностью — части объёма нет площадки", under))
    if empty:
        out.append(_check(WARNING, "no_layout",
                          f"После {HOLD_DAYS} дней удержания у РК нет площадок в раскладке", empty))
    if not by_fact:
        out.append(_check(WARNING, "stale", "Статистики за вчера нет — раскладка по весам",
                          ["факт не учтён"]))
    return out


def state_of(checks: list) -> str:
    levels = {c["level"] for c in checks or []}
    return "ошибки" if ERROR in levels else "предупреждения" if WARNING in levels else "ок"


def should_alert(prev_state: Optional[str], now_state: str) -> bool:
    """Тревога — когда стало хуже, а не каждую ночь, пока плохо."""
    rank = {s: i for i, s in enumerate(STATES)}
    return rank.get(now_state, 0) > rank.get(prev_state or "ок", 0)


def summarize(changes: list, starts: dict, today: date) -> List[str]:
    """Разбор изменений прогона по причинам — строками для журнала."""
    from app.bidder.rules import REASONS
    out = []
    hold_end = {c["campaign_id"] for c in changes
                if starts.get(c["campaign_id"])
                and today == starts[c["campaign_id"]] + timedelta(days=HOLD_DAYS)}
    if hold_end:
        n_out = sum(1 for c in changes if c["campaign_id"] in hold_end and c["reason"] == "out")
        out.append(f"{len(hold_end)} РК: закончилось удержание долей ({HOLD_DAYS + 1}-й день) — "
                   f"{n_out} незапущенных площадок вне раскладки, их объём ушёл запущенным")
    by = {}
    for c in changes:
        by[c["reason"]] = by.get(c["reason"], 0) + 1
    for code, n in sorted(by.items(), key=lambda x: -x[1]):
        out.append(f"{REASONS.get(code, code)}: {n}")
    return out


# ── сбор данных ───────────────────────────────────────────────────────────────

def dsp_unavailable(kind: str) -> dict:
    """Строка проверок: сверка среза с сырьём DSP пропущена, потому что база DSP недоступна."""
    return {"level": WARNING, "code": "dsp_db_unavailable",
            "title": "База DSP недоступна — сверка среза с сырьём пропущена",
            "count": 1, "examples": [kind]}


def gather(db, dsp_db, today: date) -> dict:
    """Входы `evaluate` из базы: РК с планом, планы и факт площадок, срез DSP против сырья."""
    from app.ad.build import CAMPAIGN_CLOSED
    from app.ad.stat_sources import fact_sources
    rows = db.execute(text("""
        SELECT c.id, d.code, c.plan_show, c.date_start, c.date_end, c.status,
               c.ms_campaign_xxhash IS NOT NULL AS in_dsp,
               (SELECT count(*) FROM ad_campaign_creative cc WHERE cc.campaign_id = c.id
                  AND coalesce(cc.ms_creative_xxhash, '') <> '') AS creatives,
               p.plan_show AS pl_plan,
               (SELECT coalesce(sum(s.shows), 0) FROM ad_campaign_stat s
                 WHERE s.placement_id = p.id AND s.source = ANY(:src)) AS pl_fact
          FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id
          LEFT JOIN ad_campaign_placement p ON p.campaign_id = c.id
         WHERE c.plan_show > 0 AND (c.status IS NULL OR c.status <> ALL(:closed))
         ORDER BY c.id"""), {"src": fact_sources(), "closed": list(CAMPAIGN_CLOSED)}).mappings().all()
    camps: dict = {}
    for r in rows:
        c = camps.setdefault(r["id"], {k: r[k] for k in (
            "code", "plan_show", "date_start", "date_end", "status", "in_dsp", "creatives")}
            | {"plans": [], "facts": []})
        c["plans"].append(r["pl_plan"])
        c["facts"].append(int(r["pl_fact"] or 0))
    # Сбой базы DSP стоит одной проверки (сверки среза с сырьём), а не всех: раньше он
    # поднимался наверх и `_checks` заменял весь список строкой «проверки не выполнены».
    # В журнал уходит только вид ошибки: в тексте ошибок драйвера бывают адрес и параметры.
    dsp_error = None
    try:
        slice_vs_raw = _slice_vs_raw(db, dsp_db, today - timedelta(days=1))
    except Exception as e:  # noqa: BLE001
        slice_vs_raw, dsp_error = None, type(e).__name__
        # Откатываем ОБЕ сессии: `_slice_vs_raw` читает и нашу базу, и после её сбоя прогон
        # не должен остаться в оборванной транзакции (журнал, факт на дату упали бы следом).
        for s in (db, dsp_db):
            try:
                s.rollback()
            except Exception:  # noqa: BLE001
                pass
    return {"campaigns": list(camps.values()), "slice_vs_raw": slice_vs_raw,
            "dsp_error": dsp_error}


def _known_creatives(db) -> list:
    return [r[0].upper() for r in db.execute(text(
        "SELECT DISTINCT ms_creative_xxhash FROM ad_campaign_creative "
        "WHERE coalesce(ms_creative_xxhash, '') <> ''")).all()]


def _slice_vs_raw(db, dsp_db, day: date) -> Optional[Tuple[int, int]]:
    """Показы DSP за день: наш срез против сырья. Нет базы DSP — проверка не делается."""
    if dsp_db is None:
        return None
    ours = db.execute(text("SELECT coalesce(sum(shows), 0) FROM ad_campaign_stat "
                           "WHERE source = 'dsp' AND date = :d"), {"d": day}).scalar()
    raw = dsp_db.execute(text(
        "SELECT coalesce(sum(shows), 0) FROM dsp_stat_raw WHERE upper(ms_creative_xxhash) = ANY(:x) "
        "AND (ts AT TIME ZONE 'Europe/Moscow')::date = :d"),
        {"d": day, "x": _known_creatives(db)}).scalar()
    return int(ours or 0), int(raw or 0)
