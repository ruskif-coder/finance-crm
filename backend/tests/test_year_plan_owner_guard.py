# -*- coding: utf-8 -*-
"""Годовой план: ответственных строки меняет только мастер (аудит 23.09.2026, 9.1 / 1.M3).

`update_plan` это запрещал, а `save_year_plan` брал продавца и аккаунта строки из
присланного брифа и `plan_id` из запроса без проверки: сейлз с областью «свои» сохранял
строку с чужим продавцом в брифе или под чужим планом — и строка уезжала в чужую корзину,
а у него самого пропадала с экрана.
"""
import inspect
import pytest
from fastapi import HTTPException

from app.routers import year_plan as yp

ROW = (5, 6)   # ответственные по сохранённому брифу строки


def test_master_may_change_owners():
    yp._guard_line_owners(True, {1}, ROW, 9, 9)


def test_non_master_may_change_owners_while_staying_on_the_line():
    """Смягчено 09.10.2026 (Bausch): аккаунт вписывает продавца в бриф своей строки."""
    yp._guard_line_owners(False, {5}, ROW, 5, 6)          # ничего не меняет — можно
    yp._guard_line_owners(False, {6}, ROW, 9, 6)          # продавец другой, сам остался аккаунтом
    yp._guard_line_owners(False, {5}, ROW, 5, 9)          # аккаунт другой, сам остался продавцом
    with pytest.raises(HTTPException) as e:
        yp._guard_line_owners(False, {5}, ROW, 9, 8)      # оба чужие — строка пропала бы с экрана
    assert e.value.status_code == 403


def test_unchanged_line_passes_even_if_saver_is_not_its_owner_by_columns():
    yp._guard_line_owners(False, {7}, ROW, 5, 6)


def test_non_master_creates_a_line_only_for_himself():
    yp._guard_line_owners(False, {5}, None, 5, 7)         # продавцом — сам
    yp._guard_line_owners(False, {5}, None, 7, 5)         # аккаунтом — сам
    with pytest.raises(HTTPException) as e:
        yp._guard_line_owners(False, {5}, None, 7, 8)     # оба чужие
    assert e.value.status_code == 403


def test_save_checks_owners_and_the_plan():
    src = inspect.getsource(yp.save_year_plan)
    assert "_guard_line_owners(" in src, "сохранение не проверяет смену ответственных"
    assert "_guard_plan_owner(" in src, "сохранение не проверяет чужой план"


def test_effective_plan_is_sum_of_months_when_column_is_empty():
    """Колонка «Годовой план» пустая → план = Σ месяцев: услуги или ручная сумма
    (владелец 09.10.2026). Введённое руками число приоритетнее."""
    from types import SimpleNamespace as L
    line = L(plan_amount=0, months_on=[1, 1, 0, 1] + [0] * 8,
             sums={"0": 100, "1": 50, "3": 7}, products={"1": [{"amount": 20}, {"amount": 5}]})
    assert yp.committed_sum(line) == 100 + 25 + 7      # услуги месяца важнее ручной суммы
    assert yp.effective_plan(line) == 132
    assert yp.effective_plan(L(plan_amount=900, months_on=line.months_on, sums=line.sums,
                               products=line.products)) == 900
    assert yp.effective_plan(L(plan_amount=0, months_on=[], sums={}, products={})) == 0
