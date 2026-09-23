# -*- coding: utf-8 -*-
"""Цепочка частичных оплат: материнская операция и её части.

Решение владельца 23.09.2026. Плановую операцию закрывают по частям: полученная сумма
становится отдельной оплаченной операцией (частью), у исходной (материнской) остаётся
план на остаток — до полного погашения. Связь — `operations.parent_operation_id`,
всегда на КОРЕНЬ цепочки (миграция `2026-09-23_operation_parent.sql`).

Здесь — правила, не зависящие от HTTP: какая сторона у операции, что считается планом,
и как разметить цепочки, которые до 23.09.2026 заводили руками без связи.
"""
from __future__ import annotations

from typing import Optional

PLAN_STATUSES = ("ПЛАН ПОСТУПЛЕНИЙ", "ПЛАН ОПЛАТ")
PAID = "ОПЛАЧЕНО"


def side(op) -> str | None:
    """Какая сторона у операции несёт деньги: 'income', 'expense' или None."""
    if (op.income or 0) > 0:
        return "income"
    if (op.expense or 0) > 0:
        return "expense"
    return None


def amount(op) -> float:
    s = side(op)
    return round(float(getattr(op, s) or 0), 2) if s else 0.0


def root_id(op) -> int:
    return op.parent_operation_id or op.id


def plan_backfill(ops) -> dict:
    """Разметка цепочек, заведённых руками до появления связи. Чистая функция.

    Группа — операции с одинаковыми № ДС, Счётом И КОНТРАГЕНТОМ. Без контрагента в ключе
    склеились бы чужие операции: у разных контрагентов номера «доп.1 / 67» совпадают
    (замер на стенде 23.09.2026 — три такие пары из десяти групп).

    Корень группы:
      · ровно одна плановая — она: это остаток, который ещё ждут, то есть исходная;
      · плановых нет (цепочка погашена) — первая по номеру, то есть заведённая раньше всех;
      · плановых больше одной — решить нечем, группа уходит человеку.

    Группа, где кто-то уже связан, не трогается: разметку делали руками или прошлым
    прогоном, и переписывать чужое решение нельзя. Смешанные стороны (приход и расход
    с одним номером) — тоже человеку.

    Возвращает {"links": {id части: id корня}, "unclear": [(ключ, [id…], причина)]}.
    """
    groups: dict = {}
    for op in ops:
        ds, inv = (op.ds_num or "").strip(), (op.invoice or "").strip()
        if not ds or not inv or not op.counterparty_id:
            continue
        groups.setdefault((op.counterparty_id, ds, inv), []).append(op)

    links, unclear = {}, []
    for key, members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        if len(members) < 2:
            continue
        ids = sorted(m.id for m in members)
        if any(m.parent_operation_id for m in members):
            continue
        if len({side(m) for m in members}) > 1:
            unclear.append((key, ids, "в группе и приход, и расход"))
            continue
        plans = [m for m in members if m.status in PLAN_STATUSES]
        if len(plans) > 1:
            unclear.append((key, ids, f"плановых операций {len(plans)} — какая остаток, неясно"))
            continue
        root = plans[0].id if plans else ids[0]
        for m in members:
            if m.id != root:
                links[m.id] = root
    return {"links": links, "unclear": unclear}


def chain_root_for(db, ds_num, invoice, counterparty_id) -> Optional[int]:
    """Корень уже размеченной цепочки с этими № ДС, Счётом и контрагентом — или None.

    Для новой строки импорта: транш, которого в базе ещё нет, встаёт частью своей цепочки,
    а не одиночкой рядом (ревью 23.09.2026). Цепочка должна быть РАЗМЕЧЕНА (хоть одна
    ссылка) и однозначна; неразмеченную группу решает скрипт разметки, не импорт.
    """
    if not (ds_num and invoice and counterparty_id):
        return None
    from app.models import Operation
    roots = {pid for (pid,) in db.query(Operation.parent_operation_id).filter(
        Operation.ds_num == ds_num, Operation.invoice == invoice,
        Operation.counterparty_id == counterparty_id,
        Operation.parent_operation_id.isnot(None)).distinct()}
    return next(iter(roots)) if len(roots) == 1 else None
