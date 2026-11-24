# -*- coding: utf-8 -*-
"""Реестр мастер-сделок в «Финансах» и право `master_deals` (владелец 19.10.2026: «нет / просмотр / редактирование»)."""
import inspect

import pytest

import app.model_registry  # noqa: F401
from app.permissions import SECTIONS
from app.master_deal import registry as RG
from app.master_deal import scope as SC
from app.routers import master_deals as R


def test_section_is_finance_with_view_edit_and_approve():
    """approve — «согласование»: даты РК во внешнем ДС (владелец 05.11.2026: мастер аккаунт и админ)."""
    s = next(x for x in SECTIONS if x["key"] == "master_deals")
    assert s["group"] == "Финансы" and s["actions"] == ["view", "edit", "approve"]


def test_every_route_is_gated_by_master_deals_permission():
    """Читающие ручки — `master_deals` view, пишущие — edit; право реестра сделок пакет больше не открывает."""
    src = inspect.getsource(R)
    assert 'require_permission("master_deals", "view")' in src and 'require_permission("master_deals", "edit")' in src
    for route in R.router.routes:
        calls = {d.call for d in route.dependant.dependencies}
        writes = bool(route.methods & {"PUT", "POST", "DELETE"}) and not route.path.endswith("/preview")
        want = R.MD_EDIT if writes else R.MD_VIEW
        if route.path.endswith("/efficiency"):        # своё право — «Эффективность мастер-сделок»
            continue
        assert want in calls, f"{route.methods} {route.path}: нет права master_deals {'edit' if writes else 'view'}"


def test_registry_lists_only_packages_in_scope(monkeypatch):
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal
    db = SessionLocal()
    try:
        all_codes = {m.code for m in db.query(MasterDeal)}
        if not all_codes:
            pytest.skip("на стенде нет мастер-сделок")
        monkeypatch.setattr(SC, "own_reps", lambda db, user: None)
        rows = RG.rows(db, object())
        assert {r["code"] for r in rows} == all_codes
        r = rows[0]
        assert {"code", "status", "period", "contract", "counterparty", "deals", "net", "gross", "ds", "built_by", "advertisers", "brands", "todo"} <= set(r)
        monkeypatch.setattr(SC, "own_reps", lambda db, user: {-1})
        assert RG.rows(db, object()) == [], "роль «свои» без своих сделок видит чужие пакеты"
    finally:
        db.rollback()
        db.close()

def test_paper_package_in_wait_pay_is_flagged_for_scans(monkeypatch):
    """«Ждём сканы» (владелец 23.11.2026): бумажный пакет в «ждём оплату» без подписанных документов попадает в эту
    вкладку — иначе оплата уводит его из поля зрения, хотя документов клиента ещё нет. Подписали все — флаг снимается.

    Сломает: вкладка «ждём сканы» осталась пустой у бумаги или, наоборот, показывает пакет, который уже подписан."""
    import pytest as _pytest
    from sqlalchemy import text
    from app.database import SessionLocal
    from app.master_deal import issue as IS
    from app.master_deal import registry as RG
    from app.master_deal import scope as SC
    from app.master_deal import status as MST
    from app.master_deal.doc_sign import SIGNED
    from app.master_deal.models import MasterDeal

    db = SessionLocal()
    try:
        m = db.query(MasterDeal).filter(MasterDeal.status == MST.WAIT_PAY).first() or db.query(MasterDeal).first()
        if m is None:
            _pytest.skip("на стенде нет мастер-сделок")
        db.execute(text("UPDATE contracts SET issue_channel = 'бумага' WHERE id = :c"), {"c": m.contract_id})
        db.execute(text("UPDATE master_deals SET status = :s WHERE id = :i"), {"s": MST.WAIT_PAY, "i": m.id})
        # и отметку подписи, и канал отправки — у УПД И у ДС: ушедшее по ЭДО держит канал и не становится бумагой (status.is_paper)
        db.execute(text("UPDATE master_deal_upds SET sign_state = NULL, sign_channel = NULL WHERE master_deal_id = :i"), {"i": m.id})
        db.execute(text("UPDATE sales_annexes SET sign_state = NULL, sign_channel = NULL WHERE master_deal_id = :i"), {"i": m.id})
        db.flush()
        db.expire_all()
        monkeypatch.setattr(SC, "own_reps", lambda db, user: None)
        monkeypatch.setattr(SC, "can_finance", lambda db, user: False)

        def row():
            return next(r for r in RG.rows(db, object()) if r["code"] == m.code)

        assert row()["scans"] is True, "бумажный невыставленный пакет не попал во вкладку «ждём сканы»"
        db.execute(text("UPDATE master_deal_upds SET sign_state = :s WHERE master_deal_id = :i"),
                   {"s": SIGNED, "i": m.id})
        db.execute(text("UPDATE sales_annexes SET sign_state = :s WHERE master_deal_id = :i"),
                   {"s": SIGNED, "i": m.id})
        db.flush()
        db.expire_all()
        assert row()["scans"] is False, "подписанный пакет остался в «ждём сканы»"
        assert not IS.unsigned(db, m)
    finally:
        db.rollback()
        db.close()
