# -*- coding: utf-8 -*-
"""Карточка договора (владелец 28.10.2026): блок отдаётся только по праву своего раздела; сделки находятся через ДС договора;
деньги — по контрагенту договора. Только чтение, на стенде ничего не пишется."""
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.contract_card import service as CC
from app.database import SessionLocal
from app.models import Contract, User


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _admin(db):
    return db.query(User).filter(User.email == "d.makarov@simb-ad.com").first()


def _contract_with_annex_deal(db):
    row = db.execute(text("""SELECT s.contract_id, d.code FROM sales_annexes s
                               JOIN sales_deal_annex_allocation x ON x.annex_id = s.id JOIN sales_deals d ON d.id = x.deal_id
                              ORDER BY s.id LIMIT 1""")).first()
    assert row, "на стенде нет ДС со сделкой"
    return db.get(Contract, row[0]), row[1]


def test_blocks_follow_the_rights_of_their_sections(db, monkeypatch):
    c, _ = _contract_with_annex_deal(db)
    only = {"annexes": {"view": True}, "sk_terms": {"view": True}, "operations": {"view": False}}
    monkeypatch.setattr(CC, "get_permissions_for_user", lambda db_, u: only)
    out = CC.card(db, c, _admin(db))
    assert set(out) == {"contract", "parties", "readiness", "sk_summary", "annexes", "sk"}


def test_admin_sees_every_block(db):
    c, _ = _contract_with_annex_deal(db)
    out = CC.card(db, c, _admin(db))
    assert set(out) == {"contract", "parties", "readiness", "sk_summary", *CC.BLOCKS}


def test_deal_closed_by_an_annex_of_the_contract_is_in_deals(db):
    c, code = _contract_with_annex_deal(db)
    out = CC.card(db, c, _admin(db))
    hit = next((d for d in out["deals"] if d["code"] == code), None)
    assert hit is not None and "ДС" in hit["via"]
    assert out["annexes"]["items"] and all(a["id"] for a in out["annexes"]["items"])


def test_money_without_counterparty_says_so():
    assert CC.money(None, SimpleNamespace(counterparty_id=None)) == {"counterparty": False}


def test_readiness_has_every_check_and_sk_text_is_hidden_without_the_right(db, monkeypatch):
    c, _ = _contract_with_annex_deal(db)
    keys = {"signer_заказчик", "signer_исполнитель", "requisites", "template", "sk", "channel", "term"}
    assert {x["key"] for x in CC.card(db, c, _admin(db))["readiness"]} == keys
    monkeypatch.setattr(CC, "get_permissions_for_user", lambda db_, u: {"annexes": {"view": True}})
    sk = next(x for x in CC.card(db, c, _admin(db))["readiness"] if x["key"] == "sk")
    assert sk["text"] in ("задано", "не задано")


def test_template_counter_matches_annexes_built_by_it(db):
    c, _ = _contract_with_annex_deal(db)
    out = CC.card(db, c, _admin(db))
    by_tpl = {}
    for a in out["annexes"]["items"]:
        if a.get("template"):
            by_tpl[a["template"]["title"]] = by_tpl.get(a["template"]["title"], 0) + 1
    for t in out["templates"]:
        if t["title"] in by_tpl:
            assert t["annexes"] == by_tpl[t["title"]]
