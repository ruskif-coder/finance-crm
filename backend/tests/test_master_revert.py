# -*- coding: utf-8 -*-
"""Возврат стадии мастер-сделки и «Обновить из сделки» (владелец 12.11.2026: «моментов, когда надо переделать, — масса»: от
написания бренда после правки справочника до ошибок в реквизитах со стороны 1С).

Поломки, которые ловит набор:
- после возврата на «ждём 1С» комплект не появляется у бухгалтера (ответ 1С остался) или остаётся «отправлен клиенту»;
- возврат на «ждём 1С» трогает ДС — ошибка была в документах 1С, а не в ДС;
- после возврата на «согласование» ДС остаётся «подписан» прежним кругом, хотя будет пересобран;
- возврат без причины, вперёд, на ту же стадию или в раскладку проходит;
- «Обновить из сделки» не переносит в комплект бренд из текущих данных или работает вне «согласования»;
- «ДС проверены → в 1С» уводит пакет с неподтверждёнными ДС.
Каждый тест — на живом пакете стенда в транзакции с откатом."""
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.master_deal import revert as RV
from app.master_deal import status as ST


@pytest.fixture
def pack():
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal
    from app.models import User
    db = SessionLocal()
    mid = db.execute(text("""SELECT m.id FROM master_deals m
                              WHERE EXISTS (SELECT 1 FROM master_deal_upds k WHERE k.master_deal_id = m.id)
                                AND EXISTS (SELECT 1 FROM sales_annexes a WHERE a.master_deal_id = m.id AND a.no IS NOT NULL
                                                                         AND coalesce(a.origin, '') <> 'загружен')
                                AND NOT EXISTS (SELECT 1 FROM sales_annexes a WHERE a.master_deal_id = m.id
                                                                             AND (a.no IS NULL OR a.origin = 'загружен'))
                              ORDER BY m.id DESC LIMIT 1""")).scalar()
    if mid is None:
        db.close()
        pytest.skip("на стенде нет пакета с подтверждёнными ДС и комплектами")
    m = db.get(MasterDeal, mid)
    m.status = ST.ISSUE
    db.execute(text("""UPDATE master_deal_upds SET onec_state = 'внесён', onec_at = now(), sign_state = 'выставлен', sign_channel = 'ЭДО'
                        WHERE master_deal_id = :m"""), {"m": mid})
    db.execute(text("UPDATE sales_annexes SET sign_state = 'подписан', sign_channel = 'ЭДО' WHERE master_deal_id = :m"), {"m": mid})
    db.flush()
    db.expire_all()
    user = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
    try:
        yield db, db.get(MasterDeal, mid), user
    finally:
        db.rollback()
        db.close()


def _kits(db, m):
    return db.execute(text("SELECT onec_state, onec_at, sign_state FROM master_deal_upds WHERE master_deal_id = :m"), {"m": m.id}).all()


def _ds(db, m):
    return [r[0] for r in db.execute(text("SELECT sign_state FROM sales_annexes WHERE master_deal_id = :m"), {"m": m.id})]


def test_back_to_1c_returns_kits_to_the_accountant_and_keeps_ds(pack):
    db, m, user = pack
    out = RV.revert(db, m, ST.WAIT_1C, user, "в УПД не тот КПП")
    db.expire_all()
    assert m.status == ST.WAIT_1C
    assert all(k == (None, None, None) for k in _kits(db, m))
    assert set(_ds(db, m)) == {"подписан"}
    assert out["kits"] >= 1 and out["in_1c"] >= 1


def test_back_to_agreement_reissues_ds(pack):
    db, m, user = pack
    RV.revert(db, m, ST.AGREE, user, "бренд переименован в справочнике")
    db.expire_all()
    assert m.status == ST.AGREE
    assert set(_ds(db, m)) == {"выпущен"}
    assert all(k == (None, None, None) for k in _kits(db, m))


@pytest.mark.parametrize("to, reason, status", [
    (ST.WAIT_1C, "  ", 400),
    (ST.ARCHIVE, "причина", 409),
    (ST.ISSUE, "причина", 409),
    (ST.DRAFT, "причина", 409),
])
def test_refused_reverts(pack, to, reason, status):
    db, m, user = pack
    with pytest.raises(RV.RevertError) as e:
        RV.revert(db, m, to, user, reason)
    assert e.value.status == status
    assert m.status == ST.ISSUE


