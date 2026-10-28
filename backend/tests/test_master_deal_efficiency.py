# -*- coding: utf-8 -*-
"""Блок эффективности мастер-сделки (владелец 19.10.2026): предварительный расчёт по пакету — выручка, СК, себестоимость,
прибыль, маржа. Числа сделки берутся у итоговой сверки (`closing.compute`) — второго расчёта суммы и СК нет.

- выручка — сумма ДС до НДС (при «скидке в счёт» СК из неё уже вычтена);
- СК «постоплата» — наш будущий расход, вычитается из прибыли; «скидка в счёт» — уже в выручке, повторно не вычитается;
- себестоимость — введённая аккаунтом, иначе оценка по показам × CPM договора площадки (с пометкой «оценка»), иначе неизвестна;
- прибыль и маржа пакета считаются, только если себестоимость известна у всех сделок, — иначе «нет данных», не ноль."""
import pytest

from app.master_deal import efficiency as EF


def _st(net, mode=None, pct=None, cost=None):
    sk = (net or 0) * (pct or 0) / 100 if mode else 0.0
    return {"total_net": net, "cost_net": cost, "sk": {"mode": mode, "percent": pct, "amount_net": round(sk, 2)}}


def test_postpay_sk_is_our_cost_discount_is_already_in_revenue():
    a = EF.row("A", _st(100000, "постоплата", 10, 50000), None)
    assert (a["revenue"], a["sk_cost"], a["cost"], a["profit"], a["margin_pct"]) == (100000, 10000, 50000, 40000, 40.0)
    b = EF.row("B", _st(90000, "скидка в счёт", 10, 50000), None)
    assert b["sk_cost"] == 0 and b["profit"] == 40000, "скидка в счёт уже вычтена из выручки — второй раз не вычитаем"


def test_cost_falls_back_to_estimate_and_is_marked():
    r = EF.row("A", _st(100000), {"cost": 30000.0, "coverage_pct": 80.0})
    assert r["cost"] == 30000 and r["cost_source"] == "оценка" and r["profit"] == 70000 and r["coverage_pct"] == 80.0
    r = EF.row("A", _st(100000, cost=45000), {"cost": 30000.0, "coverage_pct": 100.0})
    assert r["cost"] == 45000 and r["cost_source"] == "введена"


def test_unknown_cost_gives_no_profit_not_zero():
    r = EF.row("A", _st(100000), None)
    assert r["cost"] is None and r["profit"] is None and r["margin_pct"] is None


def test_total_profit_only_when_every_deal_has_cost():
    rows = [EF.row("A", _st(100000, cost=50000), None), EF.row("B", _st(50000), None)]
    t = EF.total(rows)
    assert t["revenue"] == 150000 and t["profit"] is None and t["missing_cost"] == ["B"]
    rows[1] = EF.row("B", _st(50000, cost=10000), None)
    t = EF.total(rows)
    assert t["profit"] == 90000 and t["margin_pct"] == 60.0 and t["missing_cost"] == []


def test_zero_revenue_has_no_margin():
    r = EF.row("A", _st(0, cost=0), None)
    assert r["margin_pct"] is None


@pytest.mark.parametrize("stats,want", [
    ([(1000, 200.0), (500, 100.0)], (250.0, 100.0)),       # 1000×200/1000 + 500×100/1000
    ([(1000, 200.0), (500, None)], (200.0, 66.7)),          # нет CPM у площадки — покрытие показов 2/3
    ([], None),
])
def test_estimate_by_publisher_cpm(stats, want):
    got = EF.estimate_from(stats)
    assert (got if got is None else (got["cost"], got["coverage_pct"])) == want


def test_margin_is_over_full_ds_sum_before_sk_whatever_the_mode():
    """Владелец 27.10.2026: маржа — от полной суммы ДС до СК, и при «скидке в счёт» тоже. Иначе одна и та же сделка показывала
    разную маржу в зависимости от способа выплаты: ДС 100 000, СК 30 %, себестоимость 40 000 → 30 % и 42,9 %."""
    post = EF.row("A", _st(100000, "постоплата", 30, 40000), None)
    disc = EF.row("B", {"total_net": 70000, "cost_net": 40000, "sk": {"mode": "скидка в счёт", "percent": 30, "amount_net": 30000}}, None)
    assert post["profit"] == disc["profit"] == 30000
    assert post["margin_pct"] == disc["margin_pct"] == 30.0
    assert disc["revenue"] == 70000 and disc["gross"] == 100000 and post["gross"] == 100000
    t = EF.total([post, disc])
    assert t["gross"] == 200000 and t["profit"] == 60000 and t["margin_pct"] == 30.0


def test_full_margin_subtracts_partner_and_special_over_the_same_base():
    """«Маржа с доп. СК» (владелец 27.10.2026): прибыль − партнёрская − спец. условия, база — та же сумма ДС до СК."""
    rows = [EF.row("A", _st(100000, "постоплата", 30, 40000), None)]
    eff = {"rows": rows, "total": EF.total(rows)}
    f = EF.full(eff, {"A": {"partner": 2000.0, "special": 3000.0, "extra": 5000.0, "accumulating": ["3 % от 30 млн"]}})
    assert (f["partner"], f["special"], f["extra"], f["profit"], f["margin_pct"]) == (2000, 3000, 5000, 25000, 25.0)
    assert f["accumulating"] == ["3 % от 30 млн"]
    assert eff["total"]["profit"] == 30000, "обычная маржа не меняется — полная показывается рядом"
    rows.append(EF.row("B", _st(50000), None))
    f = EF.full({"rows": rows, "total": EF.total(rows)}, {})
    assert f["profit"] is None and f["margin_pct"] is None, "нет себестоимости — нет и полной прибыли"
