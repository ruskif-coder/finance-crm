"""
Сопоставление строк файла с уже существующими операциями.

Три ошибки, найденные 2026-08-25 на живом переносе 25 операций. Все три давали
один и тот же внешний признак — «предпросмотр показывает новыми строки, которые
в базе уже есть», — и вели бы к дублям в учёте.

1. Пустота записана в базе двумя способами. Форма операции шлёт `ds_num: '' `
   (пустую строку), импорт кладёт NULL. Пул сопоставления собирался условием
   `ds_num IS NULL OR invoice IS NULL`, поэтому строки с пустой строкой в № ДС
   и заполненным счётом в пул не попадали вовсе: 222 операции на стенде, 246 на
   проде. Ни один из двух путей сопоставления их не находил.

2. Та же пустота ломала сравнение полей: `''` против `None` считалось
   изменением, и КАЖДАЯ строка с незаполненным назначением помечалась
   конфликтом.

3. Естественный ключ не включает номер счёта — он рассчитан на операции, где
   счёта нет вовсе. Но в пул попадают и строки, у которых пуст только № ДС.
   У ежемесячного счёта одного контрагента на одну сумму ключ совпадал сразу у
   нескольких записей, и бралась самая старая: правка уезжала не в ту операцию,
   а разница показывалась «конфликтом периода и ссылки».

ID из выгрузки — подсказка того же рода, что и счёт, и намеренно НЕСТРОГАЯ:
между стендами один номер принадлежит разным операциям, поэтому он смотрится
только внутри пула, то есть среди записей, уже совпавших по всем содержательным
полям.
"""
from collections import deque

from app.models import Operation
from app.routers.operations import (
    _CF_BEST_COLUMN_MAP,
    _CF_BEST_REQUIRED_FIELDS,
    _field_equal,
    _is_blank,
    _take_from_pool,
    _values_equal,
)


class _Op:
    """Минимальная замена операции: пулу нужны только id и номер счёта."""

    def __init__(self, id, invoice=None):
        self.id = id
        self.invoice = invoice

    def __repr__(self):
        return f'_Op({self.id}, {self.invoice!r})'


# ---- 1. пусто — это и NULL, и пустая строка ----

def test_blank_covers_empty_string_not_only_null():
    """Условие пула обязано покрывать оба написания пустоты.

    Проверка на тексте SQL, а не на поведении: без базы этот предикат больше
    негде увидеть, а именно он решает, попадёт запись в пул или нет.
    """
    sql = str(_is_blank(Operation.ds_num))
    assert 'IS NULL' in sql, sql
    assert '=' in sql, f'проверка на пустую строку пропала: {sql}'


def test_pool_condition_uses_the_blank_predicate():
    """Оба поля ключа проверяются одинаково — иначе дыра остаётся в одном из них."""
    for col in (Operation.ds_num, Operation.invoice):
        sql = str(_is_blank(col))
        assert 'IS NULL' in sql and '=' in sql, (col, sql)


# ---- 2. пусто не равно «изменилось» ----

def test_empty_string_and_none_are_the_same_emptiness():
    assert _values_equal('', None)
    assert _values_equal(None, '')
    assert _values_equal(None, None)
    assert _values_equal('', '')


def test_clearing_a_value_is_still_a_change():
    """Пусто сходится только с пустым: очистка непустого поля остаётся правкой."""
    assert not _values_equal('комментарий', '')
    assert not _values_equal('комментарий', None)


def test_description_no_longer_conflicts_on_every_row():
    """Ровно тот случай, что давал 25 конфликтов из 25."""
    assert _field_equal('description', '', None)


def test_numbers_are_not_swallowed_by_the_emptiness_rule():
    """Ноль — значение, а не пустота: правило про пустоту не должно его задеть."""
    assert not _values_equal(0, '')
    assert not _values_equal(0, None)
    assert _values_equal(0.0, 0.004)          # округление до копеек, как и было
    assert not _values_equal(0.0, 1.0)


# ---- 3. выбор из пула близнецов ----

