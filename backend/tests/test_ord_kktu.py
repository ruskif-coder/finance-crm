"""Справочник ККТУ: зеркало ОРД и выбор кода на карточке бренда.

Что здесь стережётся и почему именно это:

  · **формат кодов справочника совпадает с нашей проверкой.** Код ККТУ проверяется
    регуляркой при сохранении бренда, а приходит из чужого классификатора. Разойдись
    они — человек выберет код из списка, а сохранение его отклонит; либо, что хуже,
    примет код, который ОРД потом не возьмёт, и отказ придёт на этапе выпуска маркера,
    когда комплект уже собран. Прибор сверяет РЕАЛЬНОЕ содержимое зеркала с ТОЙ ЖЕ
    константой, которую читает эндпоинт, а не с её копией;
  · **ручка отдаёт только третий уровень.** Первые два в списке выбора выглядели бы
    допустимыми вариантами, каковыми не являются;
  · **апсерт не плодит дублей и не стирает пропавшее** — синк запускают повторно, и
    «обновилось 407 из 407» на неизменившемся справочнике означало бы, что мы пишем
    без нужды и не заметим настоящего изменения;
  · **незалитое зеркало не ломает экран.** `synced=false` — это «справочник не заливали»,
    и ручной ввод в карточке бренда должен остаться рабочим.

Сеть не трогается: справочник подставляется вместо транспорта, как в соседних
test_ord_*.py. Живой прогон против demo.mediascout.ru делается руками.
"""
import re
from types import SimpleNamespace

import pytest

from app.database import SessionLocal
from app.ord import sync
from app.ord.models import OrdKktu
from app.routers.sales_directories import KKTU_CODE_RE, list_kktu

_FAKE_ADMIN = SimpleNamespace(role=SimpleNamespace(key='admin'))

# Коды, которых в настоящем классификаторе нет: 900-я группа свободна, и своё от
# чужого отличается с одного взгляда.
FAKE = [
    {'code': '900', 'level': 1, 'parentCode': None, 'name': 'Тестовая группа'},
    {'code': '900.1', 'level': 2, 'parentCode': '900', 'name': 'Тестовая подгруппа'},
    {'code': '900.1.1', 'level': 3, 'parentCode': '900.1', 'name': 'Тестовый товар'},
    {'code': '900.1.2', 'level': 3, 'parentCode': '900.1', 'name': 'Другой тестовый'},
]


@pytest.fixture
def db():
    session = SessionLocal()
    _purge(session)
    try:
        yield session
    finally:
        _purge(session)
        session.close()


def _purge(session):
    session.rollback()
    session.query(OrdKktu).filter(OrdKktu.code.like('900%')).delete(
        synchronize_session=False)
    session.commit()


@pytest.fixture
def fake_ord(monkeypatch):
    """Подменить транспорт: справочник отдаётся из списка, сеть не трогается."""
    def fake_get(path, params=None):
        assert path == '/webapi/v3/dictionaries/kktu', f"неожиданный запрос: {path}"
        return list(FAKE)
    monkeypatch.setattr(sync.client, 'get', fake_get)
    monkeypatch.setattr(sync.client, 'env', lambda: 'demo')


# ── зеркало ──────────────────────────────────────────────────────────────────
def test_sync_writes_all_levels_and_is_idempotent(db, fake_ord):
    first = sync.sync_kktu(db)
    assert first['added'] == 4 and first['updated'] == 0
    assert first['by_level'] == {1: 1, 2: 1, 3: 2}

    second = sync.sync_kktu(db)
    assert second['added'] == 0, "повторный синк завёл дубли"
    assert second['updated'] == 0, (
        "неизменившийся справочник числится обновлённым — настоящее изменение "
        "потеряется в шуме")


