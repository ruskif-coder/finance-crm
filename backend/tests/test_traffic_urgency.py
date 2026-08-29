"""Срочность пары — чистая функция, поэтому проверяется входом и выходом, без базы.

Правила ранжирования однажды перепишут, и вот что при этом должно остаться верным:

  · отвеченная пара НИКОГДА не горит — иначе очередь не пустеет и её перестают читать;
  · прошедший старт строго срочнее приближающегося;
  · «висит долго» не заслоняет «старт послезавтра»: ждать можно месяц, а разместить
    вчерашним днём нельзя.
"""
from datetime import date, timedelta

from app.traffic.urgency import (NORMAL, OVERDUE, SOON, START_SOON_DAYS, STALE_DAYS,
                                 TODAY, PairFacts, evaluate)

TODAY_DATE = date(2026, 8, 28)


def test_answered_pair_is_never_urgent():
    for v in ("ок", "на переделку"):
        f = PairFacts(traffic_verdict=v, period_from=TODAY_DATE - timedelta(days=30),
                      asked_at=TODAY_DATE - timedelta(days=30))
        assert evaluate(f, TODAY_DATE).urgency == NORMAL, (
            "ответ дан — работа закрыта, даже если пара долго ждала")


def test_dropped_pair_falls_out():
    f = PairFacts(is_dropped=True, period_from=TODAY_DATE - timedelta(days=5))
    assert evaluate(f, TODAY_DATE).urgency == NORMAL


def test_passed_start_is_the_most_urgent():
    f = PairFacts(period_from=TODAY_DATE - timedelta(days=1))
    v = evaluate(f, TODAY_DATE)
    assert v.urgency == OVERDUE and "старт был" in v.reason


def test_start_within_two_days_is_today():
    for d in range(0, START_SOON_DAYS + 1):
        f = PairFacts(period_from=TODAY_DATE + timedelta(days=d))
        assert evaluate(f, TODAY_DATE).urgency == TODAY, f"старт через {d} дн."


def test_long_wait_is_soon_but_not_today():
    f = PairFacts(asked_at=TODAY_DATE - timedelta(days=STALE_DAYS),
                  period_from=TODAY_DATE + timedelta(days=40))
    assert evaluate(f, TODAY_DATE).urgency == SOON


def test_approaching_start_outranks_long_wait():
    """Оба условия сразу: висит две недели И старт завтра. Побеждает старт."""
    f = PairFacts(asked_at=TODAY_DATE - timedelta(days=14),
                  period_from=TODAY_DATE + timedelta(days=1))
    assert evaluate(f, TODAY_DATE).urgency == TODAY


def test_fresh_pair_without_dates_is_normal_but_actionable():
    """Дат нет — не повод молчать: строка всё равно ждёт проверки, просто не горит."""
    v = evaluate(PairFacts(), TODAY_DATE)
    assert v.urgency == NORMAL and v.cta == "Проверить"
