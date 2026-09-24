# -*- coding: utf-8 -*-
"""Пять мелочей по деньгам и договорам (аудит 23.09.2026, этап 8.5).

2.L7  стартовый остаток неизвестного банка отвечал «Остаток обновлён», не записав ничего;
2.L9  подтверждение ДС выдавало ЛЮБУЮ ошибку базы за «номер занят», а в колонку времени
      писало одну дату;
2.L10 выгрузка дебиторки печатала замороженные поля контрагента вместо договоров;
2.L11 сохранение договора без контрагента в запросе отвязывало его от реестра;
2.L12 импорт договоров: «30 дней» → пусто, и срок оплаты затирался.
"""
import io
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, OperationalError

APP = Path(__file__).resolve().parent.parent / "app"


# ── 2.L7 ─────────────────────────────────────────────────────────────────────

class _BalDb:
    """Строки `bank_balances` нет: UPDATE ничего не находит."""

    def __init__(self):
        self.sql = []
        self.committed = False

    def execute(self, stmt, *a, **kw):
        self.sql.append(str(stmt))
        return SimpleNamespace(rowcount=0, scalar=lambda: None)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


def test_unknown_bank_is_refused_not_reported_as_saved(monkeypatch):
    from app.routers import settings as st
    monkeypatch.setattr(st, "log_action", lambda *a, **kw: None, raising=False)
    db = _BalDb()
    with pytest.raises(HTTPException) as e:
        st.update_bank_balance(st.BankBalanceUpdate(bank="Нет такого", opening_balance=1),
                               db, SimpleNamespace(id=1))
    assert e.value.status_code == 400 and not db.committed


def test_a_listed_bank_without_a_row_gets_one(monkeypatch):
    """Экран предлагает банки из списка; строки в таблице может не быть — её заводим,
    а не отвечаем «сохранено», ничего не записав (ревью этапа 8)."""
    from app.routers import settings as st
    monkeypatch.setattr(st, "log_action", lambda *a, **kw: None, raising=False)
    db = _BalDb()
    st.update_bank_balance(st.BankBalanceUpdate(bank=st.BANKS[0], opening_balance=5),
                           db, SimpleNamespace(id=1))
    assert any(q.lstrip().startswith("INSERT INTO bank_balances") for q in db.sql)
    assert db.committed


def test_the_opening_balance_change_is_journaled():
    src = io.open(APP / "routers/settings.py", encoding="utf-8").read()
    body = src[src.index("def update_bank_balance("):]
    body = body[:body.index("\n@router")]
    assert "log_action(" in body, "смена стартового остатка не попадает в журнал"


# ── 2.L9 ─────────────────────────────────────────────────────────────────────

class _Annex(SimpleNamespace):
    pass


def _confirm_with(monkeypatch, exc):
    from app.routers import annexes as an
    a = _Annex(id=1, no=None, contract_id=2, date=None)
    monkeypatch.setattr(an, "_annex", lambda db, i: a)
    monkeypatch.setattr(an, "_contract", lambda db, i: SimpleNamespace(id=2))
    monkeypatch.setattr(an, "_check_no", lambda db, c, no: None)
    monkeypatch.setattr(an, "log_action", lambda *a, **kw: None)
    monkeypatch.setattr(an, "_out", lambda a: {"ok": True})

    class _Db:
        def commit(self):
            if exc:
                raise exc

        def rollback(self):
            pass

        def refresh(self, o):
            pass

    try:
        an.confirm_annex(1, an.ConfirmIn(no=5), _Db(), SimpleNamespace(id=1))
    finally:
        pass
    return a


def test_a_database_failure_is_not_called_a_taken_number(monkeypatch):
    err = OperationalError("UPDATE", {}, Exception("server closed the connection"))
    with pytest.raises(HTTPException) as e:
        _confirm_with(monkeypatch, err)
    assert "уже занят" not in e.value.detail and e.value.status_code != 409, e.value.detail


def test_a_taken_number_is_still_explained(monkeypatch):
    err = IntegrityError("UPDATE", {}, Exception(
        'duplicate key value violates unique constraint "uq_annex_contract_no"'))
    with pytest.raises(HTTPException) as e:
        _confirm_with(monkeypatch, err)
    assert e.value.status_code == 409 and "занят" in e.value.detail


