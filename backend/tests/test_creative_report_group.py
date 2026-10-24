"""Группа креатива в отчёте (владелец 24.10.2026): аккаунт объединяет креативы сделки, отчёт клиенту
и страница «Отчёт по РК» считают статистику по группе. Одна группа на креатив, строкой."""
import pytest
from fastapi import HTTPException

from app.models import AuditLog
from app.routers import launch_prep as lp
from tests.test_launch_prep_pairs import _ADMIN, env  # noqa: F401


def _tree_set(env, set_id):  # noqa: F811
    tree = lp.deal_creatives(env.deal.id, env.db, _ADMIN)
    return tree, next(x for x in tree["sets"] if x["id"] == set_id)


def test_group_is_set_trimmed_listed_and_cleared(env):  # noqa: F811
    try:
        out = lp.set_report_group(env.cset.id, lp.ReportGroupIn(group="  Аудитория А "), env.db, _ADMIN)
        assert out["report_group"] == "Аудитория А"
        tree, s = _tree_set(env, env.cset.id)
        assert s["report_group"] == "Аудитория А"
        assert tree["report_groups"] == ["Аудитория А"]
        lp.set_report_group(env.cset.id, lp.ReportGroupIn(group=""), env.db, _ADMIN)
        tree, s = _tree_set(env, env.cset.id)
        assert s["report_group"] is None and tree["report_groups"] == []
    finally:
        env.db.query(AuditLog).filter(AuditLog.action == "set_report_group",
                                      AuditLog.entity_id == env.deal.id).delete(synchronize_session=False)
        env.db.commit()


def test_group_name_too_long_or_unknown_set(env):  # noqa: F811
    with pytest.raises(HTTPException) as e:
        lp.set_report_group(env.cset.id, lp.ReportGroupIn(group="я" * 81), env.db, _ADMIN)
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        lp.set_report_group(10 ** 9, lp.ReportGroupIn(group="А"), env.db, _ADMIN)
    assert e.value.status_code == 404
