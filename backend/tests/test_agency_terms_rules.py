# -*- coding: utf-8 -*-
"""«Агентские условия» (владелец 27.10.2026): подбор правила СК конструктором — «чем больше условий задано, тем точнее
расчёт». Чистые функции, база не нужна."""
from datetime import date

import pytest

from app.agency_terms import rules as R

D = date(2026, 10, 31)


def _r(id, kind="основная", mode="постоплата", pct=10, frm=date(2026, 1, 1), to=None, recipient=None, **feat):
    return {"id": id, "kind": kind, "mode": mode, "percent": pct, "valid_from": frm, "valid_to": to,
            "recipient_id": recipient, **{k: feat.get(k) for k in R.FEATURES}}


DEAL = {"contract_id": 7, "agency_id": 3, "advertiser_id": 11, "brand_id": 21, "service_id": 2}


def test_more_features_win():
    base = _r(1, contract_id=7, agency_id=3, pct=10)
    brand = _r(2, contract_id=7, agency_id=3, brand_id=21, pct=15)
    assert R.pick([base, brand], DEAL, D, "основная")["id"] == 2
    other_brand = {**DEAL, "brand_id": 22}
    assert R.pick([base, brand], other_brand, D, "основная")["id"] == 1        # бренд не тот — работает база


def test_okkam_via_two_contracts_are_different_terms():
    via_mediana = _r(1, contract_id=7, agency_id=3, pct=10)
    via_da = _r(2, contract_id=8, agency_id=3, pct=20)
    assert R.pick([via_mediana, via_da], DEAL, D, "основная")["percent"] == 10
    assert R.pick([via_mediana, via_da], {**DEAL, "contract_id": 8}, D, "основная")["percent"] == 20


def test_rule_works_only_inside_its_period():
    old = _r(1, contract_id=7, agency_id=3, pct=10, to=date(2026, 9, 30))
    new = _r(2, contract_id=7, agency_id=3, pct=12, frm=date(2026, 10, 1))
    assert R.pick([old, new], DEAL, D, "основная")["id"] == 2
    assert R.pick([old, new], DEAL, date(2026, 9, 30), "основная")["id"] == 1
    assert R.pick([old], DEAL, D, "основная") is None


def test_partner_is_picked_per_recipient():
    """Партнёрская — отдельная выплата: у каждого получателя своё самое точное правило, разные получатели — обе выплаты."""
    adv = _r(1, kind="партнёрская", recipient=50, advertiser_id=11, pct=3)
    brand = _r(2, kind="партнёрская", recipient=50, advertiser_id=11, brand_id=21, pct=5)
    other = _r(3, kind="партнёрская", recipient=60, service_id=2, pct=1)
    got = {r["recipient_id"]: r["id"] for r in R.pick_partners([adv, brand, other], DEAL, D)}
    assert got == {50: 2, 60: 3}


def test_kinds_do_not_mix():
    part = _r(1, kind="партнёрская", recipient=50, contract_id=7, agency_id=3, brand_id=21)
    assert R.pick([part], DEAL, D, "основная") is None


def test_equally_specific_overlapping_rules_conflict():
    """Два одинаково точных правила, подходящих одной сделке в один период, — отказ при сохранении."""
    a = _r(1, contract_id=7, agency_id=3, brand_id=21)
    b = _r(2, contract_id=7, agency_id=3, service_id=2)                         # бренд 21 + услуга 2 — подходят оба
    assert R.conflict(b, [a])["id"] == 1
    c = _r(3, contract_id=7, agency_id=3, brand_id=22)                          # другой бренд — одной сделке не подойдут вместе
    assert R.conflict(c, [a]) is None
    d = _r(4, contract_id=7, agency_id=3, brand_id=21, frm=date(2027, 1, 1))     # другой период
    assert R.conflict(d, [_r(1, contract_id=7, agency_id=3, brand_id=21, to=date(2026, 12, 31))]) is None
    e = _r(5, contract_id=7, agency_id=3, brand_id=21, service_id=2)            # точнее — не конфликт, а уточнение
    assert R.conflict(e, [a]) is None
    assert R.conflict({**a, "id": 1}, [a]) is None                              # правка самого себя


def test_partner_conflict_only_for_the_same_recipient():
    a = _r(1, kind="партнёрская", recipient=50, brand_id=21)
    assert R.conflict(_r(2, kind="партнёрская", recipient=60, brand_id=21), [a]) is None
    assert R.conflict(_r(3, kind="партнёрская", recipient=50, brand_id=21), [a])["id"] == 1


@pytest.mark.parametrize("rule, msg", [
    (_r(1, agency_id=3), "договор"),                                            # основная без договора
    (_r(1, contract_id=7), "агентство или рекламодатель"),                      # основная без стороны связки
    (_r(1, kind="партнёрская", brand_id=21), "получател"),
    (_r(1, kind="партнёрская", recipient=50), "хотя бы один признак"),
    (_r(1, contract_id=7, agency_id=3, mode="бартер"), "Способ"),
    (_r(1, contract_id=7, agency_id=3, pct=101), "Процент"),
    (_r(1, contract_id=7, agency_id=3, frm=date(2026, 5, 1), to=date(2026, 4, 1)), "раньше"),
])
def test_validate_names_what_is_wrong(rule, msg):
    with pytest.raises(R.RuleError) as e:
        R.validate(rule)
    assert msg in str(e.value)


def test_close_date_is_the_last_day_of_the_month():
    """Условие — на момент закрытия месяца: правило «по 31.10» действует для октября, даже если месяц закрывают 5 ноября."""
    assert R.close_date("2026-10") == date(2026, 10, 31)
    assert R.close_date("2026-02") == date(2026, 2, 28)


def test_quarter_months():
    assert R.months_of("2026-Q4") == ["2026-10", "2026-11", "2026-12"]
    assert R.months_of("2026-10") == ["2026-10"]
    with pytest.raises(R.RuleError):
        R.months_of("2026-13")


def test_advertiser_main_rule_is_for_direct_deals_only():
    """Основная СК рекламодателя — «прямой договор» (схема 27.10.2026): подходит только сделкам без агентства и не спорит
    с правилом агентства на тот же договор (у сделки агентства есть и рекламодатель — оба правила подходили бы поровну)."""
    agency = _r(1, contract_id=7, agency_id=3, pct=30)
    direct = _r(2, contract_id=7, advertiser_id=11, pct=20)
    assert R.conflict(direct, [agency]) is None
    assert R.pick([agency, direct], DEAL, D, "основная")["id"] == 1                        # сделка агентства — правило агентства
    assert R.pick([agency, direct], {**DEAL, "agency_id": None}, D, "основная")["id"] == 2  # прямая — правило рекламодателя
    assert R.pick([direct], DEAL, D, "основная") is None
