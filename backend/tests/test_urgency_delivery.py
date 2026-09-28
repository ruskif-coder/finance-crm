"""Срочность «В размещении»: отставание открутки и закончившийся период (28.09.2026).

Решение владельца 27.09.2026: порог отставания — 15 % от плановой доли на сегодня.
Отставание считается ОТНОСИТЕЛЬНО плана на сегодня, а не в процентных пунктах от всего
плана: в первый день флайта план на сегодня мал, и пять пунктов там — половина нормы.

Функция чистая, поэтому проверяется прямыми комбинациями без базы, как test_urgency.
"""
from datetime import date, timedelta

from app.sales.urgency import (DealFacts, evaluate, delivery_lag_pct,
                               LAG_ALARM_PCT, OVERDUE, SOON, NORMAL)

TODAY_D = date(2026, 10, 1)


def live(**kw) -> DealFacts:
    """Сделка в размещении, флайт идёт, всё по плану."""
    base = dict(stage_key="launch", money_layer="реализуемые", has_mp=True,
                is_placement_stage=True,
                period_from=TODAY_D - timedelta(days=10), period_to=TODAY_D + timedelta(days=10),
                delivery_done_pct=50.0, delivery_pace=0.5, flight_over=False)
    base.update(kw)
    return DealFacts(**base)


def test_threshold_is_owner_decision():
    assert LAG_ALARM_PCT == 15


def test_lag_is_relative_to_todays_plan_share():
    # план на сегодня 40 %, открутили 31 % → отстаём на 22,5 % от плана на сегодня
    assert delivery_lag_pct(live(delivery_done_pct=31.0, delivery_pace=0.4)) == 22.5


def test_lag_none_without_fact_or_before_start():
    assert delivery_lag_pct(live(delivery_done_pct=None)) is None
    assert delivery_lag_pct(live(delivery_pace=0)) is None
    assert delivery_lag_pct(live(delivery_pace=None)) is None


def test_lag_at_threshold_burns():
    v = evaluate(live(delivery_done_pct=34.0, delivery_pace=0.4), TODAY_D)   # 15 %
    assert v.urgency == OVERDUE
    assert v.kind == "delivery_lag"
    assert "15" in v.reason and "отставание" in v.reason.lower()
    # Кнопки нет: РК ведёт трафик, аккаунту тут жать нечего.
    assert v.cta == ""


def test_lag_below_threshold_is_calm():
    v = evaluate(live(delivery_done_pct=35.0, delivery_pace=0.4), TODAY_D)   # 12,5 %
    assert v.kind != "delivery_lag"


def test_ahead_of_plan_is_not_lag():
    v = evaluate(live(delivery_done_pct=70.0, delivery_pace=0.5), TODAY_D)
    assert v.kind != "delivery_lag"


def test_lag_rule_only_on_placement_stage():
    """«Итоговая сверка» носит тот же stage_key launch, но флайт там уже прошёл, и
    отставание по ходу флайта — не её вопрос."""
    v = evaluate(live(is_placement_stage=False, delivery_done_pct=10.0,
                      delivery_pace=0.5), TODAY_D)
    assert v.kind != "delivery_lag"


def test_period_ended_but_stage_not_moved():
    v = evaluate(live(period_to=TODAY_D - timedelta(days=3), flight_over=True,
                      delivery_done_pct=98.0, delivery_pace=1.0), TODAY_D)
    assert v.urgency == SOON
    assert v.kind == "placement_ended"
    assert "3 дн." in v.reason


def test_flight_over_is_not_lag_even_if_underdelivered():
    """После конца флайта недокрут — итог, а не отставание: говорим «период закончился»."""
    v = evaluate(live(period_to=TODAY_D - timedelta(days=1), flight_over=True,
                      delivery_done_pct=60.0, delivery_pace=1.0), TODAY_D)
    assert v.kind == "placement_ended"


def test_on_plan_campaign_does_not_burn_in_first_days():
    """Статистика — дневной срез: за сегодня её ещё нет. План на сегодня поэтому считается
    по ЗАКРЫТЫМ дням. Иначе РК точно по плану на пятый день 30-дневного флайта выглядела
    бы отстающей на 20 % (ревью 28.09.2026)."""
    from app.sales.deal_delivery import closed_pace
    from app.ad.flight import progress
    start = TODAY_D - timedelta(days=4)                      # сегодня пятый день
    fc = progress(30000, 4000, start, start + timedelta(days=29), TODAY_D)   # 4 полных дня по плану
    v = evaluate(live(delivery_done_pct=fc["done_pct"],
                      delivery_pace=closed_pace(fc), flight_over=False), TODAY_D)
    assert v.kind != "delivery_lag", v.reason
    # Первый день флайта — закрытых дней нет, судить не по чему.
    fc1 = progress(30000, 0, TODAY_D, TODAY_D + timedelta(days=29), TODAY_D)
    assert closed_pace(fc1) == 0


def test_calm_live_campaign_stays_normal():
    assert evaluate(live(), TODAY_D).urgency == NORMAL
