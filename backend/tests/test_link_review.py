"""Повторная проверка ссылки трафиком (23.11.2026).

Включается ТОЛЬКО когда ссылку у площадки запрашивали: тогда после её прихода у трафика
появляется строка `kind='ссылка'`, и ЕРИД ждёт его «ок». Без запроса строки нет и цепочка
остаётся трёхшаговой.
"""
from datetime import datetime

import pytest

from app.launch_prep.models import LaunchPrepPair, LaunchPrepReview, LaunchPrepSetTarget
from app.routers import launch_prep as lp
from app.routers import traffic
from tests.test_launch_prep_pairs import _ADMIN, env  # noqa: F401 — фикстура


def _pair(db, env, target):
    return db.query(LaunchPrepPair).filter_by(
        set_id=env.cset.id, target_id=target.id).first()


def test_link_review_created_on_link_arrival(env):
    db = env.db
    # Площадка 0 — с ЗАПРОСОМ ссылки и без ссылки (фикстура ставит ссылку всем).
    m = db.query(LaunchPrepSetTarget).filter_by(
        set_id=env.cset.id, target_id=env.targets[0].id).first()
    m.advertiser_url = None
    m.url_requested_at = datetime.utcnow()
    db.commit()

    lp.send_set(env.cset.id, lp.SendIn(), db, _ADMIN)
    pair = _pair(db, env, env.targets[0])
    traffic.pair_verdict(pair.id, traffic.VerdictIn(verdict='ок'), db, _ADMIN)
    # ссылки ещё нет — строки проверки нет
    assert not db.query(LaunchPrepReview).filter_by(
        pair_id=pair.id, kind='ссылка').first()

    lp.set_member_url(env.cset.id, env.targets[0].id,
                      lp.TargetUrlIn(url='https://site.test/tovar/2'), db, _ADMIN)

    rec = db.query(LaunchPrepReview).filter_by(pair_id=pair.id, kind='ссылка').first()
    assert rec is not None, 'ссылка пришла по запросу — трафик должен её проверить'
    assert rec.verdict is None, 'строка заводится пустой: «спросили, ответа нет»'
    assert rec.source == 'трафики'


def test_link_review_not_created_without_request(env):
    db = env.db
    lp.send_set(env.cset.id, lp.SendIn(), db, _ADMIN)
    pair = _pair(db, env, env.targets[1])
    traffic.pair_verdict(pair.id, traffic.VerdictIn(verdict='ок'), db, _ADMIN)
    # Ссылки у этой площадки не запрашивали — повторная проверка не нужна.
    lp.set_member_url(env.cset.id, env.targets[1].id,
                      lp.TargetUrlIn(url='https://site.test/other'), db, _ADMIN)
    assert not db.query(LaunchPrepReview).filter_by(
        pair_id=pair.id, kind='ссылка').first(), 'без запроса строки «ссылка» быть не должно'


def test_chain_status_with_link():
    """Статус: у трафика → у площадки → у трафика → согласовано (владелец 23.11.2026)."""
    from app.ad.flight import chain_status
    assert chain_status(None, None, True) == 'у трафика'
    assert chain_status('ок', None, True) == 'у площадки'
    assert chain_status('ок', 'ок', True) == 'ждёт запуска'              # ссылку не запрашивали
    assert chain_status('ок', None, True, link_pending=True) == 'у площадки'
    assert chain_status('ок', 'ок', True, link_pending=True) == 'у трафика'  # ссылка на проверке
    assert chain_status('ок', 'ок', True, link_pending=False) == 'ждёт запуска'


def test_agreement_waits_for_link(env):
    """«Ок» площадки не согласует пару, пока трафик не проверил ссылку; «ок» ссылки — согласует."""
    db = env.db
    m = db.query(LaunchPrepSetTarget).filter_by(
        set_id=env.cset.id, target_id=env.targets[0].id).first()
    m.advertiser_url = None
    m.url_requested_at = datetime.utcnow()
    db.commit()

    lp.send_set(env.cset.id, lp.SendIn(), db, _ADMIN)
    pair = _pair(db, env, env.targets[0])
    traffic.pair_verdict(pair.id, traffic.VerdictIn(verdict='ок'), db, _ADMIN)
    lp.set_member_url(env.cset.id, env.targets[0].id,
                      lp.TargetUrlIn(url='https://site.test/tovar/2'), db, _ADMIN)

    lp.apply_platform_verdict(db, pair.id, 'ок', None, 'площадка', None, 'кабинет', _ADMIN)
    db.refresh(pair)
    assert pair.agreed_at is None and pair.code is None, \
        'ссылка не проверена — пара не согласована'

    lp.apply_link_verdict(db, pair.id, 'ок', None, 'трафик', _ADMIN)
    db.refresh(pair)
    assert pair.agreed_at is not None and pair.code, 'ссылка проверена — пара согласована'


def _pending_link_pair(env):
    """Пара с пришедшей и НЕ проверенной ссылкой, площадка уже «ок»."""
    db = env.db
    m = db.query(LaunchPrepSetTarget).filter_by(
        set_id=env.cset.id, target_id=env.targets[0].id).first()
    m.advertiser_url = None
    m.url_requested_at = datetime.utcnow()
    db.commit()
    lp.send_set(env.cset.id, lp.SendIn(), db, _ADMIN)
    pair = _pair(db, env, env.targets[0])
    traffic.pair_verdict(pair.id, traffic.VerdictIn(verdict='ок'), db, _ADMIN)
    lp.set_member_url(env.cset.id, env.targets[0].id,
                      lp.TargetUrlIn(url='https://site.test/tovar/2'), db, _ADMIN)
    lp.apply_platform_verdict(db, pair.id, 'ок', None, 'площадка', None, 'кабинет', _ADMIN)
    return pair


def test_erid_blocked_while_link_pending(env):
    """Маркер не выпускается, пока ссылку не проверил трафик (23.11.2026)."""
    from fastapi import HTTPException
    from app.launch_prep import erid_service
    pair = _pending_link_pair(env)
    with pytest.raises(HTTPException) as e:
        erid_service.issue_marker_for_set(env.db, env.cset, env.deal, _ADMIN)
    assert 'Ссылку проверяет трафик' in str(e.value.detail)
    # проверили ссылку — гейт по ссылке больше не срабатывает (дальше уже ОРД/цепочка)
    lp.apply_link_verdict(env.db, pair.id, 'ок', None, 'трафик', _ADMIN)
    try:
        erid_service.issue_marker_for_set(env.db, env.cset, env.deal, _ADMIN)
    except HTTPException as ex:
        assert 'Ссылку проверяет трафик' not in str(ex.detail)


