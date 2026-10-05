# -*- coding: utf-8 -*-
"""Настройки «SIMB ID» (владелец 05.10.2026): коэффициенты для отчётов клиенту — частота и
CTR, у каждого базовое значение и поправка ±% . Вкладка только админа: настройки
действуют на отчёты всех РК."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.main import app
from app.routers.auth import get_current_user
from app.routers import simb_id as S


class _Role:
    def __init__(self, key):
        self.key = key


class _User:
    def __init__(self, key):
        self.id, self.name, self.email = None, "test", "t@t"
        self.role = _Role(key)
        self.consent_accepted_at = True


@pytest.fixture
def client():
    """Настройки стенда сохраняются и ВОЗВРАЩАЮТСЯ: тест не должен трогать то, что ввёл
    человек. 05.10.2026 прежний вариант стёр настройки владельца: возврат шёл UPDATE-ом по
    строке, которую тест умолчаний уже удалил, а журнал чистился целиком, с его записью."""
    db = SessionLocal()
    was = db.execute(text("SELECT value FROM company_settings WHERE key = :k"),
                     {"k": S.KEY}).scalar()
    audit_from = db.execute(text("SELECT coalesce(max(id), 0) FROM audit_log")).scalar()
    db.close()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    db = SessionLocal()
    if was is None:
        db.execute(text("DELETE FROM company_settings WHERE key = :k"), {"k": S.KEY})
    else:
        db.execute(text("""INSERT INTO company_settings (key, value) VALUES (:k, :v)
                           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"""),
                   {"k": S.KEY, "v": was})
    db.execute(text("DELETE FROM audit_log WHERE action = 'simb_id_settings' AND id > :a"),
               {"a": audit_from})
    db.commit()
    db.close()


def test_fixture_returns_settings_it_found(client):
    """Прибор к самому себе: значение, найденное до теста, после теста на месте."""
    _as("admin")
    client.put("/api/settings/simb-id", json=S.DEFAULTS)


def _as(key):
    app.dependency_overrides[get_current_user] = lambda: _User(key)


def test_defaults_when_never_saved(client):
    _as("admin")
    db = SessionLocal()
    db.execute(text("DELETE FROM company_settings WHERE key = :k"), {"k": S.KEY})
    db.commit()
    db.close()
    r = client.get("/api/settings/simb-id")
    assert r.status_code == 200
    assert r.json() == S.DEFAULTS


def test_save_and_read_back(client):
    _as("admin")
    body = {"freq_base": 3.7, "freq_dev_pct": 10, "ctr_base": 0.25, "ctr_dev_pct": 15}
    assert client.put("/api/settings/simb-id", json=body).status_code == 200
    assert client.get("/api/settings/simb-id").json() == body


@pytest.mark.parametrize("bad", [
    {"freq_base": 0, "freq_dev_pct": 10, "ctr_base": 0.2, "ctr_dev_pct": 10},     # частота 0
    {"freq_base": 3, "freq_dev_pct": 150, "ctr_base": 0.2, "ctr_dev_pct": 10},    # поправка > 100
    {"freq_base": 3, "freq_dev_pct": -5, "ctr_base": 0.2, "ctr_dev_pct": 10},     # отрицательная
    {"freq_base": 3, "freq_dev_pct": 10, "ctr_base": 120, "ctr_dev_pct": 10},     # CTR > 100 %
])
def test_rejects_impossible_values(client, bad):
    _as("admin")
    assert client.put("/api/settings/simb-id", json=bad).status_code == 422


def test_only_admin(client):
    _as("sales")
    assert client.get("/api/settings/simb-id").status_code == 403
    assert client.put("/api/settings/simb-id", json=S.DEFAULTS).status_code == 403