def test_confirmation_time_is_a_moment(monkeypatch):
    a = _confirm_with(monkeypatch, None)
    assert isinstance(a.confirmed_at, datetime)


# ── 2.L10 ────────────────────────────────────────────────────────────────────

def test_receivables_read_contracts_not_frozen_fields():
    src = io.open(APP / "routers/reports.py", encoding="utf-8").read()
    body = src[src.index("def _compute_debt_grouped("):]
    body = body[:body.index("\ndef ", 10)]
    assert "cp.contract_number" not in body and "cp.contract_date" not in body


def test_contract_label_lists_every_contract():
    from datetime import date
    from app.routers import reports
    one = [SimpleNamespace(contract_number="12", contract_date=date(2025, 2, 1))]
    assert reports._contracts_cells(one) == ("12", date(2025, 2, 1))
    two = one + [SimpleNamespace(contract_number="7/A", contract_date=None)]
    num, when = reports._contracts_cells(two)
    assert num == "12 от 01.02.2025; 7/A" and when is None
    assert reports._contracts_cells([]) == (None, None)


# ── 2.L12 ────────────────────────────────────────────────────────────────────

def test_import_reads_days_with_a_word():
    from app.routers import contracts as ct
    assert ct._coerce_import_value("payment_term_days", "30 дней") == 30
    assert ct._coerce_import_value("payment_term_days", 45) == 45


@pytest.mark.parametrize("bad", [-30, 30.7, 1e12, "-30", "99999 дней"])
def test_import_rejects_impossible_terms(bad):
    from app.routers import contracts as ct
    assert ct._coerce_import_value("payment_term_days", bad) is ct.UNREADABLE


def test_import_does_not_wipe_on_unreadable_value():
    from app.routers import contracts as ct
    assert ct._coerce_import_value("payment_term_days", "по факту") is ct.UNREADABLE
    assert ct._coerce_import_value("contract_date", "вчера") is ct.UNREADABLE
    src = io.open(APP / "routers/contracts.py", encoding="utf-8").read()
    assert src.count("is UNREADABLE") >= 2, "предпросмотр и применение обязаны пропускать поле"


# ── 2.L11 ────────────────────────────────────────────────────────────────────

def test_saving_one_field_does_not_unlink_the_contract():
    """Живой договор стенда: шлём только примечание (то же самое) — привязка к реестру
    и остальные поля на месте. Журнал, если тест что-то записал, снимается."""
    from sqlalchemy import text
    import app.main  # noqa: F401
    from app.database import SessionLocal
    from app.models import Contract, User
    from app.routers import contracts as ct

    db = SessionLocal()
    started = datetime.utcnow()
    c = (db.query(Contract).filter(Contract.counterparty_id.isnot(None),
                                   Contract.contract_number.isnot(None))
         .order_by(Contract.id).first())
    if c is None:
        db.close()
        pytest.skip("на стенде нет привязанного договора")
    # Снимок ВСЕЙ строки: старый код стирал все поля разом, и откат пяти полей
    # оставил бы договор стенда пустым (так и случилось при проверке на старом коде).
    cols = [col.name for col in Contract.__table__.columns]
    snapshot = {k: getattr(c, k) for k in cols}
    before = (c.counterparty_id, c.counterparty_name, c.inn, c.contract_number,
              c.payment_term_days)
    admin = db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()
    try:
        ct.update_contract(c.id, ct.ContractCreate(note=c.note), db, admin)
        db.refresh(c)
        after = (c.counterparty_id, c.counterparty_name, c.inn, c.contract_number,
                 c.payment_term_days)
        assert after == before, f"частичное сохранение изменило договор: {before} → {after}"
    finally:
        db.rollback()
        c = db.query(Contract).filter(Contract.id == snapshot["id"]).first()
        for k, v in snapshot.items():
            setattr(c, k, v)
        db.execute(text("DELETE FROM audit_log WHERE action = 'update_contract' "
                        "AND entity_id = :i AND created_at >= :t"), {"i": c.id, "t": started})
        db.commit()
        db.close()
