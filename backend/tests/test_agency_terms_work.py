# -*- coding: utf-8 -*-
"""«Условия работы» (владелец 27.10.2026): договорённости для аккаунта при сборке МП. Признаки необязательны, хотя бы один;
текст обязателен; показ в МП — всем, у кого есть право на медиапланы. Всё, что тест пишет, откатывается/снимается."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.agency_terms import service as S
from app.database import SessionLocal
from app.main import app
from app.routers.auth import get_current_user


class _U:
    id = None


def test_work_term_needs_text_and_a_feature():
    db = SessionLocal()
    try:
        with pytest.raises(S.TermsError) as e:
            S.save_work(db, {"body": "cpm 330", "valid_from": "2026-01-01"}, _U())
        assert "признак" in e.value.message
        with pytest.raises(S.TermsError):
            S.save_work(db, {"agency_id": 1, "body": "  ", "valid_from": "2026-01-01"}, _U())
        with pytest.raises(S.TermsError):
            S.save_work(db, {"agency_id": 1, "body": "x", "commit_net": -5, "valid_from": "2026-01-01"}, _U())
        w = S.save_work(db, {"agency_id": 1, "body": "cpm 330 фиксируем", "mail_subject": "RE: условия 2026", "commit_net": 25_000_000,
                             "valid_from": "2026-01-01"}, _U())
        assert S.work_dict(w)["commit_net"] == 25_000_000
    finally:
        db.rollback()
        db.close()


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
    w0 = db.execute(text("SELECT coalesce(max(id), 0) FROM sk_work_terms")).scalar()
    log0 = db.execute(text("SELECT coalesce(max(id), 0) FROM audit_log")).scalar()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    db.execute(text("DELETE FROM sk_work_terms WHERE id > :w"), {"w": w0})
    db.execute(text("DELETE FROM audit_log WHERE id > :l AND action LIKE 'agency_terms_%'"), {"l": log0})
    db.commit()
    db.close()


def test_work_api_crud_and_rights(client):
    app.dependency_overrides[get_current_user] = lambda: _User("role_13")          # трафик — ни СК, ни медиапланов
    assert client.get("/api/agency-terms/work").status_code == 403
    assert client.get("/api/agency-terms/work/active").status_code == 403
    app.dependency_overrides[get_current_user] = lambda: _User("admin")
    r = client.post("/api/agency-terms/work", json={"agency_id": 1, "body": "отчёт от 500к бонусом", "valid_from": "2026-01-01"})
    assert r.status_code == 200, r.text
    wid = r.json()["id"]
    assert any(w["id"] == wid for w in client.get("/api/agency-terms/work/active").json())
    assert client.put(f"/api/agency-terms/work/{wid}", json={"agency_id": 1, "body": "отчёт от 1М", "valid_from": "2026-01-01"}).json()["body"] == "отчёт от 1М"
    assert client.delete(f"/api/agency-terms/work/{wid}").status_code == 200


def test_bonus_flags_keep_their_note_only_when_set():
    """Креативы и отчёты бонусом (владелец 27.10.2026): флажок + «при каком условии». Поломка, которую ловит: комментарий
    остаётся у снятого флажка (плашка в МП показала бы бонус, которого нет) или флажок не сохраняется вовсе."""
    db = SessionLocal()
    try:
        w = S.save_work(db, {"agency_id": 1, "body": "x", "valid_from": "2026-01-01",
                             "creatives_bonus": True, "creatives_bonus_note": " при бюджете от 1 млн ",
                             "reports_bonus": False, "reports_bonus_note": "забытый текст"}, _U())
        d = S.work_dict(w)
        assert (d["creatives_bonus"], d["creatives_bonus_note"]) == (True, "при бюджете от 1 млн")
        assert (d["reports_bonus"], d["reports_bonus_note"]) == (False, None)
        d = S.work_dict(S.save_work(db, {"agency_id": 1, "body": "x", "valid_from": "2026-01-01"}, _U(), w.id))
        assert (d["creatives_bonus"], d["creatives_bonus_note"]) == (False, None), "не прислали флажок — бонуса нет"
    finally:
        db.rollback()
        db.close()
