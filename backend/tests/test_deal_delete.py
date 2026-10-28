# -*- coding: utf-8 -*-
"""Прибор: удаление сделок — только админ и только «пустых» (аудит 23.09.2026, 3.H3).

Массовое удаление стояло под правом `sales_registry:edit` и каскадом стирало кампании,
разнесения по приложениям, сборку запуска, историю стадий. Медиапланы оставались без
сделки. Сделка с комментарием роняла всю пачку с 500 — у комментариев и ссылки
«продление от» внешний ключ без каскада.

Решение владельца 23.09.2026: удаляет ТОЛЬКО АДМИН. И даже он не удаляет сделку, к которой
уже привязана работа, — сначала её надо отвязать, чтобы удаление было осознанным.

23.10.2026 владелец изменил: админ удаляет сделку со всей НАШЕЙ цепочкой; отказ — только если след
ушёл наружу (DSP, ОРД, кабинет площадки, мастер-сделка), см. `test_admin_force_deal.py`. Удаление
воронки живёт по прежнему правилу (`deal_delete.holders`).
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


def test_deal_with_a_media_plan_goes_with_its_plan(db, admin):
    """Было (23.09.2026): сделка с медиапланом не удаляется. Владелец 23.10.2026 отменил: админ удаляет со всей нашей
    цепочкой, медиаплан не остаётся сиротой. Запрет остался только на внешний след — `test_admin_force_deal.py`."""
    d = _bare_deal(db, tag="mp")
    plan = SalesMediaPlan(deal_id=d.id, version=1, status="draft", title="прибор")
    db.add(plan)
    db.flush()
    sd.bulk_delete_deals(sd.BulkDelete(deal_ids=[d.id]), db=db, current_user=admin)
    assert db.query(SalesDeal).filter(SalesDeal.id == d.id).count() == 0
    assert db.query(SalesMediaPlan).filter(SalesMediaPlan.deal_id == d.id).count() == 0


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


def test_sent_recon_and_booked_sk_block_admin_delete(db):
    """Ревью 27.10.2026 (v2.7.0..): удаление админом стирало итоговую сверку, уже отправленную в документооборот, — сделка,
    отвязанная от пакета после «Отправить в ДО», удалялась вместе с замороженной суммой. А начисленная СК закрытого месяца
    (`sk_accruals`, ключ без каскада) роняла удаление с 500. Оба следа — уже не только наши: блок с перечнем."""
    from datetime import datetime
    from sqlalchemy import text
    from app.final_recon.models import FinalReconDeal
    from app.sales import deal_delete as DD
    d = _bare_deal(db, tag="recon-sent")
    assert DD.external(db, [d.id]) == {}
    db.add(FinalReconDeal(deal_id=d.id, sent_at=datetime.utcnow(), base_net=1000))
    db.flush()
    assert "сверка отправлена в ДО" in DD.external(db, [d.id]).get(d.id, [])
    e = _bare_deal(db, tag="sk-booked")
    db.execute(text("INSERT INTO sk_months (period) VALUES ('2019-02') ON CONFLICT DO NOTHING"))
    db.execute(text("""INSERT INTO sk_accruals (period, deal_id, kind, mode, percent, base_net, amount_net)
                       VALUES ('2019-02', :d, 'основная', 'постоплата', 10, 1000, 100)"""), {"d": e.id})
    assert "СК начислена в закрытом месяце" in DD.external(db, [e.id]).get(e.id, [])
