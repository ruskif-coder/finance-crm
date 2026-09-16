# -*- coding: utf-8 -*-
"""Арифметика строки медиаплана: объём — не показы, и запятая — это число.

Разбор 08.09.2026 по услуге Polza (Фикс, 1 ед × 80 000). Два допущения, зашитые в код,
оказались верны только для CPM:

**«объём = показы».** У Фикса и Пакета в объёме лежат ШТУКИ закупки, у CPC — клики.
Строка Polza давала «1 показ», охват 0,25 и CPM 80 000 000 ₽ — и это уезжало клиенту
в Excel и в PDF. Владелец: показы становятся собственным полем прогноза, вводит аккаунт.

**«делим на 1000».** Ветка «CPM или нет» стояла в пяти местах и отсутствовала в двух:
в приложении к договору (`sales/annex.py`) и в сборке рекламной кампании (`app/ad/build`).
Строка Фикса печаталась в подписываемом документе как 80 ₽ вместо 80 000.

Третья находка того же разбора: **десятичная запятая**. Конструктор пишет то, что набрал
человек («0,8»), фронт её понимает, бэкенд — нет: `float("0,8")` бросает ValueError.
Замерено: запятая стоит в 19 значениях CTR из 42 и в 2 значениях CR — то есть у половины
строк в клиентском Excel CTR, клики, CPC, CR, чеки, CPO, доход и ROI были пустыми, а на
экране конструктора стояли. Расхождение тихое: обе картинки правдивы по отдельности.
"""
import pytest

from app.routers.media_plans import _fc_metrics, _row_net
from app.sales import mp_row


class _Row:
    """Строка МП в том виде, в каком её видит `_row_net` (ORM-объект)."""

    def __init__(self, model, volume, unit_price, discount=0, position='услуга'):
        self.model, self.volume, self.unit_price = model, volume, unit_price
        self.discount, self.position = discount, position


# ── сумма ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('model, expected', [
    ('CPM', 80),          # 1 × 80 000 / 1000
    ('Фикс', 80000),      # справочник услуг пишет по-русски
    ('Fix', 80000),       # конструктор МП пишет латиницей — то же самое
    ('Пакет', 80000),
    ('CPC', 80000),
])
def test_only_cpm_is_divided_by_a_thousand(model, expected):
    """Деление на 1000 — свойство ОДНОЙ модели, а не всех.

    Ошибка ровно в тысячу раз и молча: 80 ₽ в подписываемом документе читается как
    опечатка, а не как неверный расчёт.
    """
    assert mp_row.row_net(model, 1, 80000, 0) == expected
    assert _row_net(_Row(model, 1, 80000)) == expected


def test_case_and_spaces_in_the_model_do_not_change_the_formula(model=' cpm '):
    """Справочник заполняется руками; «cpm» обязано остаться CPM."""
    assert mp_row.row_net(model, 1000, 300) == mp_row.row_net('CPM', 1000, 300) == 300


# ── показы ────────────────────────────────────────────────────────────────────

def test_volume_counts_as_impressions_only_for_cpm():
    """У CPM объём и есть показы. У остальных моделей — нет, и это НОЛЬ, а не объём.

    Ноль честно рисуется прочерком «не заполнено»; «1 показ» выглядит как расчёт.
    """
    assert mp_row.row_imp('CPM', 1515152, {}) == 1515152
    assert mp_row.row_imp('Фикс', 1, {}) == 0
    assert mp_row.row_imp('Пакет', 1, {}) == 0
    # CPC: в объёме КЛИКИ. Подставить их в показы значило бы посчитать клики дважды;
    # без CTR вывести показы не из чего, и это ноль (с CTR — см. блок про CPC ниже).
    assert mp_row.row_imp('CPC', 5000, {}) == 0


def test_manual_impressions_win_over_the_volume():
    """Предоплаченный объём вводит аккаунт — он привязан к сделке, а не к услуге."""
    assert mp_row.row_imp('Фикс', 1, {'imp': '250000'}) == 250000
    assert mp_row.row_imp('CPM', 1000, {'imp': '900'}) == 900


def test_fix_row_forecast_is_empty_until_the_account_fills_it():
    """Без введённых показов таблица прогноза молчит, а не врёт.

    Это и есть та строка, ради которой всё затевалось: раньше здесь стояли охват 0,25,
    клики 0,01 и CPM 80 000 000 ₽.
    """
    m = _fc_metrics({'model': 'Фикс', 'volume': 1,
                     'forecast': {'ctr': '1', 'freq': '4'}}, 80000)
    assert m['imp'] is None and m['reach'] is None
    assert m['clicks'] is None and m['cpm'] is None


def test_fix_row_forecast_counts_from_the_prepaid_volume():
    """С введённым объёмом всё считается обычным порядком: 80 000 ₽ / 250 000 = CPM 320 ₽."""
    m = _fc_metrics({'model': 'Фикс', 'volume': 1,
                     'forecast': {'ctr': '1', 'freq': '4', 'imp': '250000'}}, 80000)
    assert m['imp'] == 250000
    assert m['reach'] == 62500
    assert m['clicks'] == 2500
    assert round(m['cpm'], 2) == 320.0


def test_cpm_row_is_untouched_by_the_change():
    """Старые планы обязаны считаться ровно как считались."""
    m = _fc_metrics({'model': 'CPM', 'volume': 1515152,
                     'forecast': {'ctr': '0,8', 'freq': '4'}}, 500000)
    assert m['imp'] == 1515152
    assert round(m['cpm'], 2) == 330.0


# ── десятичная запятая ────────────────────────────────────────────────────────

