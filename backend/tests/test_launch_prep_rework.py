# -*- coding: utf-8 -*-
"""Ушедшая в доработку площадка покидает прежний комплект — и его знаменатель.

Доработка заводит НОВЫЙ комплект на одну площадку и ссылается на заменяемый
(`replaces_set_id`). С этого момента площадка работает там. В прежнем комплекте она:

  · не «молчит» — ответ уже дан;
  · не «отказала» — отказ это исход, а тут переделка;
  · и не должна стоять в знаменателе порога ЕРИД, иначе маркер ждёт ответа, который
    придёт по другому комплекту. На экране это выглядело как «согласовали 0 из 3» там,
    где спрашивать осталось двоих.

Но и удалять её нельзя: пара несёт вердикт «на доработку» с причиной и автором — тот
самый ответ на вопрос «почему креатив переделывали трижды». Поэтому она ПОМЕЧАЕТСЯ
ушедшей (решение владельца 31.08.2026), а признак ВЫЧИСЛЯЕТСЯ по ссылке нового комплекта:
хранимый пришлось бы синхронизировать при удалении доработки, и забытая синхронизация
дала бы пару, ушедшую в никуда.
"""
from types import SimpleNamespace

import pytest

from app.database import SessionLocal
from app.launch_prep.models import (LaunchPrepCreativeSet, LaunchPrepPair,
                                    LaunchPrepReview, LaunchPrepSetTarget,
                                    LaunchPrepTarget)
from app.ord import models as _ord_models   # noqa: F401  (маппер sales_deals → ord_*)
from app.routers.launch_prep import (active_pairs, moved_to_rework, threshold_numbers,
                                     threshold_state)
from app.sales.models import SalesDeal, SalesPublisher, SalesService
from tests._launch_prep_cleanup import drop_campaign_creatives

NO_BASE = 9500          # номера комплектов теста — заведомо выше рабочих


def _purge(db):
    """Убирает своё — и до теста тоже: до ловит мусор упавшего прогона."""
    db.rollback()
    drop_campaign_creatives(db, NO_BASE)   # до комплектов: FK без каскада
    sets = db.query(LaunchPrepCreativeSet).filter(
        LaunchPrepCreativeSet.no >= NO_BASE).all()
    ids = [s.id for s in sets]
    if ids:
        pairs = db.query(LaunchPrepPair).filter(LaunchPrepPair.set_id.in_(ids)).all()
        tids = {p.target_id for p in pairs}
        db.query(LaunchPrepPair).filter(
            LaunchPrepPair.set_id.in_(ids)).delete(synchronize_session=False)
        db.query(LaunchPrepSetTarget).filter(
            LaunchPrepSetTarget.set_id.in_(ids)).delete(synchronize_session=False)
        for s in sets:
            db.delete(s)
        db.flush()
        # Получателей заводим свои: чужих не трогаем, свои узнаём по паре выше.
        if tids:
            db.query(LaunchPrepTarget).filter(
                LaunchPrepTarget.id.in_(tids),
                LaunchPrepTarget.surface_kind == 'web',
                ~LaunchPrepTarget.id.in_(
                    db.query(LaunchPrepPair.target_id).filter(
                        LaunchPrepPair.target_id.in_(tids)))).delete(synchronize_session=False)
    db.commit()


