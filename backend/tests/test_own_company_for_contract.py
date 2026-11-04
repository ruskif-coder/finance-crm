# -*- coding: utf-8 -*-
"""Наше юрлицо по договору — одно правило на документы, мост в операции и новые договоры (владелец 04.11.2026).

Поломка, которую ловит: печать ДС брала «юрлицо договора, иначе единственное наше», а мост мастер-сделки в операции —
только колонку договора. У 12 договоров колонка пуста: ДС печатался с юрлицом, а операция из него приходила без юрлица,
и P&L / 1С её не разносили. Новые договоры из реестра и «Добавить данные» тоже заводились без юрлица.
"""
import pathlib
import re
from types import SimpleNamespace

from app import own_company as OC

APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def test_contract_company_wins_else_the_sole_one(monkeypatch):
    ours = SimpleNamespace(id=7)
    monkeypatch.setattr(OC, "sole", lambda db: ours)
    assert OC.for_contract(None, SimpleNamespace(own_company=SimpleNamespace(id=3))).id == 3
    assert OC.for_contract(None, SimpleNamespace(own_company=None)) is ours
    assert OC.for_contract(None, None) is ours
    assert OC.for_contract_id(None, SimpleNamespace(own_company=None)) == 7
    monkeypatch.setattr(OC, "sole", lambda db: None)          # ноль или два наших — не угадываем
    assert OC.for_contract_id(None, SimpleNamespace(own_company=None)) is None


def test_bridge_and_documents_ask_the_same_rule():
    """Мост в операции и печать ДС не держат своих копий правила — обе зовут `for_contract`."""
    bridge = (APP / "master_deal" / "bridge.py").read_text(encoding="utf-8")
    assert "own_company.for_contract_id(" in bridge
    assert not re.search(r'"own_company_id":\s*c\.own_company_id', bridge), "мост берёт голую колонку договора"
    annex = (APP / "sales" / "annex.py").read_text(encoding="utf-8")
    assert "own_company.for_contract(" in annex


def test_new_contract_is_stamped_with_our_company():
    src = (APP / "routers" / "contracts.py").read_text(encoding="utf-8")
    body = src[src.index("contract = Contract(\n        contract_number=_clean(data.contract_number)"):]
    body = body[:body.index("db.add(contract)")]
    assert "own_company_id=own_company.sole_id(db)" in body, "новый договор заводится без нашего юрлица"
