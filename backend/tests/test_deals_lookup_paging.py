# -*- coding: utf-8 -*-
"""Поиск сделок для привязки МП: страница не притворяется всем списком.

ПРОИСШЕСТВИЕ 08.09.2026. Аккаунты не находили старые сделки. Причина не в поиске:
запрос молча обрезался на 300 строках, а экран рисовал ровно то, что пришло, и подпись
«N сделок» читалась как «столько их и есть». Отличить «нашлось 50» от «показано 50 из
920» было нечем — ни на экране, ни в ответе.

Прибор держит два свойства, из которых обрезание видно:

* ответ несёт ОБЩЕЕ число и число страниц, а не только строки;
* соседние страницы не пересекаются и в сумме дают весь список — иначе сортировка по
  полю с повторами (пустой бренд, один период) перетасует строки между запросами, и
  сделка либо задвоится, либо не покажется вообще ни на одной странице.
"""
from types import SimpleNamespace

import pytest

import app.ad.models           # noqa: F401
import app.launch_prep.models  # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.routers import media_plans as mp


@pytest.fixture
def env():
    db = SessionLocal()
    actor = SimpleNamespace(id=0, name='тест',
                            role=SimpleNamespace(key='admin', is_master=True,
                                                 staff_group='account'))
    yield SimpleNamespace(db=db, user=actor)
    db.close()


def test_answer_says_how_many_there_are_in_total(env):
    """Без общего числа страница неотличима от полного списка."""
    r = mp.deals_lookup(db=env.db, current_user=env.user)
    for k in ('total', 'page', 'pages', 'per_page'):
        assert k in r, f'в ответе нет {k} — экран не сможет сказать «X из N»'
    assert r['total'] >= len(r['items'])
    assert len(r['items']) <= r['per_page']


def test_pages_do_not_overlap_and_cover_everything(env):
    """Сортировка по полю с повторами не должна терять и двоить строки.

    Берём сортировку по бренду: он пустой у большинства сделок, то есть значений-
    близнецов много. Без вторичного ключа порядок внутри группы задаёт база, и он
    меняется между запросами — ровно тот случай, когда сделка исчезает из всех страниц.
    """
    first = mp.deals_lookup(sort='brand', db=env.db, current_user=env.user)
    if first['pages'] < 2:
        pytest.skip('на стенде меньше одной страницы сделок')
    seen = []
    for p in range(1, first['pages'] + 1):
        seen += [i['id'] for i in mp.deals_lookup(sort='brand', page=p,
                                                  db=env.db, current_user=env.user)['items']]
    assert len(seen) == first['total'], 'страницы в сумме не дают весь список'
    assert len(set(seen)) == len(seen), 'одна сделка попала на две страницы'


def test_page_out_of_range_is_clamped_not_empty(env):
    """Запрос несуществующей страницы отдаёт последнюю, а не пустой экран.

    Пустая страница после смены поиска выглядит как «ничего не найдено» — и человек
    уходит, хотя сделки есть.
    """
    r = mp.deals_lookup(page=10**6, db=env.db, current_user=env.user)
    assert r['page'] == r['pages']
    if r['total']:
        assert r['items']
