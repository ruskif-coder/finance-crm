# -*- coding: utf-8 -*-
"""Расчёт спец. условий (хендофф 27.10.2026, решения владельца): % от оборота объекта; с порогом — «копится», пока оборот
года нарастающим не дошёл до порога, в месяце прохождения начисляется % со ВСЕГО оборота года задним числом, дальше — с
оборота каждого месяца; фикс — равными долями по месяцам срока. Чистые функции."""
from datetime import date

import pytest

from app.agency_terms import special as SP

TURN = {"2026-07": 6_800_000, "2026-08": 7_400_000, "2026-09": 8_100_000, "2026-10": 4_500_000,
        "2026-01": 5_000_000, "2026-02": 2_000_000}           # оборот объекта по месяцам (ДС без НДС, закрытые сделки)


def _t(pct=None, amount=None, thr=None, frm=date(2026, 1, 1), to=date(2026, 12, 31)):
    return {"id": 1, "percent": pct, "amount": amount, "threshold": thr, "valid_from": frm, "valid_to": to}


def test_percent_without_threshold_is_share_of_the_month():
    r = SP.accrue(_t(pct=2), TURN, ["2026-10"])
    assert r["accrued"] == 90_000 and r["status"] == "начислено" and r["base"] == 4_500_000


def test_threshold_accumulates_then_pays_the_whole_year_retroactively():
    """Порог 30 млн: Янв+Фев+Июл+Авг = 21,2 млн — копится; Сентябрь — 29,3 — ещё копится; Октябрь — 33,8: пройден,
    3 % со ВСЕГО оборота года (33,8 млн) задним числом."""
    t = _t(pct=3, thr=30_000_000)
    aug = SP.accrue(t, TURN, ["2026-08"])
    assert aug["accrued"] == 0 and aug["status"] == "копится" and aug["ytd"] == 21_200_000
    oct_ = SP.accrue(t, TURN, ["2026-10"])
    assert oct_["status"] == "начислено" and oct_["ytd"] == 33_800_000
    assert oct_["accrued"] == pytest.approx(33_800_000 * 0.03)
    nov = SP.accrue(t, {**TURN, "2026-11": 1_000_000}, ["2026-11"])
    assert nov["accrued"] == pytest.approx(30_000)            # после порога — только оборот месяца


def test_quarter_is_the_sum_of_its_months():
    t = _t(pct=3, thr=30_000_000)
    q = SP.accrue(t, {**TURN, "2026-11": 1_000_000}, ["2026-10", "2026-11", "2026-12"])
    assert q["accrued"] == pytest.approx(33_800_000 * 0.03 + 30_000)
    assert q["base"] == 5_500_000


def test_fix_is_split_evenly_over_the_months_of_its_term():
    t = _t(amount=450_000, frm=date(2026, 7, 1), to=date(2026, 12, 31))
    assert SP.accrue(t, TURN, ["2026-10"])["accrued"] == 75_000
    assert SP.accrue(t, TURN, ["2026-06"])["accrued"] == 0                   # до срока
    r = SP.accrue(t, TURN, ["2026-10"])
    assert (r["month_no"], r["months"]) == (4, 6)


def test_outside_the_term_nothing_is_accrued():
    t = _t(pct=2, frm=date(2026, 11, 1))
    r = SP.accrue(t, TURN, ["2026-10"])
    assert r["accrued"] == 0 and r["status"] == "не действует"


def test_turnover_of_the_year_counts_only_inside_the_term():
    """Срок начался в июле — январский оборот в порог не идёт."""
    t = _t(pct=3, thr=20_000_000, frm=date(2026, 7, 1))
    r = SP.accrue(t, TURN, ["2026-10"])
    assert r["ytd"] == 6_800_000 + 7_400_000 + 8_100_000 + 4_500_000


def test_scope_matching():
    row = {"agency_id": 3, "advertiser_id": 11, "brand_id": 21, "contract_id": 7}
    assert SP.in_scope({"scope_kind": "агентство", "scope_id": 3}, row)
    assert SP.in_scope({"scope_kind": "бренд", "scope_id": 21}, row)
    assert not SP.in_scope({"scope_kind": "рекламодатель", "scope_id": 12}, row)
    assert SP.in_scope({"scope_kind": "договор", "scope_id": 7}, row)


def test_threshold_is_stored_and_read_back():
    """Порог сохраняется в базу и читается назад (колонка в модели была забыта — 27.10.2026)."""
    import app.model_registry  # noqa: F401
    from app.agency_terms import service as S
    from app.database import SessionLocal

    class _U:
        id = None
    db = SessionLocal()
    try:
        s = S.save_special(db, {"scope_kind": "агентство", "scope_id": 1, "title": "ретро", "percent": 3, "threshold": 30_000_000,
                                "valid_from": "2026-01-01", "valid_to": "2026-12-31"}, _U())
        db.expire_all()
        from app.agency_terms.models import SkSpecialTerm
        assert S.special_dict(db.get(SkSpecialTerm, s.id))["threshold"] == 30_000_000
        with pytest.raises(S.TermsError):
            S.save_special(db, {"scope_kind": "агентство", "scope_id": 1, "title": "фикс с порогом", "amount": 1000, "threshold": 5,
                                "valid_from": "2026-01-01", "valid_to": "2026-12-31"}, _U())
    finally:
        db.rollback()
        db.close()
