# -*- coding: utf-8 -*-
"""Лог РК (владелец 05.11.2026, хендофф `docs/design_handoff_rk_log.zip`).

Поломки, которые ловит: в лог пишет не трафик и не аккаунт этой РК; запись правится (журнал — только добавление);
пустая или длиннее 2000 записывается; новые не сверху; время клиента вместо серверного; «проблема» не доходит до
аккаунта, запись аккаунта — до трафика; карточка РК не отдаёт счётчик и право писать. Всё в откатываемой транзакции.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.ad import notes as N
from app.ad.models import AdCampaign
from app.database import SessionLocal
from app.models import User
from app.sales.models import SalesDeal, SalesRep


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _rk(db):
    """РК, у сделки которой есть аккаунт с учёткой; трафиком ставим другую учётку."""
    row = db.execute(text("""
        SELECT c.id FROM ad_campaign c JOIN sales_deals d ON d.id = c.deal_id
          JOIN sales_reps r ON r.id = d.account_manager_id
         WHERE r.user_id IS NOT NULL ORDER BY c.id LIMIT 1""")).first()
    if row is None:
        pytest.skip("на стенде нет РК с аккаунтом")
    c = db.get(AdCampaign, row[0])
    deal = db.get(SalesDeal, c.deal_id)
    acc = db.get(User, db.get(SalesRep, deal.account_manager_id).user_id)
    other = db.query(User).filter(User.id != acc.id, User.is_active == 1).order_by(User.id).first()
    traf = SalesRep(name="Тест-трафик лога", user_id=other.id)
    db.add(traf)
    db.flush()
    deal.traffic_manager_id = traf.id
    db.flush()
    return c, deal, acc, other


def _stranger(db, *ids):
    u = db.query(User).filter(User.id.notin_(ids), User.is_active == 1).order_by(User.id.desc()).first()
    return SimpleNamespace(id=u.id, name=u.name, role=SimpleNamespace(key="role_8"), role_id=u.role_id)


def test_owners_write_others_do_not(db, monkeypatch):
    monkeypatch.setattr(N, "emit", lambda *a, **k: None)
    c, deal, acc, traf = _rk(db)
    assert N.can_write(db, deal, acc) and N.can_write(db, deal, traf)
    stranger = _stranger(db, acc.id, traf.id)
    assert not N.can_write(db, deal, stranger)
    with pytest.raises(N.NoteError) as e:
        N.add(db, c, deal, stranger, "note", "чужая запись")
    assert e.value.status == 403
    admin = SimpleNamespace(id=None, name="админ", role=SimpleNamespace(key="admin"), role_id=None)
    assert N.can_write(db, deal, admin)


def test_each_note_is_a_row_newest_first_with_server_time(db, monkeypatch):
    monkeypatch.setattr(N, "emit", lambda *a, **k: None)
    c, deal, acc, _ = _rk(db)
    N.add(db, c, deal, acc, "note", "первая")
    N.add(db, c, deal, acc, "agreement", "  вторая\nс переносом  ")
    rows = N.list_for(db, c.id)
    assert [r["text"] for r in rows[:2]] == ["вторая\nс переносом", "первая"]
    assert rows[0]["kind"] == "agreement" and rows[0]["author"] == acc.name
    assert len(rows[0]["at"]) == 16 and rows[0]["at"][2] == "." and rows[0]["at"][10] == " ", "дд.мм.гггг чч:мм — МСК"


def test_blank_long_or_unknown_kind_is_refused(db, monkeypatch):
    monkeypatch.setattr(N, "emit", lambda *a, **k: None)
    c, deal, acc, _ = _rk(db)
    for kind, body in (("note", "   "), ("note", "x" * 2001), ("секрет", "текст")):
        with pytest.raises(N.NoteError) as e:
            N.add(db, c, deal, acc, kind, body)
        assert e.value.status == 422


def test_a_note_cannot_be_edited_in_the_database(db, monkeypatch):
    monkeypatch.setattr(N, "emit", lambda *a, **k: None)
    c, deal, acc, _ = _rk(db)
    row = N.add(db, c, deal, acc, "note", "исходный текст")
    with pytest.raises(Exception):
        db.execute(text("UPDATE ad_campaign_note SET text = 'подмена' WHERE id = :i"), {"i": row["id"]})
        db.flush()


def test_problem_goes_to_account_and_account_note_to_traffic(db, monkeypatch):
    sent = []
    monkeypatch.setattr(N, "emit", lambda db_, key, **k: sent.append((key, k.get("ctx", {}).get("deal"))))
    c, deal, acc, traf = _rk(db)
    N.add(db, c, deal, traf, "problem", "площадка не крутит")
    N.add(db, c, deal, acc, "note", "клиент просит сдвинуть старт")
    assert [k for k, _ in sent] == ["rk_note_problem", "rk_note_from_account"]
    assert all(d is deal for _, d in sent), "резолверу нужна сделка объектом (`RESOLVER_CTX`)"


def test_traffic_manager_resolver(db):
    from app.notify import recipients as R
    _c, deal, _acc, traf = _rk(db)
    assert R.RESOLVERS["traffic_manager"](db, {"deal": deal}) == [traf.id]
    assert R.RESOLVER_CTX["traffic_manager"] == "deal" and R.RESOLVER_LABELS["traffic_manager"]


def test_routes_give_the_log_and_refuse_strangers(db, monkeypatch):
    from fastapi import HTTPException
    from app.routers import traffic_dashboard as TD
    monkeypatch.setattr(N, "emit", lambda *a, **k: None)
    monkeypatch.setattr(db, "commit", db.flush)
    c, deal, acc, traf = _rk(db)
    monkeypatch.setattr(TD, "_campaign_in_scope", lambda db_, cid, u: (c, deal))
    out = TD.add_campaign_note(c.id, TD.NoteIn(kind="agreement", text="Договорились о старте 10.11"), db=db, user=acc)
    got = TD.campaign_notes(c.id, db=db, user=traf)
    assert got["items"][0]["id"] == out["id"] and got["can_write"] is True
    with pytest.raises(HTTPException) as e:
        TD.add_campaign_note(c.id, TD.NoteIn(text="чужая"), db=db, user=_stranger(db, acc.id, traf.id))
    assert e.value.status_code == 403
