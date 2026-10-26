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
    # №2 в темпе: остаток 30 000 (3 000/день), предлагают 9 000/день → запас (9 000 − 3 000) × 10 = 60 000 (вся возможность,
    # владелец 26.10.2026: «как в макете»; до того бралась половина).
    rows = [_row(1, 100_000, 50_000, 2_000, "мало трафика"), _row(2, 100_000, 70_000, 9_000, "в темпе")]
    out = realloc.propose(rows, days_left=10)
    r = _by(out)
    assert r[1]["plan_new"] == 70_000 and r[1]["role"] == "донор"
    assert r[2]["plan_new"] == 130_000 and r[2]["role"] == "получатель"
    assert out["moved"] == 30_000 and out["unplaced"] == 0
    assert sum(x["plan_new"] for x in out["rows"]) == sum(x["plan"] for x in rows)


def test_not_enough_spare_leaves_unplaced_and_donor_gives_only_what_is_taken():
    rows = [_row(1, 100_000, 50_000, 2_000, "мало трафика"), _row(2, 100_000, 70_000, 4_000, "в темпе")]
    out = realloc.propose(rows, days_left=10)        # запас №2: (4 000 − 3 000) × 10 = 10 000
    r = _by(out)
    assert out["moved"] == 10_000 and out["unplaced"] == 20_000
    assert r[1]["plan_new"] == 90_000 and r[2]["plan_new"] == 110_000


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


# ── сценарии-кнопки окна «Перераспределить» (владелец 26.10.2026) ─────────────────────────────────────

def _sc(rows, days=6, **ctx):
    out = realloc.propose(rows, days)
    return {s["key"]: s for s in realloc.scenarios(rows, out, days, **ctx)}


def test_move_scenario_carries_exactly_the_changed_plans():
    rows = [_row(1, 30_000, 10_000, 800, "мало трафика"), _row(2, 60_000, 10_000, 20_000, "в темпе")]
    sc = _sc(rows)["move"]
    assert sc["enabled"] and sc["moved"] > 0
    assert set(sc["plans"]) == {1, 2} and sum(sc["plans"].values()) == 90_000     # сумма планов не меняется


def test_move_is_off_under_a_live_boost_and_says_why():
    rows = [_row(1, 30_000, 10_000, 800, "мало трафика"), _row(2, 60_000, 10_000, 20_000, "в темпе")]
    sc = _sc(rows, boost_live=True)["move"]
    assert not sc["enabled"] and "Поднять темп" in sc["why_not"]


def test_lagging_scenario_boosts_only_not_delivered_with_a_pct_to_reach_the_need():
    rows = [dict(_row(1, 60_000, 30_000, 6_000, "трафик есть, не открутили"), shows_day=2_500, offered_day=6_000),
            dict(_row(2, 60_000, 30_000, 9_000, "в темпе"), shows_day=5_000, offered_day=9_000)]
    sc = _sc(rows)["lagging"]
    assert sc["enabled"] and sc["placement_ids"] == [1] and sc["days"] == 6
    assert sc["pct"] == 100                      # нужно 5 000 в день при 2 500 — +100 %, не больше потолка


def test_lagging_pct_is_capped_by_what_the_network_offers():
    rows = [dict(_row(1, 60_000, 30_000, 3_000, "трафик есть, не открутили"), shows_day=2_500, offered_day=3_000)]
    assert _sc(rows)["lagging"]["pct"] == 20     # предложено 3 000 при 2 500 — выше 20 % поднимать бессмысленно


def test_lagging_skips_sites_with_a_manual_plan():
    rows = [dict(_row(1, 60_000, 30_000, 6_000, "трафик есть, не открутили"), shows_day=2_500, offered_day=6_000,
                 fixed_plan=60_000)]
    sc = _sc(rows)["lagging"]
    assert not sc["enabled"]


def test_drop_scenario_takes_only_chronically_dead_running_sites():
    rows = [dict(_row(1, 30_000, 5_000, 0, "нет трафика"), chronic=True),
            dict(_row(2, 30_000, 5_000, 0, "нет трафика"), chronic=False),
            dict(_row(3, 30_000, 5_000, 0, "нет трафика", running=False), chronic=True)]
    sc = _sc(rows)["drop"]
    assert sc["enabled"] and sc["placement_ids"] == [1]


