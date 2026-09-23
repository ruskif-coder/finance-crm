# -*- coding: utf-8 -*-
"""Прибор: ставка НДС медиаплана фиксируется на дату расчёта (правило владельца 23.09.2026).

До 2026 года ставка была 20 %, с 2026 — 22 %; пересчёт уже посчитанного по новой ставке
недопустим. План ставку не хранил: «с НДС» считалось по зашитым 22 % при каждом сохранении.

Держим:
  · новая версия берёт ТЕКУЩУЮ ставку нашего юрлица;
  · пересохранение версии ставку не трогает, даже если в карточке юрлица она уже другая;
  · выгрузка плана считает НДС по ставке плана, а не по константе.
"""
import pytest

import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.notify.models       # noqa: F401
import app.ord.models          # noqa: F401
from app import own_company
from app.database import SessionLocal
from app.models import User
from app.routers import media_plans as mp
from app.sales import mp_row
from app.sales.models import SalesMediaPlan


@pytest.fixture
def db():
    s = SessionLocal()
    s.commit = s.flush
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def admin(db, monkeypatch):
    monkeypatch.setattr(mp, "_guard_owned", lambda *a, **k: None)
    u = db.query(User).filter(User.is_active == 1, User.role.has(key="admin")).first()
    if u is None:
        pytest.skip("нужна учётка админа")
    return u


@pytest.fixture
def us(db):
    cp = own_company.sole(db)
    if cp is None:
        pytest.skip("на стенде нет нашего юрлица")
    return cp


def _form(volume=1_000_000, group_id=None, date_from=None):
    return mp.MpIn(group_id=group_id, deal_id=None, title="прибор НДС", date_from=date_from,
                   rows=[mp.MpRowIn(position="прибор", model="CPM", inventory="web",
                                    volume=volume, unit_price=500, discount=0)],
                   extras=[])


def _plan(db, res):
    return db.query(SalesMediaPlan).filter(SalesMediaPlan.id == res["id"]).first()


def test_new_plan_takes_the_current_rate(db, admin, us):
    # 25, а не 22: зашитые 22 % прошли бы проверку «ставка = 22» и при сломанном коде
    # (ревью 23.09.2026 — так этот тест и был написан).
    us.vat_rate_income = 25
    db.flush()
    p = _plan(db, mp.save_media_plan(_form(), db=db, current_user=admin))
    assert float(p.vat_rate) == 25
    assert p.amount_gross == mp_row.rub(500_000 * 1.25)


def test_new_version_after_a_dates_only_edit_keeps_the_rate(db, admin, us, monkeypatch):
    """План отдан клиенту — правка рождает новую версию. Если правили только даты, это не
    новый расчёт: ставка и сумма остаются прежними, даже если текущая ставка другая."""
    from datetime import date
    us.vat_rate_income = 22
    db.flush()
    p = _plan(db, mp.save_media_plan(_form(), db=db, current_user=admin))
    p.vat_rate, p.amount_gross = 20, mp_row.rub(500_000 * 1.20)     # посчитан до 2026
    db.flush()
    monkeypatch.setattr(mp, "_plan_is_sealed", lambda *a, **k: True)
    p2 = _plan(db, mp.save_media_plan(_form(group_id=p.group_id, date_from=date(2026, 10, 5)),
                                      db=db, current_user=admin))
    assert p2.id != p.id                                  # правда новая версия
    assert float(p2.vat_rate) == 20
    assert p2.amount_gross == mp_row.rub(500_000 * 1.20)


def test_new_version_with_new_money_takes_the_current_rate(db, admin, us, monkeypatch):
    us.vat_rate_income = 22
    db.flush()
    p = _plan(db, mp.save_media_plan(_form(), db=db, current_user=admin))
    p.vat_rate = 20
    db.flush()
    monkeypatch.setattr(mp, "_plan_is_sealed", lambda *a, **k: True)
    p2 = _plan(db, mp.save_media_plan(_form(volume=2_000_000, group_id=p.group_id),
                                      db=db, current_user=admin))
    assert p2.id != p.id and float(p2.vat_rate) == 22


