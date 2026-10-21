# -*- coding: utf-8 -*-
"""Право «Эффективность мастер-сделок» (`master_deals_finance`, просмотр; владелец 19.10.2026): без него прибыль, маржа и блок
эффективности не отдаются сервером вовсе — не только прячутся на экране."""
import app.model_registry  # noqa: F401
from app.permissions import SECTIONS
from app.master_deal import registry as RG
from app.master_deal import scope as SC
from app.master_deal import view as VW
from app.routers import master_deals as R  # noqa: F401


def test_section():
    s = next(x for x in SECTIONS if x["key"] == "master_deals_finance")
    assert s["group"] == "Финансы" and s["actions"] == ["view"]


def test_registry_and_card_hide_profit_without_right(monkeypatch):
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        monkeypatch.setattr(SC, "own_reps", lambda *a: None)
        monkeypatch.setattr(SC, "can_finance", lambda db, user: False)
        rows = RG.rows(db, object())
        if not rows:
            return
        assert all("profit" not in r and "efficiency" not in r for r in rows)
        monkeypatch.setattr(SC, "can_finance", lambda db, user: True)
        r = RG.rows(db, object())[0]
        assert {"profit", "margin_pct"} <= set(r["efficiency"])
    finally:
        db.rollback()
        db.close()


def test_card_view_has_no_efficiency_without_right():
    import inspect
    src = inspect.getsource(VW.card)
    assert "SC.can_finance(db, user)" in src, "карточка отдаёт эффективность без проверки права"
