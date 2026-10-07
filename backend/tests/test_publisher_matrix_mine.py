# -*- coding: utf-8 -*-
"""Матрица согласований: переключатель «Мои сделки / Все сделки» (аккаунтам и трафикам).

«Мои» = сделки, где человек стоит аккаунтом (рабочая группа роли «account») или трафиком («traffic»).
Профиля ответственного нет — пусто, а не чужие сделки. Тест читает данные стенда и ничего не пишет."""
import pytest
from sqlalchemy import text

from app.launch_prep import matrix


def _pick(db, field):
    return db.execute(text(f"""
        SELECT to_char(d.period_from, 'YYYY-MM'), d.{field} FROM sales_deals d
         WHERE d.{field} IS NOT NULL AND d.period_from IS NOT NULL
           AND EXISTS (SELECT 1 FROM launch_prep_target t WHERE t.deal_id = d.id)
         ORDER BY d.id DESC LIMIT 1""")).first()


@pytest.mark.parametrize("group,field", [("account", "account_manager_id"), ("traffic", "traffic_manager_id")])
def test_mine_keeps_only_deals_of_that_person(db, group, field):
    row = _pick(db, field)
    if not row:
        pytest.skip("на стенде нет сделки с таким ответственным")
    month, rep = row
    full = matrix.load(db, month)
    mine = matrix.load(db, month, mine=(group, rep))
    ids = [d["id"] for d in mine["deals"]]
    assert ids and set(ids) <= {d["id"] for d in full["deals"]}
    owners = {r[0] for r in db.execute(text(f"SELECT {field} FROM sales_deals WHERE id = ANY(:i)"), {"i": ids})}
    assert owners == {rep}
    assert {c["deal_id"] for c in mine["cells"]} <= set(ids)


def test_person_without_profile_sees_nothing(db):
    month = _pick(db, "account_manager_id")
    if not month:
        pytest.skip("нет данных")
    out = matrix.load(db, month[0], mine=("account", -1))
    assert out["deals"] == [] and out["cells"] == []


def test_without_group_mine_means_account_or_traffic(db):
    month, rep = _pick(db, "account_manager_id") or (None, None)
    if not month:
        pytest.skip("нет данных")
    out = matrix.load(db, month, mine=("", rep))
    ids = [d["id"] for d in out["deals"]]
    assert ids
    rows = db.execute(text("SELECT account_manager_id, traffic_manager_id FROM sales_deals WHERE id = ANY(:i)"), {"i": ids}).all()
    assert all(rep in r for r in rows)
