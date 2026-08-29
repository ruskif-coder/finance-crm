"""Поля маркировки в справочниках: проверки, которые иначе всплывут в ОРД.

Все три поля этого этапа объединяет одно: **ошибка в них обнаруживается не там, где её
допустили.** Код площадки уезжает в DSP внутри кода пары, ККТУ и описание — в тело
креатива при выпуске ЕРИД. Отказ приходит через дни, на другом экране, другому человеку,
и по формулировке реестра не всегда понятно, какое поле виновато.

Поэтому проверки стоят на входе, а тесты — на проверках.

Эндпоинты вызываются напрямую с фиктивным admin-пользователем: тот же приём, что в
test_ord_http.py, — без поднятия HTTP-слоя и без обхода прав.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.routers.publishers import _clean_code
from app.routers.sales_directories import BrandMarkingIn, set_brand_marking
from app.sales.models import SalesBrand, SalesPublisher

# `name` и `id` нужны журналу действий: log_action читает их у пользователя, и без них
# падает не проверка, а запись в аудит — то есть тест краснеет не по делу.
_FAKE_ADMIN = SimpleNamespace(role=SimpleNamespace(key='admin'), id=None,
                              email='test', name='тест')


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ── код площадки ─────────────────────────────────────────────────────────────
def test_code_is_uppercased(db):
    """Код собирается в строку с кодом сделки — регистр обязан быть один.

    Значение заведомо несуществующее: первая редакция брала правдоподобный «MKS» и
    покраснела в тот день, когда владелец проставил коды площадкам — Максавит занял
    именно его. Тест на форматирование не должен зависеть от содержимого справочника.
    """
    assert _clean_code(db, ' zzq9 ') == 'ZZQ9'


def test_dash_in_code_is_refused(db):
    """Дефис — разделитель в коде пары HCLA6E-MKS-01: внутри кода он разъедет разбор."""
    with pytest.raises(HTTPException) as e:
        _clean_code(db, 'MK-S')
    assert 'дефис' in e.value.detail.lower()


def test_cyrillic_code_is_refused(db):
    """Код читают в чужих системах, где кириллица ломается."""
    with pytest.raises(HTTPException):
        _clean_code(db, 'МКС')          # кириллические М, К, С


def test_empty_code_is_none_not_error(db):
    """Пустой код — законное состояние: 41 площадку заполняют руками не за один день."""
    assert _clean_code(db, '') is None
    assert _clean_code(db, None) is None


def test_taken_code_is_refused_with_the_name_of_its_owner(db):
    """Сообщение обязано называть площадку: «код занят» без имени не подсказывает выход."""
    taken = db.query(SalesPublisher).filter(SalesPublisher.code.isnot(None)).first()
    if taken is None:
        pytest.skip("ни у одной площадки код ещё не проставлен")
    with pytest.raises(HTTPException) as e:
        _clean_code(db, taken.code)
    assert taken.name in e.value.detail


def test_publisher_may_keep_its_own_code_on_edit(db):
    """Правка карточки не должна ругаться на собственный код площадки."""
    taken = db.query(SalesPublisher).filter(SalesPublisher.code.isnot(None)).first()
    if taken is None:
        pytest.skip("ни у одной площадки код ещё не проставлен")
    assert _clean_code(db, taken.code, current_id=taken.id) == taken.code


# ── маркировка бренда ────────────────────────────────────────────────────────
@pytest.fixture
def brand(db):
    row = db.query(SalesBrand).first()
    if row is None:
        pytest.skip("в базе нет ни одного бренда")
    before = (row.kktu_code, row.ad_object_description)
    yield row
    row.kktu_code, row.ad_object_description = before
    db.commit()


def test_kktu_must_be_third_level(db, brand):
    """Реестр принимает только коды третьего уровня — «58.13» отклонится уже там."""
    with pytest.raises(HTTPException) as e:
        set_brand_marking(brand.id, BrandMarkingIn(kktu_code='58.13'), db, _FAKE_ADMIN)
    assert 'третий уровень' in e.value.detail

    out = set_brand_marking(brand.id, BrandMarkingIn(kktu_code='58.13.12'), db, _FAKE_ADMIN)
    assert out['kktu_code'] == '58.13.12'


def test_empty_kktu_clears_the_field(db, brand):
    """Пустая строка значит «не задано», а не значение из пробелов."""
    set_brand_marking(brand.id, BrandMarkingIn(kktu_code='58.13.12'), db, _FAKE_ADMIN)
    out = set_brand_marking(brand.id, BrandMarkingIn(kktu_code='  '), db, _FAKE_ADMIN)
    assert out['kktu_code'] is None


def test_description_over_1000_is_refused(db, brand):
    """Ограничение схемы ОРД: 1–1000 знаков."""
    with pytest.raises(HTTPException) as e:
        set_brand_marking(brand.id, BrandMarkingIn(ad_object_description='x' * 1001),
                          db, _FAKE_ADMIN)
    assert '1000' in e.value.detail


def test_marking_fields_are_independent(db, brand):
    """Правка одного поля не обнуляет второе: exclude_unset, а не полный объект."""
    set_brand_marking(brand.id, BrandMarkingIn(kktu_code='58.13.12',
                                               ad_object_description='описание'),
                      db, _FAKE_ADMIN)
    out = set_brand_marking(brand.id, BrandMarkingIn(kktu_code='58.13.13'), db, _FAKE_ADMIN)
    assert out['ad_object_description'] == 'описание', (
        "описание обнулилось при правке одного лишь кода")


# ── посадочная страница сделки ───────────────────────────────────────────────
def test_our_string_fields_are_kept_apart_from_boolean_ones():
    """Пин на разведение списков: EDITABLE_OURS приводит значение к bool.

    Список строковых полей сейчас пуст — посадочная страница уехала на получателя, — но
    сам он остаётся: первое же строковое поле, попавшее в булев список, молча станет
    True, и заметят это не там, где ошиблись.
    """
    from app.routers.sales_dashboard import EDITABLE_OURS, EDITABLE_OURS_STR
    assert not set(EDITABLE_OURS) & set(EDITABLE_OURS_STR)
    assert 'advertiser_url' not in EDITABLE_OURS, (
        "ссылка живёт на получателе, а в булевом списке молча стала бы True")
