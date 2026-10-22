# -*- coding: utf-8 -*-
"""Ставка НДС пакета — одна: нашего юрлица на дату составления документа (владелец 21.10.2026).

До этого раскладка мастер-сделки брала ставку медиаплана первой сделки, а документ — ставку юрлица: при сделке на 20 % и
юрлице на 22 % ДС, комплект УПД и будущая операция по мосту расходились (аудит v2.6.0→v2.7.0, D3)."""
from datetime import date
from types import SimpleNamespace

from app import vat


def test_company_rate_wins():
    us = SimpleNamespace(vat_rate_income=22)
    assert vat.for_document(None, SimpleNamespace(own_company=us), date(2025, 6, 1)) == 22


def test_no_company_rate_means_law_on_document_date():
    c = SimpleNamespace(own_company=SimpleNamespace(vat_rate_income=None))
    assert vat.for_document(None, c, date(2025, 6, 1)) == vat.on(date(2025, 6, 1))
    assert vat.for_document(None, c, date(2026, 6, 1)) == vat.on(date(2026, 6, 1))


def test_layout_takes_the_document_rate_not_the_media_plan(monkeypatch):
    from app.master_deal import layout as LY
    monkeypatch.setattr(LY, "_contract_of", lambda db, m: SimpleNamespace(own_company=SimpleNamespace(vat_rate_income=22)))
    m = SimpleNamespace(contract_id=1, period="2026-10")
    assert LY._vat(None, m, [{"deal_id": 5}]) == 22
