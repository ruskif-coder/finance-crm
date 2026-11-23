"""Повторная проверка ссылки трафиком (23.11.2026).

Включается ТОЛЬКО когда ссылку у площадки запрашивали: тогда после её прихода у трафика
появляется строка `kind='ссылка'`, и ЕРИД ждёт его «ок». Без запроса строки нет и цепочка
остаётся трёхшаговой.
"""
from datetime import datetime

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
