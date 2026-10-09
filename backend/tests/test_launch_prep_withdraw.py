# -*- coding: utf-8 -*-
"""Отзыв креатива у площадки до запуска её размещения (владелец 28.09.2026).

Решения: граница — размещение площадки (не РК), даже если креатив уже в DSP; отзывать
можно и согласованное; только мастер аккаунтов; площадке — сразу и с причиной; вернуть
нельзя — только новым креативом.

Приборы держат последствия, а не только запись: отозванная пара выходит из порога ЕРИД,
не принимает ответ площадки, креатив РК — «отклонён» и площадку с ним не запустить,
заведённый в DSP креатив уходит в архив, а сбой DSP отзыв не откатывает.
"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.main  # noqa: F401 — реестр моделей целиком (FK на users, sales_deals)
from sqlalchemy import text

from app.ad.flight import can_start_placement
from app.database import SessionLocal
from app.launch_prep import withdraw as W
from app.launch_prep.models import (LaunchPrepCreativeSet, LaunchPrepPair, LaunchPrepReview,
                                    LaunchPrepSetTarget, LaunchPrepTarget)
from app.ord import models as _ord_models   # noqa: F401  (маппер sales_deals → ord_*)
from app.sales.models import SalesDeal, SalesPublisher, SalesService

NO = 9600           # номер комплекта теста — заведомо выше рабочих


def _purge(db):
    db.rollback()
    ids = [s.id for s in db.query(LaunchPrepCreativeSet).filter(LaunchPrepCreativeSet.no == NO)]
    if ids:
        pairs = db.query(LaunchPrepPair).filter(LaunchPrepPair.set_id.in_(ids)).all()
        tids = {p.target_id for p in pairs}
        pids = [p.id for p in pairs]
        if pids:
            db.query(LaunchPrepReview).filter(
                LaunchPrepReview.pair_id.in_(pids)).delete(synchronize_session=False)
        db.query(LaunchPrepPair).filter(
            LaunchPrepPair.set_id.in_(ids)).delete(synchronize_session=False)
        db.query(LaunchPrepSetTarget).filter(
            LaunchPrepSetTarget.set_id.in_(ids)).delete(synchronize_session=False)
        db.query(LaunchPrepCreativeSet).filter(
            LaunchPrepCreativeSet.id.in_(ids)).delete(synchronize_session=False)
        if tids:
            db.query(LaunchPrepTarget).filter(
                LaunchPrepTarget.id.in_(tids)).delete(synchronize_session=False)
    db.commit()


@pytest.fixture()
def env(monkeypatch):
    """Свой комплект, отправленный площадке: трафик сказал «ок», площадка молчит.

    РК, DSP и рассылка подменены — отзыв проверяется сам, без чужих систем и без писем
    живым площадкам стенда."""
    db = SessionLocal()
    _purge(db)
    # Сделка БЕЗ целей запуска и с порядком по id: `.first()` без order_by отдавал разные
    # строки после любого UPDATE, и 09.10.2026 фикстура упёрлась в живую пару сделка×площадка
    # (uq_launch_prep_target). Чужих данных фикстура не трогает — берёт чистую сделку.
    busy = db.query(LaunchPrepTarget.deal_id)
    deal = (db.query(SalesDeal).filter(SalesDeal.code.isnot(None), ~SalesDeal.id.in_(busy))
            .order_by(SalesDeal.id).first())
    pub = db.query(SalesPublisher).filter(SalesPublisher.status != 'АРХИВ').first()
    service = db.query(SalesService).filter(SalesService.is_active.is_(True)).first()
    if not (deal and pub and service):
        db.close()
        pytest.skip('нужна сделка с кодом, площадка и услуга')
    s = LaunchPrepCreativeSet(deal_id=deal.id, no=NO, origin='первичный')
    db.add(s)
    db.flush()
    t = LaunchPrepTarget(deal_id=deal.id, publisher_id=pub.id, service_id=service.id,
                         surface_kind='web', state='согласование')
    db.add(t)
    db.flush()
    pair = LaunchPrepPair(set_id=s.id, target_id=t.id, sent_at=datetime.utcnow())
    db.add(pair)
    db.flush()
    db.add(LaunchPrepReview(set_id=s.id, pair_id=pair.id, kind='трафики', verdict='ок',
                            source='трафики'))
    db.add(LaunchPrepReview(set_id=s.id, pair_id=pair.id, kind='площадка', source='аккаунт'))
    db.commit()

    state = SimpleNamespace(placement=None, row=None, told=[], archived=[])
    monkeypatch.setattr(W, '_placement', lambda db_, target: state.placement)
    monkeypatch.setattr(W, '_creative_row', lambda db_, p, target: state.row)
    monkeypatch.setattr(W, '_tell_publisher',
                        lambda db_, p, s_, t_, reason: state.told.append(reason) or {'status': 'sent'})
    from app.ad import build
    monkeypatch.setattr(build, 'sync_deal_quietly', lambda db_, deal_id: None)
    try:
        yield SimpleNamespace(db=db, set=s, target=t, pair=pair, state=state)
    finally:
        _purge(db)
        db.close()


MASTER = SimpleNamespace(id=None, name='тест отзыва', role=SimpleNamespace(key='admin'))


def test_withdraw_takes_pair_out_of_everything(env):
    from app.routers.launch_prep import active_pairs
    db = env.db
    assert [p.id for p in active_pairs(db, env.set.id)] == [env.pair.id]
    out = W.withdraw(db, env.pair.id, MASTER, '  бренд снял товар  ')
    db.refresh(env.pair)
    assert env.pair.withdrawn_at is not None and env.pair.withdraw_reason == 'бренд снял товар'
    assert active_pairs(db, env.set.id) == [], 'отозванная пара держит порог ЕРИД'
    assert env.state.told == ['бренд снял товар'], 'площадке не сказали или без причины'
    assert out['dsp'] == {'state': 'none'} and out['publisher_notified'] == 'sent'


def test_publisher_cannot_answer_withdrawn(env):
    from app.routers.launch_prep import apply_platform_verdict
    W.withdraw(env.db, env.pair.id, MASTER, 'замена')
    with pytest.raises(HTTPException) as e:
        apply_platform_verdict(env.db, env.pair.id, 'ок', None, 'площадка', None, 'кабинет')
    assert e.value.status_code == 409


def test_agreed_can_be_withdrawn_and_target_steps_back(env):
    db = env.db
    env.pair.agreed_at = datetime.utcnow()
    env.target.state = 'ерид получен'
    db.execute(text("UPDATE launch_prep_review SET verdict = 'ок' WHERE pair_id = :p "
                    "AND kind = 'площадка'"), {'p': env.pair.id})
    db.commit()
    W.withdraw(db, env.pair.id, MASTER, 'замена материала')
    db.refresh(env.target)
    assert env.target.state == 'согласование', 'получатель остался согласованным без пары'


def test_creative_in_dsp_goes_to_archive_and_row_is_rejected(env):
    row = SimpleNamespace(id=77, ms_creative_xxhash='ABCDEF0123456789', status='согласован')
    env.state.row = row
    calls = []

    class Ms:
        def creative_set_status(self, xx, st, local_ref=None):
            calls.append((xx, st, local_ref))
    out = W.withdraw(env.db, env.pair.id, MASTER, 'замена', dsp_client=Ms())
    assert row.status == 'отклонён'
    assert calls == [('ABCDEF0123456789', 'ARCHIVE', 'cr77')]
    assert out['dsp']['state'] == 'archived'


def test_dsp_failure_does_not_undo_withdraw(env):
    from app.dsp.client import MsError
    env.state.row = SimpleNamespace(id=78, ms_creative_xxhash='ABCDEF0123456780', status='согласован')

    class Ms:
        def creative_set_status(self, *a, **k):
            raise MsError('Creative.setStatus: timeout')
    out = W.withdraw(env.db, env.pair.id, MASTER, 'замена', dsp_client=Ms())
    env.db.refresh(env.pair)
    assert env.pair.withdrawn_at is not None
    assert out['dsp']['state'] == 'error' and 'timeout' in out['dsp']['why']


@pytest.mark.parametrize('setup,why', [
    (lambda e: setattr(e.pair, 'sent_at', None), 'у трафика'),
    (lambda e: setattr(e.target, 'state', 'в размещении'), 'запущено'),
    (lambda e: setattr(e.state, 'placement', SimpleNamespace(status='пауза')), 'запущено'),
    (lambda e: setattr(e.pair, 'withdrawn_at', datetime.utcnow()), 'уже отозван'),
])
def test_blockers(env, setup, why):
    setup(env)
    env.db.commit()
    with pytest.raises(W.WithdrawError) as e:
        W.withdraw(env.db, env.pair.id, MASTER, 'причина')
    assert why in str(e.value)


def test_refused_pair_is_not_withdrawn(env):
    env.db.execute(text("UPDATE launch_prep_review SET verdict = 'отказ' WHERE pair_id = :p "
                        "AND kind = 'площадка'"), {'p': env.pair.id})
    env.db.commit()
    with pytest.raises(W.WithdrawError, match='отказалась'):
        W.withdraw(env.db, env.pair.id, MASTER, 'причина')


def test_reason_is_required(env):
    with pytest.raises(W.WithdrawError, match='причину'):
        W.withdraw(env.db, env.pair.id, MASTER, '   ')


def test_only_account_master_may_withdraw():
    from app.routers.launch_prep import WithdrawIn, withdraw_pair
    for key, master, group in (('role_8', False, 'account'), ('role_12', True, 'traffic')):
        user = SimpleNamespace(id=1, role=SimpleNamespace(key=key, is_master=master,
                                                          staff_group=group))
        with pytest.raises(HTTPException) as e:
            withdraw_pair(1, WithdrawIn(reason='x'), db=None, current_user=user)
        assert e.value.status_code == 403


def test_rejected_creative_does_not_let_placement_start():
    assert not can_start_placement(['отклонён'])
    assert not can_start_placement(['отклонён', 'у площадки'])
    assert can_start_placement(['отклонён', 'согласован'])


def test_cabinet_views_hide_withdrawn():
    db = SessionLocal()
    try:
        for view in ('pub.task_v1', 'pub.campaign_v1'):
            assert db.execute(text(f"SELECT pg_get_viewdef('{view}') ~ 'withdrawn_at'")).scalar(), \
                f'{view} показывает площадке отозванное'
    finally:
        db.close()


def test_sync_marks_withdrawn_creative_rejected():
    import inspect

    from app.ad import build
    src = inspect.getsource(build.sync_creatives)
    assert 'pr.withdrawn_at' in src and 'r.get("withdrawn_at")' in src
