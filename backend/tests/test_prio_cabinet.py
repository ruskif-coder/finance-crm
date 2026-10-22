# -*- coding: utf-8 -*-
"""Приоритезация в кабинете площадки (19.10.2026): SKU и ответ площадки через шлюз ядра; чужая площадка — 404; запись в ленту.
Живая учётка кабинета стенда; транзакция откатывается, уведомления подменены."""
import pytest
from fastapi import HTTPException
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.prio import models as M
from app.prio import service as S
from app.routers import cabinet_gateway as G


class _U:
    id = None


@pytest.fixture
def env(monkeypatch):
    import app.notify.bus as bus
    monkeypatch.setattr(bus, "emit", lambda *a, **k: None)
    from app.database import SessionLocal
    from app.sales.models import SalesDeal
    db = SessionLocal()
    # Площадка, которую учётка видит через СВОЙ кабинет (`cabinet_publisher`) — то же правило, что у шлюза
    # (`cabinet.scope.account_sees_publisher`). Привязка учётки к площадке (`cabinet_account_publisher`) на стенде пуста,
    # и фикстура, опиравшаяся на неё, проходила только в общем прогоне — когда соседний тест на время её заполнял.
    acc = db.execute(text("""
        SELECT a.id, cp.publisher_id FROM cabinet_account a JOIN cabinet c ON c.id = a.cabinet_id AND c.state = 'активен'
          JOIN cabinet_publisher cp ON cp.cabinet_id = c.id
         WHERE a.can_approve ORDER BY a.id, cp.publisher_id LIMIT 1""")).first()
    did = db.execute(text("""SELECT d.id FROM sales_deals d JOIN sales_services s ON s.id = d.service_id
                              WHERE s.name = 'Приоритезация' AND d.period_from IS NOT NULL ORDER BY d.id LIMIT 1""")).scalar()
    if not acc or not did:
        pytest.skip("на стенде нет активной учётки кабинета с правом ответа или сделки Приоритезации")
    d = db.get(SalesDeal, did)
    db.execute(text("UPDATE sales_publishers SET prio_site_id = 7777 WHERE id = :p"), {"p": acc[1]})
    S.save_common(db, d, {"product_name": "Аллервэй 5мг"}, _U())
    p = S.add_placement(db, d, acc[1], _U())
    S.edit_placement(db, d, p.id, {"erid": "2SDtest", "product_url": "https://apteka.example/p/1"})
    S.send(db, d, p.id, _U())
    monkeypatch.setattr(db, "commit", db.flush)            # шлюз коммитит — в тесте только flush
    try:
        yield db, acc[0], acc[1], p
    finally:
        db.rollback()
        db.close()


def test_sku_and_approve_via_gateway(env):
    db, acc_id, pub, p = env
    with pytest.raises(HTTPException) as e:
        G.cabinet_prio_sku(p.id, G.CabinetPrioSkuIn(publisher_id=pub, account_id=acc_id, sku="12", author_name="т"), db)
    assert e.value.status_code == 400
    G.cabinet_prio_sku(p.id, G.CabinetPrioSkuIn(publisher_id=pub, account_id=acc_id, sku="1234567", author_name="т"), db)
    out = G.cabinet_prio_verdict(p.id, G.CabinetPrioVerdictIn(publisher_id=pub, account_id=acc_id, verdict="ок", author_name="т"), db)
    assert out["status"] == M.APPROVED
    kinds = [r[0] for r in db.execute(text("SELECT action FROM cabinet_log WHERE entity_type = 'prio_placement' AND entity_id = :e"),
                                      {"e": p.id})]
    assert set(kinds) >= {"приоритезация_sku", "приоритезация_ок"}


def test_foreign_publisher_is_404(env):
    db, acc_id, pub, p = env
    with pytest.raises(HTTPException) as e:
        G.cabinet_prio_verdict(p.id, G.CabinetPrioVerdictIn(publisher_id=pub + 100000, account_id=acc_id, verdict="ок", author_name="т"), db)
    assert e.value.status_code == 404


def test_return_needs_remark(env):
    db, acc_id, pub, p = env
    with pytest.raises(HTTPException) as e:
        G.cabinet_prio_verdict(p.id, G.CabinetPrioVerdictIn(publisher_id=pub, account_id=acc_id, verdict="вернуть", author_name="т"), db)
    assert e.value.status_code == 400
    G.cabinet_prio_verdict(p.id, G.CabinetPrioVerdictIn(publisher_id=pub, account_id=acc_id, verdict="вернуть",
                                                        reason="SKU не тот", author_name="т"), db)
    assert p.status == M.REWORK
