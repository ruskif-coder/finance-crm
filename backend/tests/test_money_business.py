# -*- coding: utf-8 -*-
"""Вкладка «Бизнес» экрана «Деньги» (владелец 20.11.2026): светофор продаж по месяцам против учёта.

Ловит: деньги считаются до «скидки в счёт» (светофор расходится с учётом на СК); СК постоплатой вычитается (это расход, не
выручка); бронь без разметки уходит в низкую вероятность; сорвавшаяся попадает в слои; окно месяцев съезжает на стыке года;
сверка теряет деньги (сумма шагов ≠ разница); недокрут считается при перекруте."""
from datetime import date

import pytest

from app.money import business as B


def test_window_is_previous_current_and_three_ahead_across_new_year():
    assert B.month_keys(date(2026, 11, 20)) == [("2026-10", "past"), ("2026-11", "now"), ("2026-12", "next"),
                                                ("2027-01", "next"), ("2027-02", "next")]
    assert [k for k, _ in B.month_keys(date(2027, 1, 3))] == ["2026-12", "2027-01", "2027-02", "2027-03", "2027-04"]


@pytest.mark.parametrize("layer, light, want", [
    ("фактические", "green", "docs"),
    ("реализуемые", "green", "work"),
    ("планируемые", "orange", "mid"),        # бронь без разметки — средняя (probability.effective), продажи отметили средней
    ("планируемые", "green", "mid"),         # продажи уверены, а стадия ещё в планах — вероятные, не «надёжно»
    ("планируемые", "grey", "low"),
    (None, None, "lost"),                    # «не случилась» / «сорвалась» — без слоя
    ("", "grey", "lost"),
])
def test_bucket(layer, light, want):
    assert B.bucket(layer, light) == want


def test_only_discount_in_invoice_reduces_money():
    """Владелец 20.11.2026: «за вычетом скидки в счёт». 500 000 при СК 45 % в счёт → 275 000; постоплата — расход, не вычитаем."""
    assert B.net_of_discount(500000, "скидка в счёт", 45) == 275000
    assert B.net_of_discount(500000, "постоплата", 45) == 500000
    assert B.net_of_discount(500000, None, None) == 500000


def test_money_in_flight():
    # 1 000 000 ₽, план 100 000 показов, открутилось 40 000, прогноз 90 000 (< 97 %) → открутилось 400 000, под риском 100 000
    assert B.money_in_flight(1_000_000, 100_000, 40_000, 90_000) == (400_000, 100_000)
    # прогноз 98 % — в плане, не риск; перекрут — открутка не больше суммы
    assert B.money_in_flight(1_000_000, 100_000, 40_000, 98_000) == (400_000, 0.0)
    assert B.money_in_flight(1_000_000, 100_000, 130_000, 140_000) == (1_000_000, 0.0)
    # нет плана показов — открутка неизвестна
    assert B.money_in_flight(1_000_000, None, 5, 5) == (None, 0.0)


def test_recon_steps_add_up_to_accounting():
    """Сделки 1 и 2 в документах (100 и 50), выручка: сделке 1 — 90, сделке 3 (не в документах месяца) — 20, без сделки — 5.
    Шаги: счёта нет −50 (сделка 2), сумма ≠ счёт −10, вне сделок +25 → учёт 115 = 90 + 20 + 5."""
    rc = B.recon_steps({1: 100.0, 2: 50.0}, {1: 90.0, 3: 20.0}, 5.0)
    steps = {s["key"]: s["v"] for s in rc["steps"]}
    assert rc["from"] == 150 and steps == {"no_bill": -50, "diff": -10, "outside": 25} and rc["to"] == 115


def test_build_on_stand_is_consistent():
    """Живой расчёт на копии прода: сверка прошлого месяца приходит ровно к выручке учёта; ветви не меньше друг друга."""
    import app.model_registry  # noqa: F401
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        r = B.build(db, date.today())
        rc = r["recon"]
        assert abs(rc["from"] + sum(s["v"] for s in rc["steps"]) - rc["to"]) < 0.05
        acct = B.revenue_by_month(db, [rc["key"]])[rc["key"]]
        assert abs(rc["to"] - acct) < 1.0, (rc["to"], acct)
        assert len(r["months"]) == 5 and r["months"][1]["role"] == "now"
        sp = r["speed"]                                   # «Путь денег»: дни между шагами — числа или None, не мусор
        assert set(sp) >= {"to_invoice_days", "to_pay_days", "term_days"}
        assert all(v is None or -60 < v < 400 for v in (sp["to_invoice_days"], sp["to_pay_days"]))
        prev = r["months"][0]["name"].lower()
        assert all(row["package"] or row["month"] == prev for row in r["unbilled"]["rows"]), "без пакета в списке — только прошлый месяц"
        for m in r["months"]:
            assert all(m[k] >= 0 for k in ("docs", "work", "mid", "low", "lost"))
            assert abs(sum(x["amount"] for x in m["deals"]["work"]) - m["work"]) < 1
    finally:
        db.rollback()
        db.close()
