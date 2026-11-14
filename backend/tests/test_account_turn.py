# -*- coding: utf-8 -*-
"""«Чей ход» строки дашборда аккаунта v5 (13.11.2026, design_handoff_account_dashboard_v5): ваш ход / ждём кого / всё хорошо.

Классификация — поверх `queue_state` (его факты и кнопки не меняются), по эталону `todo(d)` хендоффа, с нашими решениями там, где
они расходятся: у контура аккаунта и приоритезации «Запустить» / «Завершить» — ход аккаунта; после «ждём 1С» у аккаунта действий нет.

Поломки, которые ловят тесты: МП у клиента неделю — «ваш ход» (должно быть «ждём: клиент»); бронь за месяц до старта горит
«ваш ход»; идущая по плану РК — «ваш ход»; отставание ≥ 15 % — «ждём трафик»; сделка контура аккаунта на «В размещении» с
кончившимся периодом — «ждём трафик» (кнопка «Завершить» у аккаунта); ЭДО и оплата — «ваш ход»."""
from datetime import date

from app.sales.queue_state import Bundle, row_state
from app.sales.urgency import Verdict

TODAY = date(2026, 11, 13)


def _b(slot, **kw):
    return Bundle(slot=slot, code="T", today=TODAY, verdict=kw.pop("verdict", Verdict("normal")), **kw)


def _turn(b):
    return row_state(b)["turn"]


def test_sandbox_client_has_the_mp_then_nudge_then_stuck():
    assert _turn(_b("mp_prep")) == {"mine": True, "who": None, "good": False, "col": "prep"}
    t = _turn(_b("mp_sent", stage_days=6, start_in=40))
    assert (t["mine"], t["who"], t["col"]) == (False, "клиент", "client")
    assert _turn(_b("mp_sent", stage_days=20, start_in=40))["col"] == "nudge"
    t = _turn(_b("mp_sent", stage_days=50, start_in=40))
    assert (t["mine"], t["col"]) == (True, "stuck")


def test_booking_is_mine_only_15_days_before_start():
    assert _turn(_b("booking", start_in=10))["mine"] is True
    assert _turn(_b("booking", start_in=-3))["mine"] is True
    t = _turn(_b("booking", start_in=40))
    assert (t["mine"], t["good"], t["who"]) == (False, True, "срок не подошёл")


def test_assembly_waits_for_sites_or_traffic_after_creatives():
    assert _turn(_b("prep", start_in=5, sets=0))["mine"] is True              # креативов нет
    t = _turn(_b("prep", start_in=5, sets=1, creatives=(2, 6)))
    assert (t["mine"], t["who"]) == (False, "площадки")
    t = _turn(_b("prep", start_in=5, sets=1, creatives=(6, 6), erids=["2SDx"]))
    assert (t["mine"], t["who"], t["good"]) == (False, "трафик", True)
    t = _turn(_b("prep", start_in=5, sets=1, creatives=(6, 6), erids=["2SDx"], flow="контур аккаунта"))
    assert t["mine"] is True, "контур аккаунта запускает сам"


def test_live_lag_is_mine_on_plan_is_good():
    lag = {"done_pct": 9.0, "closed_pace": 0.41, "placements": 15, "placements_on": 14, "flight_over": False}
    assert _turn(_b("live", delivery=lag, flow="приоритезация"))["mine"] is True
    ok = {"done_pct": 40.0, "closed_pace": 0.41, "placements": 15, "placements_on": 15, "flight_over": False}
    t = _turn(_b("live", delivery=ok))
    assert (t["mine"], t["good"], t["who"]) == (False, True, "трафик")
    over = {"done_pct": 99.0, "closed_pace": 1.0, "placements": 15, "placements_on": 0, "flight_over": True}
    assert _turn(_b("live", delivery=over))["who"] == "трафик — завершить РК", "полный цикл: период кончился, РК не закрыта трафиком — своя группа (владелец 13.11.2026)"
    assert _turn(_b("live", delivery=over, flow="приоритезация"))["mine"] is True, "приоритезация: «Завершить» — аккаунт"


def test_after_1c_account_only_watches():
    for slot, who in (("closing", "бухгалтер"), ("edo", "финансы"), ("pay", "финансы")):
        t = _turn(_b(slot))
        assert (t["mine"], t["who"]) == (False, who), slot


def test_recon_without_placements_is_mine_and_missing_fact_waits_for_traffic():
    """Поломка (13.11.2026): 25 сделок сверки без размещений («неприменимо») и 9 с несобранным фактом висели в «Ждём:
    площадки». Без размещений — ход аккаунта (подтвердить сверку); факт по размещениям снимает трафик, не площадки."""
    from app.sales.stage_checks import NA, NOT_YET, Result
    na = _turn(_b("recon", flow="полный цикл", checks={"fact_collected": Result(NA, "размещений нет")}))
    assert na["mine"] is True
    wait = _turn(_b("recon", flow="полный цикл", checks={"fact_collected": Result(NOT_YET, "17 из 18")}))
    assert (wait["mine"], wait["who"]) == (False, "трафик")


LAG = {"done_pct": 9.0, "closed_pace": 0.41, "placements": 15, "placements_on": 14, "flight_over": False}
ON_PLAN = {"done_pct": 40.0, "closed_pace": 0.41, "placements": 15, "placements_on": 15, "flight_over": False}
OVER = {"done_pct": 99.0, "closed_pace": 1.0, "placements": 15, "placements_on": 0, "flight_over": True}


def test_full_cycle_lag_waits_for_traffic_and_stays_red():
    """Владелец 14.11.2026: отставание полного цикла — ход трафика (темп ведёт он), аккаунту нажать нечего. Поломка: «Ваш ход»
    без кнопки с подписью «ведёт трафик» (27 сделок на стенде)."""
    row = row_state(_b("live", delivery=LAG))
    assert (row["turn"]["mine"], row["turn"]["who"], row["turn"]["good"]) == (False, "трафик — отставание", False)
    assert any(e["type"] == "alert" for e in row["state"]), "строка остаётся красной"


def test_external_launch_live_is_good_until_period_end_then_finish_is_the_button():
    """Владелец 14.11.2026: у внешнего запуска (контур аккаунта) всё у аккаунта; до конца периода — «Всё хорошо: внешняя система»
    (не «площадки» — наших площадок там нет); период кончился — «Ваш ход» с кнопкой «Завершить». У приоритезации площадки наши."""
    t = _turn(_b("live", delivery=ON_PLAN, flow="контур аккаунта"))
    assert (t["mine"], t["who"], t["good"]) == (False, "внешняя система", True)
    assert _turn(_b("live", delivery=None, flow="контур аккаунта"))["who"] == "внешняя система"
    assert _turn(_b("live", delivery=ON_PLAN, flow="приоритезация"))["who"] == "площадки"
    for fl in ("контур аккаунта", "приоритезация"):
        row = row_state(_b("live", delivery=OVER, flow=fl))
        assert row["turn"]["mine"] is True and row["action"] == {"label": "Завершить", "do": "finish",
                                                                 "hint": "Период кончился — завершить запуск"}, fl


def test_external_lag_is_mine_with_a_button():
    """Ваш ход без кнопки — тупик. Отставание приоритезации — ход аккаунта, кнопка раскрывает открутку в строке."""
    row = row_state(_b("live", delivery=LAG, flow="приоритезация"))
    assert row["turn"]["mine"] is True and row["action"]["do"] == "expand"
