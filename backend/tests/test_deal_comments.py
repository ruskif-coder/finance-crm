# -*- coding: utf-8 -*-
"""Комментарии сделки: лента, права и область видимости.

Лента отдельна от истории (владелец 05.09.2026) и не редактируется: каждая запись —
свидетельство о том, кто что и когда сказал. Проверяем именно это, а не CRUD вообще.
"""
from types import SimpleNamespace

import pytest

import app.launch_prep.models  # noqa: F401
import app.ord.models          # noqa: F401
from app.database import SessionLocal
from app.models import User
from app.routers import sales_dashboard as sd
from app.sales.models import SalesDeal, SalesDealComment


@pytest.fixture
def env():
    db = SessionLocal()
    deal = db.query(SalesDeal).order_by(SalesDeal.id).first()
    user = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
    if not deal or not user:
        db.close()
        pytest.skip('нужны сделка и активная учётка')
    made = []
    yield SimpleNamespace(db=db, deal=deal, user=user, made=made)
    for c in made:
        db.query(SalesDealComment).filter(SalesDealComment.id == c).delete()
    db.commit()
    db.close()


def test_comment_is_a_record_with_an_author_and_a_moment(env):
    """Запись несёт автора и время — иначе лента не свидетельство, а текст.

    Автор — УЧЁТКА: профиль ответственного есть не у всех, он заводится только при
    назначении, и комментарий человека без профиля остался бы без имени.
    """
    out = sd.add_deal_comment(str(env.deal.id), sd.CommentIn(text='  проверка  '),
                              env.db, env.user)
    env.made.append(out['id'])
    assert out['text'] == 'проверка', 'пробелы по краям срезаются'
    assert out['user_id'] == env.user.id and out['author']
    assert out['at']


def test_feed_is_newest_first_and_each_send_is_its_own_row(env):
    """«Каждый новый отдельной записью»: вторая отправка НЕ дописывает первую."""
    a = sd.add_deal_comment(str(env.deal.id), sd.CommentIn(text='первый'), env.db, env.user)
    b = sd.add_deal_comment(str(env.deal.id), sd.CommentIn(text='второй'), env.db, env.user)
    env.made += [a['id'], b['id']]
    items = sd.list_deal_comments(str(env.deal.id), env.db, env.user)['items']
    texts = [i['text'] for i in items]
    assert texts[:2] == ['второй', 'первый'], 'свежие сверху, и это две разные строки'
    assert a['id'] != b['id']


def test_empty_and_oversized_comments_are_refused(env):
    """Пустая строка в неудаляемой ленте — мусор навсегда, поэтому её не заводим."""
    from fastapi import HTTPException
    for bad in ('', '   ', chr(10) + chr(9) + ' '):
        with pytest.raises(HTTPException) as e:
            sd.add_deal_comment(str(env.deal.id), sd.CommentIn(text=bad), env.db, env.user)
        assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        sd.add_deal_comment(str(env.deal.id), sd.CommentIn(text='x' * 4001), env.db, env.user)
    assert e.value.status_code == 400


def test_comments_are_not_editable_by_design():
    """Правки и удаления нет — и это должно оставаться видимым решением, а не забывчивостью.

    Прибор упадёт, если кто-то заведёт ручку правки: тогда решение придётся принять
    заново и записать, а не получить молча.
    """
    verbs = set()
    for r in sd.router.routes:
        if 'comments' in getattr(r, 'path', ''):
            verbs |= set(getattr(r, 'methods', set()) or set())
    assert verbs == {'GET', 'POST'}, f'у ленты появились лишние глаголы: {verbs}'


def test_comment_endpoints_check_deal_scope():
    """Ручки трогают сделку — значит обязаны спрашивать область видимости.

    Тот же прибор, что `test_deal_scope` держит для остальных: маршрут, трогающий
    сделку без проверки, считается дырой по умолчанию.
    """
    import inspect
    for fn in (sd.add_deal_comment, sd.list_deal_comments):
        src = inspect.getsource(fn)
        assert '_assert_deal_in_scope' in src, fn.__name__
