# -*- coding: utf-8 -*-
"""Прибор: строка с теми же номерами, но «другим» контрагентом — не новая операция, пока
другой контрагент не ДОКАЗАН (ревью 23.09.2026, HIGH-1).

ЧТО БЫЛО. После правки 2.H1 кандидатами строки считались только операции того же
контрагента, а всё остальное — «новая». Контрагент в файле — свободный текст: «ООО Ромашка»
в выгрузке и «Ромашка ООО» после ручной правки — это одна фирма, а сверка видела две, и
применение заводило ВТОРУЮ операцию с теми же деньгами.

ЧТО ДЕРЖИМ. «Новая» — только когда ИНН есть с обеих сторон и они разные: тогда это правда
другая фирма (номера «доп.1 / 67» у двух фирм разных лет). Если сравнить можно только по
названию и оно не совпало — строка «неоднозначная», решает человек.
"""
from types import SimpleNamespace as NS

from app import import_match


def _op(id_, name, inn=""):
    return NS(id=id_, ds_num="доп.1", invoice="67", status="ОПЛАЧЕНО", income=100.0,
              expense=0.0, date=None, counterparty=NS(name=name, inn=inn))


def _row(name, inn="", income=100.0):
    return {"ds_num": "доп.1", "invoice": "67", "counterparty": name, "inn": inn,
            "status": "ОПЛАЧЕНО", "income": income, "expense": 0.0, "date": None}


def test_differently_spelled_name_without_inn_is_ambiguous_not_new():
    out = import_match.match_keyed([(0, _row("Ромашка ООО"))], [_op(1, "ООО Ромашка")])
    verdict, found = out[0]
    assert verdict == "ambiguous"
    assert [op.id for op in found] == [1]


def test_row_inn_against_operation_without_inn_is_ambiguous():
    out = import_match.match_keyed([(0, _row("Ромашка", inn="7700000001"))],
                                   [_op(1, "ООО Ромашка")])
    assert out[0][0] == "ambiguous"


def test_different_inn_is_a_new_operation():
    out = import_match.match_keyed([(0, _row("Лютик", inn="7700000002"))],
                                   [_op(1, "Ромашка", inn="7700000001")])
    assert out[0] == ("new", None)


def test_same_inn_differently_spelled_name_still_matches():
    out = import_match.match_keyed([(0, _row("Ромашка ООО", inn="7700000001"))],
                                   [_op(1, "ООО Ромашка", inn="7700000001")])
    assert out[0][0] == "match" and out[0][1].id == 1


def test_operation_taken_by_its_own_row_is_not_offered_to_a_stranger():
    ops = [_op(1, "ООО Ромашка")]
    rows = [(0, _row("ООО Ромашка")), (1, _row("Ромашка ООО", income=500.0))]
    out = import_match.match_keyed(rows, ops)
    assert out[0][0] == "match"
    assert out[1] == ("new", None)      # единственная операция уже занята своей строкой
