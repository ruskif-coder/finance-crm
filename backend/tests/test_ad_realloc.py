"""«Темп размещения → Перераспределить» (владелец 24.10.2026): недобор площадок, упёршихся в СЕТЬ (предложено меньше
нужного), переносится на площадки, которые идут в темпе и имеют запас предложения. Площадка, у которой трафик есть,
а показов нет, не донор — её недобор не из-за сети. Сумма планов не меняется; план не ниже факта."""
from app.ad import realloc


def _row(i, plan, fact, capacity, status, running=True):
    return {"id": i, "name": f"p{i}", "plan": plan, "fact": fact, "capacity": capacity, "pace": status,
            "running": running}


def _by(out):
    return {r["id"]: r for r in out["rows"]}


def test_shortfall_of_network_limited_goes_to_spare():
    # 10 дней до конца. №1: остаток 50 000, сеть даёт 2 000/день → успеет 20 000, недобор 30 000.
    # №2 в темпе: остаток 30 000 (3 000/день), предлагают 9 000/день → запас (9 000 − 3 000) × 10 × ½ = 30 000.
    rows = [_row(1, 100_000, 50_000, 2_000, "мало трафика"), _row(2, 100_000, 70_000, 9_000, "в темпе")]
    out = realloc.propose(rows, days_left=10)
    r = _by(out)
    assert r[1]["plan_new"] == 70_000 and r[1]["role"] == "донор"
    assert r[2]["plan_new"] == 130_000 and r[2]["role"] == "получатель"
    assert out["moved"] == 30_000 and out["unplaced"] == 0
    assert sum(x["plan_new"] for x in out["rows"]) == sum(x["plan"] for x in rows)


def test_not_enough_spare_leaves_unplaced_and_donor_gives_only_what_is_taken():
    rows = [_row(1, 100_000, 50_000, 2_000, "мало трафика"), _row(2, 100_000, 70_000, 4_000, "в темпе")]
    out = realloc.propose(rows, days_left=10)        # запас №2: (4 000 − 3 000) × 10 × ½ = 5 000
    r = _by(out)
    assert out["moved"] == 5_000 and out["unplaced"] == 25_000
    assert r[1]["plan_new"] == 95_000 and r[2]["plan_new"] == 105_000


def test_traffic_but_not_delivered_is_not_a_donor_and_unknown_capacity_is_untouched():
    rows = [_row(1, 100_000, 50_000, 9_000, "трафик есть, не открутили"),
            _row(2, 100_000, 50_000, None, "недобор"),
            _row(3, 100_000, 50_000, 9_000, "в темпе")]
    out = realloc.propose(rows, days_left=10)
    assert out["moved"] == 0
    assert {r["role"] for r in out["rows"]} <= {"без изменений", "запас"}
    assert _by(out)[1]["note"] and _by(out)[2]["note"]


def test_paused_and_not_running_are_left_alone():
    rows = [_row(1, 100_000, 50_000, 2_000, "мало трафика"), _row(2, 100_000, 10_000, 50_000, "в темпе", running=False)]
    out = realloc.propose(rows, days_left=10)
    assert out["moved"] == 0 and _by(out)[2]["plan_new"] == 100_000


def _rows():
    return [{"id": 1, "name": "a", "plan": 60_000, "fact": 10_000, "status": "запущен"},
            {"id": 2, "name": "b", "plan": 40_000, "fact": 5_000, "status": "запущен"},
            {"id": 3, "name": "c", "plan": 0, "fact": 0, "status": "ждёт запуска"}]


def test_sum_of_plans_cannot_exceed_rk_plan():
    """Лимит РК не выходит за план (владелец 24.10.2026): сумма планов всех площадок после правки ≤ плана РК."""
    assert realloc.check_plans(_rows(), {1: 50_000, 2: 50_000}, 100_000) is None
    why = realloc.check_plans(_rows(), {1: 61_000}, 100_000)
    assert why and "больше плана РК" in why
    assert realloc.check_plans(_rows(), {1: 70_000, 2: 30_000}, 100_000) is None


def test_only_placements_in_work_get_a_manual_plan():
    why = realloc.check_plans(_rows(), {3: 1_000, 1: 59_000}, 100_000)
    assert why and "не в работе" in why


def test_rows_carry_need_after_the_move():
    rows = [_row(1, 100_000, 50_000, 2_000, "мало трафика"), _row(2, 100_000, 70_000, 9_000, "в темпе")]
    r = _by(realloc.propose(rows, days_left=10))
    assert r[1]["need"] == 5_000 and r[1]["need_new"] == 2_000      # донору после переноса — по его возможности
    assert r[2]["need"] == 3_000 and r[2]["need_new"] == 6_000      # получателю — больше, но в пределах предложенного
