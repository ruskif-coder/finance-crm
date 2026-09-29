# -*- coding: utf-8 -*-
"""Матрица согласований площадка × РК: светофор и сведение услуг (владелец 29.09.2026)."""
from datetime import date, datetime

import pytest

from app.launch_prep import matrix as M

TODAY = date(2026, 9, 29)          # вторник


@pytest.mark.parametrize("args,tone", [
    (("отказ площадки", 2, 2, 0, None), "refused"),
    (("согласование", 2, 2, 2, None), "withdrawn"),
    (("ерид получен", 1, 1, 0, None), "agreed"),
    (("в размещении", 1, 1, 0, None), "agreed"),
    (("согласование", 1, 0, 0, None), "unsent"),
    (("согласование", 1, 1, 0, datetime(2026, 9, 28, 15)), "waiting"),   # 1 раб. день
    (("согласование", 1, 1, 0, datetime(2026, 9, 25, 15)), "waiting"),   # пт → вт = 2
    (("согласование", 1, 1, 0, datetime(2026, 9, 24, 15)), "late"),      # чт → вт = 3
])
def test_look(args, tone):
    assert M.look(*args, TODAY)["tone"] == tone


def test_weekend_is_not_counted():
    assert M.workdays_between(date(2026, 9, 25), date(2026, 9, 28)) == 1   # пт → пн


def test_merge_takes_worst_and_sums():
    a = {"tone": "agreed", "days": None, "pairs": 1, "sent": 1, "agreed": 1, "withdrawn": 0,
         "services": ["еФарм"], "states": ["согласован"]}
    b = {"tone": "late", "days": 3, "pairs": 2, "sent": 2, "agreed": 0, "withdrawn": 0,
         "services": ["Polza"], "states": ["согласование"]}
    m = M._merge(a, b)
    assert m["tone"] == "late" and m["pairs"] == 3 and m["services"] == ["еФарм", "Polza"]


def test_month_bounds_december():
    assert M.month_bounds("2026-12") == (date(2026, 12, 1), date(2027, 1, 1))


def test_endpoint_needs_its_own_permission_and_valid_month():
    from fastapi import HTTPException
    from app.routers.publisher_matrix import get_matrix
    with pytest.raises(HTTPException) as e:
        get_matrix(month="2026-13", db=None, current_user=None)
    assert e.value.status_code == 400


def test_load_on_stand_data_is_consistent():
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        for m in M.months(db):
            out = M.load(db, m)
            deal_ids = {d["id"] for d in out["deals"]}
            pub_ids = {p["id"] for p in out["publishers"]}
            for c in out["cells"]:
                assert c["deal_id"] in deal_ids and c["publisher_id"] in pub_ids
                assert c["tone"] in M.RANK
                assert c["plan_cost"] is None or c["plan_show"] > 0
    finally:
        db.close()


def test_merge_shows_longest_wait_not_worst_rows_wait():
    a = {"tone": "late", "days": 3, "pairs": 1, "sent": 1, "agreed": 0, "withdrawn": 0,
         "services": ["еФарм WEB"], "states": ["согласование"]}
    b = {"tone": "late", "days": 7, "pairs": 1, "sent": 1, "agreed": 0, "withdrawn": 0,
         "services": ["еФарм APP"], "states": ["согласование"]}
    assert M._merge(a, b)["days"] == 7 and M._merge(b, a)["days"] == 7


def test_web_and_app_are_named_apart():
    import inspect
    src = inspect.getsource(M.load)
    assert "surface_kind" in src, "web и app одной услуги сливались в одно имя в подсказке"


def test_rework_is_not_waiting():
    """Площадка вернула на доработку (или отозвала согласование) — ждать от неё нечего."""
    assert M.look("согласование", 1, 1, 0, None, TODAY, rework=1)["tone"] == "rework"
    assert M.look("согласование", 2, 2, 0, datetime(2026, 9, 28, 9), TODAY, rework=1)["tone"] == "waiting"