def test_resaving_keeps_the_rate_it_was_calculated_with(db, admin, us):
    us.vat_rate_income = 22
    db.flush()
    p = _plan(db, mp.save_media_plan(_form(), db=db, current_user=admin))
    p.vat_rate = 20                      # план, посчитанный до 2026 года
    db.flush()
    us.vat_rate_income = 25              # ставку в карточке юрлица сменили
    db.flush()
    p2 = _plan(db, mp.save_media_plan(_form(volume=2_000_000, group_id=p.group_id),
                                      db=db, current_user=admin))
    assert p2.id == p.id and float(p2.vat_rate) == 20
    assert p2.amount_gross == mp_row.rub(1_000_000 * 1.20)


def test_plan_card_and_export_use_the_plan_rate(db, admin, us):
    p = _plan(db, mp.save_media_plan(_form(), db=db, current_user=admin))
    p.vat_rate = 20
    db.flush()
    full = mp._plan_full(db, p, mp._names(db))
    assert float(full["vat_rate"]) == 20
    ctx = mp._row_ctx(full["rows"][0], full)
    assert ctx["r.vat"] == mp_row.rub(500_000 * 0.20)


# ── Ставка по закону и карточка сделки ───────────────────────────────────────────

def test_law_rate_by_date():
    from datetime import date

    from app import vat
    assert vat.on(date(2025, 12, 31)) == 20
    assert vat.on(date(2026, 1, 1)) == 22


def test_old_deal_without_a_plan_is_shown_at_its_own_rate():
    """Сделка 2025 года без плана и без суммы с НДС показывается по 20 %, а не по 22 %."""
    from datetime import date
    from types import SimpleNamespace

    from app.sales.mp_amounts import vat_pct_of
    old = SimpleNamespace(id=1, amount=100.0, amount_with_vat=None,
                          period_from=date(2025, 11, 1), date_create=None)
    assert vat_pct_of(old, {}) == 20
    stored = SimpleNamespace(id=2, amount=100.0, amount_with_vat=120.0,
                             period_from=date(2026, 3, 1), date_create=None)
    assert vat_pct_of(stored, {}) == 20              # посчитанное — по своей ставке
    assert vat_pct_of(stored, {2: (100.0, 122.0)}) == 22   # план сделки главнее


# ── Ставка, выведенная из сумм, приводится к законной ─────────────────────────────

def test_rate_from_rounded_sums_snaps_to_the_law_rate():
    from app import vat
    assert vat.snap(21.98) == 22 and vat.snap(20.3) == 20
    assert vat.snap(17.0) is None and vat.snap(0.0) is None


def test_deal_rate_is_never_an_approximation():
    """Сделка на 100 / 121,98: показывается по 22 %, а не по 21,98 %. Сумма с НДС, введённая
    с ошибкой (117 на 100), не рождает ставку 17 % — берётся закон на период."""
    from datetime import date
    from types import SimpleNamespace

    from app.sales.mp_amounts import vat_pct_of
    d = SimpleNamespace(id=3, amount=100.0, amount_with_vat=121.98,
                        period_from=date(2026, 3, 1), date_create=None)
    assert vat_pct_of(d, {}) == 22
    assert vat_pct_of(d, {3: (100.0, 117.0)}) == 22       # план с кривой суммой — мимо
    bad = SimpleNamespace(id=4, amount=100.0, amount_with_vat=117.0,
                          period_from=date(2025, 6, 1), date_create=None)
    assert vat_pct_of(bad, {}) == 20


