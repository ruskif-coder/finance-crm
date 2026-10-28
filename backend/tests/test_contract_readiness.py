# -*- coding: utf-8 -*-
"""Готовность договора к ДС (макет карточки договора, владелец 28.10.2026): срок договора с учётом пролонгации и СК по договору —
самое точное действующее правило основной СК на договор, его агентство или рекламодателя; правила с брендом — отдельным счётом."""
from datetime import date

from app.contract_card import readiness as R

ON = date(2026, 10, 28)


def _rule(id, pct, mode="постоплата", kind="основная", valid_from=date(2026, 1, 1), valid_to=None, **features):
    base = {k: None for k in ("contract_id", "agency_id", "advertiser_id", "brand_id", "service_id", "recipient_id")}
    return {**base, **features, "id": id, "kind": kind, "mode": mode, "percent": pct, "valid_from": valid_from, "valid_to": valid_to}


def test_term_in_force_expired_prolonged_and_unknown():
    assert R.term_check("31.12.2026", "нет", ON)["ok"] is True
    assert R.term_check("31.12.2025", "нет", ON)["ok"] is False
    t = R.term_check("2025-12-31", "АВТО на год", ON)
    assert t["ok"] is True and "пролонгац" in t["text"]
    assert R.term_check("бессрочно", None, ON)["ok"] is True
    assert R.term_check(None, None, ON)["ok"] is False


def test_contract_rule_beats_agency_rule_and_brand_rules_are_counted():
    rules = [_rule(1, 30, agency_id=5), _rule(2, 25, contract_id=9, agency_id=5),
             _rule(3, 10, mode="скидка в счёт", agency_id=5, brand_id=77), _rule(4, 15, agency_id=6)]
    s = R.sk_summary(rules, 9, [5], [], ON)
    assert (s["percent"], s["mode"], s["scope"]) == (25, "постоплата", "договор")
    assert s["brand_rules"] == 1


def test_agency_rule_when_contract_has_none_and_expired_rules_ignored():
    rules = [_rule(1, 30, agency_id=5), _rule(2, 99, contract_id=9, valid_to=date(2026, 6, 30))]
    s = R.sk_summary(rules, 9, [5], [], ON)
    assert (s["percent"], s["scope"]) == (30, "агентство")


def test_direct_advertiser_rule_and_nothing_found():
    rules = [_rule(1, 20, advertiser_id=3)]
    assert R.sk_summary(rules, 9, [], [3], ON)["scope"] == "рекламодатель"
    assert R.sk_summary(rules, 9, [], [4], ON) is None
