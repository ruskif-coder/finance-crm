"""Ответ за площадку и перевод площадки — только администратор (владелец 26.09.2026).

У аккаунта в строке площадки одно действие — «Доработка»; остальное вне его зоны.
Экран прятал кнопки от всех, кроме администратора, но сервер пускал по правам
«Креативы — согласование / правка», а они у аккаунтов есть (на них же первичная проверка
и загрузка). Кнопку можно спрятать — запрос нет, поэтому запрет стоит в ручке.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.launch_prep.models import LaunchPrepPair, LaunchPrepReview, LaunchPrepTarget
from app.routers import launch_prep as lp
from tests.test_launch_prep_pairs import _ADMIN, env  # noqa: F401

ACCOUNT = SimpleNamespace(role=SimpleNamespace(key='role_8'), id=None, name='аккаунт')


def _pair(env):  # noqa: F811
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    p = (env.db.query(LaunchPrepPair).filter(LaunchPrepPair.set_id == env.cset.id)
         .order_by(LaunchPrepPair.id).first())
    if p is None:
        pytest.skip('у креатива фикстуры нет пары')
    return p


def test_account_cannot_answer_for_the_publisher(env):  # noqa: F811
    p = _pair(env)
    def reviews():
        return env.db.query(LaunchPrepReview).filter(LaunchPrepReview.pair_id == p.id).count()
    before = reviews()
    with pytest.raises(HTTPException) as e:
        lp.pair_verdict(p.id, lp.PairVerdictIn(verdict='ок'), env.db, ACCOUNT)
    assert e.value.status_code == 403
    assert reviews() == before, "отказ после записи — запись уже случилась"


def test_account_cannot_move_the_publisher(env):  # noqa: F811
    t = env.db.query(LaunchPrepTarget).filter(LaunchPrepTarget.deal_id == env.deal.id).first()
    if t is None:
        pytest.skip('нет площадки')
    before = t.state
    with pytest.raises(HTTPException) as e:
        lp.move_target(t.id, lp.TargetStateIn(state='заведён в DSP'), env.db, ACCOUNT)
    assert e.value.status_code == 403
    env.db.refresh(t)
    assert t.state == before
