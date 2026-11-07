# -*- coding: utf-8 -*-
"""Объём строки ДС мастер-сделки — в единицах закупки своей модели (прод 07.11.2026, M-0029/M-0030: у CPC в «Объёме
размещения» стояли показы 548 082 при цене 150 за клик и сумме 385 050 — то есть кликов 2 567).

Раскладка масштабировала объём всех строк коэффициентом «показы сверки ÷ объём МП», а у CPC объём МП — клики, у Фикса —
штуки. Показы в объём идут только у CPM; у остальных объём = сумма строки ÷ цена за единицу."""
import app.model_registry  # noqa: F401
from app.master_deal import layout as LY


def test_cpc_volume_is_clicks_from_money():
    assert LY.row_volume({"model": "CPC", "volume": 2600, "unit_price": 150.0}, 385050.0, 210.8) == 2567


def test_fix_volume_stays_pieces():
    assert LY.row_volume({"model": "Фикс", "volume": 1, "unit_price": 80000.0}, 80000.0, 0.5) == 1


def test_cpm_volume_follows_the_reconciled_shows():
    assert LY.row_volume({"model": "CPM", "volume": 1000000, "unit_price": 200.0}, 180000.0, 0.9) == 900000


def test_no_price_falls_back_to_plan_volume():
    assert LY.row_volume({"model": "CPC", "volume": 2600, "unit_price": None}, 0.0, 210.8) == 2600
