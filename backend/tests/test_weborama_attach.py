# -*- coding: utf-8 -*-
"""Привязка РК к уже заведённым в Weborama проекту и кампании (владелец 28.09.2026)."""
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.main  # noqa: F401
from app.database import SessionLocal
from app.weborama import provision as P

ACC = "TEST-ATTACH"
CAMP = SimpleNamespace(id=990001, deal_id=990002)
OTHER = SimpleNamespace(id=990003, deal_id=990004)


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setattr(P, "account_id", lambda db_: ACC)
    s = SessionLocal()
    s.execute(text("DELETE FROM weborama_refs WHERE account_id = :a"), {"a": ACC})
    s.commit()
    yield s
    s.rollback()
    s.execute(text("DELETE FROM weborama_refs WHERE account_id = :a"), {"a": ACC})
    s.commit()
    s.close()


def _refs(db):
    return dict(db.execute(text("SELECT kind || ':' || local_id, wcm_id FROM weborama_refs "
                                "WHERE account_id = :a"), {"a": ACC}).all())


def test_attach_both_then_same_again_is_noop(db):
    P.attach_existing(db, CAMP, "33", "34")
    assert _refs(db) == {"project:990002": "33", "campaign:990001": "34"}
    with pytest.raises(P.ProvisionError, match="Нечего"):
        P.attach_existing(db, CAMP, "33", "34")


def test_no_rebinding_and_no_sharing(db):
    P.attach_existing(db, CAMP, "33", "34")
    with pytest.raises(P.ProvisionError, match="уже связан с номером"):
        P.attach_existing(db, CAMP, None, "35")
    with pytest.raises(P.ProvisionError, match="другой"):
        P.attach_existing(db, OTHER, "33", None)


def test_campaign_needs_project_and_digits(db):
    with pytest.raises(P.ProvisionError, match="проект"):
        P.attach_existing(db, CAMP, None, "34")
    with pytest.raises(P.ProvisionError, match="цифры"):
        P.attach_existing(db, CAMP, "3a", "34")
    assert _refs(db) == {}
