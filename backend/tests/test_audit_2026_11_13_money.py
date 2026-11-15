# -*- coding: utf-8 -*-
"""Аудит 13.11.2026 — деньги (владелец 14.11: «пакет дёшево — да»). Каждая проверка названа поломкой, которую ловит."""
from datetime import date
from types import SimpleNamespace

import pytest

import app.model_registry  # noqa: F401
from app import vat


# ── НДС 0 % у нашего юрлица ─────────────────────────────────────────────────────────────────────

def test_zero_vat_of_our_company_stays_zero():
    """Сломать: вернуть `if rate` — ставка 0 («не облагается») превратится в ставку закона 22 %."""
    us = SimpleNamespace(vat_rate_income=0)
    assert vat.for_document(None, SimpleNamespace(own_company=us), date(2026, 11, 1)) == 0.0
    assert vat.for_document(None, SimpleNamespace(own_company=SimpleNamespace(vat_rate_income=None)),
                            date(2026, 11, 1)) == vat.on(date(2026, 11, 1))


# ── импорт операций и проверка строки ───────────────────────────────────────────────────────────

def _op(**kw):
    base = dict(status="ОПЛАЧЕНО", income=1000.0, expense=0.0, vat_rate=22.0, article_id=1, period="2026-10",
                bank="АльфаБанк")
    base.update(kw)
    return SimpleNamespace(**base)


def test_bank_outside_the_list_is_refused():
    """Сломать: убрать проверку банка — «Альфа-Банк» (дефис) пройдёт и выпадет из остатков, оставшись в ДДС."""
    from app.routers.operations import _operation_problem
    assert _operation_problem(_op()) is None
    assert "банк" in (_operation_problem(_op(bank="Альфа-Банк")) or "").lower()
    assert _operation_problem(_op(status="ПЛАН ОПЛАТ", bank=None)) is None


def test_empty_status_in_import_is_not_paid():
    """Сломать: вернуть умолчание «ОПЛАЧЕНО» — план без статуса станет фактом оплаты в остатках и P&L."""
    import pandas as pd
    from app.routers.operations import _import_status
    assert _import_status(pd.Series({"status": "план оплат"})) == "ПЛАН ОПЛАТ"
    assert _import_status(pd.Series({"status": None})) == ""
    assert _import_status(pd.Series({})) == ""


# ── одна запись на запрос ───────────────────────────────────────────────────────────────────────

def test_operation_is_not_saved_when_the_journal_fails(monkeypatch):
    """Сломать: вернуть `db.commit()` до журнала — сбой журнала даст 500 при уже записанной операции, повтор — дубль."""
    from app.database import SessionLocal
    from app.models import Operation, User, Article
    from app.routers import operations as R
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
        art = db.query(Article).order_by(Article.id).first()
        mark = "аудит-13-11-атомарность"
        monkeypatch.setattr(R, "log_action", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("журнал упал")))
        body = R.OperationCreate(date=date(2026, 11, 1), status="ПЛАН ОПЛАТ", income=0, expense=10, bank=None,
                                 period="2026-11", vat_rate=0, article_id=art.id, description=mark)
        with pytest.raises(RuntimeError):
            R.create_operation(body, db=db, current_user=user)
        db.rollback()
        left = db.query(Operation).filter(Operation.description == mark).all()
        for o in left:                     # красная фаза: убрать, что успело записаться
            db.delete(o)
        db.commit()
        assert not left, "операция записана, хотя запрос упал"
    finally:
        db.close()


def test_import_session_is_claimed_once():
    """Сломать: читать сессию через `get` и снимать в конце — два «Применить» одного разбора проведут строки дважды."""
    import uuid
    from app.import_sync_store import FileStore
    st = FileStore()
    key = uuid.uuid4().hex
    st[key] = {"rows": [1]}
    assert st.claim(key) == {"rows": [1]}
    assert st.claim(key) is None, "второй захват той же сессии"
    assert key not in st
