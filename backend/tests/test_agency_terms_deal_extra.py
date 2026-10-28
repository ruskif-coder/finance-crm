# -*- coding: utf-8 -*-
"""Доп. СК сделки для «маржи с доп. СК» мастер-сделки (владелец 27.10.2026): партнёрская выплата и доля спец. условий.
Видна только тем, кому открыта вкладка «Спец. условия» (`sk_special`), — рядом с обычной маржой, не вместо неё.

Доля спец. условия на сделку:
- % без порога — % от суммы ДС сделки до СК;
- % с порогом — % от суммы сделки, если оборот года объекта вместе с ней дошёл до порога (ретро: после порога % идёт со всего
  года, то есть с каждой его сделки); не дошёл — 0 и «копится»;
- фикс — месячная доля, разложенная по сделкам объекта пропорционально их сумме в этом месяце."""
from datetime import date

from app.agency_terms import deal_extra as DX

FEAT = {"contract_id": 7, "agency_id": 3, "advertiser_id": 11, "brand_id": 21, "service_id": 1}


def _t(**kw):
    t = {"id": 1, "name": "тест", "scope_kind": "агентство", "scope_id": 3, "percent": None, "amount": None, "threshold": None,
         "valid_from": date(2026, 1, 1), "valid_to": date(2026, 12, 31)}
    return {**t, **kw}


def test_percent_without_threshold_is_share_of_deal_sum():
    got = DX.deal_special(_t(percent=2), FEAT, "2026-10", 100000, {})
    assert got == {"amount": 2000.0, "status": "начислено"}


def test_out_of_scope_or_term_gives_nothing():
    assert DX.deal_special(_t(percent=2, scope_id=99), FEAT, "2026-10", 100000, {}) is None
    assert DX.deal_special(_t(percent=2, valid_to=date(2026, 9, 30)), FEAT, "2026-10", 100000, {}) is None
    assert DX.deal_special(_t(percent=2, scope_kind="бренд", scope_id=21), FEAT, "2026-10", 100000, {})["amount"] == 2000


def test_threshold_counts_once_year_turnover_with_the_deal_reaches_it():
    t = _t(percent=3, threshold=1_000_000)
    assert DX.deal_special(t, FEAT, "2026-10", 100000, {"2026-09": 800000}) == {"amount": 0.0, "status": "копится"}
    assert DX.deal_special(t, FEAT, "2026-10", 200000, {"2026-09": 800000}) == {"amount": 6000.0, "status": "начислено"}
    # оборот прошлого года в порог не идёт
    assert DX.deal_special(t, FEAT, "2026-10", 200000, {"2025-12": 800000})["status"] == "копится"


def test_fix_is_split_by_deal_share_of_month_turnover():
    t = _t(amount=120000)                        # 12 месяцев → 10 000 в месяц
    got = DX.deal_special(t, FEAT, "2026-10", 25000, {"2026-10": 75000})
    assert got == {"amount": 2500.0, "status": "начислено"}


def test_partner_is_percent_of_deal_sum():
    assert DX.partner_amount([{"percent": 2}, {"percent": 1.5}], 100000) == 3500.0
    assert DX.partner_amount([], 100000) == 0.0


def test_fix_share_counts_unclosed_deals_of_the_month_too():
    """Поломка (ревью 27.10.2026): знаменатель доли фикса — только закрытые сделки месяца; две незакрытые по 100 получали
    каждая ВСЮ месячную долю — месяц учитывался дважды. `month_all` — оборот объекта за месяц по всем его сделкам без этой."""
    t = _t(amount=120000)                        # 10 000 в месяц
    got = DX.deal_special(t, FEAT, "2026-10", 100, {}, month_all=100)
    assert got == {"amount": 5000.0, "status": "начислено"}
