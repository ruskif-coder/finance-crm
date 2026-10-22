# -*- coding: utf-8 -*-
"""Остановленный защитой ночной пересчёт не падает трассировкой (прод 22.10.2026: `KeyError: 'failed'`).

Когда сбор статистики DSP сломан, `run` возвращает только `held`, без `failed`, и выход крона ронял процесс. Код выхода
остановки — 1: пересчёт не состоялся, и это должно быть видно так же, как неушедшие лимиты."""
from app.ad import daily_shares as D


def test_exit_code():
    assert D.exit_code({"held": {"since": "x", "reason": "y"}}) == 1
    assert D.exit_code({"failed": 2, "shares": {}}) == 1
    assert D.exit_code({"failed": 0, "shares": {}}) == 0
