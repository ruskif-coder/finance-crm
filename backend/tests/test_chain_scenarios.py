"""Сквозные сценарии конвейера креатива: аккаунт → трафик → площадка → ЕРИД.

Каждый сценарий — свежий комплект (фикстура `env` чистит за собой) и реальные ручки,
а не вставки строк: проверяется то, как система ПРОВОДИТ крео, а не наше представление.

Статус креатива считается тем же правилом, что синк (`flight.chain_status`), поэтому
сценарии падают, если разъедется сама логика «у кого мяч», а не только цифры.
"""
# ruff: noqa: F811 — фикстура импортируется из соседнего файла (имя = аргумент теста).
from datetime import datetime

from fastapi import HTTPException

from app.ad.flight import chain_status
from app.launch_prep import erid_service
from app.launch_prep.models import (LaunchPrepPair, LaunchPrepReview,
                                    LaunchPrepSetTarget, LaunchPrepTarget)
from app.routers import launch_prep as lp
from app.routers import traffic
from tests.test_launch_prep_pairs import _ADMIN, env  # noqa: F401 — фикстура

LANDING = 'https://demo.test/tovar/1'


def _pair(db, env, i=0):
    return db.query(LaunchPrepPair).filter_by(
        set_id=env.cset.id, target_id=env.targets[i].id).first()


def _status(db, env, i=0):
    """Статус КРЕАТИВА пары — как в синке: «ждёт запуска» → «согласован»."""
    p = _pair(db, env, i)
    if p is None:
        return 'у трафика'
    tr = db.query(LaunchPrepReview).filter_by(pair_id=p.id, kind='трафики').first()
    pv = db.query(LaunchPrepReview).filter_by(pair_id=p.id, kind='площадка').first()
    lk = db.query(LaunchPrepReview).filter_by(pair_id=p.id, kind='ссылка').first()
    chain = chain_status(tr.verdict if tr else None, pv.verdict if pv else None,
                         has_pair=True,
                         link_pending=bool(lk is not None and lk.verdict != 'ок'))
    return 'согласован' if chain == 'ждёт запуска' else chain


def _with_request(env, i=0):
    """Посадочную у площадки ЗАПРОСИЛИ — ссылки ещё нет."""
    m = env.db.query(LaunchPrepSetTarget).filter_by(
        set_id=env.cset.id, target_id=env.targets[i].id).first()
    m.advertiser_url = None
    m.url_requested_at = datetime.utcnow()
    env.db.commit()


def _traffic_ok(db, env, i=0):
    traffic.pair_verdict(_pair(db, env, i).id, traffic.VerdictIn(verdict='ок'), db, _ADMIN)


def _publisher(db, env, verdict, i=0, reason=None):
    lp.apply_platform_verdict(db, _pair(db, env, i).id, verdict, reason,
                              'площадка', None, 'кабинет', _ADMIN)


def _erid_blocked(db, env):
    try:
        erid_service.issue_marker_for_set(db, env.cset, env.deal, _ADMIN)
        return False
    except HTTPException as e:
        return 'Ссылку проверяет трафик' in str(e.detail)


def test_scenario_1_link_happy_path(env):
    """С запросом ссылки: у трафика → у площадки → у трафика → согласован, ЕРИД открыт."""
    db = env.db
    _with_request(env)
    steps = [('отправка', _status(db, env))]
    lp.send_set(env.cset.id, lp.SendIn(), db, _ADMIN)
    steps.append(('после отправки', _status(db, env)))
    _traffic_ok(db, env)
    steps.append(('трафик: материал ок', _status(db, env)))
    lp.set_member_url(env.cset.id, env.targets[0].id, lp.TargetUrlIn(url=LANDING), db, _ADMIN)
    steps.append(('площадка прислала ссылку', _status(db, env)))
    _publisher(db, env, 'ок')
    steps.append(('площадка: ок', _status(db, env)))
    assert _erid_blocked(db, env), 'ЕРИД должен ждать проверки ссылки'
    lp.apply_link_verdict(db, _pair(db, env).id, 'ок', None, 'трафик', _ADMIN)
    steps.append(('трафик: ссылка ок', _status(db, env)))
    assert _pair(db, env).agreed_at is not None and _pair(db, env).code
    assert not _erid_blocked(db, env), 'после проверки ссылки гейт не держит'
    print('\nСЦЕНАРИЙ 1 (со ссылкой):')
    for at, st in steps:
        print(f'  {at:28} → {st}')
    assert [s for _, s in steps] == [
        'у трафика', 'у трафика', 'у площадки', 'у площадки', 'у трафика', 'согласован']


