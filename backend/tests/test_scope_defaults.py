# -*- coding: utf-8 -*-
"""Область видимости сделок: нет строки — ОТКАЗ, а не «все сделки».

ЗАЧЕМ. Отсутствие одной и той же строки `role_permissions` означало в проекте
ПРОТИВОПОЛОЖНОЕ в двух местах: у `require_permission` — «запрещено», у
`_own_rep_ids_or_all` — «показать все сделки». Роль, которой выдали креативы, но не
завели строку `sales_registry`, молча получала чужие сделки (F1-05 внешнего аудита
11.09.2026). 11.09.2026 умолчание перевели в отказ; тест держит это свойство.

ТРИ ВЕЩИ ПРОВЕРЯЮТСЯ ЗДЕСЬ, и третья — про сам тест.

Первые две — поведение: отказ при отсутствии строки и то, что админ по-прежнему проходит
без проверок. Они сделаны на ПОДДЕЛЬНОМ пользователе, а не на учётке со стенда: прежняя
редакция звала `pytest.skip`, если в базе не нашлось активной неадминской учётки, — то
есть несущее утверждение исчезало ровно в том сценарии, ради которого пишется прибор
(пустая база у стороннего проверяющего дала 208 скипов). `_own_rep_ids_or_all` принимает
обычный объект, подделка обходится дёшево.

Третья — состояние НАСТРОЕК, и список разделов для неё берётся ИЗ КОДА, а не пишется
руками. Прежняя редакция перечисляла `("creatives", "launch_prep")`, и `launch_prep` в
`SECTIONS` не существует вовсе: половина проверки была мёртвой, а выглядела живой.
"""
import ast
import pathlib

import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.models import RolePermission
from app.permissions import SECTIONS
from app.routers.sales_dashboard import _own_rep_ids_or_all

ROUTERS = pathlib.Path(__file__).resolve().parents[1] / "app" / "routers"


def _scope_sections() -> set:
    """Какие разделы РЕАЛЬНО спрашивают область видимости — по вызовам в коде.

    Обходим все роутеры и собираем третий аргумент `_own_rep_ids_or_all(...)`: строковый
    литерал, если он передан, и значение по умолчанию, если нет. Так список не может
    разойтись с кодом — а разойтись он уже успел.
    """
    default = "sales_registry"
    found = set()
    for path in ROUTERS.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
            if name != "_own_rep_ids_or_all":
                continue
            if len(node.args) >= 3 and isinstance(node.args[2], ast.Constant) \
                    and isinstance(node.args[2].value, str):
                found.add(node.args[2].value)
            elif len(node.args) < 3:
                found.add(default)
    return found


class _FakeRole:
    key = "роль_без_области"
    label = "Роль без настроенной области"
    id = -777


class _FakeUser:
    id = -777
    name = "тест"
    role = _FakeRole()
    role_id = -777
    is_active = 1


class _FakeAdminRole(_FakeRole):
    key = "admin"
    label = "Администратор"


class _FakeAdmin(_FakeUser):
    role = _FakeAdminRole()


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


# ── поведение ────────────────────────────────────────────────────────────────

def test_missing_row_refuses_instead_of_opening_everything(db):
    """Нет строки — отказ, а НЕ «все сделки»."""
    with pytest.raises(HTTPException) as e:
        _own_rep_ids_or_all(db, _FakeUser(), "секция_которой_нет")
    assert e.value.status_code == 403
    assert "видимость сделок" in e.value.detail


def test_the_fake_role_really_has_no_rows(db):
    """Страховка: тест выше был бы зелёным и по случайности, если бы роль с таким
    идентификатором вдруг завелась и ей что-то настроили."""
    assert db.query(RolePermission).filter(
        RolePermission.role_id == _FakeRole.id).count() == 0


def test_admin_still_sees_everything(db):
    """Админ проходит без проверок — это отдельный режим, а не «много прав»."""
    assert _own_rep_ids_or_all(db, _FakeAdmin(), "секция_которой_нет") is None


# ── список разделов ──────────────────────────────────────────────────────────

def test_every_scope_section_is_a_real_permission_key():
    """Раздел, который спрашивает область, ОБЯЗАН существовать в `SECTIONS`.

    Иначе строки `role_permissions` с таким именем не бывает никогда, и каждый запрос
    к разделу — гарантированный 403 (или, до 11.09.2026, гарантированные «все сделки»).
    """
    keys = {s["key"] for s in SECTIONS}
    unknown = sorted(_scope_sections() - keys)
    assert not unknown, (
        f"Область видимости спрашивается у разделов, которых нет в SECTIONS: {unknown}. "
        "Строки role_permissions с таким именем не существует, значит проверка мёртвая.")


def test_every_live_role_has_the_scope_row_it_needs(db):
    """Состояние НАСТРОЕК: у каждой роли, допущенной в раздел, есть строка области.

    Замер 11.09.2026: строка `sales_registry` есть у всех одиннадцати неадминских ролей.
    Тест не про код — он показывает, что настройки не разъехались, ДО жалобы человека.
    """
    sections = sorted(_scope_sections())
    assert sections, "не нашли ни одного вызова — обход кода сломался, а не всё хорошо"
    broken = []
    for section in sections:
        allowed = {rp.role_id for rp in db.query(RolePermission).filter(
            RolePermission.section == section, RolePermission.can_view == 1).all()}
        have = {rp.role_id for rp in db.query(RolePermission).filter(
            RolePermission.section == section).all()}
        # Строка области — та же самая строка раздела: если роль видит раздел, строка
        # у неё есть по определению. Ловим обратное — роль, которой раздел открыт
        # где-то ещё, а здесь строки нет.
        for role_id in sorted(allowed - have):
            broken.append(f"роль {role_id} · раздел {section}")
    assert not broken, (
        "Ролям открыт раздел, но не настроена область видимости сделок — им откажут "
        f"с 403: {broken}. Настройки → Роли.")
