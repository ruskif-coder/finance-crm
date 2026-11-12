# -*- coding: utf-8 -*-
"""Основание УПД у ДС, подписанного вне системы (владелец 05.11.2026): «генерим по шаблону наиболее близкому — если есть
прикреплённый к бренду — или исторически который был». Своей модели у внешнего ДС нет (его текст — чужой файл), поэтому
основание собирается по шаблону той же цепочкой, что в конструкторе: память бренда → основной договора → базовый формата.

Поломка, которую ловит: у внешнего ДС основание пустое — бухгалтеру нечего вписать в УПД (на проде 05.11: M-0011, M-0019, M-0020).
Живой пакет стенда, только чтение."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401


@pytest.fixture
def kit():
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal, MasterDealUpd
    db = SessionLocal()
    row = db.execute(text("""SELECT k.id FROM master_deal_upds k JOIN sales_annexes a ON a.id = k.annex_id
                              WHERE a.origin = 'загружен' AND k.basis_text IS NULL ORDER BY k.id LIMIT 1""")).first()
    if row is None:
        db.close()
        pytest.skip("на стенде нет внешних ДС в пакетах")
    k = db.get(MasterDealUpd, row[0])
    try:
        yield db, db.get(MasterDeal, k.master_deal_id), k
    finally:
        db.rollback()
        db.close()


def test_external_annex_kit_gets_basis_from_nearest_template(kit):
    db, m, k = kit
    from app.master_deal import to_annex as TA
    u = next(x for x in TA.upds_of(db, m) if x["upd_no"] == k.upd_no)
    assert u["basis"].strip(), "основание внешнего ДС — по шаблону, не пустое"
    from app.sales.models import SalesAnnex
    a = db.get(SalesAnnex, k.annex_id)
    assert str(a.no) in u["basis"], "в основании — номер самого внешнего ДС"


# ── Основание, вписанное у внешнего ДС (владелец 12.11.2026: «сделай там форму и кнопку “сгенерировать по базовому шаблону
# услуги”»). Ломается, если основание внешнего ДС снова негде задать, если УПД перестанут его брать, или если правка пройдёт
# после того, как комплект внесён в 1С.

@pytest.fixture
def open_kit(kit):
    """Тот же комплект, но ДС ещё не в 1С: отметки 1С снимаются в транзакции теста и откатываются вместе с ней."""
    db, m, k = kit
    db.execute(text("UPDATE master_deal_upds SET onec_at = NULL WHERE annex_id = :a"), {"a": k.annex_id})
    db.expire_all()
    from app.master_deal.models import MasterDealUpd
    return db, m, db.get(MasterDealUpd, k.id)


def _annex(db, k):
    from app.sales.models import SalesAnnex
    return db.get(SalesAnnex, k.annex_id)


def _basis(db, m, k):
    from app.master_deal import to_annex as TA
    return next(x for x in TA.upds_of(db, m) if x["upd_no"] == k.upd_no)


def test_basis_typed_at_external_annex_goes_to_its_upd(open_kit):
    db, m, k = open_kit
    from app.sales import annex_external as X
    X.set_closing(db, _annex(db, k), "Услуги по подписанному клиентом приложению")
    db.flush()
    u = _basis(db, m, k)
    assert u["basis"] == "Услуги по подписанному клиентом приложению"
    assert X.closing_view(db, _annex(db, k))["edited"] is True


def test_cleared_basis_returns_to_the_template(open_kit):
    db, m, k = open_kit
    from app.sales import annex_external as X
    before = _basis(db, m, k)["basis"]
    X.set_closing(db, _annex(db, k), "Временный текст основания")
    X.set_closing(db, _annex(db, k), None)
    db.flush()
    assert _basis(db, m, k)["basis"] == before


def test_basis_is_closed_once_the_kit_is_in_1c(open_kit):
    db, m, k = open_kit
    from datetime import datetime
    from app.sales import annex_external as X
    k.onec_at = datetime.utcnow()
    db.flush()
    with pytest.raises(X.ExternalError) as e:
        X.set_closing(db, _annex(db, k), "Поздняя правка")
    assert e.value.status == 409


def test_unknown_substitution_is_refused(open_kit):
    db, m, k = open_kit
    from app.sales import annex_external as X
    with pytest.raises(X.ExternalError) as e:
        X.set_closing(db, _annex(db, k), "Основание по {такой_подстановки_нет}")
    assert e.value.status == 400


def test_generated_basis_follows_the_services_of_the_annex():
    from app.sales import annex_external as X
    addons_only = X.generated_basis([{"addon_id": 7}])
    placement = X.generated_basis([{"service_id": 3}])
    mixed = X.generated_basis([{"service_id": 3}, {"addon_id": 7}])
    assert addons_only.startswith("Оказание дополнительных услуг ({услуга}) для бренда «{бренд_название}», согласно ")
    assert placement.startswith("Размещение рекламных материалов бренда «{бренд_название}», в сети {сеть}, согласно ")
    assert mixed.startswith("Размещение рекламных материалов и оказание дополнительных услуг ({услуга}) бренда ")
    assert addons_only.endswith("к Договору {договор_номер} от {договор_дата_кратко}г., с {период_с} по {период_по}г.")
