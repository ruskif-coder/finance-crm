# -*- coding: utf-8 -*-
"""Прибор: демо-скрипты отказываются работать вне стенда (аудит 23.09.2026, 8.H4).

Каждый скрипт в `scripts/`, который заводит демо-данные или переписывает РК, обязан
звать общую проверку `scripts._stand_guard.require_stand`. Проверяется И наличие вызова,
И поведение проверки: пустой `DOMAIN` — отказ, а не «видимо, стенд».
"""
import ast
import pathlib

import pytest

from scripts._stand_guard import require_stand

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"


# Исключения — с причиной. У заливки на ДЕМО-КОНТУР ОРД своя защита другой природы: она
# работает с песочницей ВНЕШНЕЙ системы и отказывается при боевом контуре ОРД, где бы ни
# запускалась. Стенд тут ни при чём — данные системы она не подделывает.
OWN_GUARD = {"2026-08-27_ord_load_demo.py": "if env != 'demo':"}

GUARDS = {"require_stand", "_stand_only", "is_stand"}


def _called(src: str) -> set:
    """Имена проверок, которые в файле ВЫЗЫВАЮТСЯ. Упоминание в комментарии или в строке
    не в счёт — до ревью 23.09.2026 гейт засчитывал любую подстроку."""
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
            if name in GUARDS:
                names.add(name)
    return names


def test_every_demo_script_calls_the_guard():
    demos = [p for p in SCRIPTS.glob("*demo*.py") if p.name not in OWN_GUARD]
    assert demos, "не нашёл демо-скриптов — прибор смотрит не туда"
    bare = [p.name for p in demos if not _called(p.read_text(encoding="utf-8"))]
    assert not bare, f"демо-скрипт без ВЫЗОВА проверки стенда: {bare}"


def test_the_gate_does_not_count_a_mere_mention():
    assert not _called("# require_stand здесь не зовётся\nx = 'require_stand'\n")
    assert _called("from scripts._stand_guard import require_stand\nrequire_stand('x')\n")


@pytest.mark.parametrize("domain,stand", [("", "1"), ("timon.simbad.pro", "1"),
                                          ("LOCALHOST.example", "1"),
                                          # compose подставляет localhost при пустом DOMAIN:
                                          # без флага запуска этого мало
                                          ("localhost", ""), ("localhost", "0")])
def test_guard_refuses_anything_but_an_explicit_stand_run(monkeypatch, domain, stand):
    monkeypatch.setenv("DOMAIN", domain)
    monkeypatch.setenv("STAND", stand)
    with pytest.raises(SystemExit):
        require_stand("прибор")


def test_guard_lets_the_stand_through(monkeypatch):
    monkeypatch.setenv("DOMAIN", "localhost")
    monkeypatch.setenv("STAND", "1")
    require_stand("прибор")


def test_exempt_scripts_keep_their_own_guard():
    for name, marker in OWN_GUARD.items():
        src = (SCRIPTS / name).read_text(encoding="utf-8")
        assert marker in src, f"{name}: исключён из проверки стенда, но своей защиты ({marker}) не видно"
