# -*- coding: utf-8 -*-
"""Карточка контрагента v2 (хендофф «контрикZ», 28.10.2026): тип по оборотам, строка причины в «Расчётах» — по плановым операциям,
предупреждение «операции идут без действующего договора». Чистые функции, база не нужна."""
from datetime import date

from app.counterparty_card import rules as R

ON = date(2026, 10, 28)


def test_kind_by_turnover():
    assert R.kind_of(100, 0) == "income"
    assert R.kind_of(0, 50) == "expense"
    assert R.kind_of(100, 50) == "mixed"
    assert R.kind_of(0, 0) is None


def test_plan_reason_names_the_newest_plan_and_counts_the_rest():
    plans = [
        {"status": "ПЛАН ОПЛАТ", "article": "СК АГЕНТСКАЯ", "period": "Q2 2026", "invoice": "26-05688", "invoice_date": "2026-07-21", "bank": None},
        {"status": "ПЛАН ПОСТУПЛЕНИЙ", "article": "РЕАЛИЗАЦИЯ", "period": "2026-09", "invoice": None, "invoice_date": None, "bank": "Альфабанк"},
    ]
    text = R.plan_reason(plans)
    assert text.startswith("План оплат СК АГЕНТСКАЯ за Q2 2026, счёт № 26-05688 от 21.07.2026 — банк не указан")
    assert text.endswith("и ещё 1 в плане")
    assert R.plan_reason([]) is None


def test_warning_when_all_contracts_expired_before_last_operation():
    contracts = [{"end_date_text": "31.12.2025", "prolongation": "Нет"}]
    w = R.no_contract_warning(contracts, date(2026, 6, 30), ON)
    assert "31.12.2025" in w and "2026" in w
    assert R.no_contract_warning([{"end_date_text": "31.12.2025", "prolongation": "АВТО на год"}], date(2026, 6, 30), ON) is None
    assert R.no_contract_warning([{"end_date_text": "31.12.2026", "prolongation": None}], date(2026, 6, 30), ON) is None
    assert R.no_contract_warning([], date(2026, 6, 30), ON) is None              # без договоров — свой блок пустой, не тревога
    assert R.no_contract_warning(contracts, date(2025, 11, 1), ON) is None      # операции кончились до окончания договора


def test_overview_on_stand_data():
    """Сводка собирается на настоящих данных стенда: сальдо = нам должны − мы должны, договоры с признаком действия."""
    import app.model_registry  # noqa: F401
    from sqlalchemy import text
    from app.counterparty_card.service import overview
    from app.database import SessionLocal
    from app.models import Counterparty, User
    db = SessionLocal()
    try:
        cp_id = db.execute(text("SELECT counterparty_id FROM operations WHERE counterparty_id IS NOT NULL "
                                "GROUP BY 1 ORDER BY count(*) DESC LIMIT 1")).scalar()
        admin = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
        out = overview(db, db.get(Counterparty, cp_id), admin)
        s = out["settlement"]
        assert abs(s["saldo"] - (s["receivable"] - s["payable"])) < 0.01
        assert out["op_count"] > 0 and out["kind"] in ("income", "expense", "mixed")
        assert all("in_force" in k and "ds_count" in k for k in out["contracts"])
    finally:
        db.rollback()
        db.close()
