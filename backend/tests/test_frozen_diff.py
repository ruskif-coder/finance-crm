# -*- coding: utf-8 -*-
"""«Было → станет» перед «Пересоздать» и «Обновить из сделки» (владелец 17.11.2026, повод — M-0004: бренд переименован в
справочнике, а выпущенный ДС и основание УПД остались со старым именем).

Поломки, которые ловит набор:
- переименованный бренд не попадает в список изменений (ни в пункт, ни в основание, ни в комплект);
- реквизиты стороны поменялись, а предпросмотр молчит;
- одинаковое показывается как изменение — список тонет в шуме;
- предпросмотр сохраняет пересборку: после него в базе другой ДС или другой бренд комплекта;
- предпросмотр не работает на пакете дальше «согласования» — а именно там его и жмут;
- «Обновить» проходит на «ждём оплату» и дальше — владелец 17.11.2026: на «выставлении» уже нет — сначала возврат на «ждём 1С»."""
import copy

import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.annex_tpl import frozen_diff as FD
from app.master_deal import revert as RV

MODEL = {
    "head": {"text": "Приложение №17\nк Договору № РМ 05-12-2023"},
    "place": {"text": "г. Москва | «31» октября 2026 г."},
    "blocks": [{"sys": "head"}, {"id": "p1", "num": "1.", "title": "Предмет", "text": "для бренда «Тонзилгон»"}],
    "customer": {"legal_name": "ООО «Заказчик»", "inn": "7700000001", "kpp": "770001001", "address": "Москва", "director": "Иванов И.И."},
    "executor": {"legal_name": "ООО «Исполнитель»", "inn": "7700000002", "kpp": "770001002"},
    "table": {"groups": [{"rows": [{"brand": "Бионорика / Тонзилгон · OLV", "volume": 4800000, "unit_price": 290.0,
                                    "amount": 1392000.0, "gross": 1698240.0}]}]},
    "amount": 1698240.0,
    "closing_basis": {"text": "Размещение рекламных материалов бренда «Тонзилгон»"},
}


def test_same_model_gives_no_changes():
    assert FD.model_changes(MODEL, copy.deepcopy(MODEL)) == []


def test_renamed_brand_shows_in_clause_table_and_basis():
    new = copy.deepcopy(MODEL)
    new["blocks"][1]["text"] = "для бренда «Тонзилгон Н»"
    new["table"]["groups"][0]["rows"][0]["brand"] = "Бионорика / Тонзилгон Н · OLV"
    new["closing_basis"]["text"] = "Размещение рекламных материалов бренда «Тонзилгон Н»"
    got = {c["where"]: (c["was"], c["now"]) for c in FD.model_changes(MODEL, new)}
    assert got == {
        "Пункт 1. Предмет": ("для бренда «Тонзилгон»", "для бренда «Тонзилгон Н»"),
        "Таблица · строка 1": ("Бионорика / Тонзилгон · OLV", "Бионорика / Тонзилгон Н · OLV"),
        "Основание к закрытию": ("Размещение рекламных материалов бренда «Тонзилгон»", "Размещение рекламных материалов бренда «Тонзилгон Н»"),
    }


def test_party_requisites_and_numbers():
    new = copy.deepcopy(MODEL)
    new["customer"]["kpp"] = "770201001"
    new["table"]["groups"][0]["rows"][0]["unit_price"] = 290.004       # копейка округления — не изменение
    new["amount"] = 1698240.004
    got = FD.model_changes(MODEL, new)
    assert got == [{"where": "Заказчик · КПП", "was": "770001001", "now": "770201001"}]


def test_kit_changes_by_upd_number():
    was = [{"upd_no": 1, "brand": "Бионорика / Тонзилгон", "service": "OLV", "gross": 1698240.0, "basis": "бренда «Тонзилгон»"}]
    now = [{**was[0], "brand": "Бионорика / Тонзилгон Н", "basis": "бренда «Тонзилгон Н»"}]
    assert [c["where"] for c in FD.kit_changes(was, now)] == ["УПД № 1 · бренд", "УПД № 1 · основание"]


@pytest.fixture
def pack():
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal
    from app.models import User
    db = SessionLocal()
    mid = db.execute(text("""SELECT m.id FROM master_deals m
                              WHERE EXISTS (SELECT 1 FROM master_deal_upds k WHERE k.master_deal_id = m.id)
                                AND EXISTS (SELECT 1 FROM sales_annexes a WHERE a.master_deal_id = m.id AND a.no IS NOT NULL)
                                AND NOT EXISTS (SELECT 1 FROM sales_annexes a WHERE a.master_deal_id = m.id
                                                                             AND (a.no IS NULL OR a.origin = 'загружен'))
                              ORDER BY m.id DESC LIMIT 1""")).scalar()
    if mid is None:
        db.close()
        pytest.skip("на стенде нет пакета с подтверждёнными ДС и комплектами")
    user = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
    try:
        yield db, db.get(MasterDeal, mid), user
    finally:
        db.rollback()
        db.close()


def _state(db, m):
    ds = db.execute(text("SELECT id, blocks::text, sign_state FROM sales_annexes WHERE master_deal_id = :m ORDER BY id"), {"m": m.id}).all()
    kits = db.execute(text("SELECT upd_no, brand, gross FROM master_deal_upds WHERE master_deal_id = :m ORDER BY upd_no"), {"m": m.id}).all()
    return ds, kits, db.execute(text("SELECT status FROM master_deals WHERE id = :m"), {"m": m.id}).scalar()


def test_preview_shows_kit_brand_and_saves_nothing(pack):
    db, m, user = pack
    m.status = RV.ST.WAIT_1C
    db.execute(text("UPDATE master_deal_upds SET brand = 'СТАРОЕ НАПИСАНИЕ' WHERE master_deal_id = :m"), {"m": m.id})
    db.flush()
    db.expire_all()
    before = _state(db, m)
    out = RV.preview(db, m, user)
    db.expire_all()
    assert _state(db, m) == before                                  # предпросмотр ничего не оставил
    kit = [c for c in out["changes"] if c["where"].endswith("· бренд")]
    assert kit and all(c["was"] == "СТАРОЕ НАПИСАНИЕ" and c["now"] != "СТАРОЕ НАПИСАНИЕ" for c in kit)
    assert out["need_back"] == (m.status != RV.ST.AGREE)


@pytest.mark.parametrize("status", [RV.ST.ISSUE, RV.ST.WAIT_PAY, RV.ST.ARCHIVE])
def test_refresh_only_up_to_wait_1c_then_via_revert(pack, status):
    db, m, user = pack
    m.status = status
    db.flush()
    assert not RV.may_refresh(m)
    with pytest.raises(RV.RevertError) as e:
        RV.preview(db, m, user)
    assert e.value.status == 409 and "ждём 1С" in e.value.message
    for ok in (RV.ST.AGREE, RV.ST.WAIT_1C):
        m.status = ok
        assert RV.may_refresh(m)
