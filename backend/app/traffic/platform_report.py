"""Отчёт «Площадки × РК» (владелец 05.11.2026): какие площадки проваливаются поперёк ИДУЩИХ РК.

Трафики просили Excel «РК × площадка» и ходили по нему глазами, чтобы найти повторяющиеся провалы и площадки,
которые расходятся с Weborama. Здесь та же таблица считается из того же распределения, что дашборд
(`flight.distribute`, план — записанный ночью, ровно лимиты DSP), и сверху — сводка по площадкам с вердиктом.

Ничего не считает заново: на вход — уже посчитанные строки площадок. Два места, считающие недокрут по-своему,
разошлись бы на первой правке порогов (то же правило, что у `flight.culprits`).

ТЕМП — прогноз к плану (владелец 05.11.2026: «% плана на сегодня», сортировка по показам). Факт к плану не годится:
РК на пятом дне из тридцати всегда «выполнена на 15 %», и молодые РК выглядели бы провалом.
"""
import io
import math
from statistics import median
from typing import Iterable, List, Optional

from app.ad.stat_sources import mismatch_level, mismatch_pct

# Пороги темпа — те же цвета, что у стены дней: норма / просадка / провал.
FAIL, UNDER = 60.0, 90.0

# Вердикт площадки — мой статус для трафиков. Порядок — порядок сортировки сводки.
VERDICTS = {
    "system_fail": "системный провал",
    "system_under": "системный недокрут",
    "spot": "точечный недокрут",
    "ok": "в норме",
    "no_data": "нет данных",
}
_RANK = {k: i for i, k in enumerate(VERDICTS)}
# «Системный» — плохо в половине РК площадки и больше, и РК хотя бы две: одна РК — частный случай, не площадка.
SYSTEMIC_SHARE, SYSTEMIC_MIN = 0.5, 2
# «За порогом» по WR — любое превышение порога сделки (уровни warn и bad `stat_sources.mismatch_level`), как на карточке
# сделки; bad — это уже вдвое выше порога, и считать только его значило бы прятать половину расхождений.
OVER = ("warn", "bad")


def tone(pace: Optional[float]) -> Optional[str]:
    if pace is None:
        return None
    return "fail" if pace < FAIL else ("under" if pace < UNDER else "ok")


def cell(*, rk: dict, row: dict, in_dsp: bool, wr: Optional[int], wr_limit: float, days_left: Optional[int],
         day: Optional[dict] = None) -> dict:
    """Пара «площадка × РК» — одна строка листа «Разбивка» и одна клетка матрицы.
    `day` — сутки среза: {before: факт до дня, on_day: факт за день, days: дней до конца флайта, считая день среза}."""
    plan, fact, fc = row.get("plan_show") or 0, row.get("fact_shows"), row.get("forecast")
    pace = round(fc / plan * 100, 1) if plan and fc is not None else None
    done = round((fact or 0) / plan * 100, 1) if plan else None
    left = max(plan - (fact or 0), 0) if plan else 0
    pct = mismatch_pct(fact, wr) if wr is not None else None
    level = mismatch_level(pct, wr_limit) if pct is not None else None
    dplan = day_goal(plan, (day or {}).get("before"), (day or {}).get("days")) if day else None
    dfact = (day or {}).get("on_day") or 0
    dpct = round(dfact / dplan * 100, 1) if dplan else None
    return {
        **rk,
        "day_plan": dplan, "day_fact": dfact if day else None, "day_pct": dpct, "day_tone": tone(dpct) if dplan else None,
        "placement_id": row.get("id"), "publisher_id": row.get("publisher_id"), "publisher_code": row.get("code"),
        "domain": row.get("domain") or row.get("publisher") or "", "publisher": row.get("publisher"),
        "in_dsp": "DSP" if in_dsp else "вне DSP", "status": row.get("status"),
        "share_pct": round((row.get("share") or 0) * 100, 2),
        "plan": round(plan), "fact": fact or 0, "forecast": fc, "under": max(row.get("under") or 0, 0),
        "pace_pct": pace, "done_pct": done, "tone": tone(pace) if plan else None,
        "wr": wr, "wr_pct": pct, "wr_level": (level or {}).get("level"),
        "need_per_day": math.ceil(left / days_left) if left and days_left else None,
    }


def day_goal(plan, before, days) -> Optional[int]:
    """План площадки на день — правило плана дня РК (`ad/day_plan.past_goals`): (план − факт ДО дня) ÷ дни до конца
    флайта, считая этот; перекрут — ноль. Буст РК здесь не учитывается: он задаётся на РК, а не на площадку."""
    if not days or days <= 0 or not plan:
        return None
    return round(max(0.0, plan - (before or 0)) / days)


def verdict(cells: List[dict]) -> dict:
    rated = [c for c in cells if c.get("tone")]
    if not rated:
        return {"code": "no_data", "label": VERDICTS["no_data"]}
    bad = sum(1 for c in rated if c["tone"] != "ok")
    med = median(c["pace_pct"] for c in rated)
    systemic = len(rated) >= SYSTEMIC_MIN and bad / len(rated) >= SYSTEMIC_SHARE
    code = ("system_fail" if med < FAIL else "system_under") if systemic else ("spot" if bad else "ok")
    return {"code": code, "label": VERDICTS[code]}


def wr_verdict(cells: List[dict]) -> str:
    """Расхождение с Weborama по площадке: «системно», «точечно» или пусто."""
    measured = [c for c in cells if c.get("wr_level")]
    bad = sum(1 for c in measured if c["wr_level"] in OVER)
    if len(measured) >= SYSTEMIC_MIN and bad / len(measured) >= SYSTEMIC_SHARE:
        return "системно"
    return "точечно" if bad else ""


