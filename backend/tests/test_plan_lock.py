# -*- coding: utf-8 -*-
"""Прибор: медиаплан фиксируется на «Сборке» — правятся только даты запуска.

Решение владельца 23.09.2026. После перевода сделки в «Сборку» («Готовятся к старту»)
план сделки больше не правится, кроме дат запуска; мастер править может, с записью в
журнал; при переводе человек видит уведомление ДО нажатия.

До этого решения любое сохранение плана возило сумму в сделку на ЛЮБОЙ стадии — в том
числе в сделку с подписанным приложением к договору (аудит 23.09.2026, 3.H4).

Все проверки — на живой базе стенда в транзакции с откатом: ручки вызываются напрямую,
в обход FastAPI, поэтому проверяется их собственный код, а не только маршрутизация.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.ord.models          # noqa: F401  — FK сделки на договоры ОРД
from app.database import SessionLocal
from app.models import AuditLog, User
from app.routers import media_plans as mp
from app.sales import plan_lock
from app.sales.catalog import Catalog
from app.sales.models import SalesDeal, SalesMediaPlan, SalesMediaPlanExtra, SalesMediaPlanRow


@pytest.fixture
def db():
    s = SessionLocal()
    # Коммиты ручек превращаются в flush: всё, что тест записал, откатывается в конце.
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def cat(db):
    return Catalog(db)


def _stage(cat, key=None, name=None):
    for s in cat.stages:
        if (key and s.stage_key == key) or (name and s.name == name):
            return s
    pytest.skip(f"в каталоге нет стадии {key or name}")


@pytest.fixture
def master(db):
    u = (db.query(User).filter(User.is_active == 1, User.role.has(key="admin"))
         .order_by(User.id).first())
    if u is None:
        pytest.skip("нужна учётка админа")
    return u


@pytest.fixture
def plain(master):
    """Не-мастер. Свою роль собираем из админа, но без признаков мастера: так проверка
    области видимости плана не мешает — её здесь не проверяем, её держит `_guard_owned`."""
    return SimpleNamespace(id=master.id, name="прибор фиксации", email=master.email,
                           role=SimpleNamespace(key="manager", is_master=False),
                           role_id=None)


@pytest.fixture(autouse=True)
def _no_own_scope(monkeypatch):
    # Область видимости здесь не проверяется — её держат `_guard_owned` (план) и
    # `_assert_deal_in_scope` (сделка, прибор test_mp_deal_scope.py). Обе — «видно всё».
    from app.routers import sales_dashboard as sd
    monkeypatch.setattr(mp, "_guard_owned", lambda *a, **k: None)
    monkeypatch.setattr(sd, "_own_rep_ids_or_all", lambda *a, **k: None)


@pytest.fixture
def locked_plan(db, cat):
    """План, привязанный к сделке, — сделка переведена на «Сборку» (в транзакции)."""
    p = (db.query(SalesMediaPlan).filter(SalesMediaPlan.deal_id.isnot(None))
         .order_by(SalesMediaPlan.id.desc()).first())
    if p is None:
        pytest.skip("нужен медиаплан, привязанный к сделке")
    p = (db.query(SalesMediaPlan).filter(SalesMediaPlan.group_id == p.group_id)
         .order_by(SalesMediaPlan.version.desc()).first())
    deal = db.query(SalesDeal).filter(SalesDeal.id == p.deal_id).first()
    deal.our_stage_id = _stage(cat, key=plan_lock.LOCK_STAGE_KEY).id
    db.flush()
    return p


def _payload(db, p, **over):
    """Форма конструктора ровно с тем, что лежит в плане, — плюс правки из `over`."""
    rows = (db.query(SalesMediaPlanRow).filter(SalesMediaPlanRow.plan_id == p.id)
            .order_by(SalesMediaPlanRow.sort_order).all())
    extras = (db.query(SalesMediaPlanExtra).filter(SalesMediaPlanExtra.plan_id == p.id)
              .order_by(SalesMediaPlanExtra.sort_order).all())
    head = {f: getattr(p, f) for f in (
        "title", "advertiser_id", "brand_id", "agency_id", "payer_counterparty_id", "period",
        "geo_id", "date_from", "date_to", "targeting", "goals", "sales_rep_id",
        "account_manager_id", "traffic_manager_id")}
    rows_in = [mp.MpRowIn(position=r.position, format=r.format, model=r.model,
                          inventory=r.inventory, volume=r.volume, unit_price=r.unit_price,
                          discount=r.discount, forecast=r.forecast) for r in rows]
    extras_in = [mp.MpExtraIn(name=e.name, period=e.period, mode=e.mode, price=e.price,
                              total=e.total) for e in extras]
    rows_fn = over.pop("rows_fn", None)
    if rows_fn:
        rows_in = rows_fn(rows_in)
    head.update(over)
    return mp.MpIn(group_id=p.group_id, deal_id=p.deal_id, rows=rows_in, extras=extras_in, **head)


# ── Граница ──────────────────────────────────────────────────────────────────────

def test_lock_starts_at_assembly(cat):
    """Всё до «Сборки» открыто, «Сборка» и дальше — зафиксировано."""
    lock = _stage(cat, key=plan_lock.LOCK_STAGE_KEY)
    booking = _stage(cat, key="booking")
    assert not plan_lock.stage_locks_plan(cat, booking.id)
    assert plan_lock.stage_locks_plan(cat, lock.id)
    for s in cat.stages:
        if cat.stages.index(s) > cat.stages.index(lock):
            assert plan_lock.stage_locks_plan(cat, s.id), s.name


def test_lost_in_sandbox_is_open_lost_after_booking_is_locked(cat):
    """«Не случилась» — до «Сборки», план открыт; «сорвалась» — после, зафиксирован."""
    lock_pos = plan_lock.lock_position(cat)
    for s in cat.stages:
        if s.is_lost:
            assert plan_lock.stage_locks_plan(cat, s.id) == (cat.stages.index(s) > lock_pos), s.name


def test_move_from_booking_to_assembly_crosses_the_lock(cat):
    booking, lock = _stage(cat, key="booking"), _stage(cat, key=plan_lock.LOCK_STAGE_KEY)
    assert plan_lock.crosses_lock(cat, booking.id, lock.id)
    assert not plan_lock.crosses_lock(cat, lock.id, cat.next_of(lock.id).id)
    assert not plan_lock.crosses_lock(cat, cat.first().id, booking.id)


# ── Запись ───────────────────────────────────────────────────────────────────────

def test_plain_user_cannot_change_rows_of_a_locked_plan(db, locked_plan, plain):
    def bump(rows):
        if not rows:
            pytest.skip("в плане нет строк")
        rows[0].volume = (rows[0].volume or 0) + 1000
        return rows
    with pytest.raises(HTTPException) as e:
        mp.save_media_plan(_payload(db, locked_plan, rows_fn=bump), db=db, current_user=plain)
    assert e.value.status_code == 409
    assert "дат" in e.value.detail


def _refused_by_lock(e):
    """Отказ именно ФИКСАЦИИ, а не соседнего правила. Код 409 даёт и правило «версия
    отдана клиенту» (3.M7): сделка на «Сборке» уже ушла с первой стадии, и без проверки
    текста тест оставался зелёным при выключенной фиксации (ревью 23.09.2026)."""
    assert e.value.status_code == 409
    assert "зафиксирован" in str(e.value.detail), e.value.detail


def test_plain_user_cannot_change_the_header_of_a_locked_plan(db, locked_plan, plain):
    with pytest.raises(HTTPException) as e:
        mp.save_media_plan(_payload(db, locked_plan, title=(locked_plan.title or "") + " ✎"),
                           db=db, current_user=plain)
    _refused_by_lock(e)


def test_launch_dates_stay_open(db, locked_plan, plain):
    from datetime import date
    res = mp.save_media_plan(_payload(db, locked_plan, date_from=date(2099, 1, 5),
                                      date_to=date(2099, 1, 25)),
                             db=db, current_user=plain)
    fresh = db.query(SalesMediaPlan).filter(SalesMediaPlan.id == res["id"]).first()
    assert (fresh.date_from, fresh.date_to) == (date(2099, 1, 5), date(2099, 1, 25))


def test_master_may_edit_a_locked_plan_and_it_is_journaled(db, locked_plan, master):
    before = db.query(AuditLog).filter(AuditLog.action == "media_plan_locked_edit").count()
    mp.save_media_plan(_payload(db, locked_plan, title=(locked_plan.title or "") + " ✎"),
                       db=db, current_user=master)
    after = db.query(AuditLog).filter(AuditLog.action == "media_plan_locked_edit").count()
    assert after == before + 1


def test_registry_inline_edit_is_locked(db, locked_plan, plain):
    with pytest.raises(HTTPException) as e:
        mp.patch_media_plan(locked_plan.id, mp.MpPatch(title="✎"), db=db, current_user=plain)
    _refused_by_lock(e)


def test_new_plan_for_a_locked_deal_is_refused(db, locked_plan, plain):
    data = _payload(db, locked_plan)
    data.group_id = None
    with pytest.raises(HTTPException) as e:
        mp.save_media_plan(data, db=db, current_user=plain)
    _refused_by_lock(e)


def test_linking_another_plan_to_a_locked_deal_is_refused(db, locked_plan, plain):
    other = (db.query(SalesMediaPlan).filter(SalesMediaPlan.group_id != locked_plan.group_id)
             .order_by(SalesMediaPlan.id.desc()).first())
    if other is None:
        pytest.skip("нужен второй медиаплан")
    other.deal_id = None        # 409 должен прийти от фиксации ЦЕЛЕВОЙ сделки, а не своей
    db.flush()
    with pytest.raises(HTTPException) as e:
        mp.link_deal(other.id, mp.LinkDealIn(deal_id=locked_plan.deal_id), db=db,
                     current_user=plain)
    _refused_by_lock(e)


def test_deleting_a_locked_plan_is_refused(db, locked_plan, plain):
    with pytest.raises(HTTPException) as e:
        mp.delete_media_plan(locked_plan.id, whole_group=False, db=db, current_user=plain)
    _refused_by_lock(e)


def test_constructor_is_told_the_plan_is_locked(db, locked_plan, plain):
    got = mp.get_media_plan(locked_plan.id, db=db, current_user=plain)
    assert got["locked"] is True
    assert got["can_edit_locked"] is False


# ── Уведомление при переводе ─────────────────────────────────────────────────────

def test_move_preview_warns_when_the_move_fixes_the_plan(db, cat, master):
    from app.routers.sales_dashboard import move_preview
    booking, lock = _stage(cat, key="booking"), _stage(cat, key=plan_lock.LOCK_STAGE_KEY)
    deal = db.query(SalesDeal).filter(SalesDeal.our_stage_id == booking.id).first()
    if deal is None:
        deal = db.query(SalesDeal).first()
        deal.our_stage_id = booking.id
        db.flush()
    got = move_preview(str(deal.id), to_stage_id=lock.id, realization_pipeline_id=None,
                       db=db, current_user=master)
    assert got["plan_lock_notice"] == plan_lock.NOTICE


def test_move_preview_is_silent_elsewhere(db, cat, master):
    from app.routers.sales_dashboard import move_preview
    booking = _stage(cat, key="booking")
    deal = db.query(SalesDeal).first()
    deal.our_stage_id = cat.first().id
    db.flush()
    got = move_preview(str(deal.id), to_stage_id=booking.id, realization_pipeline_id=None,
                       db=db, current_user=master)
    assert not got.get("plan_lock_notice")


def test_registry_stage_options_mark_the_locking_stages(db, cat, master):
    """Массовая смена стадии в реестре предупреждает по признаку с сервера — проверяем
    сам признак: стоит ровно у тех стадий, что фиксируют план, и текст приходит рядом."""
    from app.routers.sales_dashboard import filter_options
    got = filter_options(db=db, current_user=master)
    flagged = {o["value"] for o in got["our_stage_id"] if o.get("locks_plan")}
    expected = {s.id for s in cat.stages if plan_lock.stage_locks_plan(cat, s.id)}
    assert flagged == expected and flagged
    assert got["plan_lock_notice"] == plan_lock.NOTICE


def test_registry_edit_of_a_version_given_to_the_client_is_refused(db, cat, plain):
    """Версия, отданная клиенту («МП Отправлено»), из реестра на месте не правится (3.M7):
    конструктор в этом случае рождает новую версию, а реестр переписывал то, что клиент
    уже видел."""
    p = (db.query(SalesMediaPlan).filter(SalesMediaPlan.deal_id.isnot(None))
         .order_by(SalesMediaPlan.id.desc()).first())
    if p is None:
        pytest.skip("нужен медиаплан, привязанный к сделке")
    deal = db.query(SalesDeal).filter(SalesDeal.id == p.deal_id).first()
    deal.our_stage_id = cat.next_of(cat.first().id).id      # «МП Отправлено» — не первая
    db.flush()
    assert not plan_lock.stage_locks_plan(cat, deal.our_stage_id)
    with pytest.raises(HTTPException) as e:
        mp.patch_media_plan(p.id, mp.MpPatch(title="✎"), db=db, current_user=plain)
    assert e.value.status_code == 409 and "верси" in e.value.detail


def test_relinking_to_the_same_locked_deal_is_a_no_op(db, locked_plan, plain):
    """Привязка к ТОЙ ЖЕ сделке ничего не меняет — отказ «зафиксирован» тут лишний
    (ревью 23.09.2026). Ответ «уже привязан», и ничего не пишется."""
    got = mp.link_deal(locked_plan.id, mp.LinkDealIn(deal_id=locked_plan.deal_id), db=db,
                       current_user=plain)
    assert got["deal_id"] == locked_plan.deal_id and got.get("unchanged") is True
