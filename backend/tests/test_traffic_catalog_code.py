# -*- coding: utf-8 -*-
"""Буквенный код площадки: уникален и нормализован.

Код — СРЕДНЯЯ ЧАСТЬ кода пары размещения («HCLA6E-MKS-01»). Два одинаковых кода означают
два разных размещения с одним именем, и разобрать их постфактум нельзя — ни в нашей базе,
ни в отчёте площадки. Поэтому уникальность держится ручкой, а не только глазами в форме:
проверка, оставленная фронту, — это отсутствие проверки.

Замерено 05.09.2026: код не задан у 14 площадок из 41, дублей нет.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.launch_prep.models  # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.routers import traffic_catalog as tc
from app.sales.models import SalesPublisher


@pytest.fixture
def env():
    db = SessionLocal()
    pubs = db.query(SalesPublisher).order_by(SalesPublisher.id).limit(2).all()
    if len(pubs) < 2:
        db.close()
        pytest.skip('нужны две площадки')
    a, b = pubs
    was = (a.code, b.code)
    user = SimpleNamespace(id=1, name='тест', role=SimpleNamespace(key='admin', is_master=True))
    yield SimpleNamespace(db=db, a=a, b=b, user=user)
    a.code, b.code = was
    db.commit()
    db.close()


def test_code_is_normalised_before_saving(env):
    """«  mks » и «MKS» — один код. Без нормализации дубль проходит мимо проверки."""
    tc.edit_publisher_code(env.a.id, tc.PublisherCode(code='  mks '), env.db, env.user)
    env.db.refresh(env.a)
    assert env.a.code == 'MKS'


def test_same_code_on_another_publisher_is_refused(env):
    """Дубль по ДРУГИМ площадкам отбивается, и в отказе названа занявшая."""
    tc.edit_publisher_code(env.a.id, tc.PublisherCode(code='ZZQ'), env.db, env.user)
    with pytest.raises(HTTPException) as e:
        tc.edit_publisher_code(env.b.id, tc.PublisherCode(code='zzq'), env.db, env.user)
    assert e.value.status_code == 409
    assert env.a.name in str(e.value.detail), 'отказ обязан назвать, кто занял код'


def test_saving_its_own_code_again_is_not_a_duplicate(env):
    """Повторное сохранение своего же кода — не дубль: иначе форма не сохраняется вовсе."""
    tc.edit_publisher_code(env.a.id, tc.PublisherCode(code='ZZQ'), env.db, env.user)
    tc.edit_publisher_code(env.a.id, tc.PublisherCode(code='ZZQ'), env.db, env.user)
    env.db.refresh(env.a)
    assert env.a.code == 'ZZQ'


def test_empty_code_clears_it_and_is_allowed_on_many(env):
    """Пустой код — законное состояние (14 площадок из 41 на 05.09.2026), и он НЕ дубль.

    Иначе вторая площадка без кода не сохранилась бы: пустота уникальной быть не может.
    """
    tc.edit_publisher_code(env.a.id, tc.PublisherCode(code='  '), env.db, env.user)
    tc.edit_publisher_code(env.b.id, tc.PublisherCode(code=None), env.db, env.user)
    env.db.refresh(env.a)
    env.db.refresh(env.b)
    assert env.a.code is None and env.b.code is None
