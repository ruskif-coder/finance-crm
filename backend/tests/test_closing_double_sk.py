# -*- coding: utf-8 -*-
"""Двойная СК (прод 06.11.2026, четыре сделки): аккаунт вписал «скидку в счёт» в строки МП,
а на закрытии по договору сработало правило «Агентских условий» — та же скидка вычлась второй раз. И сверка была подтверждена
ДО выбора договора, то есть на сумму без СК, а выбор договора подтверждение не снял.

Правила (владелец 06.11.2026): скидка в строках МП при «скидке в счёт» по правилу — сверку не подтвердить и в ДО не отправить;
смена доходного договора или плательщика снимает подтверждение. Записи на стенд не остаются: всё в откатываемой транзакции."""
from types import SimpleNamespace

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.final_recon import closing as CL
from app.final_recon import sk as SK


class _U:
    id = None
    role = "admin"


def _sk(source, percent=45.8):
    return {"payer_id": 1, "payer_name": "Юрлицо", "payer_mode": "скидка в счёт", "payer_percent": percent, "rule_id": 1,
            "mode": "скидка в счёт", "percent": percent, "source": source}


@pytest.fixture
def deal_db():
    from app.database import SessionLocal
    from app.sales.models import SalesDeal
    db = SessionLocal()
    row = db.execute(text("""
        SELECT d.id, mp.id FROM sales_deals d JOIN sales_media_plans mp ON mp.deal_id = d.id
          LEFT JOIN final_recon_deals f ON f.deal_id = d.id
         WHERE mp.version = (SELECT max(version) FROM sales_media_plans x WHERE x.deal_id = d.id)
           AND f.sent_at IS NULL
           AND EXISTS (SELECT 1 FROM sales_media_plan_rows r WHERE r.plan_id = mp.id AND r.unit_price > 0 AND r.volume > 0)
         ORDER BY d.id LIMIT 1""")).first()
    if not row:
        pytest.skip("на стенде нет неотправленной сделки с посчитанным МП")
    try:
        yield db, db.get(SalesDeal, row[0]), row[1]
    finally:
        db.rollback()
        db.close()


def _discount_rows(db, plan_id, disc):
    db.execute(text("UPDATE sales_media_plan_rows SET discount = :d WHERE plan_id = :p"), {"d": disc, "p": plan_id})


def test_rule_discount_over_discounted_mp_is_flagged_and_blocks(deal_db, monkeypatch):
    db, d, plan_id = deal_db
    _discount_rows(db, plan_id, 0.458)
    monkeypatch.setattr(SK, "of_deal", lambda db, deal: _sk("rule"))
    st = CL.compute(db, d)
    assert st["sk"]["mp_discount"] == [45.8]
    assert st["sk"]["double"] is True
    CL.set_mode(db, d, "plan", None, _U(), privileged=True)
    with pytest.raises(CL.ClosingError) as e:
        CL.confirm(db, d, True, _U())
    assert e.value.status == 409 and "дважды" in e.value.message
    with pytest.raises(CL.ClosingError) as e2:
        CL.freeze(db, d, _U())
    assert e2.value.status == 409


def test_no_mp_discount_is_not_double(deal_db, monkeypatch):
    db, d, plan_id = deal_db
    _discount_rows(db, plan_id, 0)
    monkeypatch.setattr(SK, "of_deal", lambda db, deal: _sk("rule"))
    st = CL.compute(db, d)
    assert st["sk"]["mp_discount"] == [] and st["sk"]["double"] is False


def test_sk_set_on_the_deal_is_a_conscious_choice(deal_db, monkeypatch):
    """Поправка СК по сделке — аккаунт решил сам (бывает и законная скидка в МП поверх агентской): предупреждаем, не блокируем."""
    db, d, plan_id = deal_db
    _discount_rows(db, plan_id, 0.10)
    monkeypatch.setattr(SK, "of_deal", lambda db, deal: _sk("deal", 45.0))
    st = CL.compute(db, d)
    assert st["sk"]["mp_discount"] == [10.0] and st["sk"]["double"] is False
    CL.set_mode(db, d, "plan", None, _U(), privileged=True)
    assert CL.confirm(db, d, True, _U())["confirmed"]


def test_changing_final_contract_drops_confirmation(deal_db, monkeypatch):
    from app.routers import ord as ORD
    db, d, plan_id = deal_db
    _discount_rows(db, plan_id, 0)
    monkeypatch.setattr(db, "commit", db.flush)          # роутер коммитит — на стенде ничего не остаётся
    monkeypatch.setattr(ORD, "_deal_or_404", lambda db, user, deal_id: d)
    monkeypatch.setattr(ORD, "log_action", lambda *a, **k: None)
    CL.set_mode(db, d, "plan", None, _U(), privileged=True)
    CL.confirm(db, d, True, _U())
    assert CL._rec(db, d.id).confirmed_at is not None
    ORD.set_final(d.id, ORD.SetFinal(contract_id=None), db=db, current_user=SimpleNamespace(id=None))
    assert CL._rec(db, d.id).confirmed_at is None


def test_client_discount_unlike_sk_is_legit(deal_db, monkeypatch):
    """Владелец 06.11.2026: 10 % в МП — скидка клиенту к CGV, 45 % — комиссия агентства. Разные проценты —
    законная пара: предупреждение, не блок. Двойная — когда в МП вписана сама СК (% в пределах ±1 п.п. от правила)."""
    db, d, plan_id = deal_db
    _discount_rows(db, plan_id, 0.10)
    monkeypatch.setattr(SK, "of_deal", lambda db, deal: _sk("rule", 45.0))
    st = CL.compute(db, d)
    assert st["sk"]["mp_discount"] == [10.0] and st["sk"]["double"] is False
    CL.set_mode(db, d, "plan", None, _U(), privileged=True)
    assert CL.confirm(db, d, True, _U())["confirmed"]


def test_mp_discount_near_sk_percent_is_double(deal_db, monkeypatch):
    """Прод 06.11.2026: в МП 45,8 %, по правилу 44,8 % — та же СК с опечаткой, всё равно двойная."""
    db, d, plan_id = deal_db
    _discount_rows(db, plan_id, 0.458)
    monkeypatch.setattr(SK, "of_deal", lambda db, deal: _sk("rule", 44.8))
    assert CL.compute(db, d)["sk"]["double"] is True
