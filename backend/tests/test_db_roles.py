# -*- coding: utf-8 -*-
"""Прибор: каждая роль, которой миграции выдают права, заводится в `2026-10-01_db_roles.sql`.

Роли кластера в `pg_dump` не попадают. Восстановление ночного бэкапа на чистом Postgres
(01.10.2026) упало на `role "cabinet" does not exist`; `deploy.sh restore` теперь заводит
роли из одного файла ДО разворота дампа. Появится в миграциях новая роль — этот прибор
не даст забыть дописать её туда, иначе следующее восстановление упадёт в аварию.

Каталог `migrations/` тест читает из контейнера — перед прогоном донести целиком
(`docker cp backend/migrations/. finance_backend:/app/migrations`).
"""
import pathlib
import re

MIG = pathlib.Path(__file__).resolve().parent.parent / "migrations"
ROLES_FILE = MIG / "2026-10-01_db_roles.sql"

# Роль владельца базы создаёт сам образ Postgres (POSTGRES_USER), PUBLIC — не роль.
BUILTIN = {"finance_user", "dsp", "public", "postgres"}
GRANTEE = re.compile(r"\bTO\s+([a-z_][a-z0-9_]*)\s*;", re.I)
CREATED = re.compile(r"CREATE\s+ROLE\s+([a-z_][a-z0-9_]*)", re.I)


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _grantees() -> dict:
    out = {}
    for f in sorted(MIG.rglob("*.sql")):
        for m in GRANTEE.finditer(_strip_comments(f.read_text(encoding="utf-8"))):
            # «ALTER … OWNER TO x;» и «GRANT … TO x;» — обе формы требуют, чтобы роль была.
            out.setdefault(m.group(1).lower(), set()).add(f.name)
    return out


def test_roles_file_exists_and_is_rerun_safe():
    sql = ROLES_FILE.read_text(encoding="utf-8")
    assert CREATED.search(sql), "в файле ролей нет ни одного CREATE ROLE"
    assert "IF NOT EXISTS" in sql, "роль создаётся без проверки — повторный накат упадёт"
    assert "PASSWORD" not in _strip_comments(sql).upper(), "пароль роли — в .env, не в гите"


def test_every_granted_role_is_created_in_the_roles_file():
    created = {r.lower() for r in CREATED.findall(_strip_comments(ROLES_FILE.read_text(encoding="utf-8")))}
    missing = {r: sorted(fs)[:3] for r, fs in _grantees().items()
               if r not in BUILTIN and r not in created}
    assert not missing, (
        f"миграции выдают права ролям, которых нет в {ROLES_FILE.name}: {missing} — "
        "дописать туда «создать, если нет», иначе восстановление дампа на чистом "
        "сервере упадёт на `role does not exist`")


def test_cabinet_is_known():
    """Самопроверка прибора: роль кабинета он обязан видеть среди получателей прав."""
    assert "cabinet" in _grantees()