@pytest.fixture()
def env():
    """Свой комплект с двумя площадками на живой сделке. Чужие комплекты не трогаем."""
    db = SessionLocal()
    _purge(db)
    deal = db.query(SalesDeal).filter(SalesDeal.code.isnot(None)).first()
    pubs = db.query(SalesPublisher).filter(SalesPublisher.status != 'АРХИВ').limit(2).all()
    service = db.query(SalesService).filter(SalesService.is_active.is_(True)).first()
    if not (deal and len(pubs) == 2 and service):
        db.close()
        pytest.skip('нужна сделка с кодом, две площадки и услуга')

    base = LaunchPrepCreativeSet(deal_id=deal.id, no=NO_BASE, origin='первичный')
    db.add(base)
    db.flush()
    targets, pairs = [], []
    for p in pubs:
        # Посадочная у времянки заполнена НЕ ДЛЯ КРАСОТЫ: с 18.09.2026 отправка
        # требует либо ссылку, либо нажатый запрос — иначе согласованному креативу
        # некуда вести. Без неё фикстура проверяла бы путь, которого больше нет.
        t = LaunchPrepTarget(deal_id=deal.id, publisher_id=p.id, service_id=service.id,
                             surface_kind='web',
                             advertiser_url=f'https://{p.domain or "site.test"}/tovar/1')
        db.add(t)
        db.flush()
        db.add(LaunchPrepSetTarget(set_id=base.id, target_id=t.id))
        pair = LaunchPrepPair(set_id=base.id, target_id=t.id)
        db.add(pair)
        targets.append(t)
        pairs.append(pair)
    db.commit()
    try:
        yield SimpleNamespace(db=db, deal=deal, base=base, pubs=pubs,
                              targets=targets, pairs=pairs)
    finally:
        _purge(db)
        db.close()


def _rework(db, env, pub):
    """То, что делает кнопка «Доработка»: новый комплект на одну площадку со ссылкой."""
    s = LaunchPrepCreativeSet(deal_id=env.deal.id, no=NO_BASE + 1, origin='доработка',
                              publisher_id=pub.id, replaces_set_id=env.base.id)
    db.add(s)
    db.commit()
    return s


def test_nobody_has_left_until_a_rework_set_appears(env):
    """Пока доработки нет, из комплекта никто не уходил."""
    assert moved_to_rework(env.db, [env.base.id]) == {}
    assert len(active_pairs(env.db, env.base.id)) == 2


def test_the_rework_set_marks_its_publisher_as_gone(env):
    """Признак читается по ссылке нового комплекта, а не по колонке."""
    s = _rework(env.db, env, env.pubs[0])
    gone = moved_to_rework(env.db, [env.base.id])
    assert gone == {(env.base.id, env.pubs[0].id): s.no}


def test_the_gone_publisher_leaves_the_counter(env):
    """Ушедшая выпадает из счётчика «согласовали N из M».

    Порог снят 31.08.2026, и запирать маркер этому числу больше нечем — но строка на
    экране осталась, и врать она не должна: «0 из 3» там, где спрашивать осталось
    двоих, читается как «две площадки молчат», хотя молчит одна.
    """
    before = threshold_state(env.db, env.base.id)
    assert before['sent'] == 2, before

    _rework(env.db, env, env.pubs[0])
    after = threshold_state(env.db, env.base.id)
    assert after['sent'] == 1, 'ушедшая площадка осталась в счётчике'


def test_the_pair_itself_survives(env):
    """Пара остаётся: в ней вердикт с причиной и автором — это история переделок."""
    _rework(env.db, env, env.pubs[0])
    left = env.db.query(LaunchPrepPair).filter(
        LaunchPrepPair.set_id == env.base.id).count()
    assert left == 2, 'пару удалили — вместе с ней исчезла причина доработки'


def test_a_refusal_stays_in_the_counter(env):
    """Отказ из счётчика не выпадает: он ОТВЕТ, просто отрицательный.

    Разница с доработкой остаётся и после снятия порога: отказавшая ответила ЗДЕСЬ, и
    строка «1 из 4» это описывает; ушедшая в доработку отвечает в другом комплекте, и
    держать её тут значило бы считать вопрос заданным дважды.
    """
    pairs = [SimpleNamespace(agreed_at=None), SimpleNamespace(agreed_at=1),
             SimpleNamespace(agreed_at=None), SimpleNamespace(agreed_at=None)]
    assert threshold_numbers(pairs) == {
        'sent': 4, 'agreed': 1, 'need': 0, 'ready': True}


# ── Маркер: чужой ответ не запирает выпуск ──────────────────────────────────
#
# Вопрос владельца 31.08.2026: «если по другим площадкам в рамках креатива есть
# согласования, ЕРИД выдаётся?». Ответ должен держаться прибором, а не памятью: выпуск
# маркера необратим, и ошибка в обе стороны дорога — не выпустить вовремя мешает работе,
# выпустить лишний раз нельзя отозвать.