def test_sync_keeps_codes_that_vanished_from_ord(db, fake_ord, monkeypatch):
    """Исчезнувший код остаётся: он уже проставлен у брендов и уехал в ЕРИР."""
    sync.sync_kktu(db)
    monkeypatch.setattr(sync.client, 'get', lambda p, params=None: FAKE[:3])
    sync.sync_kktu(db)

    assert db.query(OrdKktu).filter(OrdKktu.code == '900.1.2').first() is not None, (
        "код удалён из зеркала — расшифровка уже отправленного в ЕРИР потеряна")


def test_row_without_level_is_skipped_not_guessed(db, monkeypatch):
    """Строка без уровня — непонятная, а не пустая: угадывать уровень нельзя."""
    monkeypatch.setattr(sync.client, 'get', lambda p, params=None: [
        {'code': '900.9.9', 'name': 'Без уровня', 'parentCode': '900.9'}])
    monkeypatch.setattr(sync.client, 'env', lambda: 'demo')
    report = sync.sync_kktu(db)

    assert report['added'] == 0 and len(report['skipped']) == 1
    assert db.query(OrdKktu).filter(OrdKktu.code == '900.9.9').first() is None


# ── ручка выбора ─────────────────────────────────────────────────────────────
def test_lookup_returns_only_third_level(db, fake_ord):
    sync.sync_kktu(db)
    answer = list_kktu(q='900', db=db, current_user=_FAKE_ADMIN)

    levels = {row['code'].count('.') for row in answer['items']}
    assert levels == {2}, "в выборе оказался код не третьего уровня"
    assert {r['code'] for r in answer['items']} == {'900.1.1', '900.1.2'}


def test_lookup_finds_by_code_by_name_and_by_parent(db, fake_ord):
    sync.sync_kktu(db)

    by_code = list_kktu(q='900.1.1', db=db, current_user=_FAKE_ADMIN)['items']
    assert [r['code'] for r in by_code] == ['900.1.1']

    by_name = list_kktu(q='ТЕСТОВЫЙ ТОВАР', db=db, current_user=_FAKE_ADMIN)['items']
    assert [r['code'] for r in by_name] == ['900.1.1'], "поиск чувствителен к регистру"

    by_parent = list_kktu(q='подгруппа', db=db, current_user=_FAKE_ADMIN)['items']
    assert {r['code'] for r in by_parent} == {'900.1.1', '900.1.2'}, (
        "поиск по имени родителя не работает — «лекарства» не приведут к своим товарам")


def test_lookup_carries_parent_name_as_path(db, fake_ord):
    sync.sync_kktu(db)
    row = next(r for r in list_kktu(q='900.1.1', db=db, current_user=_FAKE_ADMIN)['items'])
    assert row['path'] == 'Тестовая подгруппа', (
        "без подписи родителя пять похожих названий фармы неразличимы")


def test_empty_mirror_says_not_synced_instead_of_failing():
    """Незалитое зеркало обязано оставить ручной ввод, а не отнять его."""
    class _Empty:
        def query(self, *a, **k): return self
        def filter(self, *a, **k): return self
        def order_by(self, *a, **k): return self
        def all(self): return []

    answer = list_kktu(q=None, db=_Empty(), current_user=_FAKE_ADMIN)
    assert answer['synced'] is False and answer['items'] == []


# ── шов между справочником и проверкой бренда ────────────────────────────────
def test_every_real_third_level_code_passes_brand_validation():
    """Реальное зеркало против ТОЙ ЖЕ константы, что читает сохранение бренда.

    Прибор пропускается, если справочник не залит, — и это честно: проверять нечего.
    """
    session = SessionLocal()
    try:
        rows = (session.query(OrdKktu.code)
                       .filter(OrdKktu.level == 3, ~OrdKktu.code.like('900%')).all())
    finally:
        session.close()
    if not rows:
        pytest.skip("справочник ККТУ не залит — сверять нечего")

    bad = [code for (code,) in rows if not re.fullmatch(KKTU_CODE_RE, code)]
    assert not bad, (
        f"{len(bad)} кодов справочника не проходят нашу проверку формата: {bad[:5]}. "
        "Человек выберет их из списка, а сохранение бренда отклонит")
