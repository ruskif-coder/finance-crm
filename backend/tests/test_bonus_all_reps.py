"""«Мой квартал» — вариант «Все сотрудники» (владелец 22.10.2026): админу, мастер-сейлзу и наблюдателю (роль `viewer`).
Остальным флаг ничего не даёт — они видят только себя. Только чтение базы стенда."""
import pytest

from app.database import SessionLocal
from app.routers.sales_dashboard import dashboard_bonus
from app.sales.models import SalesRep


class _Role:
    def __init__(self, key):
        self.key = key


class _User:
    def __init__(self, key, uid=-1):
        self.id = uid           # без профиля сейлза: своих сделок нет
        self.role = _Role(key)


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.mark.parametrize("key", ["admin", "viewer"])
def test_all_reps_for_those_who_see_others(db, key):
    j = dashboard_bonus(quarter="all", rep_id=None, all_reps=True, db=db, current_user=_User(key))
    assert j["can_view_others"] is True
    assert j["rep"] == "Все сотрудники"
    assert sorted(j["rep_ids"]) == sorted(i for (i,) in db.query(SalesRep.id).all())


def test_all_reps_ignored_for_plain_sales(db):
    j = dashboard_bonus(quarter="all", rep_id=None, all_reps=True, db=db, current_user=_User("role_7"))
    assert j["can_view_others"] is False
    assert j["rep_ids"] == []