def summarize(cells: Iterable[dict]) -> List[dict]:
    by: dict = {}
    for c in cells:
        by.setdefault(c.get("publisher_id") or c.get("domain"), []).append(c)
    out = []
    for group in by.values():
        rated = [c for c in group if c.get("tone")]
        wr = [c["wr_pct"] for c in group if c.get("wr_pct") is not None]
        days = [c["day_pct"] for c in group if c.get("day_tone")]
        kinds = {c.get("in_dsp") for c in group}
        out.append({
            "publisher_id": group[0].get("publisher_id"), "domain": group[0].get("domain"),
            "code": group[0].get("publisher_code"),
            "in_dsp": kinds.pop() if len(kinds) == 1 else "частично",
            "rk_count": len(group), "rated": len(rated),
            "bad_count": sum(1 for c in rated if c["tone"] != "ok"),
            "fail_count": sum(1 for c in rated if c["tone"] == "fail"),
            "median_pace": round(median(c["pace_pct"] for c in rated), 1) if rated else None,
            "plan": sum(c.get("plan") or 0 for c in group), "fact": sum(c.get("fact") or 0 for c in group),
            "under": sum(c.get("under") or 0 for c in group),
            "day_rated": len(days), "median_day": round(median(days), 1) if days else None,
            "day_bad": sum(1 for c in group if c.get("day_tone") in ("fail", "under")),
            "wr_count": len(wr), "wr_bad": sum(1 for c in group if c.get("wr_level") in OVER),
            "median_wr": round(median(wr), 2) if wr else None,
            "verdict": verdict(group), "wr_verdict": wr_verdict(group),
        })
    return sorted(out, key=lambda s: (_RANK[s["verdict"]["code"]], -s["under"], s["domain"] or ""))


# ── Excel ───────────────────────────────────────────────────────────────────

SUMMARY_COLS = [
    ("Площадка", "domain", 26), ("Код", "in_dsp", 10), ("Статус (вердикт)", "verdict_label", 22),
    ("РК", "rk_count", 6), ("С недокрутом", "bad_count", 13), ("Из них провал", "fail_count", 13),
    ("Медиана % плана", "median_pace", 15), ("Ниже плана дня", "day_bad", 14), ("РК с планом дня", "day_rated", 15),
    ("План", "plan", 12), ("Факт", "fact", 12), ("Недокрут", "under", 12),
    ("РК с WR", "wr_count", 9), ("WR за порогом", "wr_bad", 13), ("Медиана расхождения WR", "median_wr", 20),
    ("Расхождение WR", "wr_verdict", 16),
]
# Колонки «Разбивки» — как в примере трафиков, дальше — то, чего в примере не было.
BREAKDOWN_COLS = [
    ("Название РК", "deal_code", 12), ("Площадка", "domain", 24), ("Код", "in_dsp", 10), ("Доля", "share_pct", 8),
    ("План", "plan", 12), ("Факт", "fact", 12), ("% плана", "done_pct", 9), ("Weborama", "wr", 12),
    ("Расхождения WR", "wr_pct", 15), ("Нужно в день", "need_per_day", 13),
    ("Прогноз", "forecast", 12), ("% плана на сегодня", "pace_pct", 17), ("Недокрут", "under", 12),
    ("План дня", "day_plan", 11), ("Факт дня", "day_fact", 11), ("% плана дня", "day_pct", 12),
    ("Статус площадки", "status", 15), ("Трафик", "traffic", 18), ("Сделка", "deal_title", 40),
]
_FILL = {"fail": "F8D7DA", "under": "FFF3CD", "ok": "D4EDDA"}


def _sheet(ws, title: str, cols, rows, tone_key: Optional[str] = None, tone_col: Optional[str] = None):
    from openpyxl.styles import Font, PatternFill
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    ws.append([c[0] for c in cols])
    for c in ws[3]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([r.get(c[1]) for c in cols])
        fill = _FILL.get(r.get(tone_key)) if tone_key else None
        if fill:
            ws.cell(row=ws.max_row, column=[c[1] for c in cols].index(tone_col) + 1).fill = \
                PatternFill("solid", start_color=fill, end_color=fill)
    for i, c in enumerate(cols, start=1):
        ws.column_dimensions[ws.cell(row=3, column=i).column_letter].width = c[2]
    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A3:{ws.cell(row=3, column=len(cols)).column_letter}{max(ws.max_row, 3)}"


_VERDICT_TONE = {"system_fail": "fail", "system_under": "under", "spot": "under", "ok": "ok"}


def to_xlsx(summary: List[dict], cells: List[dict], as_of: str) -> bytes:
    from openpyxl import Workbook
    from app.xlsx_safe import save_workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Сводка"
    srows = [{**s, "verdict_label": s["verdict"]["label"], "_tone": _VERDICT_TONE.get(s["verdict"]["code"])} for s in summary]
    _sheet(ws, f"Площадки × РК — сводка по идущим РК, срез {as_of}", SUMMARY_COLS, srows, "_tone", "verdict_label")
    order = {s["domain"]: i for i, s in enumerate(summary)}
    brows = sorted(cells, key=lambda c: (c.get("deal_code") or "", order.get(c.get("domain"), 0)))
    _sheet(wb.create_sheet("Разбивка"), f"Площадки × РК — разбивка по РК, срез {as_of}", BREAKDOWN_COLS, brows,
           "tone", "pace_pct")
    buf = io.BytesIO()
    save_workbook(wb, buf)
    return buf.getvalue()
