# -*- coding: utf-8 -*-
"""Копейки медиаплана не теряются ни в одном денежном месте.

Находка владельца 16.09.2026: «не даёт вводить копейки, обнуляет введённое до целого».
Причина была не во вводе — округлялась САМА СУММА. И не в одном месте: по `media_plans.py`
россыпью стояли `round(...)` без точности — сумма строки, НДС, «с НДС», скидка в рублях,
доп. услуги, итог документа. Каждый из них по отдельности выглядел безобидно, а вместе
они означали, что цена с копейками в системе не живёт.

Показательно, что формат денежной ячейки в шаблоне Excel — `#,##0.00`: копейки там ЖДАЛИ
и печатали «,00» независимо от того, какими они были на самом деле.

Проверяется по двум осям: результат (суммы сходятся с копейками) и источник (в денежном
файле не появляется нового округления без точности).
"""
import ast
import io
from pathlib import Path

from app.routers import media_plans as mp_api
from app.sales import mp_row


class _Row:
    def __init__(self, model, volume, unit_price, discount=0, position='услуга'):
        self.model, self.volume, self.unit_price = model, volume, unit_price
        self.discount, self.position = discount, position


class _Extra:
    def __init__(self, total):
        self.total = total


def test_plan_totals_keep_kopecks():
    """2 927 400 показов по 250,50 ₽ за тысячу — 733 313,70 ₽, и с НДС 894 642,71 ₽."""
    net, gross = mp_api._amounts([_Row('CPM', 2927400, 250.50)], [], 22.0)
    assert net == 733313.70
    assert gross == 894642.71


def test_extras_are_added_with_their_kopecks():
    net, gross = mp_api._amounts([_Row('Fix', 1, 1000.55)], [_Extra(499.45)], 22.0)
    assert net == 1500.0 and gross == 1830.0


def test_the_document_row_context_keeps_kopecks():
    """Контекст строки идёт прямо в ячейки шаблона Excel и в docx — там же, где подпись."""
    ctx = mp_api._row_ctx({'model': 'CPM', 'volume': 2927400, 'unit_price': 250.50,
                           'discount': 0.1, 'position': 'услуга', 'forecast': {}}, {})
    assert ctx['r.net_nodisc'] == 733313.70
    assert ctx['r.net'] == 659982.33
    assert ctx['r.disc_rub'] == 73331.37
    assert round(ctx['r.net'] + ctx['r.disc_rub'], 2) == ctx['r.net_nodisc']
    assert round(ctx['r.net'] + ctx['r.vat'], 2) == ctx['r.gross']


def test_a_fractional_discount_stays_fractional_in_the_document():
    """Скидка 12,5 % печаталась как 13 %, и документ переставал сходиться: «до скидки»
    минус «скидка» не давало суммы к оплате при указанном проценте."""
    ctx = mp_api._row_ctx({'model': 'Fix', 'volume': 1, 'unit_price': 1000,
                           'discount': 0.125, 'position': 'услуга', 'forecast': {}}, {})
    assert ctx['r.disc_pct'] == 12.5
    assert ctx['r.net'] == 875.0
    assert ctx['r.disc_rub'] == 125.0


def test_the_deal_sum_does_not_grow_a_binary_tail():
    """Складывая копейки, float даёт 733 314,0000000001 — и сумма сделки в реестре
    отличалась бы от суммы в медиаплане последним знаком (`mp_amounts`)."""
    assert mp_row.rub(733313.70 + 0.30) == 733314.0
    assert mp_row.rub(0.1 + 0.2) == 0.3


def test_no_money_is_rounded_to_a_whole_rouble_in_the_money_file():
    """Прибор на ИСТОЧНИК: `round(x)` без точности в `media_plans.py` — это снова потеря
    копеек. Деньги проходят через `mp_row.rub`, и если понадобилось целое, точность
    указывается явно — тогда это видно при чтении, а не всплывает в документе клиента.
    """
    src = io.open(Path(mp_api.__file__), encoding='utf-8').read()
    bad = [n.lineno for n in ast.walk(ast.parse(src))
           if isinstance(n, ast.Call) and getattr(n.func, 'id', '') == 'round'
           and len(n.args) == 1]
    assert bad == [], f'round() без точности в денежном файле, строки: {bad}'
