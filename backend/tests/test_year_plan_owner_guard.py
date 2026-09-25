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


def test_non_master_keeps_owners_of_an_existing_line():
    yp._guard_line_owners(False, {5}, ROW, 5, 6)          # ничего не меняет — можно
    with pytest.raises(HTTPException) as e:
        yp._guard_line_owners(False, {5}, ROW, 9, 6)      # продавец другой
    assert e.value.status_code == 403
    with pytest.raises(HTTPException):
        yp._guard_line_owners(False, {5}, ROW, 5, 9)      # аккаунт другой


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
