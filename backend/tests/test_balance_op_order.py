# -*- coding: utf-8 -*-
"""Баланс: операции внутри строки долга сортируются, даже когда у части из них нет даты (07.10.2026).

БЫЛО. `sorted(group_ops, key=lambda o: o.date or o.id)` сравнивал дату с числом: у «ПЛАН ОПЛАТ» на проде
81 операция из 88 без даты, и в строке, где есть и датированные, и нет, `/api/reports/balance/full` отвечал
500 (TypeError: '<' not supported between 'datetime.date' and 'int'). ТЕПЕРЬ — датированные по дате, потом
без даты по номеру.
"""
from datetime import date
from types import SimpleNamespace as Op

from app.routers.reports import op_order_key


def test_mixed_dated_and_undated_sort_without_error():
    ops = [Op(id=5, date=None), Op(id=2, date=date(2026, 9, 1)), Op(id=1, date=None), Op(id=9, date=date(2026, 8, 1))]
    assert [o.id for o in sorted(ops, key=op_order_key)] == [9, 2, 1, 5]


def test_all_undated_go_by_id():
    ops = [Op(id=3, date=None), Op(id=1, date=None)]
    assert [o.id for o in sorted(ops, key=op_order_key)] == [1, 3]


def test_same_date_goes_by_id():
    ops = [Op(id=7, date=date(2026, 9, 1)), Op(id=4, date=date(2026, 9, 1))]
    assert [o.id for o in sorted(ops, key=op_order_key)] == [4, 7]
