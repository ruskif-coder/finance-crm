# -*- coding: utf-8 -*-
"""Сверка импорта: какая существующая операция соответствует строке файла с № ДС и Счётом.

ЧТО БЫЛО ДО 23.09.2026. Пара «№ ДС + Счёт» считалась уникальным ключом: существующие
операции клались в словарь по паре номеров, и оставалась одна — последняя по id. А пара
не уникальна по построению:
  · частичные оплаты одного счёта — несколько операций с одними номерами (практика
    владельца, с 23.09.2026 — цепочка через `parent_operation_id`);
  · у РАЗНЫХ контрагентов номера совпадают («доп.1 / 67» у двух фирм разных лет).
Итог на стенде: выгрузка, загруженная обратно без единой правки, давала пять «конфликтов»,
все против одной операции и с одним ключом подтверждения — одна галка переписала бы её
трижды (аудит 23.09.2026, 2.H1).

КАК ТЕПЕРЬ. Кандидаты строки — операции с теми же номерами И тем же контрагентом (по ИНН,
если он есть с обеих сторон, иначе по названию). Каждая операция отдаётся не более чем
одной строке. Порядок подсказок, от сильной к слабой:

  1. ID из выгрузки — но только среди кандидатов. Сам по себе ID не сопоставляет ничего:
     файл мог прийти с другого стенда, где этот номер принадлежит чужой операции (та же
     осторожность, что у `_take_from_pool` для строк без номеров);
  2. совпали статус, сумма и дата;
  3. совпали статус и сумма;
  4. остался единственный свободный кандидат и единственная строка, которой он подходит, —
     это правка той самой операции.

Не решилось ни одно — строка «неоднозначная»: показывается человеку со списком кандидатов
и не применяется. Своих кандидатов нет, но есть свободная операция с теми же номерами у
фирмы, которая НЕ ДОКАЗАННО другая (ИНН не различаются), — тоже «неоднозначная»: название
в файле свободный текст. Новая — только когда таких нет.
"""
from __future__ import annotations

from collections import defaultdict


def _norm(s) -> str:
    return " ".join(str(s or "").split()).casefold()


def same_counterparty(op, row) -> bool:
    """Та же ли фирма у существующей операции и у строки файла."""
    cp = getattr(op, "counterparty", None)
    row_inn, row_name = (row.get("inn") or "").strip(), _norm(row.get("counterparty"))
    if not row_inn and not row_name:
        return True                         # файл контрагента не называет — не спорим
    if cp is None:
        return False
    cp_inn = (cp.inn or "").strip()
    if row_inn and cp_inn:
        return row_inn == cp_inn
    return _norm(cp.name) == row_name


def proven_other(op, row) -> bool:
    """Доказано ли, что у операции и строки РАЗНЫЕ фирмы. Доказательство — только два
    непустых различных ИНН. Название — свободный текст («ООО Ромашка» / «Ромашка ООО»):
    его несовпадение не доказывает ничего, и строка тогда уходит человеку, а не в новые
    (ревью 23.09.2026: иначе применение заводило вторую операцию с теми же деньгами)."""
    cp = getattr(op, "counterparty", None)
    row_inn = (row.get("inn") or "").strip()
    cp_inn = ((cp.inn if cp is not None else "") or "").strip()
    return bool(row_inn and cp_inn and row_inn != cp_inn)


def _op_amounts(op) -> tuple:
    return (round(float(op.income or 0), 2), round(float(op.expense or 0), 2))


def _row_amounts(row) -> tuple:
    return (round(float(row.get("income") or 0), 2), round(float(row.get("expense") or 0), 2))


def match_keyed(rows, existing) -> dict:
    """Сопоставить строки файла с номерами существующим операциям.

    rows     — [(индекс строки, строка)], у каждой заполнены `ds_num` и `invoice`;
    existing — операции с теми же номерами (у каждой загружен `counterparty`).
    Возвращает {индекс: ("match", операция) | ("new", None) | ("ambiguous", [операции])}.
    """
    by_key = defaultdict(list)
    for op in existing:
        by_key[(op.ds_num, op.invoice)].append(op)

    groups = defaultdict(list)
    for i, row in rows:
        groups[(row["ds_num"], row["invoice"])].append((i, row))

    out = {}
    for key, members in groups.items():
        pool = by_key.get(key, [])
        cands = {i: [op for op in pool if same_counterparty(op, row)] for i, row in members}
        used, todo = set(), dict(members)

        def take(i, op):
            out[i] = ("match", op)
            used.add(op.id)
            todo.pop(i, None)

        # 1. ID из выгрузки — только если он среди кандидатов этой строки.
        for i, row in list(todo.items()):
            hit = next((op for op in cands[i] if op.id == row.get("op_id") and op.id not in used), None)
            if hit:
                take(i, hit)

        # 2–3. По содержанию: сначала статус + сумма + дата, потом статус + сумма.
        for strict in (True, False):
            for i, row in list(todo.items()):
                hit = next((op for op in cands[i] if op.id not in used
                            and op.status == row.get("status")
                            and _op_amounts(op) == _row_amounts(row)
                            and (not strict or op.date == row.get("date"))), None)
                if hit:
                    take(i, hit)

        # 4. Единственный свободный кандидат, на которого претендует единственная строка.
        for i in list(todo):
            free = [op for op in cands[i] if op.id not in used]
            if len(free) != 1:
                continue
            rivals = [j for j in todo if j != i and any(op.id == free[0].id for op in cands[j])]
            if not rivals:
                take(i, free[0])

        for i, row in todo.items():
            free = [op for op in cands[i] if op.id not in used]
            if not free:
                # Своих кандидатов нет. Свободная операция с теми же номерами у фирмы, которая
                # не доказанно другая, — вероятно, та же фирма под другим написанием.
                free = [op for op in pool if op.id not in used and not proven_other(op, row)]
            out[i] = ("ambiguous", free) if free else ("new", None)
    return out