def test_invoice_picks_the_right_twin():
    """Два ежемесячных счёта одного контрагента на одну сумму неотличимы по ключу."""
    pool = deque([_Op(2800, '6'), _Op(3017, '8')])
    assert _take_from_pool(pool, '8').id == 3017
    assert len(pool) == 1, 'выбранная запись обязана уйти из пула'


def test_different_invoice_numbers_mean_different_operations():
    """Найдено на боевых данных при выкладке 2026-08-25.

    В файле счёт 1778 за июль, в пуле — операция со счётом 1345 за июнь, суммы
    и контрагент те же. Откат «на самую раннюю» объявлял их одной операцией, и
    подтверждение такого конфликта переписало бы июньскую запись июльскими
    данными: не дубль, а потеря строки.
    """
    pool = deque([_Op(2872, '1345')])
    assert _take_from_pool(pool, '1778') is None
    assert len(pool) == 1, 'запись не должна быть израсходована впустую'


def test_row_with_invoice_still_matches_a_row_without_one():
    """Обратная сторона правила: файл дописывает номер счёта.

    Операция в базе без счёта — законный кандидат для строки со счётом, иначе
    обогащение реестра номерами превращалось бы в дубли.
    """
    assert _take_from_pool(deque([_Op(500, None)]), '189').id == 500
    assert _take_from_pool(deque([_Op(500, '')]), '189').id == 500


def test_foreign_invoice_does_not_block_a_blank_candidate():
    """В пуле и чужой счёт, и запись без счёта — берётся вторая."""
    assert _take_from_pool(deque([_Op(2872, '1345'), _Op(500, None)]), '189').id == 500


def test_id_chooses_only_among_eligible_candidates():
    """Подсказка по ID не должна протаскивать запись с чужим счётом."""
    pool = deque([_Op(2872, '1345'), _Op(500, None), _Op(600, None)])
    assert _take_from_pool(pool, '189', 600).id == 600
    # ID указывает на запись с чужим счётом — она всё равно не годится
    pool = deque([_Op(2872, '1345'), _Op(500, None)])
    assert _take_from_pool(pool, '189', 2872).id == 500


def test_id_is_used_when_the_invoice_does_not_help():
    pool = deque([_Op(2800, None), _Op(3017, None)])
    assert _take_from_pool(pool, None, 3017).id == 3017


def test_invoice_outranks_id():
    """Счёт осмыслен на любом стенде, id — только на своём, поэтому счёт важнее."""
    pool = deque([_Op(2800, '6'), _Op(3017, '8')])
    assert _take_from_pool(pool, '8', 2800).id == 3017


def test_foreign_id_does_not_reject_the_match():
    """Подсказка нестрогая: чужой номер не отменяет совпадения по существу.

    Иначе перенос между стендами (где номера ничего не значат) превращал бы
    каждую строку в новую — то есть ровно в дубль.
    """
    pool = deque([_Op(2800, None), _Op(3017, None)])
    assert _take_from_pool(pool, None, 999999).id == 2800     # самая ранняя


def test_id_alone_never_matches_anything():
    """ID не ищет по базе: он выбирает только среди уже совпавших.

    Пустой пул означает, что по содержательным полям не совпало ничего — и
    никакой ID этого изменить не может.
    """
    assert _take_from_pool(deque(), None, 3017) is None
    assert _take_from_pool(None, None, 3017) is None


def test_pool_entry_is_consumed_only_once():
    """N одинаковых строк файла не должны съесть одну и ту же запись базы."""
    pool = deque([_Op(1, '5'), _Op(2, '5')])
    first = _take_from_pool(pool, '5')
    second = _take_from_pool(pool, '5')
    assert {first.id, second.id} == {1, 2}
    assert _take_from_pool(pool, '5') is None


# ---- ID как колонка импорта ----

def test_id_column_is_recognised_but_optional():
    """Колонка ID читается, но её отсутствие не должно ломать старые файлы.

    В шаблоне массового импорта колонки ID нет вовсе — если op_id попадёт в
    обязательные, каждый такой файл начнёт отвергаться.
    """
    assert _CF_BEST_COLUMN_MAP.get('id') == 'op_id'
    assert 'op_id' not in _CF_BEST_REQUIRED_FIELDS