def _agree(db, pair):
    """Согласие площадки — это `agreed_at` у пары: по нему считается числитель."""
    from sqlalchemy.sql import func as sa_func
    pair.agreed_at = sa_func.now()
    db.commit()


def _refuse(db, pair, reason='Товара нет в наличии'):
    db.add(LaunchPrepReview(set_id=pair.set_id, pair_id=pair.id, kind='площадка',
                            verdict='отказ', reason=reason, source='аккаунт',
                            decided_by='тест'))
    db.commit()


def test_refusal_does_not_lock_the_marker(env):
    """Отказ соседа маркер не запирает — ни при чьём согласии, ни без него.

    До 31.08.2026 это держалось порогом: четверть от двух — один, и согласие второй
    площадки его брало. Порог сняли, и правило стало прямым: ответы площадок на выпуск
    маркера не влияют вовсе. Прибор проверяет обе половины — с согласием и без.
    """
    db = env.db
    _refuse(db, env.pairs[0])
    assert threshold_state(db, env.base.id)['ready'] is True, 'отказ запер маркер'

    _agree(db, env.pairs[1])
    st = threshold_state(db, env.base.id)
    assert (st['sent'], st['agreed']) == (2, 1), st
    assert st['ready'] is True


def test_what_still_blocks_the_marker(env):
    """Что осталось запретами — и это НЕ ответы площадок.

    После снятия порога блокеров два, и оба — требования самого реестра: собранная
    договорная цепочка ОРД и код ККТУ у бренда. Прибор пинит именно состав: чтобы
    вернувшийся однажды «порог» было видно.
    """
    from app.routers import launch_prep as lp
    import inspect
    src = inspect.getsource(lp.erid_readiness)
    assert '"code": "chain"' in src and '"code": "kktu"' in src
    assert '"code": "threshold"' not in src, 'порог вернулся в блокеры'


def test_departure_to_rework_does_not_lock_the_marker(env):
    """Ушедшая в доработку не ждётся: порог берут оставшиеся.

    Разница с отказом: отказавшая ответила здесь, ушедшая отвечает в другом комплекте.
    Держи мы её в знаменателе — маркер ждал бы ответа, который сюда уже не придёт.
    """
    db = env.db
    _agree(db, env.pairs[1])
    st_before = threshold_state(db, env.base.id)
    assert (st_before['sent'], st_before['agreed']) == (2, 1)

    _rework(db, env, env.pubs[0])
    st = threshold_state(db, env.base.id)
    assert (st['sent'], st['agreed']) == (1, 1), st
    assert st['ready'] is True


def test_a_set_with_nobody_left_cannot_get_a_marker(env):
    """Комплект, из которого ушли ВСЕ, маркера не получает.

    Снимая порог 31.08.2026, я снял вместе с ним и последнее дно — `ready = bool(sent)`.
    Оно проверяло не долю ответивших, а то, что материал вообще кому-то показан. Без него
    комплект, целиком ушедший в доработку (или ещё не собранный), уезжал бы в ЕРИР: запись
    там необратима и не отзывается, а креатив к этому моменту уже переделывается в другом
    комплекте.
    """
    import inspect

    from app.routers import launch_prep as lp

    _rework(env.db, env, env.pubs[0])
    _rework2 = LaunchPrepCreativeSet(deal_id=env.deal.id, no=NO_BASE + 2,
                                     origin='доработка', publisher_id=env.pubs[1].id,
                                     replaces_set_id=env.base.id)
    env.db.add(_rework2)
    env.db.commit()

    assert active_pairs(env.db, env.base.id) == [], 'кто-то остался — проверка не о том'
    assert threshold_state(env.db, env.base.id)['sent'] == 0

    # Сам запрет — в ручке выпуска, и он читается по коду, а не по формулировке:
    # для вызова эндпоинта нужна авторизация и живой ОРД, а проверка нужна здесь.
    src = inspect.getsource(lp.issue_erid)
    assert 'active_pairs(db, set_id)' in src, 'дно из выпуска ЕРИД пропало'
    assert '"code": "empty"' in inspect.getsource(lp.erid_readiness), (
        'экран не узнает, почему кнопка не сработает')
