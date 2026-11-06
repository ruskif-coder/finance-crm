# -*- coding: utf-8 -*-
"""Паблишеры → Взаимодействия (владелец 06.11.2026).

Отзыв сверки «на корявые пальцы»: сверка стирается целиком (переписка, файлы), строка снова «готово» — отправляется
исправленная; согласованную отозвать нельзя — под неё уже посчитана разаллокация. Площадке — «сверка отозвана».
Выгрузка месяца в Excel: первая вкладка — сводная, дальше каждая площадка на своей вкладке с кампаниями.
Записей на стенд нет: всё в откатываемой транзакции."""
from io import BytesIO
from types import SimpleNamespace

import openpyxl
import pytest
from sqlalchemy import text

import app.model_registry  # noqa: F401
from app.notify import recon as N
from app.publisher_recon import board as B
from app.publisher_recon import export as E
from app.publisher_recon import service as S
from app.publisher_requests import PublisherRecon, PublisherRequest, PublisherRequestMessage

USER = SimpleNamespace(id=None, name="Менеджер", email="m@example.com")


@pytest.fixture
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def _req(db, verdict=None):
    pid = db.execute(text("SELECT id FROM sales_publishers ORDER BY id LIMIT 1")).scalar()
    r = PublisherRequest(kind="сверка", publisher_id=pid, period="2031-01", verdict=verdict)
    db.add(r)
    db.flush()
    db.add(PublisherRecon(request_id=r.id, our_volume=1000))
    db.add(PublisherRequestMessage(request_id=r.id, side="система", body="отправлена"))
    db.flush()
    return r


def test_withdraw_erases_unagreed_recon(db):
    r = _req(db)
    rid = r.id
    out = S.withdraw(db, r, USER)
    db.flush()
    assert {k: out[k] for k in ("publisher_id", "period", "our_volume", "files")} == {
        "publisher_id": r.publisher_id, "period": "2031-01", "our_volume": 1000, "files": []}
    assert db.get(PublisherRequest, rid) is None
    assert db.execute(text("SELECT count(*) FROM publisher_request_message WHERE request_id = :r"), {"r": rid}).scalar() == 0


def test_agreed_recon_cannot_be_withdrawn(db):
    r = _req(db, verdict=B.AGREED)
    with pytest.raises(S.ReconError) as e:
        S.withdraw(db, r, USER)
    assert e.value.status == 409


def test_withdrawn_message_tells_not_to_answer():
    title, body, facts = N.message("отозвана", "январь 2031", 1000, None, None)
    assert "отозвана" in title.lower() and "не нужно" in body and facts == []


def test_month_export_has_summary_then_a_sheet_per_site(db):
    period = B.last_period(db)
    rows = B.month_rows(db, period) if period else []
    if not rows:
        pytest.skip("на стенде нет месяца со сверками")
    wb = openpyxl.load_workbook(BytesIO(E.export_xlsx(db, period)))
    assert wb.sheetnames[0] == "Сводная"
    assert len(wb.sheetnames) == 1 + len(rows)
    head = [c.value for c in wb["Сводная"][1]]
    assert head[0] == "Площадка" and "Наши показы" in head and "Статус" in head
    site = wb[wb.sheetnames[1]]
    assert [c.value for c in site[1]][:2] == ["Бренд", "Услуга"]