@pytest.mark.parametrize('raw, expected', [
    ('0,8', 0.8), ('0.8', 0.8), ('1 500,5', 1500.5), ('4', 4.0),
    # Единицы измерения человек дописывает руками. Фронт их снимал с самого начала,
    # бэкенд — нет, и `float("0,2%")` давал ноль. Найдено 16.09.2026 на живых данных:
    # МП 109 «Клик-аут», CTR «0,201619081013%» — весь прогноз строки был прочерком.
    ('0,8%', 0.8), ('55 ₽', 55.0), ('0.201619081013%', 0.201619081013),
])
def test_units_typed_by_hand_are_not_a_parse_error(raw, expected):
    assert mp_row.num(raw) == expected


def test_both_mirrors_strip_the_same_characters():
    """Зеркала обязаны снимать ОДИН набор символов.

    Разойдясь, они дают картинку, в которой на экране число есть, а в документе клиента
    прочерк — и обе половины правдивы по отдельности. Файла фронта в контейнере бэкенда
    нет, поэтому сверяется ПОВЕДЕНИЕ по тому же правилу, что записано в `lib/mpRow.js`.
    """
    import re
    for raw in ('0,8%', '55 ₽', '1 500,5', '0.2%', '1 200 000'):
        expected = float(re.sub(r'[\s ₽%]', '', raw).replace(',', '.'))
        assert mp_row.num(raw) == expected, raw


def test_comma_in_ctr_no_longer_empties_the_client_facing_columns():
    """«0,8» в CTR обязано давать клики. Их отсутствие и было тихим расхождением."""
    m = _fc_metrics({'model': 'CPM', 'volume': 1000000,
                     'forecast': {'ctr': '0,8'}}, 300000)
    assert m['ctr'] == 0.8
    assert m['clicks'] == 8000
    assert m['cpc'] is not None


def test_garbage_stays_zero_and_does_not_raise():
    """Мусор в поле — ноль, а не 500-я: прогноз вводится руками."""
    assert mp_row.num('абв') == 0
    assert mp_row.num(None) == 0
    assert mp_row.row_imp('Фикс', 1, {'imp': 'много'}) == 0


# ── CPC: куплены клики, показы выводятся ──────────────────────────────────────

def test_cpc_clicks_come_from_the_volume_not_from_the_impressions():
    """Разбор 16.09.2026, находка владельца: «при модели cpc неверно считает показы и клики».

    В CPC-строке куплены КЛИКИ — они и лежат в объёме. Формула `клики = показы × CTR`
    стояла в шести местах сразу (конструктор, PDF-маппер, карточка сделки, формула Excel,
    `_fc_metrics`), и для CPC была неверна дважды: показов у CPC нет вовсе, поэтому они
    выходили в ноль, а клики следом. На экране строка «CPC · 50 000 кликов» показывала
    прочерки в кликах, показах, CPM и CPC — притом что клики единственное, что в ней
    куплено наверняка.
    """
    assert mp_row.row_clicks('CPC', 50000, {'ctr': '0,5'}) == 50000
    # показы выводятся обратной формулой: 50 000 кликов при CTR 0,5 % = 10 млн показов
    assert mp_row.row_imp('CPC', 50000, {'ctr': '0,5'}) == 10_000_000


def test_cpc_without_ctr_shows_clicks_but_not_impressions():
    """Клики известны и без CTR. Показы — нет, и это прочерк, а не выдуманное число."""
    m = _fc_metrics({'model': 'CPC', 'volume': 50000, 'forecast': {}}, 1_000_000)
    assert m['clicks'] == 50000
    assert m['imp'] is None and m['cpm'] is None
    assert m['cpc'] == 20.0                       # 1 000 000 ₽ / 50 000 кликов


def test_cpc_row_is_whole_once_the_ctr_is_filled():
    """Полная строка: CPC считается от закупленных кликов, CPM — от выведенных показов."""
    m = _fc_metrics({'model': 'CPC', 'volume': 50000,
                     'forecast': {'ctr': '0,5', 'freq': '2'}}, 1_000_000)
    assert m['clicks'] == 50000
    assert m['imp'] == 10_000_000
    assert m['reach'] == 5_000_000
    assert round(m['cpm'], 2) == 100.0
    assert round(m['cpc'], 2) == 20.0


def test_other_models_still_count_clicks_from_the_impressions():
    """Правило меняется ТОЛЬКО для CPC; остальные планы обязаны считаться как считались."""
    assert mp_row.row_clicks('CPM', 1_000_000, {'ctr': '0,8'}) == 8000
    assert mp_row.row_clicks('Фикс', 1, {'ctr': '1', 'imp': '250000'}) == 2500
    assert mp_row.row_clicks('Фикс', 1, {'ctr': '1'}) == 0


# ── копейки ───────────────────────────────────────────────────────────────────

def test_the_row_sum_keeps_kopecks():
    """Находка владельца 16.09.2026: «не даёт вводить копейки, обнуляет введённое до целого».

    Сумма строки округлялась до РУБЛЯ, и на самом обычном CPM-случае это съедало копейки
    цены: 2 927 400 показов по 250,50 ₽ за тысячу это 733 313,70 ₽. В конструкторе так и
    выглядело — поле бюджета возвращалось к целому числу после ввода.
    """
    assert mp_row.row_net('CPM', 2927400, 250.50) == 733313.70
    assert mp_row.row_net('Fix', 3, 1000.33) == 3000.99
    assert mp_row.row_net('CPC', 50000, 20.25, 0.1) == 911250.0


def test_the_sum_is_not_a_float_tail():
    """Копейки — две цифры, а не хвост двоичной дроби: 0.1+0.2 в документе недопустимо."""
    v = mp_row.row_net('Fix', 3, 0.1)
    assert v == 0.3 and str(v) == '0.3'
