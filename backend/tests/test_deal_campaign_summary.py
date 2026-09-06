# -*- coding: utf-8 -*-
"""Сводка РК на карточке сделки: появляется по факту, считает не сама.

Блок «Рекламная кампания» и предварительная сверка едят ОДИН ответ (владелец 05.09.2026),
поэтому важны два свойства: он не заводит собственной арифметики и честно молчит, пока
показывать нечего. Пустой блок из прочерков читается как поломка, а не как «ещё не
началось», — отсюда `has: false` с причиной словами.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.launch_prep.models  # noqa: F401
import app.ord.models          # noqa: F401
from app.ad.models import AdCampaign
from app.database import SessionLocal
from app.models import User
from app.routers import sales_dashboard as sd, traffic_dashboard as td


@pytest.fixture
def env():
    db = SessionLocal()
    u = db.query(User).filter(User.is_active == 1).order_by(User.id).first()
    if not u:
        db.close()
        pytest.skip('нужна активная учётка')
    actor = SimpleNamespace(id=u.id, name=u.name,
                            role=SimpleNamespace(key='admin', is_master=True))
    yield SimpleNamespace(db=db, user=actor)
    db.close()


def _rows(env):
    return td.dashboard(db=env.db, user=env.user, scope='all')['rows']


def test_block_is_silent_until_the_first_measurement(env):
    """Нет замеров — нет блока, и причина названа словами."""
    quiet = [r for r in _rows(env) if r['fact_shows'] is None]
    if not quiet:
        pytest.skip('на стенде все РК с фактом')
    out = sd.deal_campaign(quiet[0]['deal_code'], env.db, env.user)
    assert out['has'] is False and out['reason']


def test_numbers_match_the_traffic_dashboard_exactly(env):
    """Карточка и дашборд трафика показывают ОДНИ числа.

    Это и есть причина, по которой сводка не считает сама: два расчёта одного недокрута
    разошлись бы при первой правке порогов — как уже было со статусом площадки, который
    в реестре брался от пар, а в расхлопе от креативов.
    """
    live = [r for r in _rows(env) if r['fact_shows']]
    if not live:
        pytest.skip('на стенде нет РК с фактом')
    r = live[0]
    out = sd.deal_campaign(r['deal_code'], env.db, env.user)
    assert out['has'] is True
    for k in ('plan_show', 'fact_shows', 'under', 'forecast', 'pace', 'done_pct', 'days_left'):
        assert out[k] == r[k], f'{k}: карточка {out[k]} против дашборда {r[k]}'


def test_deal_without_a_campaign_says_so_and_does_not_fail(env):
    """Сделка без РК — это состояние, а не ошибка."""
    ids = {c.deal_id for c in env.db.query(AdCampaign).all()}
    from app.sales.models import SalesDeal
    free = (env.db.query(SalesDeal).filter(~SalesDeal.id.in_(ids or {0}))
            .order_by(SalesDeal.id).first())
    if not free:
        pytest.skip('все сделки с РК')
    out = sd.deal_campaign(str(free.id), env.db, env.user)
    assert out['has'] is False and 'РК' in out['reason']


def test_unknown_deal_is_404_not_500(env):
    with pytest.raises(HTTPException) as e:
        sd.deal_campaign(str(10 ** 9), env.db, env.user)
    assert e.value.status_code == 404


def test_endpoint_checks_deal_scope():
    """Ручка трогает сделку — значит спрашивает область видимости."""
    import inspect
    assert '_assert_deal_in_scope' in inspect.getsource(sd.deal_campaign)
