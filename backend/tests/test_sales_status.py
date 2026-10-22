# -*- coding: utf-8 -*-
"""«Статусы продаж» (22.10.2026): чтение матрицы, заметки по бренду, ручная дата, перенос пина. Сделки стенда, транзакция
откатывается; запись — в той же сессии, без commit (ручки зовутся с подменённым commit)."""
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.routers import sales_status as R


@pytest.fixture
def db(monkeypatch):
    from app.database import SessionLocal
    s = SessionLocal()
    s.commit = s.flush                                  # ничего не уходит на стенд
    monkeypatch.setattr(R, "log_action", lambda *a, **k: None)
    monkeypatch.setattr(R, "own_rep_ids_or_all", lambda db, user, section="sales_registry": None)
    try:
        yield s
    finally:
        s.rollback()
        s.close()


U = SimpleNamespace(id=None, role=SimpleNamespace(key="admin"))


def test_shift_keeps_day_within_month():
    assert R._shift(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert R._shift(date(2026, 11, 1), -1) == date(2026, 10, 1)
    assert R._shift(date(2026, 12, 15), 2) == date(2027, 2, 15)


def test_matrix_reads_window(db):
    out = R.matrix("2026-10", "2026-12", db, U)
    assert all("2026-10" <= d["month"] <= "2026-12" for d in out["deals"])
    assert all(d["locked"] == (d["stage_key"] in R.LOCKED) for d in out["deals"])
    # все рекламодатели справочника — и без сделок в окне
    n = db.execute(text("SELECT count(*) FROM sales_advertisers WHERE is_active")).scalar()
    assert len(out["directory"]) == n
    with pytest.raises(HTTPException):
        R.matrix("2026-12", "2026-10", db, U)


def test_note_upsert_and_excel_mark(db):
    adv, brand = db.execute(text("SELECT advertiser_id, id FROM sales_brands WHERE advertiser_id IS NOT NULL LIMIT 1")).first()
    db.execute(text("INSERT INTO sales_status_notes (advertiser_id, brand_id, comment_sales, from_excel) "
                    "VALUES (:a, :b, 'из таблицы', ARRAY['comment_sales','meet_brand']) "
                    "ON CONFLICT DO NOTHING"), {"a": adv, "b": brand})
    n = R.save_note(R.NoteIn(advertiser_id=adv, brand_id=brand, field="comment_sales", value="новый"), db, U)
    assert n["comment_sales"] == "новый" and "comment_sales" not in n["from_excel"]
    n2 = R.save_note(R.NoteIn(advertiser_id=adv, brand_id=brand, field="meet_agency", value="предложена"), db, U)
    assert n2["id"] == n["id"]
    with pytest.raises(HTTPException):
        R.save_note(R.NoteIn(advertiser_id=adv, brand_id=brand, field="meet_brand", value="наверное"), db, U)


def test_move_refuses_launched_and_moves_planned(db):
    locked = db.execute(text("SELECT d.id FROM sales_deals d JOIN sales_stages s ON s.id = d.our_stage_id "
                             "WHERE s.stage_key = 'launch' AND d.period_from IS NOT NULL LIMIT 1")).scalar()
    free = db.execute(text("SELECT d.id FROM sales_deals d JOIN sales_stages s ON s.id = d.our_stage_id "
                           "WHERE s.stage_key IN ('media_plan','booking') AND d.period_from IS NOT NULL LIMIT 1")).scalar()
    if locked:
        with pytest.raises(HTTPException) as e:
            R.apply_moves(R.ApplyIn(moves=[R.MoveIn(deal_id=locked, month="2026-01", light="green")]), db, U)
        assert e.value.status_code == 409
    if free:
        from app.sales.models import SalesDeal
        d = db.get(SalesDeal, free)
        target = R._shift(d.period_from.replace(day=1), 1).strftime("%Y-%m")
        out = R.apply_moves(R.ApplyIn(moves=[R.MoveIn(deal_id=free, month=target, light="orange")]), db, U)
        assert out["saved"] and d.period_from.strftime("%Y-%m") == target and d.probability_color == "orange"


def test_manual_date(db):
    did = db.execute(text("SELECT id FROM sales_deals LIMIT 1")).scalar()
    assert R.set_status_date(did, R.DateIn(date=date(2026, 10, 5)), db, U)["status_date_manual"] == "2026-10-05"
    assert R.set_status_date(did, R.DateIn(date=None), db, U)["status_date_manual"] is None


def test_routes_need_rights():
    from app.main import app
    paths = {r.path: r for r in app.routes if getattr(r, "path", "").startswith("/api/sales-status")}
    assert set(paths) == {"/api/sales-status", "/api/sales-status/note", "/api/sales-status/deal/{deal_id}/date",
                          "/api/sales-status/apply"}


def test_month_end_stays_month_end():
    """Ревью 22.10: 01.11–30.11 на декабрь — 01.12–31.12, а не 30.12; туда-обратно январь не сжимается до 28-го."""
    assert R._shift_end(date(2026, 11, 30), 1) == date(2026, 12, 31)
    assert R._shift_end(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert R._shift_end(date(2026, 2, 28), -1) == date(2026, 1, 31)
    assert R._shift_end(date(2026, 11, 15), 1) == date(2026, 12, 15)      # не конец месяца — день сохраняется


def test_date_year_is_sane():
    """Ввод с клавиатуры даёт «0002-10-21» на первой цифре года — такая дата не принимается."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        R.DateIn(date=date(2, 10, 21))
    assert R.DateIn(date=date(2026, 10, 21)).date.year == 2026


def test_model_carries_the_checks():
    """Если таблицу создаст create_all раньше миграции, ограничения не должны потеряться (ревью 22.10)."""
    from app.sales.status_models import SalesStatusNote
    names = {c.name for c in SalesStatusNote.__table__.constraints}
    assert {"ck_sales_status_note_owner", "ck_sales_status_note_meet_brand", "ck_sales_status_note_meet_agency"} <= names


def test_apply_needs_registry_edit_too(db, monkeypatch):
    """Перенос меняет период и светофор сделки — то же, что правка реестра: без `sales_registry.edit` — 403."""
    monkeypatch.setattr(R, "_registry_edit", lambda db, user: False)
    with pytest.raises(HTTPException) as e:
        R.apply_moves(R.ApplyIn(moves=[R.MoveIn(deal_id=1, month="2026-10", light="green")]), db, U)
    assert e.value.status_code == 403


def test_amount_follows_media_plan_like_registry(db):
    """Сделка рождается с заявкой на МП и примерной суммой, потом сумму даёт медиаплан (владелец 22.10.2026):
    матрица показывает ту же сумму без НДС, что реестр — `mp_amounts.eff_net`."""
    from app.sales.mp_amounts import eff_net, mp_amounts_by_deal
    from app.sales.models import SalesDeal
    out = R.matrix("2026-10", "2026-12", db, U)
    ids = [d["id"] for d in out["deals"]]
    mp = mp_amounts_by_deal(db, ids)
    got = {d["id"]: d["amount"] for d in out["deals"]}
    diff = [i for i in ids if abs(got[i] - round(eff_net(db.get(SalesDeal, i), mp), 2)) > 0.01]
    assert not diff, f"сумма не как в реестре: {diff[:5]}"


def test_move_refuses_when_registry_changed_it_meanwhile(db, monkeypatch):
    """Перенос висел в панели, а светофор или период поменяли в реестре — «Сохранить» не затирает чужую правку: 409
    (вопрос владельца 22.10.2026 «где ещё мы можем конфликтовать с реестром»)."""
    monkeypatch.setattr(R, "_registry_edit", lambda db, user: True)
    free = db.execute(text("SELECT d.id FROM sales_deals d JOIN sales_stages s ON s.id = d.our_stage_id "
                           "WHERE s.stage_key IN ('media_plan','booking') AND d.period_from IS NOT NULL LIMIT 1")).scalar()
    if not free:
        pytest.skip("нет сделки до Брони")
    from app.sales.models import SalesDeal
    d = db.get(SalesDeal, free)
    now_month, now_light = d.period_from.strftime("%Y-%m"), d.probability_color
    stale = "green" if now_light != "green" else "grey"                 # экран видел другой светофор
    with pytest.raises(HTTPException) as e:
        R.apply_moves(R.ApplyIn(moves=[R.MoveIn(deal_id=free, month=now_month, light="orange",
                                                from_month=now_month, from_light=stale)]), db, U)
    assert e.value.status_code == 409 and "реестр" in e.value.detail
