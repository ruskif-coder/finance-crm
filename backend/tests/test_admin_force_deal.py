# -*- coding: utf-8 -*-
"""Админ двигает сделку куда хочет и удаляет её со всей цепочкой (владелец 23.10.2026, пример 2T7US3).

· Перенос: админ с причиной проходит мимо ВСЕХ запретов стадий — срыв чужого этапа, воронка, услуга, требования; в
  карточке и массово в реестре. Без причины — отказ с просьбой её указать. Мастер (не админ) живёт по прежним правилам.
· Удаление: наша цепочка (медиаплан, РК без DSP, сборка, сверка, комментарии) стирается вместе со сделкой; след снаружи
  (РК или креатив в DSP, ЕРИД в ОРД, задача в кабинете площадки, мастер-сделка) — отказ с перечнем, ничего не удалено.
Тест строит свои сделки и убирает за собой всё, включая журнал; уведомления и сборка РК подменены."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.database import SessionLocal
from app.routers import sales_dashboard as sd


def _q(db, sql, **kw):
    return db.execute(text(sql), kw)


@pytest.fixture
def env(monkeypatch):
    from app.ad import build
    from app.models import Role, User
    from app.notify import closing as CN
    monkeypatch.setattr(sd, "_notify_move", lambda *a, **k: None)
    monkeypatch.setattr(build, "ensure_campaign_on_move", lambda *a, **k: None)
    monkeypatch.setattr(CN, "deal_on_recon", lambda *a, **k: None)
    db = SessionLocal()
    admin = db.query(User).join(Role, Role.id == User.role_id).filter(Role.key == "admin", User.is_active == 1).first()
    adv = _q(db, "SELECT id FROM sales_advertisers ORDER BY id LIMIT 1").scalar()
    if not admin or not adv:
        db.close()
        pytest.skip("на стенде нет админа или рекламодателя")
    made = []

    def new_deal(stage_key=None):
        out = sd.create_deal(sd.DealCreate(advertiser_id=adv, product="тест", pipeline="Песочница",
                                           bitrix_stage="МП Подготовка", period="2026-06", amount=1000.0,
                                           title="тест админ-обхода"), db, admin)
        made.append(out["id"])
        if stage_key:
            _q(db, "UPDATE sales_deals SET our_stage_id = (SELECT id FROM sales_stages WHERE stage_key = :k LIMIT 1), "
                   "realization_pipeline_id = NULL WHERE id = :i", k=stage_key, i=out["id"])
            db.commit()
        return out["id"]

    try:
        yield SimpleNamespace(db=db, admin=admin, new_deal=new_deal, made=made)
    finally:
        db.rollback()
        for i in made:
            _q(db, "DELETE FROM audit_log WHERE entity_type = 'sales_deal' AND entity_id = :i", i=i)
            _q(db, "DELETE FROM sales_media_plans WHERE deal_id = :i", i=i)
            _q(db, "DELETE FROM final_recon_deals WHERE deal_id = :i", i=i)
            _q(db, "DELETE FROM sales_deal_comments WHERE deal_id = :i", i=i)
            _q(db, "DELETE FROM sales_deals WHERE id = :i", i=i)
        _q(db, "DELETE FROM audit_log WHERE action = 'bulk_delete_deals' AND details LIKE '%тест админ-обхода%'")
        db.commit()
        db.close()


def _stage(db, key):
    return _q(db, "SELECT id FROM sales_stages WHERE stage_key = :k LIMIT 1", k=key).scalar()


def _lost_of_sandbox(db):
    return _q(db, """SELECT s.id FROM sales_stages s WHERE s.is_lost AND s.phase_id =
                       (SELECT phase_id FROM sales_stages WHERE stage_key = 'media_plan' LIMIT 1) LIMIT 1""").scalar()


# ───────────── перенос ─────────────

def test_admin_moves_from_documents_to_sandbox_lost_with_reason(env):
    d = env.new_deal("closing_fact")
    lost = _lost_of_sandbox(env.db)
    sd.move_deal(d, sd.MoveIn(to_stage_id=lost, comment="тест", override_reason="разбор хвоста"), env.db, env.admin)
    assert _q(env.db, "SELECT our_stage_id FROM sales_deals WHERE id = :i", i=d).scalar() == lost
    why = _q(env.db, "SELECT reason FROM sales_deal_stage_history WHERE deal_id = :i ORDER BY id DESC LIMIT 1", i=d).scalar()
    assert "принудительно" in why


def test_admin_moves_to_realization_without_pipeline(env):
    d = env.new_deal("closing_fact")
    booking = _q(env.db, """SELECT s.id FROM sales_stages s JOIN sales_stage_phases p ON p.id = s.phase_id
                             WHERE p.is_realization AND NOT s.is_terminal ORDER BY s.sort_order LIMIT 1""").scalar()
    sd.move_deal(d, sd.MoveIn(to_stage_id=booking, comment="тест", override_reason="вернуть в работу"), env.db, env.admin)
    assert _q(env.db, "SELECT our_stage_id FROM sales_deals WHERE id = :i", i=d).scalar() == booking


def test_admin_without_reason_is_asked_for_it(env):
    d = env.new_deal("closing_fact")
    with pytest.raises(HTTPException) as e:
        sd.move_deal(d, sd.MoveIn(to_stage_id=_lost_of_sandbox(env.db), comment="тест"), env.db, env.admin)
    assert e.value.status_code == 400 and "причин" in e.value.detail


def test_admin_bulk_moves_past_every_rule_with_reason(env):
    a, b = env.new_deal("closing_fact"), env.new_deal("closing_fact")
    lost = _lost_of_sandbox(env.db)
    out = sd.bulk_update_deals(sd.BulkUpdate(deal_ids=[a, b], our_stage_id=lost, override_reason="разбор"), env.db, env.admin)
    assert not out.get("skipped"), out
    assert {r[0] for r in _q(env.db, "SELECT our_stage_id FROM sales_deals WHERE id IN (:a, :b)", a=a, b=b)} == {lost}


# ───────────── удаление ─────────────

def _chain(db, d):
    """Наша цепочка без внешних следов: медиаплан со строкой, РК без DSP, комплект с файлом, цель площадки, сверка, комментарий."""
    plan = _q(db, "INSERT INTO sales_media_plans (deal_id, version, status) VALUES (:d, 1, 'draft') RETURNING id", d=d).scalar()
    _q(db, "INSERT INTO sales_media_plan_rows (plan_id, sort_order) VALUES (:p, 1)", p=plan)
    _q(db, "INSERT INTO ad_campaign (deal_id) VALUES (:d)", d=d)
    st = _q(db, "INSERT INTO launch_prep_creative_set (deal_id, no) VALUES (:d, 1) RETURNING id", d=d).scalar()
    _q(db, "INSERT INTO launch_prep_creative_file (set_id, path) VALUES (:s, 'creatives/__test_absent__.png')", s=st)
    _q(db, "INSERT INTO final_recon_deals (deal_id) VALUES (:d)", d=d)
    uid = _q(db, "SELECT id FROM users ORDER BY id LIMIT 1").scalar()
    _q(db, "INSERT INTO sales_deal_comments (deal_id, user_id, text) VALUES (:d, :u, 'тест')", d=d, u=uid)
    db.commit()
    return plan


def test_admin_deletes_deal_with_the_whole_internal_chain(env):
    d = env.new_deal()
    plan = _chain(env.db, d)
    sd.bulk_delete_deals(sd.BulkDelete(deal_ids=[d]), env.db, env.admin)
    left = {t: _q(env.db, f"SELECT count(*) FROM {t} WHERE deal_id = :d", d=d).scalar()
            for t in ("sales_media_plans", "ad_campaign", "launch_prep_creative_set", "final_recon_deals", "sales_deal_comments")}
    left["deal"] = _q(env.db, "SELECT count(*) FROM sales_deals WHERE id = :d", d=d).scalar()
    left["mp_rows"] = _q(env.db, "SELECT count(*) FROM sales_media_plan_rows WHERE plan_id = :p", p=plan).scalar()
    assert not any(left.values()), left


@pytest.mark.parametrize("trace,word", [
    ("UPDATE ad_campaign SET ms_campaign_xxhash = 'TESTHASH' WHERE deal_id = :d", "DSP"),
    ("UPDATE launch_prep_creative_set SET erid = 'TESTERID' WHERE deal_id = :d", "ОРД"),
])
def test_external_trace_blocks_deletion_and_nothing_is_removed(env, trace, word):
    d = env.new_deal()
    _chain(env.db, d)
    _q(env.db, trace, d=d)
    env.db.commit()
    with pytest.raises(HTTPException) as e:
        sd.bulk_delete_deals(sd.BulkDelete(deal_ids=[d]), env.db, env.admin)
    assert e.value.status_code == 409 and word in e.value.detail
    env.db.rollback()
    assert _q(env.db, "SELECT count(*) FROM sales_media_plans WHERE deal_id = :d", d=d).scalar() == 1
    _q(env.db, "DELETE FROM ad_campaign WHERE deal_id = :d", d=d)
    _q(env.db, "DELETE FROM launch_prep_creative_set WHERE deal_id = :d", d=d)
    env.db.commit()


def test_sent_pair_counts_as_cabinet_task(env):
    d = env.new_deal()
    _chain(env.db, d)
    pub, svc = _q(env.db, "SELECT (SELECT id FROM sales_publishers ORDER BY id LIMIT 1), (SELECT id FROM sales_services ORDER BY id LIMIT 1)").one()
    tg = _q(env.db, "INSERT INTO launch_prep_target (deal_id, publisher_id, service_id, surface_kind) VALUES (:d, :p, :s, 'web') RETURNING id",
            d=d, p=pub, s=svc).scalar()
    st = _q(env.db, "SELECT id FROM launch_prep_creative_set WHERE deal_id = :d", d=d).scalar()
    _q(env.db, "INSERT INTO launch_prep_pair (set_id, target_id, sent_at) VALUES (:s, :t, now())", s=st, t=tg)
    env.db.commit()
    with pytest.raises(HTTPException) as e:
        sd.bulk_delete_deals(sd.BulkDelete(deal_ids=[d]), env.db, env.admin)
    assert e.value.status_code == 409 and "кабинет" in e.value.detail
    env.db.rollback()
    for t in ("launch_prep_target", "launch_prep_creative_set", "ad_campaign"):
        _q(env.db, f"DELETE FROM {t} WHERE deal_id = :d", d=d)
    env.db.commit()


def test_deal_with_an_annex_is_not_deleted(env):
    """Ревью 23.10: ДС (приложение) — документ, который уже у клиента; удаление сделки оставило бы его без сделки."""
    d = env.new_deal()
    annex = _q(env.db, "SELECT id FROM sales_annexes ORDER BY id LIMIT 1").scalar()
    if not annex:
        pytest.skip("на стенде нет ДС")
    _q(env.db, "INSERT INTO sales_deal_annex_allocation (deal_id, annex_id, amount) VALUES (:d, :a, 1)", d=d, a=annex)
    env.db.commit()
    with pytest.raises(HTTPException) as e:
        sd.bulk_delete_deals(sd.BulkDelete(deal_ids=[d]), env.db, env.admin)
    assert e.value.status_code == 409 and "ДС" in e.value.detail
    env.db.rollback()
    _q(env.db, "DELETE FROM sales_deal_annex_allocation WHERE deal_id = :d", d=d)
    env.db.commit()
