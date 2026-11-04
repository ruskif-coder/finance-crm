# -*- coding: utf-8 -*-
"""Окно контрагента — проверки блоков «Договоры» и «Шаблоны документов» (план 2026-11-05, Task 4).

Поломки, которые ловит: окно зелёное, когда ДС по договору не соберётся (нет канала выдачи, формата, нашего подписанта) —
то есть проверки разошлись с `contract_check.gaps`, `signers.for_side` и `resolve_for_contract`; договоры, где юрлицо —
наше (`own_company_id`), попадают в «Договоры» как договоры контрагента; у площадки без CPM сверке не из чего считать.
Всё в откатываемой транзакции.
"""
from datetime import date

import pytest

import app.model_registry  # noqa: F401
from app.annex_tpl import service as TS
from app.database import SessionLocal
from app.models import Contract, Counterparty
from app.readiness import contracts as C

ON = date(2026, 11, 4)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


_N = iter(range(10**6))


def _cp(db, **kw):
    c = Counterparty(name=f"ООО «Тест договоров {next(_N)}»", inn="7707083893", kpp="770701001", term_days=kw.pop("term_days", 60), **kw)
    db.add(c)
    db.flush()
    return c


def _ct(db, cp, **kw):
    base = dict(contract_number="Т-01/26", contract_date=date(2026, 1, 15), counterparty_id=cp.id, issue_channel="ЭДО",
                cooperation_format=None, payment_term_days=60, end_date_text="31.12.2026", prolongation="АВТО на год",
                document_link="https://edo.example/1")
    base.update(kw)
    c = Contract(**base)
    db.add(c)
    db.flush()
    db.refresh(c)
    return c


def _ids(checks):
    return {c["id"]: c for c in checks}


def test_contract_gaps_are_the_documents_gaps(db):
    cp = _cp(db)
    ct = _ct(db, cp, issue_channel=None)
    got = _ids(C.ct_checks(db, cp, ON))[f"ct.channel.{ct.id}"]
    assert got["sev"] == "bad" and got["source"] == "annex_tpl/contract_check.gaps"


def test_no_format_means_no_template(db):
    cp = _cp(db)
    ct = _ct(db, cp, cooperation_format=None)
    assert _ids(C.ct_checks(db, cp, ON))[f"ct.format.{ct.id}"]["sev"] == "bad"
    tpl = _ids(C.tpl_checks(db, cp))[f"tpl.resolve.{ct.id}"]
    assert tpl["sev"] == "bad" and tpl["why"] == TS.resolve_for_contract(db, ct)["reason"]


def test_our_signer_missing(db, monkeypatch):
    cp = _cp(db)
    ct = _ct(db, cp)
    monkeypatch.setattr("app.signers.service.for_side",
                        lambda db_, c, side: (object(), "договор") if side == "заказчик" else (None, None))
    got = _ids(C.ct_checks(db, cp, ON))
    assert got[f"ct.our_signer.{ct.id}"]["sev"] == "bad" and f"ct.customer_signer.{ct.id}" not in got


def test_term_differs_from_counterparty_is_warn(db):
    cp = _cp(db, term_days=90)
    ct = _ct(db, cp, payment_term_days=60)
    assert _ids(C.ct_checks(db, cp, ON))[f"ct.term.{ct.id}"]["sev"] == "warn"


def test_no_document_is_warn(db):
    cp = _cp(db)
    ct = _ct(db, cp, document_link=None, attached_filename=None)
    assert _ids(C.ct_checks(db, cp, ON))[f"ct.document.{ct.id}"]["sev"] == "warn"


def test_expired_without_prolongation_is_bad(db):
    cp = _cp(db)
    ct = _ct(db, cp, end_date_text="31.12.2025", prolongation="Нет")
    assert _ids(C.ct_checks(db, cp, ON))[f"ct.valid_until.{ct.id}"]["sev"] == "bad"


def test_contracts_where_cp_is_only_our_company_are_not_its_contracts(db):
    cp = _cp(db)
    other = _cp(db)
    _ct(db, other, own_company_id=cp.id)
    assert C.ct_data(db, cp) == []


def test_contract_data_shape(db):
    cp = _cp(db)
    ct = _ct(db, cp, attached_filename="договор.pdf")
    from sqlalchemy import text
    db.execute(text("UPDATE contracts SET nds = true, own_legal_role = 'EXECUTOR' WHERE id = :i"), {"i": ct.id})
    row = C.ct_data(db, cp)[0]
    assert row["id"] == ct.id and row["vat"] == "с НДС" and row["own_legal_role"] == "исполнитель"
    assert row["valid_until"] == "31.12.2026" and row["document_url"] == "https://edo.example/1"
    assert row["document_file"] == {"name": "договор.pdf"}


def test_template_tags_read_from_resolved_version(db, monkeypatch):
    cp = _cp(db)
    ct = _ct(db, cp)
    tpl = type("T", (), {"id": 1})()
    monkeypatch.setattr(TS, "resolve_for_contract", lambda db_, c: {"template": tpl, "reason": None})
    monkeypatch.setattr(TS, "current", lambda db_, tid: type("V", (), {"blocks": [
        {"text": "Заказчик {заказчик} и {юр_название}"}, {"text": "сумма {итого}"}]})())
    assert C.template_tags(db, ct) == {"заказчик", "юр_название", "итого"}
    monkeypatch.setattr(TS, "resolve_for_contract", lambda db_, c: {"template": None, "reason": "нет формата"})
    assert C.template_tags(db, ct) == set()


def test_publisher_contract_has_cpm_check(db):
    from app.sales.models import SalesPublisher, SalesPublisherContract
    cp = _cp(db)
    ct = _ct(db, cp)
    pub = SalesPublisher(name="тест площадки окна", domain="okno-test.example", cpm_contract=None)
    db.add(pub)
    db.flush()
    db.add(SalesPublisherContract(publisher_id=pub.id, contract_id=ct.id, role="с площадкой"))
    db.flush()
    assert _ids(C.ct_checks(db, cp, ON))[f"ct.cpm.{ct.id}"]["sev"] == "bad"


def test_annex_word_shows_its_ui_name(db):
    from app.annex_tpl.doc_kind import KINDS
    cp = _cp(db)
    _ct(db, cp, annex_word="приложение")
    assert "приложение" in KINDS and C.ct_data(db, cp)[0]["annex_word"] == "Приложение"


def test_signer_label_without_position_has_no_none():
    s = type("S", (), {"director_name": "Кряжев Д. Д.", "signer_position": None})()
    assert C._signer_label(s) == "Кряжев Д. Д."
