"""Дашборд руководителя — сводка на один экран.

Отвечает на четыре вопроса, а не показывает всё, что есть: зарабатываем ли, где деньги
остановились, продано ли на будущее, что горит. Спека — `docs/SPEC_дашборд_руководителя.md`.

**Доступ: `require_admin`, а не своё право.** Экран сквозной и для одного человека; ключ
права неизменяем, а новая секция видна в конструкторе ролей и может быть выдана по
неосторожности — здесь это означало бы показать маржу и всю воронку денег. Тот же приём,
что у «Пользователей» и «Журнала действий», и у ярлыка-рубля в панели.

**Своих формул денег здесь нет.** Маржа считается по той же разметке `articles.pl_line`,
что и P&L, дебиторка — тем же `_compute_debt_grouped`, что и реестр. Второй расчёт того же
числа в этом проекте уже расходился с первым, и расхождение выглядит как ошибка отчёта.
"""

import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import require_admin
from ..database import get_db
from ..models import Article, Operation, User
from ..sales.models import (SalesDeal, SalesPublisher, SalesPublisherCounterparty,
                            SalesStage, SalesStagePhase)
from .reports import QUARTER_MONTHS, _compute_debt_grouped

router = APIRouter()

QUARTER_RE = re.compile(r"^(Q[1-4])\s+(\d{4})$")
STALE_DAYS = 30          # сколько дней без правки считаем «сделка стоит»
BOOKING_MONTHS = 6       # горизонт блока загрузки
SERIES_MONTHS = 12       # глубина помесячной динамики маржи
MONTH_NAMES = ["январь", "февраль", "март", "апрель", "май", "июнь",
               "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


def _shift(anchor: str, back: int) -> str:
    """Месяц на `back` назад от `YYYY-MM`."""
    y, m = int(anchor[:4]), int(anchor[5:7]) - back
    while m <= 0:
        m += 12
        y -= 1
    return f"{y}-{m:02d}"


def _months_of(scale: str, anchor: str) -> list:
    """Месяцы выбранного периода. Квартал — три, месяц — один."""
    y, m = int(anchor[:4]), int(anchor[5:7])
    if scale == "quarter":
        q = (m - 1) // 3 + 1
        return [f"{y}-{mm}" for mm in QUARTER_MONTHS[f"Q{q}"]]
    return [f"{y}-{m:02d}"]


def _period_label(scale: str, months: list) -> str:
    y = months[0][:4]
    if scale == "quarter":
        return f"{(int(months[0][5:7]) - 1) // 3 + 1} квартал {y}"
    return f"{MONTH_NAMES[int(months[0][5:7]) - 1].capitalize()} {y}"


def _pl_by_month(db: Session, months: set) -> dict:
    """{месяц: {строка P&L: {income, expense}}} — ОДНИМ проходом по операциям.

    Квартальная строка операции раскладывается на три месяца равными долями: так же, как в
    отчётах. Иначе дашборд и P&L показали бы разные числа на одних данных, и расхождение
    выглядело бы как ошибка расчёта.

    Проход один намеренно: помесячная динамика за год — это двенадцать точек, и запрос на
    каждую превратил бы экран в тринадцать полных сканов таблицы операций.
    """
    rows = (db.query(Operation.period, Article.pl_line,
                     func.sum(Operation.income).label("inc"),
                     func.sum(Operation.expense).label("exp"))
            .outerjoin(Article, Article.id == Operation.article_id)
            .group_by(Operation.period, Article.pl_line).all())
    out = {mo: {} for mo in months}
    for period, line, inc, exp in rows:
        if not period:
            continue
        qm = QUARTER_RE.match(period)
        if qm:
            quarter, year = qm.group(1), qm.group(2)
            targets = [f"{year}-{mm}" for mm in QUARTER_MONTHS[quarter]]
            share = 1 / 3.0
        else:
            targets, share = [period], 1.0
        key = line or "unmarked"
        for mo in targets:
            if mo not in out:
                continue
            cur = out[mo].setdefault(key, {"income": 0.0, "expense": 0.0})
            cur["income"] += float(inc or 0) * share
            cur["expense"] += float(exp or 0) * share
    return out


def _sum_lines(per_month: dict, months: list) -> dict:
    acc = {}
    for mo in months:
        for line, v in per_month.get(mo, {}).items():
            cur = acc.setdefault(line, {"income": 0.0, "expense": 0.0})
            cur["income"] += v["income"]
            cur["expense"] += v["expense"]
    return acc


def _margin_of(acc: dict) -> dict:
    """Итоги P&L по набору строк.

    Два признака, а не один. `has_data` — было ли вообще движение, `has_revenue` — была ли
    проведена ВЫРУЧКА. Разница не косметическая: на 06.09.2026 у августа есть себестоимость
    и нет выручки, и по одному флагу экран нарисовал бы отрицательную маржу, хотя верное
    утверждение — «месяц ещё не закрыт». Пустое в проекте рисуется прочерком, ноль — нулём.
    """
    revenue = acc.get("revenue", {}).get("income", 0.0)
    cogs = acc.get("cogs", {}).get("expense", 0.0)
    opex = acc.get("opex", {}).get("expense", 0.0)
    marketing = acc.get("marketing", {}).get("expense", 0.0)
    gross = revenue - cogs
    return {
        "has_data": bool(revenue or cogs),
        "has_revenue": bool(revenue),
        "revenue": round(revenue, 2), "cogs": round(cogs, 2), "gross": round(gross, 2),
        "gross_pct": round(gross / revenue * 100, 1) if revenue else None,
        "opex": round(opex, 2), "marketing": round(marketing, 2),
        "ebitda": round(gross - opex - marketing, 2),
    }


def _funnel(db: Session) -> list:
    """Лестница стадий как она заведена в справочнике, а не выдуманная мной.

    У стадии есть фаза и денежный слой — берём их. Нули показываются: пустая ступень это и
    есть находка, ради которой блок существует. На 06.09.2026 вся закрывающая половина
    (Согласование ДС, Подготовка закрывающих, ЭДО, Отчёты в ОРД, Оплата) стоит в нуле, а
    сделки оказываются сразу в архиве — значит ступени не проходят, а перепрыгивают.
    """
    rows = (db.query(SalesStage.id, SalesStage.name, SalesStage.sort_order,
                     SalesStage.money_layer, SalesStage.is_terminal, SalesStage.is_lost,
                     SalesStagePhase.name.label("phase"),
                     SalesStagePhase.sort_order.label("phase_order"),
                     func.count(SalesDeal.id).label("deals"),
                     func.coalesce(func.sum(SalesDeal.amount), 0).label("amount"))
            .join(SalesStagePhase, SalesStagePhase.id == SalesStage.phase_id)
            .outerjoin(SalesDeal, SalesDeal.our_stage_id == SalesStage.id)
            .group_by(SalesStage.id, SalesStage.name, SalesStage.sort_order,
                      SalesStage.money_layer, SalesStage.is_terminal, SalesStage.is_lost,
                      SalesStagePhase.name, SalesStagePhase.sort_order)
            .order_by(SalesStagePhase.sort_order, SalesStage.sort_order).all())
    return [{"stage": r.name, "phase": r.phase, "layer": r.money_layer,
             "terminal": bool(r.is_terminal), "lost": bool(r.is_lost),
             "deals": r.deals, "amount": float(r.amount or 0)} for r in rows]


def _next_month(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=8)).replace(day=1)


