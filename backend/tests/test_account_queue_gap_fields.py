# -*- coding: utf-8 -*-
"""Прибор: строка очереди аккаунта несёт каждое поле, по которому фильтрует «Незаполненные».

На дашборде аккаунта фильтр работает НА ФРОНТЕ, по строкам, уже пришедшим с сервера:
`!r[поле]`. Если поля в строке нет вовсе, оно `undefined` — то есть «пусто» у КАЖДОЙ
строки. 22.09.2026 в список меток (`GAP_FIELDS`, components/salesTableKit.js) добавили
«нет стадии» (`our_stage_id`), а очередь отдавала только `our_stage` — и фильтр «нет
стадии» показывал всю очередь (аудит 23.09.2026).

Список ниже — копия `GAP_FIELDS`: JS из контейнера бэкенда не прочитать. Новая метка на
фронте без строки здесь этот прибор не покрасит, поэтому рядом с `GAP_FIELDS` стоит
напоминание сюда же.
"""
from app.database import SessionLocal
from app.models import User
from app.routers.account_dashboard import account_queue

# = GAP_FIELDS в frontend/components/salesTableKit.js. `payer` фронт проверяет по
# `payer_counterparty_id` — так и записано.
GAP_KEYS = ("advertiser_id", "brand_id", "agency_id", "sales_rep_id", "account_manager_id",
            "period_from", "payer_counterparty_id", "our_stage_id")


def test_queue_rows_carry_every_gap_field():
    db = SessionLocal()
    db.commit = db.flush
    try:
        admin = db.query(User).filter(User.role.has(key="admin"), User.is_active == 1).first()
        if admin is None:
            import pytest
            pytest.skip("нужна учётка админа")
        res = account_queue(rep_id=None, all_reps=True, day=None, db=db, current_user=admin)
        rows = [r for g in res["groups"] for r in g["rows"]]
        if not rows:
            import pytest
            pytest.skip("очередь стенда пуста")
        missing = [k for k in GAP_KEYS if k not in rows[0]]
        assert not missing, "строке очереди не хватает полей фильтра: %s" % missing
        # И значение — то самое: id нашей стадии, а не её имя.
        with_stage = [r for r in rows if r.get("our_stage")]
        assert all(r["our_stage_id"] for r in with_stage)
    finally:
        db.rollback()
        db.close()


def test_queue_gross_is_the_same_rule_as_the_registry(monkeypatch):
    """Очередь «Что делать» считает сумму с НДС тем же правилом, что реестр и карточка
    (`mp_amounts.gross_of`). До ревью 23.09.2026 здесь стоял `eff_gross`: у старой сделки
    без плана и без суммы с НДС очередь показывала пусто, а реестр — досчитанную сумму."""
    import pytest
    from app.routers import account_dashboard as ad
    db = SessionLocal()
    db.commit = db.flush
    try:
        admin = db.query(User).filter(User.role.has(key="admin"), User.is_active == 1).first()
        if admin is None:
            pytest.skip("нужна учётка админа")
        monkeypatch.setattr(ad, "gross_of", lambda deal, mp: -123.0, raising=False)
        res = ad.account_queue(rep_id=None, all_reps=True, day=None, db=db, current_user=admin)
        rows = [r for g in res["groups"] for r in g["rows"]]
        if not rows:
            pytest.skip("очередь стенда пуста")
        assert all(r["amount_with_vat"] == -123.0 for r in rows)
    finally:
        db.rollback()
        db.close()
