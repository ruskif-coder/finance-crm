# -*- coding: utf-8 -*-
"""Прибор: назначение платежа и кодировка выгрузки в Альфа-Банк (аудит 23.09.2026, 2.M5, 2.L1).

  · «НДС не облагается» писалось при ЛЮБОЙ ставке, если описание пустое, а с описанием
    НДС не упоминался вовсе — хотя в платёжке его указывают;
  · символ «₽» или неразрывный дефис в описании роняли выгрузку с 500 при кодировании в
    cp1251 — и уже ПОСЛЕ того, как счётчик номеров был записан: номера сгорали.
"""
import asyncio
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.ad.models  # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.notify.models  # noqa: F401
import app.ord.models  # noqa: F401
from app.database import SessionLocal
from app.models import Article, CounterpartyBankAccount, Operation, User
from app.routers import operations as ops


def _op(desc=None, rate=0, expense=1220.0):
    return SimpleNamespace(description=desc, vat_rate=rate, expense=expense, income=0.0,
                           vat_fact=ops.compute_vat_fact(0, expense, rate))


def test_vat_is_named_when_the_rate_is_not_zero():
    p = ops._payment_purpose(_op(rate=22))
    assert "НДС 22%" in p and "220.00" in p and "не облагается" not in p


def test_zero_rate_says_not_taxed():
    assert "НДС не облагается" in ops._payment_purpose(_op(rate=0))


def test_description_gets_the_vat_clause():
    p = ops._payment_purpose(_op(desc="Оплата по счёту 15", rate=22))
    assert p.startswith("Оплата по счёту 15") and "НДС 22%" in p


def test_description_that_already_names_vat_is_kept_as_is():
    d = "Оплата по счёту 15, в т.ч. НДС 20% 200 руб."
    assert ops._payment_purpose(_op(desc=d, rate=22)) == d


def test_purpose_fits_the_bank_limit():
    assert len(ops._payment_purpose(_op(desc="х" * 400, rate=22))) <= 210


def test_symbols_outside_cp1251_do_not_break_the_file():
    s = ops._cp1251_text("Оплата 1 000 ₽ по счёту 5‑1 — ок тест")
    s.encode("cp1251")                     # не падает
    assert "руб." in s and "5-1" in s


# ── Ревью 23.09.2026: поле файла — одна строка; обрезка не съедает НДС ───────────────────

def test_newline_in_a_value_does_not_add_a_field():
    """Файл 1С построчный: «Ключ=значение». Перенос строки в описании или в имени
    получателя дописывал в документ ЛИШНЕЕ поле — например «Сумма=…» второй раз."""
    doc = ops._alfa_document([("Сумма", "100.00"),
                              ("НазначениеПлатежа", "Оплата\r\nСумма=999999.00\tдоп")])
    lines = doc.split("\n")
    assert [ln.split("=", 1)[0] for ln in lines] == [
        "СекцияДокумент", "Сумма", "НазначениеПлатежа", "КонецДокумента"]
    assert "\r" not in doc and "\t" not in doc
    assert lines[2] == "НазначениеПлатежа=Оплата Сумма=999999.00 доп"


def test_multiline_description_reaches_the_purpose_as_one_line():
    p = ops._payment_purpose(_op(desc="Оплата по счёту 15\nза сентябрь", rate=22))
    assert "\n" not in p and p.startswith("Оплата по счёту 15 за сентябрь")


def test_long_description_keeps_the_vat_clause():
    p = ops._payment_purpose(_op(desc="х" * 400, rate=22))
    assert len(p) <= ops.PURPOSE_MAX
    assert p.endswith("В т.ч. НДС 22% — 220.00 руб.")


def test_vat_clause_is_computed_not_read_from_the_stored_field():
    op = _op(rate=22)
    op.vat_fact = 0          # поле могло разойтись со ставкой (старые строки, ручная правка)
    assert "220.00" in ops._payment_purpose(op)


# ── Выгрузка целиком: документ не расползается, номера не сгорают ─────────────────────────




@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def paid_op(db):
    """Расходная операция на контрагента с реквизитами; реквизиты нашего банка — в транзакции."""
    ba = (db.query(CounterpartyBankAccount)
          .filter(CounterpartyBankAccount.bik != "", CounterpartyBankAccount.rs != "")
          .order_by(CounterpartyBankAccount.id).first())
    if ba is None:
        pytest.skip("нет контрагента с банковскими реквизитами")
    db.execute(text("UPDATE bank_balances SET rs='40702810000000000001', bik='044525593', "
                    "company_name='Прибор', inn='7700000000' WHERE bank='АльфаБанк'"))
    art = db.query(Article).order_by(Article.id).first()
    op = Operation(date=date(2099, 3, 1), status="ОПЛАЧЕНО", income=0.0, expense=1220.0,
                   bank="АльфаБанк", period="2099-03", vat_rate=22, vat_fact=220.0,
                   article_id=art.id, counterparty_id=ba.counterparty_id,
                   description="Оплата по счёту 7\nСумма=1.00")
    db.add(op)
    db.flush()
    return op


def _admin(db):
    return (db.query(User).filter(User.is_active == 1, User.role.has(key="admin"))
            .order_by(User.id).first())


def _counter(db):
    return db.execute(text(
        "SELECT value FROM company_settings WHERE key='payment_number_last'")).scalar()


def test_exported_document_has_every_field_once(db, paid_op):
    resp = ops.export_to_alfa(ops.AlfaExportRequest(ids=[paid_op.id], bank="АльфаБанк"),
                              db=db, current_user=_admin(db))

    async def read():
        return b"".join([c async for c in resp.body_iterator])
    doc = asyncio.run(read()).decode("cp1251")
    body = doc.split("СекцияДокумент=", 1)[1].split("КонецДокумента", 1)[0]
    keys = [ln.split("=", 1)[0] for ln in body.strip().split("\n")[1:]]
    assert keys.count("Сумма") == 1 and len(keys) == len(set(keys))
    assert "Сумма=1220.00" in doc


def test_failed_build_does_not_burn_payment_numbers(db, paid_op, monkeypatch):
    db.execute(text("INSERT INTO company_settings (key, value) VALUES ('payment_number_last', '0') "
                    "ON CONFLICT (key) DO NOTHING"))
    before = _counter(db)

    def boom(_fields):
        raise RuntimeError("сборка упала")
    monkeypatch.setattr(ops, "_alfa_document", boom)
    with pytest.raises(RuntimeError):
        ops.export_to_alfa(ops.AlfaExportRequest(ids=[paid_op.id], bank="АльфаБанк"),
                           db=db, current_user=_admin(db))
    assert _counter(db) == before
