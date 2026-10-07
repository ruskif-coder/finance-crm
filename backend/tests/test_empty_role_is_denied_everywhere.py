# -*- coding: utf-8 -*-
"""Роль без единого права не проходит ни в одну закрытую ручку — живым запросом.

`test_route_guards` отвечает на вопрос «у каждой ручки объявлена охрана». Он не отвечает на
другой: «охрана на самом деле срабатывает». Объявленная зависимость может быть не той
(подставили чужую), может не доходить до проверки роли, а ошибка в цепочке «токен → пользователь →
роль → право» может превратиться в 500 вместо отказа. Этот тест проверяет следствие, а не объявление:
пользователь с ПУСТОЙ ролью (строки прав есть, галочек нет) обходит все закрытые зависимостями ручки,
и каждая обязана ответить 403, а не пустить, не упасть и не ответить 404 «нет такого объекта»
(404 значит, что охрана пропустила и ручка пошла искать запись).

Что НЕ проверяется: ручки без зависимости-охраны (своё, открытое, проверка в теле) — их
перечисляет `test_route_guards`, и вызывать их здесь вслепую небезопасно.

Безопасность запуска: пока охрана цела, ни одна ручка не выполняется. Если охрана когда-нибудь
сломается, часть ручек без тела всё же выполнится — проверено 07.10.2026 нарочно выключенной
охраной: ручка «проверка почтового канала» поставила письмо в очередь, а «пересчёт индексов площадок» обновил настоящие строки
индексов. Поэтому адрес пользователя
теста — на недоставляемом домене `example.test`, идентификаторы несуществующие, а уборка стирает и
такие следы (`mail_log`). Тест пишет только свои строки.
"""
import uuid
from datetime import datetime

import pytest
from starlette.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import Role, RolePermission, User
from sqlalchemy import text
from app.permissions import SECTIONS
from app.routers.auth import create_access_token, token_claims

from tests import test_route_guards as guards   # те же классы охраны, что и в инвентаре

BIG = 999999999


def _fill(path: str) -> str:
    """Подставить несуществующие значения в параметры пути."""
    out, i = [], 0
    while i < len(path):
        if path[i] == "{":
            j = path.index("}", i)
            name = path[i + 1:j]
            kind = name.split(":")[-1] if ":" in name else ""
            out.append("zz" if kind in ("path", "str") or name in ("kind", "event_key", "secret",
                                                                    "field_name", "section", "key",
                                                                    "code", "name") else str(BIG))
            i = j + 1
        else:
            out.append(path[i])
            i += 1
    return "".join(out)


@pytest.fixture(scope="module")
def empty_role_client():
    db = SessionLocal()
    role = Role(key=f"zz_empty_{uuid.uuid4().hex[:8]}", label="zz пустая роль теста")
    db.add(role)
    db.commit()
    for s in SECTIONS:
        db.add(RolePermission(role_id=role.id, section=s["key"]))
    user = User(name="zz пустой", email=f"zz-empty-{uuid.uuid4().hex[:8]}@example.test",
                hashed_password="!", role_id=role.id, is_active=1,
                consent_accepted_at=datetime.utcnow())
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(token_claims(user))
    client = TestClient(app, raise_server_exceptions=False,
                        headers={"Authorization": f"Bearer {token}"})
    yield client
    db.rollback()
    # Следы ошибочно пропущенных ручек (проверено нарочно выключенной охраной 07.10.2026: «проверка
    # почтового канала» ставит письмо в очередь, «пересчёт индексов» пишет автора в строки индексов).
    db.execute(text("DELETE FROM mail_log WHERE user_id = :u"), {"u": user.id})
    db.execute(text("UPDATE publisher_balance_index SET updated_by = NULL WHERE updated_by = :u"),
               {"u": user.id})
    db.execute(text("UPDATE audit_log SET user_id = NULL WHERE user_id = :u"), {"u": user.id})
    db.query(User).filter(User.id == user.id).delete()
    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
    db.query(Role).filter(Role.id == role.id).delete()
    db.commit()
    db.close()


def _guarded_routes():
    out = []
    for (method, path), route in guards._routes():
        if guards._classify(route) != "guarded":
            continue
        if "require_cabinet_service" in guards._dep_names(route.dependant):
            continue                       # охрана другого рода: служебный токен, не роль
        out.append((method, path))
    return sorted(out)


def test_the_census_finds_a_lot_of_guarded_routes():
    assert len(_guarded_routes()) > 300, "перепись нашла слишком мало закрытых ручек — прибор слеп"


def test_every_guarded_route_refuses_a_role_with_no_rights(empty_role_client):
    leaks, crashes = [], []
    for method, path in _guarded_routes():
        r = empty_role_client.request(method, _fill(path))
        if r.status_code >= 500:
            crashes.append(f"{method} {path} -> {r.status_code}")
        elif r.status_code != 403:
            leaks.append(f"{method} {path} -> {r.status_code}")
    assert not crashes, "охрана упала вместо отказа:\n  " + "\n  ".join(crashes)
    assert not leaks, "пустая роль прошла охрану (или получила не отказ):\n  " + "\n  ".join(leaks)


def test_without_a_token_every_guarded_route_asks_to_log_in():
    anon = TestClient(app, raise_server_exceptions=False)
    bad = []
    for method, path in _guarded_routes():
        r = anon.request(method, _fill(path))
        if r.status_code != 401:
            bad.append(f"{method} {path} -> {r.status_code}")
    assert not bad, "без токена ответ не 401:\n  " + "\n  ".join(bad)
