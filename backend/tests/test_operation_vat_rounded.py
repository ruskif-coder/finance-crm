# -*- coding: utf-8 -*-
"""НДС операции округляется до копейки (аудит 2.6.76, п. 1.2; сделано 22.10.2026): «в том числе» — сумма × ставка / (100 + ставка),
«половина вверх», тем же правилом, что документы (`final_recon.money`). Без округления в `vat_fact` ложились хвосты вроде 18.0327…"""
import pytest

from app.routers.operations import compute_vat_fact


@pytest.mark.parametrize("income,expense,rate,vat", [
    (122.0, 0, 22, 22.0), (100.0, 0, 22, 18.03), (0, 100.0, 20, 16.67), (0.05, 0, 22, 0.01), (1000.0, 0, 0, 0)])
def test_vat_fact_is_rounded_to_kopecks(income, expense, rate, vat):
    assert compute_vat_fact(income, expense, rate) == vat