def _booking(db: Session, today: date) -> dict:
    """Продано по месяцам флайта плюс СОПОСТАВИМАЯ точка прошлого года.

    Сравнивается не с итогом прошлого года, а с тем, сколько было продано к той же
    календарной дате: итог против незавершённого месяца — сравнение ни о чём.
    """
    start = date(today.year, today.month, 1)
    end = start
    for _ in range(BOOKING_MONTHS):
        end = _next_month(end)

    def by_month(a, b, created_before=None):
        q = (db.query(func.to_char(SalesDeal.period_from, "YYYY-MM").label("mo"),
                      func.count(SalesDeal.id).label("deals"),
                      func.coalesce(func.sum(SalesDeal.amount), 0).label("amount"))
             .filter(SalesDeal.amount > 0,
                     SalesDeal.period_from >= a, SalesDeal.period_from < b))
        if created_before is not None:
            q = q.filter(SalesDeal.date_create <= created_before)
        return {r.mo: {"deals": r.deals, "amount": float(r.amount or 0)}
                for r in q.group_by("mo").all()}

    prev_a, prev_b = start.replace(year=start.year - 1), end.replace(year=end.year - 1)
    now = by_month(start, end)
    prev_same = by_month(prev_a, prev_b, created_before=today.replace(year=today.year - 1))
    prev_total = by_month(prev_a, prev_b)

    months, cur = [], start
    while cur < end:
        key, prev_key = cur.strftime("%Y-%m"), cur.replace(year=cur.year - 1).strftime("%Y-%m")
        months.append({"month": key,
                       "deals": now.get(key, {}).get("deals", 0),
                       "amount": now.get(key, {}).get("amount", 0.0),
                       "prev_same_date": prev_same.get(prev_key, {}).get("amount", 0.0),
                       "prev_total": prev_total.get(prev_key, {}).get("amount", 0.0)})
        cur = _next_month(cur)

    # Честность блока держится на этой цифре. Поле period_from завели в октябре 2025: у
    # части сделок прошлого года его нет вовсе, и база сравнения дырявая. Направление
    # читать можно, КРАТНОСТЬ — нет. Дыру считаем и показываем на экране, а не прячем.
    gap = (db.query(func.count(SalesDeal.id), func.coalesce(func.sum(SalesDeal.amount), 0))
           .filter(SalesDeal.amount > 0, SalesDeal.period_from.is_(None),
                   func.extract("year", SalesDeal.date_create) == today.year - 1).first())
    return {"months": months,
            "prev_year_gap": {"deals": gap[0] or 0, "amount": float(gap[1] or 0)}}


