# -*- coding: utf-8 -*-
"""Подписанты (владелец 28.10.2026): несколько у юрлица, один по умолчанию; договор выбирает подписанта стороны из списка её юрлица;
нет выбора — по умолчанию; истёкшая доверенность — ДС не подтверждается. Всё внутри транзакции, откатывается."""
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.models import Contract, Counterparty
from app.signers import service as S

USER = SimpleNamespace(id=None, name="тест")


@pytest.fixture
def db():
    s = SessionLocal()
    before = s.execute(text("select count(*) from counterparty_signers")).scalar()
    try:
        yield s
    finally:
        s.rollback()
        left = s.execute(text("select count(*) from counterparty_signers")).scalar()
        s.close()
        assert left == before, "тест оставил подписантов на стенде"


def _cp(db, name="ТЕСТ подписанты"):
    cp = Counterparty(name=name, inn="7700000000")
    db.add(cp)
    db.flush()
    return cp


def _contract(db, cp):
    c = Contract(contract_number="ТЕСТ-ПОДП", counterparty_name=cp.name, counterparty_id=cp.id)
    db.add(c)
    db.flush()
    return c


GEN = {"director_name": "Иванов Иван Иванович", "signer_position": "Генеральный директор", "signer_basis": "Устава"}
POA = {"director_name": "Петров Пётр Петрович", "signer_position": "Коммерческий директор",
       "signer_basis": "доверенности № 12 от 01.02.2026", "valid_until": date(2026, 12, 31)}


def test_first_signer_is_default_and_default_switches(db):
    cp = _cp(db)
    a = S.create(db, cp.id, GEN, USER)
    b = S.create(db, cp.id, POA, USER)
    assert a.is_default is True and b.is_default is False
    S.set_default(db, b.id, USER)
    db.refresh(a)
    assert S.default_of(db, cp.id).id == b.id and a.is_default is False


def test_default_cannot_be_archived_others_can(db):
    cp = _cp(db)
    a = S.create(db, cp.id, GEN, USER)
    b = S.create(db, cp.id, POA, USER)
    with pytest.raises(S.SignerError) as e:
        S.archive(db, a.id, True, USER)
    assert e.value.status == 409
    S.archive(db, b.id, True, USER)
    assert [s.id for s in S.list_of(db, cp.id)] == [a.id]
    assert {s.id for s in S.list_of(db, cp.id, archived=True)} == {a.id, b.id}


def test_contract_side_uses_its_choice_or_the_default(db):
    cp = _cp(db)
    c = _contract(db, cp)
    a = S.create(db, cp.id, GEN, USER)
    b = S.create(db, cp.id, POA, USER)
    assert S.for_side(db, c, "заказчик") == (a, "по умолчанию")
    S.choose(db, c, "заказчик", b.id, USER)
    assert S.for_side(db, c, "заказчик") == (b, "договор")
    S.archive(db, b.id, True, USER)
    assert S.for_side(db, c, "заказчик") == (a, "по умолчанию")       # подписант в архиве — снова по умолчанию
    S.choose(db, c, "заказчик", None, USER)
    assert S.for_side(db, c, "заказчик") == (a, "по умолчанию")


def test_signer_of_another_legal_entity_is_refused(db):
    cp, other = _cp(db), _cp(db, "ТЕСТ чужой")
    c = _contract(db, cp)
    foreign = S.create(db, other.id, GEN, USER)
    with pytest.raises(S.SignerError) as e:
        S.choose(db, c, "заказчик", foreign.id, USER)
    assert e.value.status == 400
    with pytest.raises(S.SignerError):
        S.choose(db, c, "сторона", None, USER)


def test_expired_power_of_attorney_blocks_the_document(db):
    cp = _cp(db)
    c = _contract(db, cp)
    b = S.create(db, cp.id, {**POA, "valid_until": date(2026, 10, 1)}, USER)
    S.choose(db, c, "заказчик", b.id, USER)
    p = S.party_of(db, cp, c, "заказчик", on=date(2026, 10, 15))
    assert p["director"] == "Петров Пётр Петрович"
    assert any("доверенность" in m and "01.10.2026" in m for m in p["missing"])
    assert not any("доверенность" in m for m in S.party_of(db, cp, c, "заказчик", on=date(2026, 9, 30))["missing"])


def test_no_signer_means_missing_fields(db):
    cp = _cp(db)
    miss = S.party_of(db, cp)["missing"]
    assert "ФИО подписанта" in miss and "основание полномочий" in miss


def test_upsert_default_creates_then_updates(db):
    cp = _cp(db)
    S.upsert_default(db, cp, GEN, USER)
    S.upsert_default(db, cp, {**GEN, "signer_basis": "Устава и доверенности"}, USER)
    rows = S.list_of(db, cp.id)
    assert len(rows) == 1 and rows[0].is_default and rows[0].signer_basis == "Устава и доверенности"
