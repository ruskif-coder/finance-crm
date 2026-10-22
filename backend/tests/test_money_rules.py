# -*- coding: utf-8 -*-
"""Денежные правила сверки, раскладки и ДС — одно место (`app/final_recon/money.py`), по внешнему аудиту 2.7.0 (пп. 2.3, 2.4)
и решению владельца 22.10.2026: «НДС в документах — по строкам». Строки базовой услуги, масштабированные под сумму сверки,
складываются РОВНО в неё (копейки остатка — последней строке); НДС документа = сумма НДС строк."""
import random
from decimal import Decimal

import pytest

from app.final_recon import money as M


def test_scaled_rows_sum_exactly_to_target():
    rnd = random.Random(270)
    for _ in range(4000):
        n = rnd.randint(2, 150)
        amounts = [rnd.randint(100_000, 9_000_000) / 100 for _ in range(n)]
        target = round(sum(amounts) * rnd.uniform(0.33, 1.04), 2)
        out = M.scale_to(amounts, target)
        assert len(out) == n
        assert sum(Decimal(str(x)) for x in out) == Decimal(str(target))


def test_scale_keeps_proportions_and_handles_edges():
    assert M.scale_to([100.0, 300.0], 200.0) == [50.0, 150.0]
    assert M.scale_to([], 100.0) == []
    assert M.scale_to([0.0, 0.0], 100.0) == [0.0, 0.0]        # нечего масштабировать — сумма не выдумывается
    assert M.scale_to([100.0], 33.33) == [33.33]


@pytest.mark.parametrize("net,rate,vat", [(100.0, 22, 22.0), (0.05, 22, 0.01), (0.02, 22, 0.0), (12345.67, 22, 2716.05),
                                          (2.5, 20, 0.5), (1.125, 20, 0.23)])
def test_line_vat_rounds_half_up(net, rate, vat):
    assert M.line_vat(net, rate) == vat


def test_document_vat_is_sum_of_line_vats():
    nets = [0.03, 0.03, 0.03]
    assert M.doc_vat(nets, 22) == 0.03                  # по строкам 0,01 × 3; от суммы было бы 0,09 × 0,22 = 0,0198 → 0,02
    nets = [10.05, 20.05, 30.05]
    assert M.doc_vat(nets, 22) == sum(M.line_vat(x, 22) for x in nets)


def test_none_rate_means_no_vat():
    assert M.line_vat(100.0, None) == 0.0
    assert M.doc_vat([100.0, 50.0], None) == 0.0
