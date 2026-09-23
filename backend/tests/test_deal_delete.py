# -*- coding: utf-8 -*-
"""Прибор: удаление сделок — только админ и только «пустых» (аудит 23.09.2026, 3.H3).

Массовое удаление стояло под правом `sales_registry:edit` и каскадом стирало кампании,
разнесения по приложениям, сборку запуска, историю стадий. Медиапланы оставались без
сделки. Сделка с комментарием роняла всю пачку с 500 — у комментариев и ссылки
«продление от» внешний ключ без каскада.

Решение владельца 23.09.2026: удаляет ТОЛЬКО АДМИН. И даже он не удаляет сделку, к которой
уже привязана работа, — сначала её надо отвязать, чтобы удаление было осознанным.
"""
import pytest
from fastapi import HTTPException

import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.notify.models       # noqa: F401
import app.ord.models          # noqa: F401
from app.audit import require_admin
from app.database import SessionLocal
from app.main import app as fastapi_app
from app.models import User
from app.routers import sales_dashboard as sd
from app.sales.models import SalesDeal, SalesDealComment, SalesMediaPlan


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def admin(db):
    return db.query(User).filter(User.is_active == 1, User.role.has(key="admin")).first()


def _bare_deal(db, **kw):
    d = SalesDeal(bitrix_id=f"local-probe-{kw.pop('tag', 'x')}", title="прибор удаления", **kw)
    db.add(d)
    db.flush()
    return d


def test_only_admin_may_delete_deals():
    route = next(r for r in fastapi_app.routes
                 if getattr(r, "path", "") == "/api/sales/deals/bulk-delete")
    deps = {d.call for d in route.dependant.dependencies}
    assert require_admin in deps, "удаление сделок снова открыто не только админу"


def test_deal_with_a_media_plan_is_not_deleted(db, admin):
    d = _bare_deal(db, tag="mp")
    db.add(SalesMediaPlan(deal_id=d.id, version=1, status="draft", title="прибор"))
    db.flush()
    with pytest.raises(HTTPException) as e:
        sd.bulk_delete_deals(sd.BulkDelete(deal_ids=[d.id]), db=db, current_user=admin)
    assert e.value.status_code == 409 and "медиаплан" in e.value.detail
    assert db.query(SalesDeal).filter(SalesDeal.id == d.id).count() == 1


def test_empty_deal_with_a_comment_is_deleted_without_500(db, admin):
    d = _bare_deal(db, tag="comment")
    db.add(SalesDealComment(deal_id=d.id, text="прибор", user_id=admin.id))
    db.flush()
    sd.bulk_delete_deals(sd.BulkDelete(deal_ids=[d.id]), db=db, current_user=admin)
    assert db.query(SalesDeal).filter(SalesDeal.id == d.id).count() == 0


def test_prolongation_link_is_released_not_broken(db, admin):
    old = _bare_deal(db, tag="old")
    new = _bare_deal(db, tag="new", prolonged_from_id=old.id)
    sd.bulk_delete_deals(sd.BulkDelete(deal_ids=[old.id]), db=db, current_user=admin)
    db.expire_all()
    assert db.query(SalesDeal).filter(SalesDeal.id == new.id).first().prolonged_from_id is None


# ── Удаление воронки (аудит 3.M9) ────────────────────────────────────────────────

def test_pipeline_with_our_own_deals_is_not_deleted(db, admin):
    from app.routers import sales_directories as sdir
    from app.sales.models import SalesPipeline
    p = SalesPipeline(name="прибор воронки", sort_order=999)
    db.add(p)
    db.flush()
    d = _bare_deal(db, tag="pipe", pipeline=p.name)
    with pytest.raises(HTTPException) as e:
        sdir.delete_pipeline(p.id, db=db, current_user=admin)
    assert e.value.status_code == 409 and "заведённых у нас" in e.value.detail
    assert db.query(SalesDeal).filter(SalesDeal.id == d.id).count() == 1
