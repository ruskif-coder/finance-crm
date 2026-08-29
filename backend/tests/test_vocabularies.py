# -*- coding: utf-8 -*-
"""Русские значения в базе не расходятся с объявленными словарями.

Значения перечислений в этом проекте — русские строки, и сравниваются они БУКВАЛЬНО:
в Python, в SQL-view схемы `pub` и в JS обоих фронтов. Опечатка не падает, а тихо
перестаёт совпадать — строка просто выпадает из выборки, и на экране становится на одну
меньше. Однажды так и случилось: составное значение фильтра (воронка\x1fстадия) утекло
в `bitrix_stage` через масс-правку.

CHECK-констрейнтов на эти колонки нет намеренно (модуль трафиков добавляет свои
под-этапы, и расширение не должно требовать миграции). Значит единственная защита —
прибор, который сверяет ФАКТ в базе с объявлением в коде.

Проверяется одно направление: в базе не должно быть значений, которых нет в словаре.
Обратное (в словаре есть, в базе нет) — норма: состояние может просто не наступить.
"""
import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.launch_prep.models import (REVIEW_KINDS, REVIEW_VERDICTS_BY_KIND,
                                    SET_ORIGINS, TARGET_STATES)

# (таблица, колонка, допустимые значения)
COLUMNS = [
    ('launch_prep_target', 'state', set(TARGET_STATES)),
    ('launch_prep_review', 'kind', set(REVIEW_KINDS)),
    ('launch_prep_creative_set', 'origin', set(SET_ORIGINS)),
    # Вид файла пары: снимок размещения или приложение к доработке от площадки. Без
    # вида очередь трафика посчитала бы чужие картинки своими доказательствами.
    ('launch_prep_pair_file', 'kind', {'размещение', 'доработка'}),
    # Чьими руками записан вердикт. Через год отличить одно от другого будет не по чему.
    ('launch_prep_review', 'source', {'аккаунт', 'кабинет', 'трафики', 'продление'}),
]


@pytest.mark.parametrize('table,column,allowed', COLUMNS,
                         ids=[f'{t}.{c}' for t, c, _ in COLUMNS])
def test_no_value_outside_the_vocabulary(table, column, allowed):
    db = SessionLocal()
    try:
        found = {v for (v,) in db.execute(
            text(f'SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL'))}
    finally:
        db.close()
    extra = found - allowed
    assert not extra, (
        f'{table}.{column}: в базе есть значения вне словаря — {sorted(extra)}. '
        'Сравнение буквальное: такая строка молча выпадает из всех выборок.'
    )


def test_verdict_vocabulary_is_per_kind():
    """Вердикт зависит от СТУПЕНИ, и общего словаря у колонки нет.

    Площадка просит доработать и остаётся в кампании; трафик отправляет комплект на
    переделку целиком. Разные слова — разный смысл и разный адресат.
    """
    db = SessionLocal()
    try:
        rows = db.execute(text(
            'SELECT kind, verdict FROM launch_prep_review WHERE verdict IS NOT NULL')).all()
    finally:
        db.close()
    bad = [(k, v) for k, v in rows if v not in REVIEW_VERDICTS_BY_KIND.get(k, ())]
    assert not bad, f'вердикты вне словаря своей ступени: {sorted(set(bad))}'


def test_traffic_rework_word_is_declared():
    """`на переделку` объявлено — иначе CHECK, собранный из словаря площадки, его отверг.

    Прибор поставлен 30.08.2026 по факту находки: `REVIEW_VERDICTS` читался как словарь
    колонки, а был набором одной ступени.
    """
    from app.routers.traffic import TRAFFIC_VERDICTS
    assert set(TRAFFIC_VERDICTS) <= set(REVIEW_VERDICTS_BY_KIND['трафики'])


def test_platform_verdicts_match_the_declaration():
    from app.routers.launch_prep import PLATFORM_VERDICTS
    assert set(PLATFORM_VERDICTS) == set(REVIEW_VERDICTS_BY_KIND['площадка'])