def test_reset_scenario_only_when_there_are_manual_plans():
    rows = [_row(1, 30_000, 10_000, 800, "в темпе")]
    assert not _sc(rows)["reset"]["enabled"]
    assert _sc(rows, has_manual=True)["reset"]["enabled"]


def test_nothing_runs_on_a_closed_campaign():
    rows = [_row(1, 30_000, 10_000, 800, "мало трафика"), _row(2, 60_000, 10_000, 20_000, "в темпе")]
    assert not any(s["enabled"] for s in _sc(rows, closed=True).values())


def test_lagging_takes_days_the_way_the_boost_counts_them():
    """Темп считает дни от даты факта (6), буст — от сегодня (5): сценарий отдаёт буст-дни, иначе буст откажет."""
    rows = [dict(_row(1, 60_000, 30_000, 6_000, "трафик есть, не открутили"), shows_day=2_500, offered_day=6_000)]
    out = realloc.propose(rows, 6)
    sc = {s["key"]: s for s in realloc.scenarios(rows, out, 6, boost_days=5)}["lagging"]
    assert sc["days"] == 5 and "5 дн." in sc["what"]
    sc0 = {s["key"]: s for s in realloc.scenarios(rows, out, 6, boost_days=0)}["lagging"]
    assert not sc0["enabled"]


def test_under_a_live_boost_lagging_says_the_boost_is_running():
    rows = [dict(_row(1, 60_000, 30_000, 6_000, "мало трафика"), shows_day=2_500, offered_day=3_000)]
    sc = _sc(rows, boost_live=True)["lagging"]
    assert not sc["enabled"] and "уже идёт" in sc["why_not"]



# ── окно по хендоффу 26.10.2026: баланс, причина, история ─────────────────────────────────────────────

def test_move_must_keep_the_sum_of_plans():
    """«Перенос должен сохранять сумму» (хендофф): новые планы в сумме — ровно прежние, иначе отказ."""
    why = realloc.check_plans(_rows(), {1: 55_000}, 100_000)
    assert why and "не сходится" in why
    assert realloc.check_plans(_rows(), {1: 55_000, 2: 45_000}, 100_000) is None


def test_reason_is_required_and_bounded():
    assert realloc.check_reason("") and realloc.check_reason("   ")
    assert realloc.check_reason("x" * 301)
    assert realloc.check_reason("площадка упёрлась в сеть") is None


def test_history_reads_what_where_volume_and_reason_from_the_journal():
    rows = [{"created_at": "2026-10-26T12:20:00", "user_name": "Дарья Г.", "action": "traffic_realloc",
             "details": "РК 37ZTY3: перенесено 15 425 · 120на80.рф −15 425; minicen.ru +7 000; 366.ru +8 425 · причина: «упёрлась в сеть»"},
            {"created_at": "2026-10-25T09:00:00", "user_name": "Андрей М.", "action": "traffic_realloc_reset",
             "details": "РК 37ZTY3: ручные планы площадок сняты (3)"}]
    h = realloc.history_of(rows)
    assert h[0]["moved"] == 15425 and h[0]["why"] == "упёрлась в сеть" and "120на80.рф" in h[0]["what"]
    assert h[1]["what"] == "ручные планы площадок сняты (3)" and h[1]["moved"] is None and h[1]["why"] is None


# План РК урезали ниже суммы ручных планов (владелец 26.10.2026): сначала уведомление, убирать — по согласию человека.
def test_plan_cut_below_manual_plans_is_new_only_once():
    assert realloc.newly_over(1_000, old_plan=2_000, new_plan=900) is True
    assert realloc.newly_over(1_000, old_plan=900, new_plan=800) is False        # уже было превышение — не шумим
    assert realloc.newly_over(1_000, old_plan=2_000, new_plan=1_000) is False    # ровно план — не превышение
    assert realloc.newly_over(0, old_plan=2_000, new_plan=10) is False           # ручных планов нет
    assert realloc.newly_over(1_000, old_plan=None, new_plan=900) is True        # РК только завели


def test_lagging_skips_sites_with_creative_volumes():
    """Ревью 26.10.2026: буст не поднимает площадку с объёмом по креативам (`boost.boostable` — «заданный объём»), а
    сценарий её предлагал — «+X %» обещалось и ничего не меняло."""
    rows = [dict(_row(1, 60_000, 30_000, 6_000, "трафик есть, не открутили"), shows_day=2_500, offered_day=6_000,
                 fixed=60_000)]
    assert not _sc(rows)["lagging"]["enabled"]
