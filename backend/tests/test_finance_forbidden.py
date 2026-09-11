# -*- coding: utf-8 -*-
"""Роль без права на финансы получает 403, а не данные.

ЗАЧЕМ ИМЕННО HTTP. В проекте есть `test_route_guards.py` — он обходит все 288 маршрутов
и проверяет, что у каждого объявлена зависимость проверки прав. Это ценный прибор, но
он про ИНВЕНТАРЬ: «охрана поставлена». Он не отвечает на вопрос, что увидит клиент,
если охрана сработает, — а именно этого и не хватало (F2-29 / F6-08 внешнего аудита
11.09.2026: клиентских проверок 403 на финансовые ручки не нашлось ни одной).

Разница не теоретическая. Зависимость можно объявить и при этом вернуть данные — если
она стоит не на том эндпоинте, если вместо `require_permission` подставлен
`require_any_permission` с лишней секцией, или если её результат нигде не используется.
Инвентарь всё это пропустит: имя в сигнатуре есть.

ЧТО ПРОВЕРЯЕТСЯ. Пользователь с ролью, у которой НЕТ ни одного финансового права,
получает 403 на каждой из ручек, читающих деньги. Не 200 с пустотой, не 500 — именно
отказ, и именно по коду.
"""
import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Role, RolePermission
from app.routers.auth import get_current_user

# Ручки, каждая из которых читает деньги. Список не полный по проекту — он полный по
# смыслу: сюда попало по одной точке на каждый финансовый экран.
MONEY_ROUTES = [
    "/api/operations/",
    "/api/reports/dds",
    "/api/reports/pl",
    "/api/reports/plan-fact",
    "/api/reports/receivables",
    "/api/reports/balance/full",
    "/api/finreport",
]


class _FakeRole:
    """Роль БЕЗ финансовых прав. `key` намеренно не 'admin': админ проходит везде без
    проверок, и на нём этот тест был бы зелёным всегда и ничего не значил."""
    key = "нет_прав_на_финансы"
    label = "Роль без финансов"
    id = -1


class _FakeUser:
    id = -1
    name = "тест"
    role = _FakeRole()
    role_id = -1
    is_active = 1


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.parametrize("route", MONEY_ROUTES)
def test_role_without_finance_rights_is_refused(client, route):
    r = client.get(route)
    assert r.status_code == 403, (
        f"{route} ответил {r.status_code} вместо 403. Роль без прав на финансы не должна "
        f"получать ни данные, ни ошибку сервера — только отказ. Тело: {r.text[:200]}")


def test_the_fake_role_really_has_no_rights():
    """Страховка: тест выше был бы зелёным и по случайности, если бы роль с таким
    ключом внезапно оказалась заведена и что-то ей было открыто."""
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.key == _FakeRole.key).first()
        assert role is None, (
            f"В базе завелась роль с ключом {_FakeRole.key!r} — тест перестал быть "
            "проверкой отказа. Поменяйте ключ в _FakeRole.")
        assert db.query(RolePermission).filter(
            RolePermission.role_id == _FakeRole.id).count() == 0
    finally:
        db.close()
