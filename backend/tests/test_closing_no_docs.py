# -*- coding: utf-8 -*-
"""«Закрыть без документов» (владелец 19.10.2026): бонусное размещение — к закрытию 0 ₽ → сверка замораживается, сделка сразу
в «Архив успешных сделок», без мастер-сделки и ДС. Сделки со стенда, транзакция откатывается."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.final_recon import closing as CL
from app.final_recon import no_docs as ND


class _U:
    id = None
    name = "тест"


@pytest.fixture
def db(monkeypatch):
    import app.notify.bus as bus
    monkeypatch.setattr(bus, "emit", lambda *a, **k: None)
    from app.database import SessionLocal
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def _on_recon(db, code_sql):
    from app.sales.models import SalesDeal
    did = db.execute(text(code_sql)).scalar()
    if not did:
        pytest.skip("нет подходящей сделки на стенде")
    d = db.get(SalesDeal, did)
    d.our_stage_id = db.execute(text("SELECT id FROM sales_stages WHERE name = 'Итоговая сверка'")).scalar()
    db.flush()
    return d


ZERO = """SELECT d.id FROM sales_deals d JOIN sales_media_plans mp ON mp.deal_id = d.id AND mp.status <> 'rejected'
           JOIN sales_media_plan_rows r ON r.plan_id = mp.id
          WHERE NOT EXISTS (SELECT 1 FROM master_deal_items i WHERE i.deal_id = d.id)
          GROUP BY d.id HAVING bool_and(coalesce(r.discount, 0) >= 1 OR coalesce(r.unit_price, 0) = 0) ORDER BY d.id LIMIT 1"""
PAID = """SELECT d.id FROM sales_deals d JOIN sales_media_plans mp ON mp.deal_id = d.id AND mp.status <> 'rejected'
           JOIN sales_media_plan_rows r ON r.plan_id = mp.id AND r.unit_price > 0 AND coalesce(r.discount, 0) < 1 AND r.volume > 0
          WHERE NOT EXISTS (SELECT 1 FROM master_deal_items i WHERE i.deal_id = d.id)
            AND NOT EXISTS (SELECT 1 FROM final_recon_deals f WHERE f.deal_id = d.id AND f.sent_at IS NOT NULL)
          ORDER BY d.id DESC LIMIT 1"""


def test_zero_deal_closes_into_archive(db):
    d = _on_recon(db, ZERO)
    st = CL.compute(db, d)
    assert st["base_plan_net"] == 0 and st["paid_extras_net"] == 0 and st["no_docs"]["eligible"]
    out = ND.close(db, d, _U())
    st = CL.compute(db, d)
    assert st["frozen"] and st["no_docs"]["closed_at"]
    stage = db.execute(text("SELECT name FROM sales_stages WHERE id = :s"), {"s": d.our_stage_id}).scalar()
    assert stage == "Архив успешных сделок" and out["moved_to"] == stage
    assert not db.execute(text("SELECT 1 FROM master_deal_items WHERE deal_id = :d"), {"d": d.id}).first()


def test_paid_deal_cannot_close_without_docs(db):
    d = _on_recon(db, PAID)
    assert not CL.compute(db, d)["no_docs"]["eligible"]
    with pytest.raises(CL.ClosingError) as e:
        ND.close(db, d, _U())
    assert e.value.status == 409


def test_repeat_is_refused(db):
    d = _on_recon(db, ZERO)
    ND.close(db, d, _U())
    with pytest.raises(CL.ClosingError):
        ND.close(db, d, _U())