def _alerts(db: Session, today: date) -> list:
    """Счётчики «что горит». У каждого — адрес, куда провалиться."""
    debt = _compute_debt_grouped(db, "ПЛАН ПОСТУПЛЕНИЙ", "income", "counterparty")
    overdue = debt.get("aging_summary", {}).get("overdue", {}) or {}

    stale = (db.query(func.count(SalesDeal.id), func.coalesce(func.sum(SalesDeal.amount), 0))
             .join(SalesStage, SalesStage.id == SalesDeal.our_stage_id)
             .filter(SalesDeal.amount > 0, SalesStage.is_terminal.is_(False),
                     SalesDeal.date_modify < today - timedelta(days=STALE_DAYS)).first())

    linked = db.query(SalesPublisherCounterparty.publisher_id).distinct().subquery()
    orphan = (db.query(func.count(SalesPublisher.id))
              .filter(~SalesPublisher.id.in_(db.query(linked.c.publisher_id))).scalar())

    return [
        {"key": "overdue", "label": "Просроченная дебиторка",
         "value": float(overdue.get("amount") or 0), "unit": "money",
         "hint": f"{overdue.get('count') or 0} операций", "href": "/finance/receivables"},
        {"key": "stale", "label": f"Сделки без движения дольше {STALE_DAYS} дней",
         "value": stale[0] or 0, "unit": "count",
         "hint": f"на {float(stale[1] or 0):,.0f} ₽".replace(",", " "), "href": "/sales/deals"},
        {"key": "orphan_publishers", "label": "Площадки без юрлица",
         "value": orphan or 0, "unit": "count",
         "hint": "договор на них не выпустить", "href": "/publishers"},
    ]


@router.get("/overview")
def overview(scale: str = Query("month", pattern="^(month|quarter)$"),
             anchor: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
             db: Session = Depends(get_db),
             user: User = Depends(require_admin)):
    today = date.today()
    # Умолчание — ПРОШЛЫЙ месяц, а не текущий. Месяц закрывается с задержкой: открыв экран
    # 6-го числа на текущем месяце, руководитель увидел бы нули и решил бы, что что-то
    # сломалось. Прошлый месяц — последний, про который есть что сказать.
    anchor = anchor or _shift(today.strftime("%Y-%m"), 1)
    months = _months_of(scale, anchor)
    series_months = [_shift(anchor, i) for i in range(SERIES_MONTHS - 1, -1, -1)]

    per_month = _pl_by_month(db, set(months) | set(series_months))
    return {
        "period": {"scale": scale, "anchor": anchor,
                   "label": _period_label(scale, months), "months": months},
        "margin": _margin_of(_sum_lines(per_month, months)),
        # Маржа В РАЗРЕЗЕ КЛИЕНТА не считается и притворяться не должна: доход приходит от
        # рекламодателя, расход уходит площадке, связать их можно только через приложение к
        # договору. Экран пишет это прямо, а не оставляет читателя гадать.
        "margin_per_client": False,
        "margin_series": [{"month": mo, **_margin_of(_sum_lines(per_month, [mo]))}
                          for mo in series_months],
        # Последний месяц, где выручка реально проведена. Экран называет его, когда
        # выбранный период пуст: «не закрыт» вместо молчаливого нуля.
        "last_revenue_month": next((x for x in reversed(series_months)
                                    if _margin_of(_sum_lines(per_month, [x]))["has_revenue"]), None),
        "funnel": _funnel(db),
        "booking": _booking(db, today),
        "alerts": _alerts(db, today),
    }
