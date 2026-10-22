# -*- coding: utf-8 -*-
"""Проверка РК: светофоры заведения, сбора статистики и раскладки по каждой идущей РК.

Экран «Трафики → Проверка РК» (владелец 11.10.2026) и скелет будущих алертов о проблемах РК.
Таблица результатов — `rk_check_result` (миграция 2026-10-11_rk_check_result.sql), хранение три
календарных месяца: прогон сам подметает старше `retention.cutoff()`.

    docker exec finance_backend python -m app.ad.rk_check            # ночной прогон (крон после Weborama)

ПРАВИЛО: ничего нового не изобретаем. Расхождение с Weborama — те же `stat_sources.comparable` /
`mismatch_pct` / `mismatch_level` / `goal_limit`, что на дашборде трафика; темп — `flight.forecast_of`;
статус РК — `flight.campaign_chain_status` по запущенным площадкам. Своя здесь только обвязка.

Проверка — чистая функция от собранных данных РК (`Camp`), без базы: так её проверяют тестом.
Нечего проверять (нет пикселя в сделке, нет плана) — уровень `skip`, а не зелёный: зелёный
говорит «проверили и в порядке», пропуск — «проверить нечем».
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text

import app.model_registry  # noqa: F401 — крон отдельным процессом: все таблицы для внешних ключей (аудит 21.10.2026)

log = logging.getLogger("finance.rk_check")

GREEN, YELLOW, RED, SKIP = "green", "yellow", "red", "skip"
_RANK = {SKIP: 0, GREEN: 1, YELLOW: 2, RED: 3}
_FROM_MISMATCH = {"ok": GREEN, "warn": YELLOW, "bad": RED}

# Группы колонок экрана и их проверки (порядок = порядок в строке).
GROUPS = (("setup", "Заведение"), ("collect", "Сбор"), ("layout", "Раскладка"))
# ключ → (группа, заголовок)
CHECKS = {
    "stage_sync": ("setup", "Сделка в «В размещении», когда РК крутит"),
    "dsp_campaign": ("setup", "Кампания заведена в DSP"),
    "launch": ("setup", "Площадки запущены"),
    "ready_to_start": ("setup", "Готовые площадки не запущены"),
    "awaiting_dsp": ("setup", "Согласованные площадки не выгружены в DSP"),
    "pixel": ("setup", "Пиксель Weborama"),
    "erid": ("setup", "ЕРИД у креативов"),
    "fact_fresh": ("collect", "Свежесть статистики"),
    "delivery": ("collect", "Открутка за вчера"),
    "gaps": ("collect", "Пропущенные дни"),
    "wr_mismatch": ("collect", "Расхождение с Weborama"),
    "adfox_fresh": ("collect", "Adfox загружен"),
    "shares": ("layout", "Доли и план площадок"),
    "pace": ("layout", "Темп к плану"),
}

# Что делать по проверке: подпись ссылки и блок раскрытой РК на дашборде трафика, куда она ведёт
# (экран сводки не уводит на новую страницу — владелец 11.10.2026).
ACTIONS = {
    "stage_sync": ("перевести сделку", "deal"),
    "dsp_campaign": ("завести в DSP", "dsp"),
    "launch": ("включить площадки", "placements"),
    "ready_to_start": ("запустить готовые", "start"),
    "awaiting_dsp": ("выгрузить в DSP", "dsp"),
    "pixel": ("площадки без пикселя", "pixel"),
    "erid": ("креативы без ЕРИД", "placements"),
    "fact_fresh": ("проверить съём", "stats"),
    "delivery": ("площадки без показов", "placements"),
    "gaps": ("посмотреть площадки", "placements"),
    "wr_mismatch": ("сверить код", "wr"),
    "adfox_fresh": ("загрузить Adfox", "adfox"),
    "shares": ("перераспределить", "alloc"),
    "pace": ("перераспределить", "alloc"),
}
# Общая причина: проблема этих проверок у стольких РК сразу — это одна системная поломка (встал
# съём, не загрузили Adfox), а не N разных. Такие строки приглушаются и уровень РК не поднимают.
COMMON_KEYS = ("adfox_fresh", "fact_fresh")
COMMON_MIN = 3
# В каких фазах РК проверка не имеет смысла (причина показывается человеку как есть).
GATES = {
    "before": {"fact_fresh": "Флайт ещё не начался", "delivery": "Флайт ещё не начался",
               "gaps": "Флайт ещё не начался", "wr_mismatch": "Флайт ещё не начался",
               "pace": "Флайт ещё не начался — темп появится после первого дня"},
    "paused": {"ready_to_start": "РК на паузе или остановлена", "awaiting_dsp": "РК на паузе или остановлена", "fact_fresh": "РК на паузе или остановлена — открутка не ожидается",
               "delivery": "РК на паузе или остановлена — открутка не ожидается",
               "gaps": "РК на паузе или остановлена", "pace": "РК на паузе или остановлена — темп не считается"},
}
MANUAL_OFF = ("пауза", "остановлена")
START_SOON_DAYS = 3                     # «до старта» — когда уже пора запускать площадки

PACE_RED, PACE_YELLOW = 0.80, 0.95      # прогноз ÷ план
SHARE_TOLERANCE = 0.02                  # допуск суммы долей и суммы планов площадок
RUNNING_STAGE = "В размещении"           # имя стадии: `routers/traffic_dashboard.RUNNING_STAGE`
RECENT_DAYS = 3                         # «давно ли открутка» — окно для пикселя и откруток


def today_msk() -> date:
    return datetime.now(ZoneInfo("Europe/Moscow")).date()


@dataclass
class Item:
    """Строка про площадку внутри проверки (пишется только для не-зелёных)."""
    placement_id: int
    level: str
    message: str
    value: dict = field(default_factory=dict)


@dataclass
class Result:
    level: str
    message: str
    value: dict = field(default_factory=dict)
    items: List[Item] = field(default_factory=list)


@dataclass
class Camp:
    """Всё, что нужно проверкам, по одной РК. Собирает `load`; в тестах строится руками."""
    id: int
    code: str
    title: str
    status: str
    date_start: Optional[date]
    date_end: Optional[date]
    plan_show: Optional[float]
    ms_hash: Optional[str]
    goals: dict
    px_on: bool
    px_mode: str                      # own | external
    px_tag: bool
    as_of: date
    stale: bool
    placements: List[dict] = field(default_factory=list)   # id, name, status, pixel, plan_show, share, creatives[{hash, erid}]
    dsp_days: Dict[int, Dict[date, int]] = field(default_factory=dict)   # площадка → день → показы DSP
    own_by_pl: Dict[int, int] = field(default_factory=dict)              # факт OWN по площадкам до среза
    own_total: int = 0
    ver: dict = field(default_factory=dict)                              # {shows, by_placement}
    adfox_last: Optional[date] = None
    stage_name: str = ""                  # стадия сделки сейчас
    stage_behind: bool = False            # стадия РАНЬШЕ «В размещении» по лестнице воронки
    today: Optional[date] = None          # календарный день прогона (МСК); нет — по срезу статистики
    last_stat: Optional[date] = None      # последний день факта OWN по этой РК
    awaiting: List[dict] = field(default_factory=list)   # «ждёт запуска», согласованы, но креатив ещё не в DSP
    ready: List[dict] = field(default_factory=list)   # площадки «ждёт запуска», которые можно включить прямо сейчас (id, name)

    @property
    def phase(self) -> str:
        """paused — ручная пауза/стоп; before — флайт не начался; live — идёт."""
        if self.status in MANUAL_OFF:
            return "paused"
        t = self.today or self.as_of
        return "before" if self.date_start and self.date_start > t else "live"

    def running(self) -> List[dict]:
        return [p for p in self.placements if p["status"] == "запущен"]

    def name(self, pid: int) -> str:
        return next((p["name"] for p in self.placements if p["id"] == pid), str(pid))


def _fmt(n) -> str:
    return f"{int(round(n)):,}".replace(",", " ")


def _worst(levels) -> str:
    return max(levels, key=lambda lv: _RANK[lv], default=SKIP)


# ── проверки ────────────────────────────────────────────────────────────────

def check_stage_sync(c: Camp) -> Result:
    """РК крутит в нашей DSP — сделка обязана стоять в «В размещении» или дальше.

    Хранимый `ad_campaign.status` для «ожидает сборки / готова / запущена» НЕ сравниваем: это
    заглушка со дня создания РК, экраны трафика считают статус по площадкам на лету
    (`flight.effective_campaign_status`), и устаревшее значение ничего не останавливает
    (замер 11.10.2026: 9 крутящих РК с «ожидает сборки» в базе, у всех сделка уже в размещении)."""
    live = [p for p in c.running() if _in_dsp(c, p)]
    if not live or not c.ms_hash:
        return Result(SKIP, "В нашей DSP никто не запущен", {"stage": c.stage_name})
    val = {"stage": c.stage_name, "running": len(live)}
    if c.stage_behind:
        return Result(RED, f"РК крутит ({len(live)} площ.), а сделка на стадии «{c.stage_name}»: перевод в "
                           f"«В размещении» не случился (отказ по требованиям стадии или запуск мимо кнопок)", val)
    return Result(GREEN, f"РК крутит, сделка на стадии «{c.stage_name}»", val)


def check_launch(c: Camp) -> Result:
    """Флайт идёт, а ни одна площадка не запущена — показов не будет; до старта — напоминание за несколько дней."""
    n, run = len(c.placements), len(c.running())
    val = {"placements": n, "running": run}
    if c.phase == "paused":
        return Result(SKIP, f"РК {c.status}: площадки не должны крутить", val)
    if run:
        return Result(GREEN, f"Запущено {run} из {n} площадок", val)
    if c.phase == "before":
        left = (c.date_start - (c.today or c.as_of)).days
        if left <= START_SOON_DAYS:
            return Result(YELLOW, f"До старта {left} дн., а запущено 0 из {n} площадок", {**val, "days_left": left})
        return Result(SKIP, f"Флайт с {c.date_start:%d.%m} — запуск ещё не нужен", val)
    return Result(RED, f"Флайт идёт, а ни одна из {n} площадок не запущена — показов не будет", val)


def check_ready_to_start(c: Camp) -> Result:
    """Площадки согласованы, креатив в DSP, а они не включены — трафик может запустить, и это не видно.

    «Готова» — то же правило, что у кнопки «Запустить РК» (`traffic_dashboard.start_block` +
    `mass_start_skip`): статус «ждёт запуска», есть согласованный креатив, он выгружен в DSP, площадка не
    внешняя. Пауза — решение человека, её не подсвечиваем."""
    n, rd = len(c.placements), len(c.ready)
    if not rd:
        return Result(GREEN, "Готовых невключённых площадок нет", {"ready": 0})
    if c.phase == "before" and (c.date_start - (c.today or c.as_of)).days > START_SOON_DAYS:
        return Result(SKIP, f"Флайт с {c.date_start:%d.%m} — запуск ещё не нужен", {"ready": rd})
    names = ", ".join(p["name"] for p in c.ready[:3]) + (f" и ещё {rd - 3}" if rd > 3 else "")
    items = [Item(p["id"], YELLOW, "Готова к запуску: креатив согласован и в DSP, площадка не включена",
                  {"name": p["name"]}) for p in c.ready]
    return Result(YELLOW, f"Готовы к запуску, но не включены: {rd} из {n} — {names}",
                  {"ready": rd, "placements": n}, items)


def check_awaiting_dsp(c: Camp) -> Result:
    """Площадка согласована («ждёт запуска»), а креатив в DSP не выгружен — запустить её нечем, пока трафик
    не нажмёт «В DSP». Висит незамеченной: статус у площадки хороший, показов нет."""
    aw = len(c.awaiting)
    if not aw:
        return Result(GREEN, "Все согласованные площадки выгружены в DSP", {"awaiting": 0})
    if c.phase == "before" and (c.date_start - (c.today or c.as_of)).days > START_SOON_DAYS:
        return Result(SKIP, f"Флайт с {c.date_start:%d.%m} — выгрузка ещё не горит", {"awaiting": aw})
    names = ", ".join(p["name"] for p in c.awaiting[:3]) + (f" и ещё {aw - 3}" if aw > 3 else "")
    items = [Item(p["id"], YELLOW, "Согласована, креатив не выгружен в DSP", {"name": p["name"]}) for p in c.awaiting]
    return Result(YELLOW, f"Согласованы, но не выгружены в DSP: {aw} — {names}", {"awaiting": aw}, items)


def check_dsp_campaign(c: Camp) -> Result:
    run = len(c.running())
    if not run:
        return Result(SKIP, "Запущенных площадок нет", {})
    if not c.ms_hash:
        return Result(RED, "Есть запущенные площадки, а кампании в DSP нет (нет хеша)", {"running": run})
    return Result(GREEN, "Кампания есть в DSP", {"hash": c.ms_hash})


def _delivers_recently(c: Camp, pid: int) -> bool:
    days = c.dsp_days.get(pid) or {}
    return any(d > c.as_of - timedelta(days=RECENT_DAYS) and (n or 0) > 0 for d, n in days.items())


def check_pixel(c: Camp) -> Result:
    if not c.px_on:
        return Result(SKIP, "В сделке пиксель Weborama не включён", {})
    if c.px_mode == "external":
        if not c.px_tag:
            return Result(RED, "Выбран внешний пиксель, а тег не загружен", {"mode": "external"})
        return Result(GREEN, "Внешний пиксель, тег загружен (вставку заводит сеть)", {"mode": "external"})
    items = [Item(p["id"], RED, "Площадка откручивает, а пикселя Weborama у неё нет",
                  {"name": p["name"]})
             for p in c.running() if not p["pixel"] and _delivers_recently(c, p["id"])]
    if items:
        return Result(RED, f"Нет пикселя у откручивающих площадок: {len(items)}", {"count": len(items)}, items)
    return Result(GREEN, "У откручивающих площадок пиксель стоит", {"mode": "own"})


def check_erid(c: Camp) -> Result:
    items = []
    for p in c.running():
        miss = [x for x in p["creatives"] if x.get("hash") and not x.get("erid")]
        if miss:
            items.append(Item(p["id"], RED, f"Креативов без ЕРИД: {len(miss)}", {"name": p["name"], "count": len(miss)}))
    if items:
        return Result(RED, f"Без ЕРИД у креативов в DSP: площадок {len(items)}", {"count": len(items)}, items)
    if not any(x.get("hash") for p in c.running() for x in p["creatives"]):
        return Result(SKIP, "Креативов в DSP у запущенных площадок нет", {})
    return Result(GREEN, "У всех креативов в DSP есть ЕРИД", {})


def check_fact_fresh(c: Camp) -> Result:
    """Статистика по РК не отстала от общего среза. Общий срез встал — красный у всех (общая причина)."""
    if c.stale:
        return Result(RED, f"Статистика встала на {c.as_of:%d.%m}: ночной съём не отработал", {"as_of": str(c.as_of)})
    live = [p for p in c.running() if _in_dsp(c, p)]
    val = {"as_of": str(c.as_of), "last": str(c.last_stat) if c.last_stat else None}
    if not live:
        return Result(GREEN, f"Срез статистики за {c.as_of:%d.%m}", val)
    if c.last_stat is None:
        return Result(RED, "Площадки запущены, а статистики по РК нет ни за один день", val)
    lag = (c.as_of - c.last_stat).days
    if lag >= 2:
        return Result(RED, f"Статистики нет {lag} дн. — последние данные от {c.last_stat:%d.%m}", {**val, "lag": lag})
    if lag == 1:
        return Result(YELLOW, f"Статистики за {c.as_of:%d.%m} нет — последние данные от {c.last_stat:%d.%m}", {**val, "lag": lag})
    return Result(GREEN, f"Статистика за {c.as_of:%d.%m} на месте", val)


def _in_dsp(c: Camp, p: dict) -> bool:
    return any(x.get("hash") for x in p["creatives"]) or bool(c.dsp_days.get(p["id"]))


def check_delivery(c: Camp) -> Result:
    live = [p for p in c.running() if _in_dsp(c, p)]
    if not live:
        return Result(SKIP, "Запущенных площадок в DSP нет", {})
    items = []
    for p in live:
        if (c.dsp_days.get(p["id"]) or {}).get(c.as_of, 0) <= 0:
            items.append(Item(p["id"], YELLOW, f"Нет показов DSP за {c.as_of:%d.%m}", {"name": p["name"]}))
    if len(items) == len(live):
        return Result(RED, f"Ни одна из {len(live)} площадок не откручивала за {c.as_of:%d.%m}", {"zero": len(items)}, items)
    if items:
        return Result(YELLOW, f"Без показов за {c.as_of:%d.%m}: {len(items)} из {len(live)}", {"zero": len(items), "of": len(live)}, items)
    return Result(GREEN, f"Откручивают все {len(live)} площ.", {"of": len(live)})


def check_gaps(c: Camp) -> Result:
    items = []
    for p in c.running():
        days = {d for d, n in (c.dsp_days.get(p["id"]) or {}).items() if (n or 0) > 0}
        if len(days) < 2:
            continue
        first, last = min(days), max(days)
        hole = [first + timedelta(days=i) for i in range((last - first).days + 1)
                if first + timedelta(days=i) not in days]
        if hole:
            items.append(Item(p["id"], YELLOW, "Дни без показов внутри периода: " + ", ".join(f"{d:%d.%m}" for d in hole[:6]),
                              {"name": p["name"], "days": [str(d) for d in hole]}))
    if items:
        return Result(YELLOW, f"Есть «дыры» в днях у площадок: {len(items)}", {"count": len(items)}, items)
    return Result(GREEN, "Дыр в днях нет", {})


def check_wr_mismatch(c: Camp) -> Result:
    from app.ad import stat_sources as S
    own, wr, covered = S.comparable(c.own_total, c.own_by_pl, c.ver)
    if wr is None or not own:
        why = "внешний пиксель: Weborama вводится вручную" if c.px_on and c.px_mode == "external" else "Weborama площадки не мерила"
        return Result(SKIP, f"Сверять нечем: {why}", {})
    pct = S.mismatch_pct(own, wr)
    limit = S.goal_limit(c.goals)
    lvl = S.mismatch_level(pct, limit)
    items = []
    by = (c.ver or {}).get("by_placement") or {}
    for pid, w in by.items():
        o = c.own_by_pl.get(pid)
        pp = S.mismatch_pct(o, w) if o else None
        pl = S.mismatch_level(pp, limit) if pp is not None else None
        if pl and pl["level"] != "ok":
            items.append(Item(pid, _FROM_MISMATCH[pl["level"]], f"{pp:+g} % ({_fmt(o)} против {_fmt(w)})",
                              {"name": c.name(pid), "pct": pp, "own": o, "wr": w}))
    val = {"pct": pct, "own": own, "wr": wr, "limit": limit, "covered": covered}
    return Result(_FROM_MISMATCH[lvl["level"]],
                  f"{pct:+g} % (наш {_fmt(own)}, Weborama {_fmt(wr)}); {lvl['hint']}", val, items)


def check_adfox_fresh(c: Camp) -> Result:
    if not c.adfox_last:
        return Result(SKIP, "Adfox по этой РК не загружался", {})
    if c.adfox_last < c.as_of:
        return Result(YELLOW, f"Adfox загружен по {c.adfox_last:%d.%m}, срез статистики — {c.as_of:%d.%m}",
                      {"adfox_last": str(c.adfox_last)})
    return Result(GREEN, f"Adfox загружен по {c.adfox_last:%d.%m}", {"adfox_last": str(c.adfox_last)})


def check_shares(c: Camp) -> Result:
    inplan = [p for p in c.placements if p["status"] in ("запущен", "пауза") and p.get("share")]
    if not c.plan_show:
        return Result(SKIP, "Нет плана — раскладывать нечего", {})
    if not inplan:
        return Result(SKIP, "Раскладывать нечего", {})
    sh = sum(p["share"] or 0 for p in inplan)
    pl = sum(p["plan_show"] or 0 for p in inplan)
    val = {"share_sum": round(sh, 4), "plan_sum": round(pl), "plan": round(c.plan_show)}
    if abs(sh - 1) > SHARE_TOLERANCE:
        return Result(YELLOW, f"Сумма долей площадок {sh:.0%}, а должна быть 100 %", val)
    if abs(pl - c.plan_show) / c.plan_show > SHARE_TOLERANCE:
        return Result(YELLOW, f"Сумма планов площадок {_fmt(pl)} не равна плану РК {_fmt(c.plan_show)}", val)
    return Result(GREEN, "Доли и планы площадок складываются в план РК", val)


def check_pace(c: Camp) -> Result:
    from app.ad import flight
    fl = flight.flight_of(c.date_start, c.date_end, c.as_of)
    if not c.plan_show:
        return Result(SKIP, "Нет плана — темп не считается", {})
    if fl is None or fl.done < 3:
        return Result(SKIP, "Мало данных для темпа (меньше трёх дней)", {})
    fc = flight.forecast_of(c.plan_show, c.own_total, fl)
    ratio = fc / c.plan_show if fc is not None else None
    if ratio is None:
        return Result(SKIP, "Прогноза нет", {})
    val = {"fact": c.own_total, "forecast": round(fc), "plan": round(c.plan_show), "ratio": round(ratio, 3)}
    text_ = f"Прогноз {_fmt(fc)} из {_fmt(c.plan_show)} ({ratio:.0%})"
    if ratio < PACE_RED:
        return Result(RED, text_ + " — недокрут", val)
    if ratio < PACE_YELLOW:
        return Result(YELLOW, text_ + " — чуть ниже плана", val)
    return Result(GREEN, text_, val)


RUNNERS: Dict[str, Callable[[Camp], Result]] = {
    "stage_sync": check_stage_sync, "dsp_campaign": check_dsp_campaign, "launch": check_launch, "ready_to_start": check_ready_to_start, "awaiting_dsp": check_awaiting_dsp, "pixel": check_pixel,
    "erid": check_erid, "fact_fresh": check_fact_fresh, "delivery": check_delivery, "gaps": check_gaps,
    "wr_mismatch": check_wr_mismatch, "adfox_fresh": check_adfox_fresh, "shares": check_shares,
    "pace": check_pace,
}


def run_checks(c: Camp) -> Dict[str, Result]:
    """Все проверки одной РК. Упавшая проверка не валит остальные — она сама красная."""
    out = {}
    gates = GATES.get(c.phase, {})
    for key, fn in RUNNERS.items():
        if key in gates:
            out[key] = Result(SKIP, gates[key], {"phase": c.phase})
            continue
        try:
            out[key] = fn(c)
        except Exception as e:  # noqa: BLE001 — сбой проверки сам должен быть виден
            log.exception("rk_check %s %s", c.code, key)
            out[key] = Result(RED, f"Проверка не отработала: {e.__class__.__name__}", {})
    return out


def group_levels(results: Dict[str, Result]) -> Dict[str, str]:
    """Худший уровень по каждой группе колонок."""
    out = {}
    for g, _t in GROUPS:
        out[g] = _worst([r.level for k, r in results.items() if CHECKS[k][0] == g])
    return out


# ── сбор данных ─────────────────────────────────────────────────────────────

def load(db, today: Optional[date] = None, campaign_id: Optional[int] = None) -> List[Camp]:
    from app.ad import build, stat_sources as S
    today = today or today_msk()
    as_of = S.fact_as_of(db, today)
    stale = S.is_stale(as_of, today)
    q = """SELECT c.id, d.code, d.title, c.status, c.date_start, c.date_end, c.plan_show, c.ms_campaign_xxhash,
                  d.id AS deal_id, d.weborama_pixel, coalesce(d.weborama_pixel_mode, 'own') AS px_mode,
                  (d.weborama_pixel_tag IS NOT NULL AND d.weborama_pixel_tag <> '') AS px_tag
             FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id
            WHERE (c.status IS NULL OR NOT (c.status = ANY(:closed)))
              AND c.date_start <= CAST(:t AS date) + 14 AND (c.date_end IS NULL OR c.date_end >= CAST(:t AS date) - 2)
              AND EXISTS (SELECT 1 FROM ad_campaign_placement p WHERE p.campaign_id = c.id)"""
    params = {"closed": list(build.CAMPAIGN_CLOSED), "t": today}
    if campaign_id is not None:
        q += " AND c.id = :cid"
        params["cid"] = campaign_id
    rows = db.execute(text(q + " ORDER BY c.id"), params).mappings().all()
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    goals = build.deal_goals_many(db, {r["deal_id"] for r in rows})
    camps = {r["id"]: Camp(id=r["id"], code=r["code"] or str(r["id"]), title=r["title"] or "", status=r["status"] or "",
                           date_start=r["date_start"], date_end=r["date_end"], plan_show=r["plan_show"],
                           ms_hash=r["ms_campaign_xxhash"], goals=goals.get(r["deal_id"]) or {}, px_on=bool(r["weborama_pixel"]),
                           px_mode=r["px_mode"], px_tag=bool(r["px_tag"]), as_of=as_of, stale=stale, today=today) for r in rows}
    from app.sales import catalog as catalog_mod
    cat = catalog_mod.Catalog(db)
    target = next((st for st in cat.stages if st.name == RUNNING_STAGE), None)
    for r in db.execute(text("SELECT c.id, d.our_stage_id FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id "
                             "WHERE c.id = ANY(:i)"), {"i": ids}).all():
        cur = cat.by_id.get(r[1])
        camps[r[0]].stage_name = cur.name if cur else ""
        camps[r[0]].stage_behind = bool(cur and target and cat.is_before(r[1], target.id))
    pls = {}
    for r in db.execute(text("""SELECT p.id, p.campaign_id, p.publisher_id, p.status, p.weborama_pixel IS NOT NULL AS pixel, p.plan_show, p.share,
                                       coalesce(pb.domain, pb.name) AS name
                                  FROM ad_campaign_placement p JOIN sales_publishers pb ON pb.id = p.publisher_id
                                 WHERE p.campaign_id = ANY(:i) ORDER BY p.id"""), {"i": ids}).mappings().all():
        pl = {"id": r["id"], "name": r["name"], "publisher_id": r["publisher_id"], "status": r["status"], "pixel": bool(r["pixel"]),
              "plan_show": r["plan_show"], "share": r["share"], "creatives": []}
        pls[r["id"]] = pl
        camps[r["campaign_id"]].placements.append(pl)
    _mark_ready(db, rows, camps)
    for r in db.execute(text("""SELECT placement_id, ms_creative_xxhash AS hash, erid FROM ad_campaign_creative
                                 WHERE campaign_id = ANY(:i)"""), {"i": ids}).mappings().all():
        if r["placement_id"] in pls:
            pls[r["placement_id"]]["creatives"].append({"hash": r["hash"], "erid": r["erid"]})
    for r in db.execute(text("""SELECT campaign_id, placement_id, date, source, shows FROM ad_campaign_stat
                                 WHERE campaign_id = ANY(:i) AND date <= :a"""), {"i": ids, "a": as_of}).mappings().all():
        c, src, n = camps[r["campaign_id"]], r["source"], r["shows"] or 0
        pid = r["placement_id"]
        if src == "dsp" and pid is not None:
            c.dsp_days.setdefault(pid, {})[r["date"]] = n
        if src in S.fact_sources():
            if n > 0 and (c.last_stat is None or r["date"] > c.last_stat):
                c.last_stat = r["date"]
            c.own_total += n
            if pid is not None:
                c.own_by_pl[pid] = c.own_by_pl.get(pid, 0) + n
        if S.is_verifier(src):
            slot = c.ver or {"shows": 0, "by_placement": {}}
            c.ver = slot
            slot["shows"] += n
            if pid is not None:
                slot["by_placement"][pid] = slot["by_placement"].get(pid, 0) + n
        if src == "adfox" and (c.adfox_last is None or r["date"] > c.adfox_last):
            c.adfox_last = r["date"]
    return list(camps.values())


def _mark_ready(db, rows, camps: Dict[int, "Camp"]) -> None:
    """Площадки «ждёт запуска», которые трафик может включить сейчас: то же правило, что у кнопки РК."""
    from app.ad.flight import PLACEMENT_READY
    from app.launch_prep import pub_rules
    from app.routers import traffic_dashboard as td
    deal_of = {r["id"]: r["deal_id"] for r in rows}
    for c in camps.values():
        waiting = [p for p in c.placements if p["status"] == PLACEMENT_READY]
        if not waiting:
            continue
        creatives = td._creatives_of(db, c.id)
        keys = {(deal_of[c.id], p["publisher_id"]) for p in waiting}
        modes = pub_rules.placement_modes(db, keys)
        for p in waiting:
            mode = (modes.get((deal_of[c.id], p["publisher_id"])) or {}).get("mode")
            if td.mass_start_skip(mode):
                continue
            why = td.start_block(db, _Shim(deal_of[c.id]), _Shim(deal_of[c.id], p["publisher_id"]),
                                 creatives.get(p["id"], []), mode)
            if not why:
                c.ready.append({"id": p["id"], "name": p["name"]})
            elif "не выгружен в DSP" in why:
                c.awaiting.append({"id": p["id"], "name": p["name"]})


class _Shim:
    """Минимум полей, которые читает `start_block` (когда режим уже известен, он их не трогает)."""
    def __init__(self, deal_id, publisher_id=None):
        self.deal_id, self.publisher_id = deal_id, publisher_id


# ── запись ──────────────────────────────────────────────────────────────────

def save(db, camps: List[Camp], run_date: date, commit: bool = True) -> dict:
    """Результаты прогона за сутки: перезапись сегодняшних строк и уборка старше трёх месяцев."""
    from app import retention
    ids = [c.id for c in camps]
    db.execute(text("DELETE FROM rk_check_result WHERE run_date = :d AND campaign_id = ANY(:i)"), {"d": run_date, "i": ids})
    ins = text("""INSERT INTO rk_check_result (run_date, campaign_id, placement_id, check_key, level, value, message)
                  VALUES (:d, :c, :p, :k, :l, CAST(:v AS jsonb), :m)""")
    counts = {GREEN: 0, YELLOW: 0, RED: 0, SKIP: 0}
    for c in camps:
        res = run_checks(c)
        for key, r in res.items():
            counts[r.level] += 1
            db.execute(ins, {"d": run_date, "c": c.id, "p": None, "k": key, "l": r.level,
                             "v": json.dumps(r.value, ensure_ascii=False, default=str), "m": r.message})
            for it in r.items:
                db.execute(ins, {"d": run_date, "c": c.id, "p": it.placement_id, "k": key, "l": it.level,
                                 "v": json.dumps(it.value, ensure_ascii=False, default=str), "m": it.message})
    swept = db.execute(text("DELETE FROM rk_check_result WHERE run_date < :c"),
                       {"c": retention.cutoff(today_msk()).date()}).rowcount
    if commit:
        db.commit()
    return {"campaigns": len(camps), "levels": counts, "swept": swept, "run_date": str(run_date)}


def run(campaign_id: Optional[int] = None, dry_run: bool = False) -> dict:
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        camps = load(db, campaign_id=campaign_id)
        if dry_run:
            lv = {GREEN: 0, YELLOW: 0, RED: 0, SKIP: 0}
            for c in camps:
                for r in run_checks(c).values():
                    lv[r.level] += 1
            return {"campaigns": len(camps), "levels": lv, "dry_run": True}
        return save(db, camps, today_msk())
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    import sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    out = run(dry_run=a.dry_run)
    print("Проверка РК:", json.dumps(out, ensure_ascii=False))
    sys.exit(0)


# ── сводка для дашборда и общие причины ──────────────────────────────────────

def common_keys(levels_by_campaign: Dict[int, Dict[str, str]]) -> Dict[str, int]:
    """Какие проверки — общая причина: красные/жёлтые у ≥ COMMON_MIN РК сразу → {ключ: число РК}."""
    out = {}
    for key in COMMON_KEYS:
        n = sum(1 for lv in levels_by_campaign.values() if lv.get(key) in (RED, YELLOW))
        if n >= COMMON_MIN:
            out[key] = n
    return out


def build_summary(checks: List[dict], common: Dict[str, int]) -> dict:
    """Сводка одной РК: уровень, три колонки (текст, действие, пипсы). `checks` — строки уровня РК
    {key, level, message}. Общие причины в уровень не входят и помечаются `common`."""
    order = list(CHECKS)
    groups = []
    for gkey, gtitle in GROUPS:
        mine = sorted((x for x in checks if CHECKS[x["key"]][0] == gkey), key=lambda x: order.index(x["key"]))
        real = [x for x in mine if x["key"] not in common]
        bad = sorted((x for x in real if x["level"] in (RED, YELLOW)),
                     key=lambda x: (-_RANK[x["level"]], order.index(x["key"])))
        level = _worst([x["level"] for x in real])
        if bad:
            top = bad[0]
            text = top["message"] + (f" · ещё проверок: {len(bad) - 1}" if len(bad) > 1 else "")
            label, target = ACTIONS[top["key"]]
            action = {"label": label, "target": target, "check": top["key"]}
        else:
            pick = next((x for x in real if x["level"] == GREEN), None) or next(iter(real), None) \
                or next(iter(mine), None)
            text = pick["message"] if pick else "—"
            action = None
        scored = [x for x in mine if x["level"] != SKIP]
        groups.append({
            "key": gkey, "title": gtitle, "level": level, "text": text, "action": action,
            "ok": sum(1 for x in scored if x["level"] == GREEN), "total": len(scored),
            "pips": [{"key": x["key"], "title": CHECKS[x["key"]][1], "level": x["level"],
                      "common": x["key"] in common, "message": x["message"]} for x in mine],
        })
    worst = _worst([g["level"] for g in groups])
    return {"worst": worst, "groups": groups,
            "all_ok": worst in (GREEN, SKIP) and all(g["level"] != YELLOW for g in groups)}
