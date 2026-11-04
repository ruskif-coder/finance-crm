# -*- coding: utf-8 -*-
"""Окно контрагента — сборка ответа, права, сводка, журнал, дубли (план 2026-11-05, Task 6).

Поломки, которые ловит: юрлицо двух видов сразу получает блоки только первого вида; у нашего юрлица в «Договорах»
оказываются договоры, где оно лишь наша сторона; блок без права виден или его алерты остаются в сводке и счётчиках;
главная строка сводки говорит «всё готово», когда ДС не собрать; дубль по ИНН не отличается от филиала с другим КПП;
«было → стало» журнала не разбирается; пакетный счёт расходится с одиночным; вход без права `directory_add`.
Всё в откатываемой транзакции; журнал, который пишет тест, снимается по id.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.main import app
from app.models import AuditLog, Contract, Counterparty, User
from app.readiness import history as H
from app.readiness import service as S
from app.routers.auth import get_current_user
from app.sales.models import (SalesAgency, SalesAgencyCounterparty, SalesPublisher, SalesPublisherCounterparty)

_N = iter(range(10**6))


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _admin(db):
    return db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()


def _cp(db, **kw):
    c = Counterparty(name=f"ООО «Тест окна {next(_N)}»", inn=kw.pop("inn", "7707083893"), kpp=kw.pop("kpp", "770701001"), **kw)
    db.add(c)
    db.flush()
    return c


def _agency_and_publisher(db, cp):
    ag = SalesAgency(name=f"Тест-агентство окна {next(_N)}", short_name="Тест-агентство окна")
    pub = SalesPublisher(name=f"тест площадки окна {next(_N)}", domain=f"okno-{next(_N)}.example")
    db.add_all([ag, pub])
    db.flush()
    db.add_all([SalesAgencyCounterparty(agency_id=ag.id, counterparty_id=cp.id),
                SalesPublisherCounterparty(publisher_id=pub.id, counterparty_id=cp.id)])
    db.flush()


def test_agency_and_publisher_at_once_gets_both_block_sets(db):
    cp = _cp(db)
    _agency_and_publisher(db, cp)
    assert set(S.kinds_of(db, cp)) == {"agency", "publisher"}
    out = S.build(db, cp.id, _admin(db))
    assert {"cp", "sg", "ct", "tpl", "ag", "sk", "ord"} <= set(out["blocks"])
    assert "ad" not in out["blocks"], "у агентства нет блока рекламодателей — они независимы (владелец 04.11.2026)"
    assert out["agency"]["short_name"] == "Тест-агентство окна"
    assert any(c["id"] == "cp.publisher_vat" for c in out["checks"]), "проверка площадки пропала у агентства"


def test_plain_counterparty_is_contractor_without_market_blocks(db):
    cp = _cp(db)
    assert S.kinds_of(db, cp) == ["contractor"]
    out = S.build(db, cp.id, _admin(db))
    assert out["blocks"] == ["cp", "sg", "ct", "tpl"] and "ord" not in out


def test_own_company_opens_without_its_own_contracts(db):
    us = _cp(db, is_own_company=True)
    other = _cp(db)
    db.add(Contract(contract_number=f"Т-{next(_N)}", counterparty_id=other.id, own_company_id=us.id))
    db.flush()
    out = S.build(db, us.id, _admin(db))
    assert out["contracts"] == []


def test_no_sk_terms_hides_block_and_its_checks(db, monkeypatch):
    cp = _cp(db)
    _agency_and_publisher(db, cp)
    db.add(Contract(contract_number=f"Т-{next(_N)}", counterparty_id=cp.id))
    db.flush()
    full = S.build(db, cp.id, _admin(db))
    assert any(c["block"] == "sk" for c in full["checks"])
    perms = {s: {"view": True, "edit": True} for s in S.SECTIONS.values()}
    perms["sk_terms"] = {"view": False, "edit": False}
    monkeypatch.setattr(S, "get_permissions_for_user", lambda db_, u: perms)
    out = S.build(db, cp.id, _admin(db))
    assert "sk" not in out and "sk" not in out["blocks"]
    assert not any(c["block"] == "sk" for c in out["checks"])
    assert out["total"] < full["total"] and "sk_terms" not in out["permissions"]["view"]


def test_headline_rules():
    c = lambda block, sev, title: {"block": block, "sev": sev, "title": title}  # noqa: E731
    assert S.headline([c("ad", "bad", "Сироп: нет ККТУ третьего уровня"),
                       c("ct", "bad", "РМ-01/25: нет формата сотрудничества")]) == "ДС по РМ-01/25 сейчас не собрать"
    assert S.headline([c("ad", "bad", "Сироп: нет ККТУ третьего уровня")]) == "ЕРИД по Сироп не выпустится"
    assert S.headline([c("ct", "bad", "договор 103: номер")]) == "ДС по договору 103 сейчас не собрать"
    assert S.headline([c("cp", "warn", "Нет: ОГРН")]) == "документы соберутся"
    assert S.headline([]) == "всё готово к документам и ОРД"


def test_lookup_exact_inn_kpp_and_branch(db):
    inn = f"77{next(_N):08d}"
    head = _cp(db, inn=inn, kpp="770101001")
    branch = _cp(db, inn=inn, kpp="780101001")
    got = {r["id"]: r for r in S.lookup(db, inn, "770101001")["counterparties"]}
    assert got[head.id]["exact"] is True and got[branch.id]["exact"] is False
    assert got[branch.id]["kpp"] == "780101001" and "договор" in got[head.id]["info"]


def test_history_parses_before_after(db):
    cp = _cp(db)
    ct = Contract(contract_number=f"Т-{next(_N)}", counterparty_id=cp.id)
    db.add(ct)
    db.flush()
    db.add(AuditLog(user_name="Тест", action="update_contract", entity_type="contract", entity_id=ct.id,
                    details="пролонгация: — → АВТО на год"))
    db.flush()
    rows = H.of_block(db, cp.id, "ct")
    assert rows[0]["what"] == "пролонгация" and rows[0]["from"] is None and rows[0]["to"] == "АВТО на год"
    assert rows[0]["who"] == "Тест"


def test_build_many_matches_build(db):
    ids = [i for (i,) in db.execute(text("SELECT counterparty_id FROM contracts WHERE counterparty_id IS NOT NULL "
                                         "GROUP BY counterparty_id ORDER BY count(*) DESC LIMIT 3"))]
    many = S.build_many(db, ids)
    for i in ids:
        one = S.build(db, i, _admin(db))
        assert many[i] == {"bad": sum(c["sev"] == "bad" for c in one["checks"]),
                           "warn": sum(c["sev"] == "warn" for c in one["checks"])}


class _Role:
    def __init__(self, key):
        self.key, self.id = key, None


def test_readiness_needs_directory_add(db):
    cp_id = db.execute(text("SELECT min(id) FROM counterparties")).scalar()
    nobody = SimpleNamespace(id=None, name="test", email="t@t", role=_Role("role_nobody"), role_id=None, consent_accepted_at=True)
    app.dependency_overrides[get_current_user] = lambda: nobody
    try:
        with TestClient(app) as c:
            for url in (f"/api/directory-add/readiness/{cp_id}", f"/api/directory-add/readiness/{cp_id}/history?block=cp",
                        "/api/directory-add/lookup?inn=7707083893"):
                assert c.get(url).status_code == 403, url
    finally:
        app.dependency_overrides.clear()


def test_fields_overwritten_by_writers_come_back(db):
    """Ручки реквизитов, агентства и рекламодателя перезаписывают `note` (рекламодатель — и `counterparty_id`) целиком:
    окно обязано их получить, иначе первое же «Сохранить» сотрёт примечание и отвяжет рекламодателя."""
    from app.sales.models import SalesAdvertiser, SalesAdvertiserCounterparty
    cp = _cp(db, note="примечание юрлица")
    _agency_and_publisher(db, cp)
    a = SalesAdvertiser(name=f"Тест-рекл окна {next(_N)}", short_name="Тест-рекл окна", note="примечание рекл", counterparty_id=cp.id)
    db.add(a)
    db.flush()
    db.add(SalesAdvertiserCounterparty(advertiser_id=a.id, counterparty_id=cp.id))
    db.flush()
    out = S.build(db, cp.id, _admin(db))
    assert out["counterparty"]["note"] == "примечание юрлица"
    assert "note" in out["agency"]
    adv = next(x for x in out["advertisers"] if x["id"] == a.id)
    assert adv["note"] == "примечание рекл" and adv["counterparty_id"] == cp.id


def test_signer_options_carry_ids(db):
    from app.signers.models import CounterpartySigner
    cp = _cp(db)
    db.add(CounterpartySigner(counterparty_id=cp.id, director_name="Иванов Иван", signer_position="директор",
                              signer_basis="Устав", is_default=True))
    db.flush()
    out = S.build(db, cp.id, _admin(db))
    opt = out["options"]["signers"]
    assert opt and opt[0]["label"].startswith("Иванов Иван") and opt[0]["id"]
    assert isinstance(out["options"]["ourSigners"], list)


def test_header_is_there_without_counterparties_right(db, monkeypatch):
    """Ревью: без `counterparties.view` блока «Юрлицо» нет, но шапке окна нужны имя и ИНН — иначе белый экран."""
    cp = _cp(db)
    perms = {s: {"view": True, "edit": True} for s in S.SECTIONS.values()}
    perms["counterparties"] = {"view": False, "edit": False}
    monkeypatch.setattr(S, "get_permissions_for_user", lambda db_, u: perms)
    out = S.build(db, cp.id, _admin(db))
    assert "cp" not in out["blocks"] and "banks" not in out
    assert out["counterparty"] == {"id": cp.id, "name": cp.name, "inn": cp.inn, "kpp": cp.kpp, "status": cp.status}


def test_contract_history_has_no_ord_events(db):
    """Ревью: события ОРД пишутся на договор — в истории «Договоров» их быть не должно, они видны только с правом ОРД."""
    cp = _cp(db)
    ct = Contract(contract_number=f"Т-{next(_N)}", counterparty_id=cp.id)
    db.add(ct)
    db.flush()
    db.add_all([AuditLog(user_name="Тест", action="ord_register_final", entity_type="contract", entity_id=ct.id, details="ОРД"),
                AuditLog(user_name="Тест", action="update_contract", entity_type="contract", entity_id=ct.id, details="номер: — → 1")])
    db.flush()
    assert [r["what"] for r in H.of_block(db, cp.id, "ct")] == ["номер"]
    assert [r["what"] for r in H.of_block(db, cp.id, "ord")] == ["ОРД"]


def test_lookup_hides_advertisers_without_their_right(db):
    from app.sales.models import SalesAdvertiser
    inn = f"78{next(_N):08d}"
    db.add(SalesAdvertiser(name=f"Тест-рекл дубля {next(_N)}", short_name="Тест-рекл дубля", inn=inn))
    db.flush()
    assert S.lookup(db, inn)["advertisers"]
    assert S.lookup(db, inn, see_advertisers=False)["advertisers"] == []