def test_backfill_snaps_like_the_code(db):
    """Миграция заполнения приводит ставку так же, как `vat.snap`: прогон её UPDATE на
    своих строках внутри транзакции теста."""
    from datetime import datetime
    from pathlib import Path

    from sqlalchemy import text
    rows = {"a": (100.0, 121.98, datetime(2026, 2, 1)), "b": (100.0, 120.3, datetime(2025, 5, 1)),
            "c": (100.0, 117.0, datetime(2025, 5, 1)), "d": (100.0, 117.0, datetime(2026, 5, 1))}
    ids = {}
    for k, (net, gross, created) in rows.items():
        ids[k] = db.execute(text(
            "INSERT INTO sales_media_plans (title, version, status, amount_net, amount_gross, created_at) "
            "VALUES (:t, 1, 'draft', :n, :g, :c) RETURNING id"),
            {"t": f"прибор ставки {k}", "n": net, "g": gross, "c": created}).scalar()
    sql = Path(__file__).resolve().parents[1].joinpath(
        "migrations", "2026-09-23_media_plan_vat_rate.sql").read_text(encoding="utf-8")
    update = sql[sql.index("UPDATE sales_media_plans m"):]
    db.execute(text(update))
    got = {k: float(db.execute(text("SELECT vat_rate FROM sales_media_plans WHERE id=:i"),
                               {"i": i}).scalar()) for k, i in ids.items()}
    assert got == {"a": 22, "b": 20, "c": 20, "d": 22}


# ── Сумма с НДС сделки — одно правило для карточки и реестра (ревью 23.09.2026) ──────────

def test_gross_of_a_deal_follows_its_own_rate():
    """Реестр не отдавал сумму с НДС вовсе, и доска досчитывала её по зашитым 22 %.
    Теперь и карточка, и реестр берут её из `mp_amounts.gross_of`."""
    from datetime import date
    from types import SimpleNamespace

    from app.sales.mp_amounts import gross_of
    old = SimpleNamespace(id=1, amount=100.0, amount_with_vat=None,
                          period_from=date(2025, 11, 1), date_create=None)
    assert gross_of(old, {}) == 120.0                     # 2025 год — 20 %, а не 22
    stored = SimpleNamespace(id=2, amount=100.0, amount_with_vat=121.0,
                             period_from=date(2026, 3, 1), date_create=None)
    assert gross_of(stored, {}) == 121.0                  # посчитанное не трогаем
    empty = SimpleNamespace(id=3, amount=None, amount_with_vat=None,
                            period_from=None, date_create=None)
    assert gross_of(empty, {}) is None


def test_registry_rows_carry_gross_and_rate(db, admin):
    from app.routers import sales_dashboard as sd
    res = sd.deals_registry(limit=5, offset=0, db=db, current_user=admin)
    rows = res["items"]
    if not rows:
        pytest.skip("реестр сделок пуст")
    assert all("amount_with_vat" in r and "vat_rate" in r for r in rows)


def test_front_gets_the_rate_from_the_server(db, admin, us):
    """Фронт не держит своей ставки: новая сделка — `vat_current` юрлица, бриф бренда —
    ставка года из ответа годового плана."""
    from app import own_company
    from app.routers import year_plan as yp
    us.vat_rate_income = 25
    db.flush()
    assert own_company.public(db)["vat_current"] == 25
    assert yp.get_year_plan(year=2025, rep_id=None, db=db, current_user=admin)["vat_rate"] == 20
    assert yp.get_year_plan(year=2026, rep_id=None, db=db, current_user=admin)["vat_rate"] == 25


def test_excel_names_the_plan_rate_not_22(db, admin, us):
    """Шаблон и запасная книга подписывали колонку «НДС 22%» при любой ставке: план 2025
    года уходил клиенту с суммой по 20 % под заголовком 22 % (ревью 23.09.2026)."""
    import os
    p = _plan(db, mp.save_media_plan(_form(), db=db, current_user=admin))
    p.vat_rate = 20
    db.flush()
    full = mp._plan_full(db, p, mp._names(db))

    def labels(wb):
        return {c.value for ws in wb for row in ws.iter_rows() for c in row
                if isinstance(c.value, str) and c.value.startswith("НДС ")}
    got = labels(mp._render_from_template(full, p, os.path.abspath(mp.TEMPLATE_PATH)))
    assert "НДС 20%" in got and "НДС 22%" not in got, got
    got = labels(mp._wb_programmatic(full, p))
    assert "НДС 20%" in got and "НДС 22%" not in got, got