def test_scenario_2_no_link_happy_path(env):
    """Без запроса ссылки: у трафика → у площадки → согласован, ЕРИД открыт."""
    db = env.db
    lp.send_set(env.cset.id, lp.SendIn(), db, _ADMIN)
    _traffic_ok(db, env)
    _publisher(db, env, 'ок')
    assert _status(db, env) == 'согласован'
    assert _pair(db, env).agreed_at is not None
    assert not _erid_blocked(db, env), 'без запроса ссылки гейт не должен держать'


def test_scenario_3_link_rework_then_fix(env):
    """Ссылку вернули → аккаунт прислал новую → трафик проверил → согласован."""
    db = env.db
    _with_request(env)
    lp.send_set(env.cset.id, lp.SendIn(), db, _ADMIN)
    _traffic_ok(db, env)
    lp.set_member_url(env.cset.id, env.targets[0].id, lp.TargetUrlIn(url=LANDING), db, _ADMIN)
    _publisher(db, env, 'ок')
    # Трафик вернул ССЫЛКУ на переделку (креатив не убит, пара не согласована)
    lp.apply_link_verdict(db, _pair(db, env).id, 'на переделку', 'не та страница', 'трафик', _ADMIN)
    assert _status(db, env) == 'у трафика', 'ссылка на переделке — мяч у трафика'
    assert _pair(db, env).agreed_at is None
    assert _erid_blocked(db, env)
    # Аккаунт прислал новую ссылку — строка проверки сбросилась
    lp.set_member_url(env.cset.id, env.targets[0].id,
                      lp.TargetUrlIn(url='https://demo.test/tovar/2'), db, _ADMIN)
    lk = db.query(LaunchPrepReview).filter_by(pair_id=_pair(db, env).id, kind='ссылка').first()
    assert lk.verdict is None, 'новая ссылка = новая проверка'
    assert _status(db, env) == 'у трафика'
    # Трафик проверил новую
    lp.apply_link_verdict(db, _pair(db, env).id, 'ок', None, 'трафик', _ADMIN)
    assert _status(db, env) == 'согласован'
    assert _pair(db, env).agreed_at is not None
    assert not _erid_blocked(db, env)
    print('\nСЦЕНАРИЙ 3 (ссылка на переделке → новая → ок): согласован, ЕРИД открыт')


def test_scenario_4_material_rework(env):
    """Трафик вернул МАТЕРИАЛ: строка площадки не заводится, пара не согласована."""
    db = env.db
    lp.send_set(env.cset.id, lp.SendIn(), db, _ADMIN)
    p = _pair(db, env)
    traffic.pair_verdict(p.id, traffic.VerdictIn(verdict='на переделку', reason='кривой баннер'),
                         db, _ADMIN)
    assert db.query(LaunchPrepReview).filter_by(pair_id=p.id, kind='площадка').first() is None, \
        'площадке материал не уходил — строки ожидания нет'
    assert _status(db, env) == 'у трафика'
    assert p.agreed_at is None


def test_scenario_5_publisher_refusal(env):
    """Площадка отказалась: боковой выход, пара не согласована, ЕРИД по ней не нужен."""
    db = env.db
    lp.send_set(env.cset.id, lp.SendIn(), db, _ADMIN)
    _traffic_ok(db, env)
    _publisher(db, env, 'отказ', reason='нет товара')
    p = _pair(db, env)
    assert p.agreed_at is None
    t = db.query(LaunchPrepTarget).filter_by(id=p.target_id).first()
    assert t.state == 'отказ площадки'


def test_scenario_6_publisher_rework(env):
    """Площадка просит доработку: пара не согласована, материал уходит в переделку."""
    db = env.db
    lp.send_set(env.cset.id, lp.SendIn(), db, _ADMIN)
    _traffic_ok(db, env)
    _publisher(db, env, 'на доработку', reason='баннер не по ТТ')
    p = _pair(db, env)
    assert p.agreed_at is None
    assert _status(db, env) == 'у площадки'
