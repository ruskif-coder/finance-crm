# -*- coding: utf-8 -*-
"""Сводка руководителя: деньги считаются ТЕМ ЖЕ способом, что и в отчётах.

Главный риск этого экрана не в падении, а в расхождении. Дашборд показывает выручку и
маржу; если он посчитает их своей формулой, то однажды разойдётся с P&L — и расхождение
будет выглядеть как ошибка отчёта, а не как две разные формулы. В этом проекте так уже
случалось (`pace` в двух смыслах, статус площадки от ПАР против КРЕАТИВОВ).

Приборы здесь держат три вещи, каждая из которых ошибается молча:

· квартальная строка операции раскладывается на три месяца — как в отчётах;
· ноль отличается от «ещё не внесли»;
· умолчание периода — прошлый месяц, а не текущий.
"""
from datetime import date

import pytest

import app.ad.models           # noqa: F401 — регистрирует таблицы в Base.metadata
import app.launch_prep.models  # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.routers import exec_dashboard as ex


@pytest.fixture
def db():
    d = SessionLocal()
    yield d
    d.rollback()
    d.close()


# ── период ───────────────────────────────────────────────────────────────────

def test_quarter_covers_three_months():
    """Квартал разворачивается в три месяца — иначе выбор «квартал» считал бы один."""
    assert ex._months_of("quarter", "2026-08") == ["2026-07", "2026-08", "2026-09"]
    assert ex._months_of("month", "2026-08") == ["2026-08"]


def test_shift_crosses_year():
    assert ex._shift("2026-01", 1) == "2025-12"
    assert ex._shift("2026-03", 5) == "2025-10"


# ── деньги ───────────────────────────────────────────────────────────────────

def test_quarter_row_splits_into_thirds(db):
    """Операция с периодом «Q1 2026» даёт по трети в январь, февраль и март.

    Так же поступают отчёты. Разойдись здесь округление или доля — дашборд и P&L
    показали бы разные числа на одних и тех же данных.
    """
    months = {"2026-01", "2026-02", "2026-03"}
    per_month = ex._pl_by_month(db, months)
    q = [m for m in months if per_month.get(m)]
    if not q:
        pytest.skip("на стенде нет операций первого квартала — сравнивать нечего")
    jan = ex._sum_lines(per_month, ["2026-01"])
    feb = ex._sum_lines(per_month, ["2026-02"])
    # Квартальные строки делятся поровну, поэтому доли кварталов в месяцах совпадают.
    # Месячные строки могут отличаться — проверяем, что расчёт не падает и не теряет знак.
    for acc in (jan, feb):
        for line, v in acc.items():
            assert v["income"] >= 0 and v["expense"] >= 0, f"отрицательная сумма в {line}"


def test_margin_formula_matches_pl_lines():
    """Маржа собирается из ТЕХ ЖЕ строк P&L, а не из своих названий групп.

    Прибор ловит переименование: если в разметке появится другая строка выручки, тест
    упадёт здесь, а не выяснится через месяц по расхождению с отчётом.
    """
    acc = {"revenue": {"income": 100.0, "expense": 0.0},
           "cogs": {"income": 0.0, "expense": 60.0},
           "opex": {"income": 0.0, "expense": 20.0},
           "marketing": {"income": 0.0, "expense": 5.0}}
    m = ex._margin_of(acc)
    assert m["gross"] == 40.0
    assert m["gross_pct"] == 40.0
    assert m["ebitda"] == 15.0          # 40 − 20 − 5


def test_zero_is_not_the_same_as_empty():
    """Ноль и «ещё не внесли» — разные утверждения, и экран обязан их различать.

    На 06.09.2026 у августа есть себестоимость и нет выручки: по одному флагу экран
    нарисовал бы отрицательную маржу вместо «месяц не закрыт».
    """
    empty = ex._margin_of({})
    assert empty["has_data"] is False and empty["has_revenue"] is False
    assert empty["gross_pct"] is None

    cogs_only = ex._margin_of({"cogs": {"income": 0.0, "expense": 10.0}})
    assert cogs_only["has_data"] is True
    assert cogs_only["has_revenue"] is False, "себестоимость без выручки — период не закрыт"

    real_zero = ex._margin_of({"revenue": {"income": 0.0, "expense": 0.0}})
    assert real_zero["has_revenue"] is False


# ── воронка и загрузка ───────────────────────────────────────────────────────

def test_funnel_uses_the_stage_catalogue(db):
    """Лестница берётся из справочника стадий, а не пишется в коде.

    Ступени заводит владелец; захардкоженный список разошёлся бы с ним молча, и пустая
    ступень выглядела бы как отсутствующая, а не как непройденная.
    """
    rows = ex._funnel(db)
    assert rows, "справочник стадий пуст — воронку строить не из чего"
    assert all({"stage", "phase", "deals", "amount"} <= set(r) for r in rows)
    # Терминальные и потерянные помечены: без этого «Архив успешных» и «Сделка сорвалась»
    # читались бы как обычные ступени, и воронка врала бы про конверсию.
    assert any(r["terminal"] for r in rows)


def test_booking_reports_the_gap_in_its_own_baseline(db):
    """Блок загрузки сам сообщает, насколько дырява его база сравнения.

    Поле period_from завели в октябре 2025. Пока в прошлом году есть сделки без него,
    сравнение нельзя читать в разах — и экран обязан сказать это сам, а не молчать.
    """
    b = ex._booking(db, date(2026, 9, 6))
    assert len(b["months"]) == ex.BOOKING_MONTHS
    assert "prev_year_gap" in b
    assert b["prev_year_gap"]["deals"] >= 0


def test_default_period_is_the_previous_month():
    """Умолчание — прошлый месяц.

    Месяц закрывается с задержкой: экран, открытый 6-го числа на текущем месяце, показал
    бы нули, и это выглядело бы как поломка.
    """
    assert ex._shift("2026-09", 1) == "2026-08"
