# -*- coding: utf-8 -*-
"""Черновой ДС пакета подтягивает строки из сделок (владелец 06.11.2026, письмо аккаунтов по XKKTAZ: дату МП поправили после
«Создать ДС», а ДС остался со старой). Пока ДС не подтверждён и не ушёл клиенту — даты, объём, цена и сумма строк приходят из
раскладки сами; правки текста в конструкторе остаются; комплекты УПД пересчитываются.

Поломки, которые ловит:
- правка МП после «Создать ДС» не доходит до ДС (снимок строк заморожен навсегда);
- обновление стирает правку текста, сделанную в конструкторе;
- обновляется подтверждённый ДС — документ с номером меняется задним числом.
Пакет стенда «согласование» с черновым ДС, который уже в ногу со сделками; транзакция откатывается.
До 15.11.2026 тест брал живой M-0018 и всегда пропускался: на копии прода у M-0018 ДС уже подтверждён."""
import copy

import pytest

import app.model_registry  # noqa: F401

FAKE_DATE = "2020-01-01"            # дата «до правки МП» — заведомо не та, что в раскладке


def _fmt(iso):
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}"


@pytest.fixture
def pkg():
    from sqlalchemy import text
    from app.database import SessionLocal
    from app.master_deal import sync_rows as SR
    from app.master_deal.models import MasterDeal
    from app.sales.models import SalesAnnex
    db = SessionLocal()
    ids = [i for (i,) in db.execute(text("""
        SELECT DISTINCT m.id FROM master_deals m JOIN sales_annexes a ON a.master_deal_id = m.id
         WHERE m.status = 'согласование' AND a.no IS NULL ORDER BY m.id"""))]
    found = None
    for mid in ids:
        m = db.get(MasterDeal, mid)
        if SR.sync(db, m) != []:                     # черновик отстал от сделок — исходное состояние не чистое
            db.rollback()
            continue
        for a in db.query(SalesAnnex).filter_by(master_deal_id=m.id, no=None).order_by(SalesAnnex.id):
            row = next((i for i, r in enumerate(a.rows or []) if r.get("date_from")), None)
            if row is not None:
                found = (m, a, row)
                break
        if found:
            break
    if not found:
        db.close()
        pytest.skip("на стенде нет пакета «согласование» с черновым ДС в ногу со сделками")
    m, a, i = found
    rows = copy.deepcopy(a.rows)
    orig = str(rows[i]["date_from"])[:10]
    rows[i]["date_from"] = FAKE_DATE                 # как будто МП поправили после «Создать ДС»
    a.rows = rows
    db.flush()
    try:
        yield db, m, a, orig
    finally:
        db.rollback()
        db.close()


def test_draft_ds_takes_new_dates_and_keeps_text_edits(pkg):
    db, m, a, orig = pkg
    from app.master_deal import sync_rows as SR
    edits = copy.deepcopy(a.blocks)
    changes = SR.sync(db, m)
    assert any(f"{_fmt(FAKE_DATE)} → {_fmt(orig)}" in c for c in changes), changes
    assert not any(str(r.get("date_from"))[:10] == FAKE_DATE for r in a.rows), "дата строки — из МП"
    assert a.blocks == edits, "правки текста в конструкторе не трогаем"
    assert SR.sync(db, m) == [], "второй раз менять нечего"


def test_confirmed_ds_is_not_touched(pkg):
    db, m, a, _orig = pkg
    from app.master_deal import sync_rows as SR
    a.no = 92
    db.flush()
    assert SR.sync(db, m) == []
    assert any(str(r.get("date_from"))[:10] == FAKE_DATE for r in a.rows), "подтверждённый ДС не меняется задним числом"
