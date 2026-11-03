# -*- coding: utf-8 -*-
"""Сторона договора одной строкой: «ООО …, именуемое в дальнейшем «Заказчик», в лице … действующего на основании …».

Одна функция на прежнюю формулу преамбулы (файл DOCX) и на подстановки `{заказчик}` / `{исполнитель}` шаблона
(02.11.2026): две формулировки одной стороны в одном документе разошлись бы.
"""
from typing import Optional


def party_line(p: Optional[dict], role: str) -> str:
    if not p or not p.get("name"):
        return f"___________, именуемое в дальнейшем «{role}»"
    pos = p.get("position_gen") or p.get("position") or "___________"
    fio = p.get("director_gen") or p.get("director") or "___________"
    basis = p.get("basis_gen") or p.get("basis") or "___________"
    acting = p.get("acting") or "действующего"
    return (f"{p.get('legal_name') or p['name']}, именуемое в дальнейшем «{role}», в лице {pos} {fio}, "
            f"{acting} на основании {basis}")