def test_targets_are_earlier_stages_only(pack):
    db, m, _ = pack
    assert RV.targets(db, m) == [ST.AGREE, ST.WAIT_1C]


def test_refresh_takes_current_data_into_kits(pack):
    db, m, user = pack
    RV.revert(db, m, ST.AGREE, user, "бренд")
    db.execute(text("UPDATE master_deal_upds SET brand = 'СТАРОЕ НАПИСАНИЕ' WHERE master_deal_id = :m"), {"m": m.id})
    db.flush()
    db.expire_all()
    RV.refresh(db, m, user)
    db.expire_all()
    brands = [r[0] for r in db.execute(text("SELECT brand FROM master_deal_upds WHERE master_deal_id = :m"), {"m": m.id})]
    assert "СТАРОЕ НАПИСАНИЕ" not in brands


def test_refresh_only_on_agreement(pack):
    db, m, user = pack
    with pytest.raises(RV.RevertError) as e:
        RV.refresh(db, m, user)
    assert e.value.status == 409


def test_agreed_sends_to_1c_only_when_every_ds_confirmed(pack):
    db, m, user = pack
    RV.revert(db, m, ST.AGREE, user, "бренд")
    RV.agreed(db, m)
    assert m.status == ST.WAIT_1C


# ── «Вернуть на переделку» из «Закрывающих документов» (владелец 12.11.2026): один комплект, не весь пакет ──────────

def test_redo_kit_resets_only_that_kit_and_brings_pack_to_1c(pack):
    """Поломка: переделка одного комплекта сбрасывает и соседние внесённые, или пакет остаётся на «выставлении» с
    комплектом без ответа 1С (бухгалтер его не увидит — очередь берёт пакеты от «ждём 1С»)."""
    db, m, user = pack
    from app.master_deal.models import MasterDealUpd
    kits = db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id).order_by(MasterDealUpd.upd_no).all()
    k = kits[0]
    RV.redo_kit(db, m, k, user, "в счёте не тот КПП")
    db.expire_all()
    assert m.status == ST.WAIT_1C
    assert (k.onec_state, k.onec_at, k.sign_state) == (None, None, None)
    assert all(x.onec_state == "внесён" for x in kits[1:])


def test_redo_kit_needs_reason_and_a_kit_in_1c(pack):
    db, m, user = pack
    from app.master_deal.models import MasterDealUpd
    k = db.query(MasterDealUpd).filter(MasterDealUpd.master_deal_id == m.id).first()
    with pytest.raises(RV.RevertError) as e:
        RV.redo_kit(db, m, k, user, " ")
    assert e.value.status == 400
    k.onec_state, k.onec_at = None, None
    db.flush()
    with pytest.raises(RV.RevertError) as e:
        RV.redo_kit(db, m, k, user, "причина")
    assert e.value.status == 409


def test_revert_retires_old_scans(pack):
    """Ревью 12.11.2026: скан старого документа после возврата засчитался бы подписью нового («Подписан клиентом» по скану
    того, что переделали). Скан остаётся в пакете историей, но к документу больше не привязан."""
    db, m, user = pack
    upd = db.execute(text("SELECT upd_no FROM master_deal_upds WHERE master_deal_id = :m ORDER BY upd_no LIMIT 1"), {"m": m.id}).scalar()
    db.execute(text("""INSERT INTO master_deal_files (master_deal_id, kind, filename, path, upd_no)
                       VALUES (:m, 'скан УПД', 'старый.pdf', 'master_files/test_old.pdf', :u)"""), {"m": m.id, "u": upd})
    db.flush()
    RV.revert(db, m, ST.WAIT_1C, user, "переделка")
    row = db.execute(text("SELECT kind, upd_no FROM master_deal_files WHERE master_deal_id = :m AND filename = 'старый.pdf'"), {"m": m.id}).one()
    assert tuple(row) == ("скан до возврата", None)
