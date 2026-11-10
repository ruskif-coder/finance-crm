# -*- coding: utf-8 -*-
"""Кредитная линия ↔ операции (владелец 10.11.2026: «как в операциях синхронизировать, чтобы висело в ДДС»).

«Выбрано» у линии с банком-контрагентом = оплаченный приход − оплаченный расход по статьям тела кредита (`loan_body`) с этим
контрагентом. Не считаются: план (ещё не взяли / не вернули), проценты («КРЕДИТЫ»), тело другого банка. У линии без контрагента —
ручное значение, как было. Ломается, если в «выбрано» попадут план, проценты или чужой банк. Транзакция откатывается."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app import credit_lines as CL


@pytest.fixture
def env():
    from app.database import SessionLocal
    db = SessionLocal()
    body = db.execute(text("SELECT id FROM articles WHERE pl_line = 'loan_body' ORDER BY id LIMIT 1")).scalar()
    interest = db.execute(text("SELECT id FROM articles WHERE name = 'КРЕДИТЫ'")).scalar()
    cps = db.execute(text("SELECT id FROM counterparties ORDER BY id LIMIT 2")).scalars().all()
    if body is None or interest is None or len(cps) < 2:
        db.close()
        pytest.skip("нет статьи тела кредита (миграция 2026-11-10) или контрагентов")
    bank, other = cps

    def op(article, cp, status, income=0, expense=0):
        db.execute(text("""INSERT INTO operations (article_id, counterparty_id, status, income, expense, period, date)
                           VALUES (:a, :c, :s, :i, :e, '2031-01', DATE '2031-01-10')"""),
                   {"a": article, "c": cp, "s": status, "i": income, "e": expense})

    op(body, bank, "ОПЛАЧЕНО", income=1_000_000)       # взяли
    op(body, bank, "ОПЛАЧЕНО", expense=300_000)        # вернули часть
    op(body, bank, "ПЛАН ОПЛАТ", expense=200_000)      # возврат по плану — ещё не выбрано меньше
    op(interest, bank, "ОПЛАЧЕНО", expense=10_000)     # проценты — не тело
    op(body, other, "ОПЛАЧЕНО", income=50_000)         # тело другого банка
    lid = db.execute(text("""INSERT INTO credit_lines (bank, limit_amount, used_amount, counterparty_id, is_active, updated_at)
                             VALUES ('АльфаБанк', 2000000, 0, :c, true, now()) RETURNING id"""), {"c": bank}).scalar()
    manual = db.execute(text("""INSERT INTO credit_lines (bank, limit_amount, used_amount, is_active, updated_at)
                                VALUES ('ОПТ Банк', 500000, 123000, true, now()) RETURNING id""")).scalar()
    # чужие операции тела этого банка на стенде (если есть) — в ожидание
    base = db.execute(text("""SELECT coalesce(sum(o.income - o.expense), 0) FROM operations o JOIN articles a ON a.id = o.article_id
                               WHERE a.pl_line = 'loan_body' AND o.status = 'ОПЛАЧЕНО' AND o.counterparty_id = :c
                                 AND o.period <> '2031-01'"""), {"c": bank}).scalar()
    try:
        yield db, lid, manual, float(base)
    finally:
        db.rollback()
        db.close()


def test_used_is_paid_body_of_this_bank_only(env):
    from app.models import CreditLine
    db, lid, manual, base = env
    used = CL.used_of(db, [db.get(CreditLine, lid), db.get(CreditLine, manual)])
    assert used[lid] == pytest.approx(base + 700_000)          # 1 000 000 − 300 000; план, проценты и чужой банк — мимо
    assert used[manual] == pytest.approx(123_000)              # без контрагента — ручное, как было


def test_money_today_takes_computed_used(env):
    from app import pay_plan_summary as PS
    db, lid, manual, base = env
    lines = {round(c["limit_amount"]): c for c in PS._credit_lines(db)}
    assert lines[2_000_000]["used_amount"] == pytest.approx(base + 700_000)
    assert lines[500_000]["used_amount"] == pytest.approx(123_000)


def test_settings_line_with_bank_shows_used_from_operations_and_ignores_typed_value(env):
    """Экран «Кредитные линии»: у линии с банком «выбрано» — из операций, введённое руками не записывается; неизвестный банк — 400."""
    from fastapi import HTTPException
    from app.models import CreditLine, User
    from app.routers import settings as R
    db, lid, manual, base = env
    db.commit = db.flush                                           # ручки коммитят — в тесте только сбрасываем, транзакцию откатит фикстура
    user = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
    cp = db.get(CreditLine, lid).counterparty_id
    out = R.update_credit_line(lid, R.CreditLineIn(bank="АльфаБанк", limit_amount=2_000_000, used_amount=5, counterparty_id=cp),
                               db=db, current_user=user)
    assert out["used_amount"] == pytest.approx(base + 700_000) and out["free"] == pytest.approx(2_000_000 - base - 700_000)
    assert out["used_from_operations"] is True and db.get(CreditLine, lid).used_amount == 0
    with pytest.raises(HTTPException) as e:
        R.update_credit_line(lid, R.CreditLineIn(bank="АльфаБанк", limit_amount=2_000_000, counterparty_id=-1), db=db, current_user=user)
    assert e.value.status_code == 400
