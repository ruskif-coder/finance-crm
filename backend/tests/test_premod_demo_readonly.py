# -*- coding: utf-8 -*-
"""Премодерация — ДЕМО: только приём входящих заявок SSP, никаких отправок статусов (владелец 07.11.2026).

Прибор по исходникам: в модуле премодерации и его ручках нет ни одного пишущего метода модерации SSP.
Падает, если кто-то добавит approve / decline / update — это решение владельца, а не правка по ходу.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent / "app"
SOURCES = sorted((ROOT / "premod").glob("*.py")) + [ROOT / "routers" / "premod.py"]
WRITES = re.compile(r"creativeModeration\.(approve|decline|update)\b|[\"'](approve|decline|update)[\"']")


def test_premoderation_never_writes_to_ssp():
    found = [f"{p.relative_to(ROOT)}: {m.group(0)}"
             for p in SOURCES for m in WRITES.finditer(p.read_text(encoding="utf-8"))]
    assert len(SOURCES) >= 7, "прибор не нашёл файлов модуля — проверяет пустоту"
    assert not found, "Премодерация в демо-режиме: запись в SSP запрещена владельцем. Найдено: " + "; ".join(found)
