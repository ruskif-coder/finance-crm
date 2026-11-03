# -*- coding: utf-8 -*-
"""Единица количества услуги — по справочнику (владелец 03.11.2026: «к услугам нужно единицы помимо суммы в соответствии со
справочником услуг»). Отдельного поля единицы в справочниках нет; она выводится из того, как услуга закупается:

  · основная услуга — по модели закупки (`calc_form`): CPM — показы, CPC — клики, остальное (Фикс, Пакет) — штуки. Те же правила,
    что у строки медиаплана (`mp_row.is_cpm` / `is_cpc`): «объём ≠ показы» уже ломал прогнозы;
  · доп. услуга — по периоду: «по итогам РК» — показы (цена за показ, как у верификации пикселем), остальное («разово») — штуки.
"""
from app.sales import mp_row

SHOWS, CLICKS, PIECES = "показы", "клики", "штуки"


def service_unit(calc_form) -> str:
    if mp_row.is_cpm(calc_form):
        return SHOWS
    if mp_row.is_cpc(calc_form):
        return CLICKS
    return PIECES


def addon_unit(period) -> str:
    return SHOWS if "итогам" in (period or "").lower() else PIECES
