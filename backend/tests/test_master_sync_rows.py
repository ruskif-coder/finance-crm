# -*- coding: utf-8 -*-
"""Черновой ДС пакета подтягивает строки из сделок (владелец 06.11.2026, письмо аккаунтов по XKKTAZ: дату МП поправили после
«Создать ДС», а ДС остался со старой). Пока ДС не подтверждён и не ушёл клиенту — даты, объём, цена и сумма строк приходят из
раскладки сами; правки текста в конструкторе остаются; комплекты УПД пересчитываются.

Поломки, которые ловит:
- правка МП после «Создать ДС» не доходит до ДС (снимок строк заморожен навсегда);
- обновление стирает правку текста, сделанную в конструкторе;
- обновляется подтверждённый ДС — документ с номером меняется задним числом.
Живой пакет стенда M-0018 (XKKTAZ, ДС-черновик), транзакция откатывается."""
import copy

import pytest

import app.model_registry  # noqa: F401


@pytest.fixture
def pkg():
    from app.database import SessionLocal
    from app.master_deal.models import MasterDeal
    from app.sales.models import SalesAnnex
    db = SessionLocal()
    m = db.query(MasterDeal).filter_by(code="M-0018").first()
    a = db.query(SalesAnnex).filter_by(master_deal_id=m.id).first() if m else None
    if m is None or a is None or a.no is not None or not a.rows:
        db.close()
        pytest.skip("нужен M-0018 с черновым ДС")
    rows = copy.deepcopy(a.rows)
    for r in rows:
        if r.get("date_from"):
            r["date_from"] = "2026-10-01"                  # как в снимке 04.11 — до правки МП
    a.rows = rows
    db.flush()
    try:
        yield db, m, a
    finally:
        db.rollback()
        db.close()


def test_draft_ds_takes_new_dates_and_keeps_text_edits(pkg):
    db, m, a = pkg
    from app.master_deal import sync_rows as SR
    edits = copy.deepcopy(a.blocks)
    changes = SR.sync(db, m)
    assert any("01.10.2026 → 02.10.2026" in c for c in changes), changes
    assert any(r.get("date_from") == "2026-10-02" for r in a.rows), "дата строки — из МП"
    assert a.blocks == edits, "правки текста в конструкторе не трогаем"
    assert SR.sync(db, m) == [], "второй раз менять нечего"


def test_confirmed_ds_is_not_touched(pkg):
    db, m, a = pkg
    from app.master_deal import sync_rows as SR
    a.no = 92
    db.flush()
    assert SR.sync(db, m) == []
    assert all(r.get("date_from") in (None, "2026-10-01") for r in a.rows)
