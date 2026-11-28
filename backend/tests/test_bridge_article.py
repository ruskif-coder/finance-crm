# -*- coding: utf-8 -*-
"""Статья операции из закрывающих (владелец 28.11.2026).

Правило: допы, вынесенные в отдельный ДС `#n-01` под основным, при формировании операции получают статью «Доп услуги».
Остальные ДС — по своему составу (базовая услуга → её статья; только допы → статья услуги сделки).

Поломка, которую ловит: доп-ДС не имеет базовой строки, и статья бралась по услуге сделки — у еФарм-пакетов
доп-операция получала «еФарм», хотя это доп-услуга. Транзакция откатывается.
"""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.master_deal import bridge as B


@pytest.fixture
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _addon(db):
    return db.execute(text("""SELECT a.id FROM sales_annexes a
                               WHERE a.sub_no IS NOT NULL AND a.sub_no <> ''
                               ORDER BY a.id LIMIT 1""")).scalar()


def test_addon_annex_gets_the_addons_article(db):
    from app.master_deal.models import MasterDealUpd
    from app.sales.models import SalesAnnex
    annex_id = _addon(db)
    if annex_id is None:
        pytest.skip("на стенде нет доп-ДС #n-01")
    annex = db.get(SalesAnnex, annex_id)
    k = db.query(MasterDealUpd).filter_by(annex_id=annex.id).order_by(MasterDealUpd.upd_no).first()
    if k is None:
        pytest.skip("у доп-ДС нет комплектов")
    addons_article = B._addons_article(db)
    if addons_article is None:
        pytest.skip("в справочнике статей нет «Доп услуги»")
    # «по составу» доп-ДС дал бы статью услуги сделки (еФарм у этих пакетов) — правило должно её перебить
    assert B._article_of_annex(db, annex, k) != addons_article, "данные стенда не показывают разницу"
    assert B._article(db, annex, k) == addons_article


def test_main_annex_is_not_touched_by_the_addons_rule(db):
    """Основной ДС пакета продолжает считаться по своему составу: у него есть базовая строка."""
    from app.sales.models import SalesAnnex
    annex_id = _addon(db)
    if annex_id is None:
        pytest.skip("на стенде нет доп-ДС #n-01")
    addon = db.get(SalesAnnex, annex_id)
    main_id = db.execute(text("""SELECT id FROM sales_annexes WHERE master_deal_id = :m
                                  AND (sub_no IS NULL OR sub_no = '') ORDER BY id LIMIT 1"""),
                         {"m": addon.master_deal_id}).scalar()
    if main_id is None:
        pytest.skip("у пакета нет основного ДС")
    main = db.get(SalesAnnex, main_id)
    assert not getattr(main, "sub_no", None)
    assert B._article(db, main, None) == B._article_of_annex(db, main, None)
