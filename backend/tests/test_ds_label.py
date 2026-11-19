# -*- coding: utf-8 -*-
"""Правило «ДС № / ПР №» в системе (владелец 09.11 и 18.11.2026). Примеры — ТЕ ЖЕ, что во frontend/lib/annexNumber.test.mjs.

Ломается, если: вернуть «Прил. №»; сокращение тронет запись без номера («доплата июль»); номер операции перестанет приводиться
при записи (валидатор модели) — тогда сверка импорта снова видит `доп.12` и `ДС № 12` разными; импорт перестанет приводить
номер из файла до сверки.
"""
import pytest

from app.ds_label import short

CASES = [
    ('Приложение № 17', 'ПР № 17'), ('Дополнительное соглашение № 28', 'ДС № 28'), ('Доп. соглашение №68', 'ДС № 68'),
    ('доп.12', 'ДС № 12'), ('доп 153', 'ДС № 153'), ('доп. 8', 'ДС № 8'), ('доп.согл.4', 'ДС № 4'), ('доп.12-1', 'ДС № 12-1'),
    ('прил 64', 'ПР № 64'), ('прил.15', 'ПР № 15'), ('прилож. 19', 'ПР № 19'), ('Приложение № 5-2', 'ПР № 5-2'),
    ('ДС № 12', 'ДС № 12'), ('ПР № 64', 'ПР № 64'),
    ('доплата июль', 'доплата июль'), ('заявка 3', 'заявка 3'), ('пени', 'пени'), ('95', '95'), ('доп да-1/2', 'доп да-1/2'),
]


@pytest.mark.parametrize("raw,want", CASES)
def test_short(raw, want):
    assert short(raw) == want


def test_empty_stays():
    assert short(None) is None and short('') == ''


def test_operation_stores_short_number():
    """Валидатор модели: любое написание в `Operation.ds_num` хранится как «ДС № N»."""
    from app.models import Operation
    assert Operation(ds_num='доп.12').ds_num == 'ДС № 12'
    assert Operation(ds_num='прил 64').ds_num == 'ПР № 64'


def test_import_normalizes_file_number_before_matching():
    """Импорт приводит номер из файла до сверки — иначе `доп.12` в файле не нашёл бы `ДС № 12` в базе."""
    import inspect
    from app.routers import operations
    assert "ds_label.short(str(row['ds_num']))" in inspect.getsource(operations)
