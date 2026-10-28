# -*- coding: utf-8 -*-
"""«Агентские условия» — расчёт СК за месяц/квартал (владелец 27.10.2026): группировка агентство → юрлицо → договор →
сделки, итоги по способу, партнёрская отдельно по получателям, закрытый месяц — снимком."""
from datetime import date

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.agency_terms import calc as C


def _row(deal, agency="ОККАМ", ent="МЕДИАНА", contract="РМ-1", base=1000.0, mode="постоплата", pct=10.0, partners=()):
    return {"deal_id": deal, "code": f"D{deal}", "side": agency, "entity": ent, "entity_id": hash(ent) % 100,
            "contract": contract, "contract_id": hash(contract) % 100, "base_net": base,
            "main": {"mode": mode, "percent": pct, "amount": round(base * pct / 100, 2) if mode else None,
                     "rule_id": 1 if mode else None, "source": "rule" if mode else "none"},
            "partners": list(partners)}


def test_tree_groups_side_entity_contract():
    rows = [_row(1), _row(2, contract="РМ-2"), _row(3, agency="ОККАМ", ent="ДИДЖИТАЛ АЛЬЯНС", contract="ДА-5"),
            _row(4, agency="Медиа Инстинкт")]
    t = C.tree(rows)
    assert [s["name"] for s in t] == ["Медиа Инстинкт", "ОККАМ"]
    okkam = t[1]
    assert [e["name"] for e in okkam["entities"]] == ["ДИДЖИТАЛ АЛЬЯНС", "МЕДИАНА"]
    assert [c["name"] for c in okkam["entities"][1]["contracts"]] == ["РМ-1", "РМ-2"]
    assert okkam["base_net"] == 3000 and okkam["main_amount"] == 300


def test_totals_split_by_mode_and_partner_by_recipient():
    rows = [_row(1, mode="постоплата", pct=10), _row(2, mode="скидка в счёт", pct=20, base=500),
            _row(3, mode=None, pct=None,
                 partners=[{"recipient_id": 9, "recipient": "Партнёр", "mode": "постоплата", "percent": 3, "amount": 30.0}])]
    t = C.totals(rows)
    assert t["base_net"] == 2500
    assert t["by_mode"] == {"постоплата": 100.0, "скидка в счёт": 100.0}
    assert t["no_rule"] == 1                                       # условие не задано — считается отдельно
    assert t["partners"] == [{"recipient_id": 9, "recipient": "Партнёр", "amount": 30.0}]


def test_close_month_snapshot_and_refusals():
    """Закрытие пишет снимок; второй раз — отказ; закрытый месяц читается из снимка. Всё откатывается."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        period = "2026-10"
        if db.execute(text("SELECT 1 FROM sk_months WHERE period = :p"), {"p": period}).first():
            pytest.skip("октябрь уже закрыт на стенде")
        live = C.month_rows(db, period)
        if any(r["main"]["source"] == "none" for r in live["rows"]):
            with pytest.raises(C.CalcError) as e:
                C.close_month(db, period, None)
            assert e.value.status == 409 and "условие" in e.value.message
            return
        C.close_month(db, period, None)
        snap = C.month_rows(db, period)
        assert snap["closed"] and len(snap["rows"]) == len(live["rows"])
        with pytest.raises(C.CalcError) as e:
            C.close_month(db, period, None)
        assert e.value.status == 409
    finally:
        db.rollback()
        db.close()


def test_period_check():
    with pytest.raises(C.CalcError):
        C.calc(None, "2026-13")
    assert C.months("2026-Q4") == ["2026-10", "2026-11", "2026-12"]
    assert C.months("2026-10") == ["2026-10"]
    assert date(2026, 10, 31) == C.R.close_date("2026-10")


def test_late_deal_lands_in_exactly_one_open_month():
    """Поломка (ревью 27.10.2026): сделка закрытого месяца, прошедшая ДО позже, попадала в КАЖДЫЙ открытый месяц после
    своего — квартал и обороты спец. условий считали её дважды. Её место — первый незакрытый месяц после её месяца."""
    from app.agency_terms import calc as C
    closed = {"2026-08", "2026-09"}
    assert C.late_home("2026-08", closed) == "2026-10"
    assert C.late_home("2026-09", closed) == "2026-10"
    assert C.late_home("2026-12", {"2026-12"}) == "2027-01"
    homes = [m for m in ("2026-10", "2026-11") if C.late_home("2026-08", closed) == m]
    assert homes == ["2026-10"]


def test_closed_month_snapshot_keeps_a_deal_that_later_went_lost():
    """Поломка (ревью 27.10.2026): шапки строк снимка брались с фильтром «не проиграна» — сделка, ушедшая в проигрыш ПОСЛЕ
    закрытия месяца, оставалась без стороны и договора, дерево падало KeyError (500 на месяц и квартал), а её оборот выпадал
    из спец. условий. Снимок — что начислено, проиграна она позже или нет. Всё в транзакции, откатывается."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        lost = db.execute(text("""SELECT d.id FROM sales_deals d JOIN sales_stages st ON st.id = d.our_stage_id
                                   WHERE st.is_lost ORDER BY d.id DESC LIMIT 1""")).scalar()
        if lost is None:
            pytest.skip("на стенде нет проигранных сделок")
        period = "2019-01"
        db.execute(text("INSERT INTO sk_months (period) VALUES (:p)"), {"p": period})
        db.execute(text("""INSERT INTO sk_accruals (period, deal_id, kind, mode, percent, base_net, amount_net)
                           VALUES (:p, :d, 'основная', 'постоплата', 10, 1000, 100)"""), {"p": period, "d": lost})
        rows = C.month_rows(db, period)["rows"]
        assert [r["deal_id"] for r in rows] == [lost]
        assert rows[0].get("side") and rows[0].get("code"), "у строки снимка есть шапка сделки"
        C.tree(rows)
    finally:
        db.rollback()
        db.close()
