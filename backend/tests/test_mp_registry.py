# -*- coding: utf-8 -*-
"""Реестр медиапланов v2 (хендофф 17.11.2026): этап, замок, виза, «кто обновил», «мой».

Что ловят тесты:

* замок разошёлся с сервером — экран пускал бы в правку, которую `PATCH` отклонит 409 (или наоборот прятал открытое);
* виза считается не так, как плашка «Требуется виза» на карточке сделки (владелец 17.11.2026: «как на карточке»);
* «МП подготовка» и «МП отправлено» слиплись — у обеих стадий ключ `media_plan`, различает их только место в цепочке;
* ручка реестра перестала отдавать новые поля, и экран молча показал пустые колонки.
"""
from types import SimpleNamespace as NS

from app.sales import mp_registry as R


def _st(id_, key, terminal=False):
    return NS(id=id_, stage_key=key, is_terminal=terminal)


FIRST = _st(1, "media_plan")


def test_bucket_tells_prep_from_sent_by_place_not_key():
    # Обе стадии с ключом media_plan: первая цепочки — «подготовка», вторая — «отправлено».
    assert R.bucket_of(FIRST, 1) == "prep"
    assert R.bucket_of(_st(3, "media_plan"), 1) == "sent"


def test_bucket_groups():
    assert R.bucket_of(None, 1) == "none"
    assert R.bucket_of(_st(5, "booking"), 1) == "booking"
    assert R.bucket_of(_st(6, "launch_prep"), 1) == "assembly"
    assert R.bucket_of(_st(8, "launch"), 1) == "launch"
    assert R.bucket_of(_st(10, "closing"), 1) == "closing"
    assert R.bucket_of(_st(15, "closing_fact"), 1) == "closing"
    # Терминальные — и успешный архив, и срывы — одна группа.
    assert R.bucket_of(_st(16, "archive", terminal=True), 1) == "done"
    assert R.bucket_of(_st(9, None, terminal=True), 1) == "done"


def test_lock_matches_server_rules():
    # Нет сделки или первая стадия — правится; ушла с первой — отдан клиенту; «Сборка» и дальше — зафиксирован.
    assert R.lock_of(None, 1, False) == ""
    assert R.lock_of(FIRST, 1, False) == ""
    assert R.lock_of(_st(3, "media_plan"), 1, False) == "sent"
    assert R.lock_of(_st(6, "launch_prep"), 1, True) == "fixed"
    # «Сделка не случилась» до «Сборки»: план отдан клиенту, но не зафиксирован.
    assert R.lock_of(_st(4, None, terminal=True), 1, False) == "sent"


def test_visa_as_on_deal_card():
    assert R.needs_visa(None, None) is True                       # без сделки, без визы
    assert R.needs_visa(None, _st(3, "media_plan")) is True
    assert R.needs_visa("2026-11-01", _st(3, "media_plan")) is False
    # Карточка прячет плашку у терминальной стадии (`our_stage.is_terminal`) — реестр тоже.
    assert R.needs_visa(None, _st(9, None, terminal=True)) is False


def test_origin_of_planless_journal():
    assert R._origin(12, None) == R.SYSTEM_YEAR
    assert R._origin(None, 40) == R.SYSTEM_PROLONG
    assert R._origin(None, None) is None


def test_registry_endpoint_returns_new_fields():
    """Живой прогон ручки на данных стенда: каждая строка несёт новые поля, и замок сходится с правилом сервера."""
    from app.database import SessionLocal
    from app.models import Role, User
    from app.routers.media_plans import _plan_is_sealed, list_media_plans
    from app.sales import plan_lock
    from app.sales.models import SalesMediaPlan
    import app.notify.models  # noqa: F401  — FK users → notification_profiles

    db = SessionLocal()
    try:
        admin = (db.query(User).join(Role).filter(Role.key == "admin", User.is_active == 1)
                 .order_by(User.id).first())
        out = list_media_plans(db=db, current_user=admin)
        keys = {b["key"] for b in out["buckets"]}
        assert out["own_only"] is False and out["can_edit_locked"] is True
        for it in out["items"][:120]:
            for k in ("stage_bucket", "stage_pos", "lock", "verified", "needs_visa", "updated_by", "mine",
                      "product_label", "surface"):
                assert k in it, k
            assert it["stage_bucket"] in keys
            p = db.get(SalesMediaPlan, it["id"])
            want = ("fixed" if plan_lock.deal_locks_plan(db, p.deal_id)
                    else "sent" if _plan_is_sealed(db, p) else "")
            assert it["lock"] == want, (it["id"], it["lock"], want)
    finally:
        db.close()
