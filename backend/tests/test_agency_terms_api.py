# -*- coding: utf-8 -*-
"""«Агентские условия» — двери: права, сохранение правила, спор одинаково точных правил (409), Excel. Всё, что тест
пишет (правила, журнал), снимается за собой по id — данные стенда не трогаются."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.main import app
from app.routers.auth import get_current_user


class _Role:
    def __init__(self, key):
        self.key, self.id = key, None


class _User:
    def __init__(self, key):
        self.id, self.name, self.email = None, "test", "t@t"
        self.role, self.role_id, self.consent_accepted_at = _Role(key), None, True


@pytest.fixture
def client():
    db = SessionLocal()
    rule0 = db.execute(text("SELECT coalesce(max(id), 0) FROM sk_rules")).scalar()
    log0 = db.execute(text("SELECT coalesce(max(id), 0) FROM audit_log")).scalar()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    db.execute(text("DELETE FROM sk_rules WHERE id > :r"), {"r": rule0})
    db.execute(text("DELETE FROM audit_log WHERE id > :l AND action LIKE 'agency_terms_%'"), {"l": log0})
    db.commit()
    db.close()


def _pair():
    db = SessionLocal()
    try:
        return db.execute(text("""SELECT c.id, l.agency_id FROM sales_agency_counterparties l
                                    JOIN contracts c ON c.counterparty_id = l.counterparty_id LIMIT 1""")).first()
    finally:
        db.close()


def test_closed_without_the_right(client):
    app.dependency_overrides[get_current_user] = lambda: _User("role_13")          # трафик — права нет
    assert client.get("/api/agency-terms/tree").status_code == 403
    assert client.get("/api/agency-terms/calc?period=2026-10").status_code == 403
    assert client.get("/api/agency-terms/special").status_code == 403


def test_save_conflict_and_delete(client):
    pair = _pair()
    if not pair:
        pytest.skip("на стенде нет договора агентства")
    db = SessionLocal()
    try:
        brand = db.execute(text("SELECT id FROM sales_brands LIMIT 1")).scalar()
    finally:
        db.close()
    app.dependency_overrides[get_current_user] = lambda: _User("admin")
    # уточнение брендом — точнее правила по умолчанию на этот договор, с ним не спорит
    body = {"kind": "основная", "contract_id": pair[0], "agency_id": pair[1], "brand_id": brand, "mode": "постоплата",
            "percent": 12, "valid_from": "2026-01-01"}
    r = client.post("/api/agency-terms/rules", json=body)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    again = client.post("/api/agency-terms/rules", json={**body, "percent": 15})
    assert again.status_code == 409 and "той же точности" in again.json()["detail"]
    bad = client.post("/api/agency-terms/rules", json={**body, "contract_id": None})
    assert bad.status_code == 400 and "договор" in bad.json()["detail"]
    tree = client.get("/api/agency-terms/tree?side=agency").json()["items"]
    assert any(rule["id"] == rid for s in tree for e in s["entities"] for c in e["contracts"] for rule in c["rules"])
    assert client.delete(f"/api/agency-terms/rules/{rid}").status_code == 200


def test_calc_and_excel_answer(client):
    app.dependency_overrides[get_current_user] = lambda: _User("admin")
    r = client.get("/api/agency-terms/calc?period=2026-Q4")
    assert r.status_code == 200 and [m["period"] for m in r.json()["months"]] == ["2026-10", "2026-11", "2026-12"]
    assert client.get("/api/agency-terms/calc?period=октябрь").status_code == 400
    x = client.get("/api/agency-terms/calc.xlsx?period=2026-10")
    assert x.status_code == 200 and x.content[:2] == b"PK"


def test_reopen_month_is_admin_only(client):
    app.dependency_overrides[get_current_user] = lambda: _User("role_5")           # Мастер Сейлз — закрывает, но не открывает
    assert client.delete("/api/agency-terms/months/2026-10").status_code == 403


def test_partner_lives_under_the_special_right(client):
    """Хендофф 27.10.2026: партнёрская СК — во вкладке «Спец. условия» и по её праву; общие ручки — только основная."""
    pair = _pair()
    if not pair:
        pytest.skip("на стенде нет договора агентства")
    body = {"kind": "партнёрская", "agency_id": pair[1], "recipient_id": None, "mode": "постоплата", "percent": 2,
            "valid_from": "2026-01-01"}
    app.dependency_overrides[get_current_user] = lambda: _User("admin")
    assert client.post("/api/agency-terms/rules", json=body).status_code == 400
    app.dependency_overrides[get_current_user] = lambda: _User("role_9")          # Мастер аккаунт: правит основную, спец. — нет
    assert client.post("/api/agency-terms/special/partner", json=body).status_code == 403
    assert client.get("/api/agency-terms/special/calc?period=2026-10").status_code == 403
    app.dependency_overrides[get_current_user] = lambda: _User("admin")
    calc = client.get("/api/agency-terms/calc?period=2026-10").json()
    assert all(not r["partners"] for r in calc["rows"]) and calc["totals"]["partners"] == []


def test_special_calc_answers_for_month_and_quarter(client):
    app.dependency_overrides[get_current_user] = lambda: _User("admin")
    for p in ("2026-10", "2026-Q4"):
        r = client.get(f"/api/agency-terms/special/calc?period={p}")
        assert r.status_code == 200 and set(r.json()["kpi"]) == {"accrued", "accumulating", "year"}
    bad = client.post("/api/agency-terms/special", json={"scope_kind": "агентство", "scope_id": 1, "title": "фикс",
                                                         "amount": 100000, "valid_from": "2026-01-01"})
    assert bad.status_code == 400 and "дату «по»" in bad.json()["detail"]


def test_audit_text_of_partner_rule_hides_percent():
    """Поломка (ревью 27.10.2026): журнал действий видят по праву «Журнал», а не «Спец. условия» — запись о партнёрской СК
    с получателем и процентом раскрывала скрытую вкладку. Партнёрская — только номер правила; основная — как была."""
    from datetime import date
    from app.routers import agency_terms as AT
    base = {"contract_id": 7, "agency_id": 3, "advertiser_id": None, "brand_id": None, "service_id": None,
            "mode": "постоплата", "percent": 7.0, "valid_from": date(2026, 1, 1), "valid_to": None, "id": 42}
    partner = AT._rule_text({**base, "kind": "партнёрская", "recipient_id": 9})
    assert "7" not in partner.replace("№42", "") and "постоплата" not in partner and "№42" in partner
    assert "7 %" in AT._rule_text({**base, "kind": "основная"})


@pytest.mark.parametrize("fn,payload", [
    ("save_special", {"scope_kind": "агентство", "scope_id": "AG", "title": "x", "percent": 1000, "valid_from": "2026-01-01"}),
    ("save_special", {"scope_kind": "агентство", "scope_id": "AG", "title": "x", "percent": -3, "valid_from": "2026-01-01"}),
    ("save_special", {"scope_kind": "агентство", "scope_id": "AG", "title": "x", "amount": 1e13, "valid_from": "2026-01-01",
                      "valid_to": "2026-12-31"}),
    ("save_special", {"scope_kind": "агентство", "scope_id": 2_000_000_000, "title": "x", "percent": 3, "valid_from": "2026-01-01"}),
    ("save_work", {"agency_id": 2_000_000_000, "body": "x", "valid_from": "2026-01-01"}),
    ("save_work", {"agency_id": "AG", "body": "x", "commit_net": 1e13, "valid_from": "2026-01-01"}),
    ("save_rule", {"kind": "основная", "contract_id": 2_000_000_000, "agency_id": "AG", "mode": "постоплата", "percent": 10,
                   "valid_from": "2026-01-01"}),
])
def test_bad_input_is_a_clear_400_not_a_500(fn, payload):
    """Поломка (ревью 27.10.2026): процент спец. условия вне 0–100, отрицательная или огромная сумма, номер несуществующего
    агентства/договора — уходили в базу и падали переполнением или внешним ключом (500). Должно быть 400 с объяснением."""
    from app.agency_terms import service as S
    db = SessionLocal()
    try:
        ag = db.execute(text("SELECT id FROM sales_agencies ORDER BY id LIMIT 1")).scalar()
        p = {k: (ag if v == "AG" else v) for k, v in payload.items()}
        with pytest.raises(S.TermsError) as e:
            getattr(S, fn)(db, p, None)
            db.flush()
        assert e.value.status == 400 and e.value.message
    finally:
        db.rollback()
        db.close()


def test_excel_name_survives_any_spelling_of_the_period(client):
    """Сторож (ревью 27.10.2026, находка не подтвердилась): период идёт в заголовок файла как есть, поэтому строгая проверка
    периода — единственное, что не пускает туда кириллицу и перевод строки (500 в заголовке). Ослабят проверку — упадёт здесь."""
    app.dependency_overrides[get_current_user] = lambda: _User("admin")
    r = client.get("/api/agency-terms/calc.xlsx", params={"period": "2026-10" + chr(10)})
    assert r.status_code in (200, 400), r.text[:200]
    if r.status_code == 200:
        assert r.headers["content-disposition"].startswith('attachment; filename="sk_2026-10.xlsx"')
