"""Ядро модуля: отправка, вердикты, выдача кода.

Здесь собраны правила, каждое из которых до первого нарушения проверяется глазами — и
именно поэтому однажды перестаёт выполняться молча:

  · **отправка заводит ПУСТЫЕ строки ожидания.** Из них считается и знаменатель порога
    ЕРИД, и «кто молчит третий день». Заводи их код вместе с вердиктом — обе величины
    стали бы невычислимыми, и это не упало бы, а просто дало неверные числа;
  · **трафик отвечает ПЕРЕД площадкой** (28.08.2026). Отправка спрашивает только его;
    строка ожидания у площадки появляется вердиктом «ок» трафика, потому что до него
    площадку не спрашивали. До разворота вердикт трафика ставился машинально, и в этом
    файле стоял прибор на пометку `авто` — он снят вместе с самой машинной отметкой;
  · **код выдаётся только при схождении и ровно один раз.** Он уезжает в DSP, и второй
    код на ту же пару — это две строки учёта вместо одной;
  · **нумерация считает сросшиеся пары, а не итерации.** Отвергнутая версия имени не
    получает, поэтому в номерах нет дыр от того, чего не было в эфире;
  · **общий комплект не уходит площадке, которая уже ушла на персональный** — иначе её
    спрашивают заново о том, на что она ответила «нет».

Тесты идут на живой базе: настоящая сделка, настоящие площадки (их коды подменяются на
время теста и возвращаются), свои получатели и комплекты. Всё созданное убирается.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.launch_prep.models import (LaunchPrepCreativeFile, LaunchPrepCreativeSet,
                                    LaunchPrepPair, LaunchPrepReview,
                                    LaunchPrepSetTarget, LaunchPrepTarget)
from app.routers import launch_prep as lp
from app.routers import traffic
from app.sales.models import SalesRep, SalesDeal, SalesPublisher, SalesService
from tests._launch_prep_cleanup import drop_campaign_creatives

NO_BASE = 9700
CODES = ('ZZTA', 'ZZTB')

_ADMIN = SimpleNamespace(role=SimpleNamespace(key='admin'), id=None, name='тест')
_LANDING = 'https://site.test/tovar/1'


def _pass_traffic(db, set_id, only=None):
    """Пройти ступень трафика — с 28.08.2026 она стоит ПЕРЕД площадкой.

    Настоящей ручкой, а не вставкой строк: тогда прибор ниже проверяет живую цепочку,
    а не наше представление о ней. Возвращает пары комплекта по порядку.
    """
    pairs = (db.query(LaunchPrepPair).filter(LaunchPrepPair.set_id == set_id)
             .order_by(LaunchPrepPair.id).all())
    for p in pairs:
        if only is None or p.id in only:
            traffic.pair_verdict(p.id, traffic.VerdictIn(verdict='ок'), db, _ADMIN)
    return pairs


@pytest.fixture
def env():
    """Сделка, две площадки с временными кодами, два получателя и готовый комплект.

    Сделка берётся **без единого получателя**: тогда уборка может смести всех её
    получателей, не рискуя задеть настоящую работу. Первая редакция этого файла чистила
    только комплекты — получатели копились между тестами и падали на ограничении
    уникальности. Ошибка нашлась сама, но чинить пришлось уборку, а не проверку.
    """
    db = SessionLocal()
    _purge(db)

    busy = {d for (d,) in db.query(LaunchPrepTarget.deal_id).distinct().all()}
    q = db.query(SalesDeal).filter(SalesDeal.code.isnot(None))
    if busy:
        q = q.filter(~SalesDeal.id.in_(busy))
    deal = q.first()
    service = db.query(SalesService).filter(SalesService.is_active.is_(True)).first()
    # Не архивные: архивная площадка не попадает в список выбора вовсе, и прибор,
    # который её ждёт, падал бы по причине, к правилу отношения не имеющей. Условие
    # «без кода» снято: кодов нет только у архивных, а свой код фикстура и так
    # проставляет временно и возвращает в уборке.
    pubs = (db.query(SalesPublisher)
              .filter(SalesPublisher.status != 'АРХИВ')
              .order_by(SalesPublisher.id).limit(2).all())
    if not (deal and service and len(pubs) == 2):
        db.close()
        pytest.skip("не хватает данных: нужна свободная сделка с кодом, услуга и две площадки")

    saved = [(p.id, p.code) for p in pubs]
    for p, code in zip(pubs, CODES):
        p.code = code
    # Ответственный трафик для отправки БОЛЬШЕ НЕ ТРЕБУЕТСЯ (владелец 03.09.2026):
    # очередь общая, назначение — отметка, а не условие. Фикстура его всё равно ставит:
    # приборы области видимости (`test_traffic_queue.py`) проверяют и назначенное, и
    # снятое, а завести назначение дешевле, чем каждый раз искать представителя.
    #
    # ИСХОДНОЕ значение сохраняем и возвращаем как есть, а не обнуляем: сделка боевая, и
    # «вернуть в NULL» однажды уже означало снять настоящее назначение (см. план выкладки,
    # раздел про опасные на боевой базе приборы).
    saved_traffic = deal.traffic_manager_id
    if not deal.traffic_manager_id:
        any_rep = db.query(SalesRep.id).order_by(SalesRep.id).first()
        if any_rep:
            deal.traffic_manager_id = any_rep[0]
    db.commit()

    targets = []
    for p in pubs:
        # Посадочная у времянки заполнена НЕ ДЛЯ КРАСОТЫ: с 18.09.2026 отправка
        # требует либо ссылку, либо нажатый запрос — иначе согласованному креативу
        # некуда вести. Без неё фикстура проверяла бы путь, которого больше нет.
        t = LaunchPrepTarget(deal_id=deal.id, publisher_id=p.id, service_id=service.id,
                             surface_kind='web')
        db.add(t)
        targets.append(t)
    db.flush()

    cset = LaunchPrepCreativeSet(deal_id=deal.id, no=NO_BASE + 1)
    db.add(cset)
    db.flush()
    # Состав комплекта — ЧЛЕНСТВО, а не все площадки сделки (миграция
    # 2026-08-27_set_targets.sql): у второго креатива состав свой.
    for t in targets:
        # Посадочная — у пары «креатив × площадка» (с 25.09.2026), не у площадки сделки.
        db.add(LaunchPrepSetTarget(set_id=cset.id, target_id=t.id,
                                   advertiser_url=_LANDING))
    db.flush()
    db.add(LaunchPrepCreativeFile(set_id=cset.id, path='creatives/test.png',
                                  original_name='test.png', size_bytes=10))
    db.add(LaunchPrepReview(set_id=cset.id, kind='первичная_тт', verdict='ок',
                            source='аккаунт', decided_by='тест'))
    db.commit()

    yield SimpleNamespace(db=db, deal=deal, pubs=pubs, targets=targets, cset=cset,
                          service=service)

    _purge(db, deal.id)
    for pid, code in saved:
        db.query(SalesPublisher).filter(SalesPublisher.id == pid).update({"code": code})
    db.query(SalesDeal).filter(SalesDeal.id == deal.id).update(
        {"traffic_manager_id": saved_traffic})
    db.commit()
    db.close()


def _purge(db, deal_id=None):
    """Убирает своё — и до теста тоже: до ловит мусор упавшего прогона.

    Порядок обязателен: пары ссылаются и на комплект, и на получателя, проверки — на пару.
    """
    db.rollback()
    drop_campaign_creatives(db, NO_BASE)   # до комплектов: FK без каскада
    sets = db.query(LaunchPrepCreativeSet).filter(
        LaunchPrepCreativeSet.no >= NO_BASE).all()
    deal_ids = {s.deal_id for s in sets}
    if deal_id:
        deal_ids.add(deal_id)

    ids = [s.id for s in sets]
    targets = (db.query(LaunchPrepTarget).filter(LaunchPrepTarget.deal_id.in_(deal_ids)).all()
               if deal_ids else [])
    tids = [t.id for t in targets]

    pair_q = db.query(LaunchPrepPair)
    pair_ids = [p.id for p in pair_q.filter(
        (LaunchPrepPair.set_id.in_(ids) if ids else False)
        | (LaunchPrepPair.target_id.in_(tids) if tids else False)).all()] if (ids or tids) else []

    if pair_ids:
        db.query(LaunchPrepReview).filter(
            LaunchPrepReview.pair_id.in_(pair_ids)).delete(synchronize_session=False)
        db.query(LaunchPrepPair).filter(
            LaunchPrepPair.id.in_(pair_ids)).delete(synchronize_session=False)
    if ids:
        db.query(LaunchPrepReview).filter(
            LaunchPrepReview.set_id.in_(ids)).delete(synchronize_session=False)
        db.query(LaunchPrepCreativeFile).filter(
            LaunchPrepCreativeFile.set_id.in_(ids)).delete(synchronize_session=False)
        db.query(LaunchPrepCreativeSet).filter(
            LaunchPrepCreativeSet.id.in_(ids)).delete(synchronize_session=False)
    if tids:
        db.query(LaunchPrepTarget).filter(
            LaunchPrepTarget.id.in_(tids)).delete(synchronize_session=False)
    db.query(SalesPublisher).filter(SalesPublisher.code.in_(CODES)).update(
        {"code": None}, synchronize_session=False)
    db.commit()


# ── отправка ─────────────────────────────────────────────────────────────────
def test_send_creates_pairs_and_empty_waiting_rows(env):
    out = lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    assert out["sent"] == 2

    pairs = env.db.query(LaunchPrepPair).filter(
        LaunchPrepPair.set_id == env.cset.id).all()
    assert len(pairs) == 2
    assert all(p.code is None for p in pairs), (
        "код выдаётся при схождении, а не при отправке")

    waiting = env.db.query(LaunchPrepReview).filter(
        LaunchPrepReview.set_id == env.cset.id,
        LaunchPrepReview.kind == 'трафики').all()
    assert len(waiting) == 2
    assert all(r.verdict is None for r in waiting), (
        "строка ожидания обязана быть пустой: пустой вердикт значит «спросили, ответа нет»")
    assert all(r.asked_at is not None for r in waiting), (
        "без момента вопроса молчание нечем считать")


def test_platform_is_not_asked_until_traffic_answers(env):
    """Разворот цепочки 28.08.2026: отправка спрашивает трафик, а не площадку.

    Прибор именно на ОТСУТСТВИЕ строки. Заведи её отправка «на будущее» — «строка
    проверки = спросили» перестало бы быть правдой, и молчание площадки считалось бы
    с минуты, когда её ещё не спрашивали.
    """
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    assert env.db.query(LaunchPrepReview).filter(
        LaunchPrepReview.set_id == env.cset.id,
        LaunchPrepReview.kind == 'площадка').count() == 0
    assert all(p.sent_at is None for p in env.db.query(LaunchPrepPair).filter(
        LaunchPrepPair.set_id == env.cset.id)), (
        "`sent_at` пары означает «ушла площадке», а она ещё не ушла")

    pairs = _pass_traffic(env.db, env.cset.id)
    rows = env.db.query(LaunchPrepReview).filter(
        LaunchPrepReview.set_id == env.cset.id,
        LaunchPrepReview.kind == 'площадка').all()
    assert len(rows) == len(pairs)
    assert all(r.verdict is None for r in rows)
    env.db.refresh(pairs[0])
    assert pairs[0].sent_at is not None


def test_send_without_primary_review_is_refused(env):
    other = LaunchPrepCreativeSet(deal_id=env.deal.id, no=NO_BASE + 2)
    env.db.add(other)
    env.db.commit()
    with pytest.raises(HTTPException) as e:
        lp.send_set(other.id, lp.SendIn(), env.db, _ADMIN)
    assert 'первичная проверка' in e.value.detail.lower()


def test_send_to_publisher_without_code_is_refused_by_name(env):
    """Отправить то, что потом нельзя будет назвать, — тупик. Проверка на отправке, а не
    на вердикте: на вердикте отказ пришёлся бы на факт, сообщённый площадкой."""
    env.pubs[0].code = None
    env.db.commit()
    with pytest.raises(HTTPException) as e:
        lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    assert env.pubs[0].name in e.value.detail


def test_repeated_send_does_not_duplicate_pairs(env):
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    again = lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    assert again["sent"] == 0
    assert env.db.query(LaunchPrepPair).filter(
        LaunchPrepPair.set_id == env.cset.id).count() == 2


# ── вердикт и код ────────────────────────────────────────────────────────────
def test_code_is_issued_on_agreement_only(env):
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    pairs = _pass_traffic(env.db, env.cset.id)

    out = lp.pair_verdict(pairs[0].id, lp.PairVerdictIn(verdict='ок'), env.db, _ADMIN)
    env.db.refresh(pairs[0])
    assert out["code"] == f"{env.deal.code}-{CODES[0]}-01"
    assert pairs[0].agreed_at is not None

    out2 = lp.pair_verdict(pairs[1].id, lp.PairVerdictIn(verdict='на доработку',
                                                         reason='тяжёлый файл'),
                           env.db, _ADMIN)
    env.db.refresh(pairs[1])
    assert out2["code"] is None and pairs[1].code is None, (
        "отвергнутая пара имени не получает — иначе в нумерации появятся дыры")


def test_verdict_is_immutable(env):
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    pair = _pass_traffic(env.db, env.cset.id)[0]
    lp.pair_verdict(pair.id, lp.PairVerdictIn(verdict='ок'), env.db, _ADMIN)
    with pytest.raises(HTTPException) as e:
        lp.pair_verdict(pair.id, lp.PairVerdictIn(verdict='на доработку', reason='передумал'),
                        env.db, _ADMIN)
    assert 'уже выставлен' in e.value.detail


def test_rework_verdict_requires_reason(env):
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    pair = _pass_traffic(env.db, env.cset.id)[0]
    with pytest.raises(HTTPException) as e:
        lp.pair_verdict(pair.id, lp.PairVerdictIn(verdict='на доработку'), env.db, _ADMIN)
    assert 'причин' in e.value.detail.lower()


def test_open_url_request_blocks_agreement(env):
    """Запрос посадочной, на который не ответили, не даёт поставить «ок».

    Проверяется именно ЗАПРОС, а не пустота поля: без запроса тот же «ок» проходит
    (`test_code_is_issued_on_agreement_only` выше идёт с пустым `advertiser_url`).
    Иначе правило запретило бы согласование всем, кому мы ссылку не заказывали.
    """
    from datetime import datetime

    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    pairs = _pass_traffic(env.db, env.cset.id)

    def member(pair):
        return env.db.query(LaunchPrepSetTarget).filter(
            LaunchPrepSetTarget.set_id == pair.set_id,
            LaunchPrepSetTarget.target_id == pair.target_id).first()

    m = member(pairs[0])
    # Ссылку СНИМАЕМ: фикстура заполняет её всем получателям (без неё не проходит
    # отправка), а здесь проверяется именно открытый запрос без ответа.
    m.advertiser_url = None
    m.url_requested_at = datetime.now()
    env.db.commit()

    with pytest.raises(HTTPException) as e:
        lp.pair_verdict(pairs[0].id, lp.PairVerdictIn(verdict='ок'), env.db, _ADMIN)
    assert 'посадочн' in e.value.detail.lower()

    # Отрицательные исходы запрос НЕ держит: они закрывают размещение целиком.
    lp.pair_verdict(pairs[0].id, lp.PairVerdictIn(verdict='отказ', reason='нет товара'),
                    env.db, _ADMIN)

    # Ссылка пришла — «ок» проходит.
    m2 = member(pairs[1])
    m2.advertiser_url = None          # см. выше: фикстура заполняет её для отправки
    m2.url_requested_at = datetime.now()
    env.db.commit()
    with pytest.raises(HTTPException):
        lp.pair_verdict(pairs[1].id, lp.PairVerdictIn(verdict='ок'), env.db, _ADMIN)
    m2.advertiser_url = 'https://example.test/lp'
    env.db.commit()
    out = lp.pair_verdict(pairs[1].id, lp.PairVerdictIn(verdict='ок'), env.db, _ADMIN)
    assert out["code"], "с пришедшей ссылкой пара срастается как обычно"


def test_numbering_counts_agreed_pairs_not_iterations(env):
    """Завернули первый комплект, согласовали второй — второй получает -01, а не -02."""
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    _pass_traffic(env.db, env.cset.id)
    first = env.db.query(LaunchPrepPair).filter(
        LaunchPrepPair.set_id == env.cset.id,
        LaunchPrepPair.target_id == env.targets[0].id).first()
    lp.pair_verdict(first.id, lp.PairVerdictIn(verdict='на доработку', reason='правки'),
                    env.db, _ADMIN)

    second = LaunchPrepCreativeSet(deal_id=env.deal.id, no=NO_BASE + 3,
                                   publisher_id=env.pubs[0].id, origin='доработка',
                                   replaces_set_id=env.cset.id)
    env.db.add(second)
    env.db.flush()
    # Персональный комплект адресован своей площадке — это делает `create_set`,
    # а здесь комплект собран руками, поэтому членство заводим явно.
    env.db.add(LaunchPrepSetTarget(set_id=second.id, target_id=env.targets[0].id,
                                   advertiser_url=_LANDING))
    env.db.add(LaunchPrepCreativeFile(set_id=second.id, path='creatives/t2.png',
                                      original_name='t2.png', size_bytes=10))
    env.db.add(LaunchPrepReview(set_id=second.id, kind='первичная_тт', verdict='ок',
                                source='аккаунт', decided_by='тест'))
    env.db.commit()

    lp.send_set(second.id, lp.SendIn(), env.db, _ADMIN)
    pair2 = _pass_traffic(env.db, second.id)[0]
    out = lp.pair_verdict(pair2.id, lp.PairVerdictIn(verdict='ок'), env.db, _ADMIN)
    assert out["code"].endswith('-01'), (
        f"первая сросшаяся пара размещения обязана быть -01, получили {out['code']}")


def test_common_set_skips_publishers_moved_to_personal(env):
    """Доработка адресуется только возразившему, и общий комплект к нему больше не идёт."""
    personal = LaunchPrepCreativeSet(deal_id=env.deal.id, no=NO_BASE + 4,
                                     publisher_id=env.pubs[0].id, origin='доработка',
                                     replaces_set_id=env.cset.id)
    env.db.add(personal)
    env.db.commit()

    targets = lp._targets_for_set(env.db, env.cset)
    assert env.pubs[0].id not in {t.publisher_id for t in targets}
    assert env.pubs[1].id in {t.publisher_id for t in targets}


def test_target_becomes_agreed_after_first_agreement(env):
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    _pass_traffic(env.db, env.cset.id)
    pair = env.db.query(LaunchPrepPair).filter(
        LaunchPrepPair.target_id == env.targets[0].id).first()
    lp.pair_verdict(pair.id, lp.PairVerdictIn(verdict='ок'), env.db, _ADMIN)
    env.db.refresh(env.targets[0])
    assert env.targets[0].state == 'согласован'
    env.db.refresh(env.targets[1])
    assert env.targets[1].state == 'согласование', (
        "площадки идут своим темпом: одна согласовала — вторая ещё ждёт")


# ── состав принадлежит КРЕАТИВУ, а не сделке ─────────────────────────────────
def test_second_creative_does_not_inherit_the_first_ones_platforms(env):
    """Найдено владельцем 27.08.2026: площадка второго креатива появлялась в первом.

    Причина была в том, что список брался по `deal_id`: все неотправленные комплекты
    показывали одно и то же. Теперь состав — членство, и у второго креатива он свой.
    """
    second = LaunchPrepCreativeSet(deal_id=env.deal.id, no=NO_BASE + 7)
    env.db.add(second)
    env.db.flush()
    env.db.add(LaunchPrepSetTarget(set_id=second.id, target_id=env.targets[1].id,
                                   advertiser_url=_LANDING))
    env.db.commit()

    first_list = {t.id for t in lp._targets_for_set(env.db, env.cset)}
    second_list = {t.id for t in lp._targets_for_set(env.db, second)}

    assert second_list == {env.targets[1].id}, (
        "второй креатив увидел чужой состав — список снова считается по сделке")
    assert first_list == {t.id for t in env.targets}, (
        "состав первого креатива изменился от появления второго")


def test_new_creative_starts_empty(env):
    """Второй креатив открывается пустым (владелец, 27.08.2026): второй материал обычно
    идёт не туда же, куда первый, и копия чужого состава — работа по вычёркиванию."""
    fresh = LaunchPrepCreativeSet(deal_id=env.deal.id, no=NO_BASE + 8)
    env.db.add(fresh)
    env.db.commit()

    assert lp._targets_for_set(env.db, fresh) == [], (
        "новый комплект унаследовал площадки — состав снова общий")


def test_removing_a_platform_leaves_it_in_the_other_creative(env):
    """Крестик снимает площадку ИЗ ЭТОГО креатива, а не из сделки."""
    second = LaunchPrepCreativeSet(deal_id=env.deal.id, no=NO_BASE + 9)
    env.db.add(second)
    env.db.flush()
    env.db.add(LaunchPrepSetTarget(set_id=second.id, target_id=env.targets[0].id,
                                   advertiser_url=_LANDING))
    env.db.commit()

    lp.drop_set_target(second.id, env.targets[0].id, env.db, _ADMIN)

    assert env.targets[0].id in {t.id for t in lp._targets_for_set(env.db, env.cset)}, (
        "снятие из одного креатива убрало площадку и из другого")
    assert lp._targets_for_set(env.db, second) == []


def test_platform_needed_by_nobody_returns_to_the_picker(env):
    """Площадка, не адресованная ни одному креативу, удаляется из сделки.

    Иначе она числилась бы участником кампании, не получая ни одного материала, и в
    список выбора под «+ Площадки» уже не вернулась бы.
    """
    tid = env.targets[0].id
    lp.drop_set_target(env.cset.id, tid, env.db, _ADMIN)

    assert env.db.query(LaunchPrepTarget).filter(LaunchPrepTarget.id == tid).first() is None
    options = lp.target_options(env.deal.id, set_id=env.cset.id, db=env.db,
                                current_user=_ADMIN)
    assert env.pubs[0].id in {p["publisher_id"] for p in options["all"] if not p["already"]}, (
        "площадка не вернулась в список выбора")


def test_sent_platform_may_not_be_dropped(env):
    """После отправки снять нельзя: у получателя уже есть пара и строки ожидания."""
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    with pytest.raises(HTTPException) as e:
        lp.drop_set_target(env.cset.id, env.targets[0].id, env.db, _ADMIN)
    assert 'уже отправляли' in str(e.value.detail)


def test_picker_offers_a_platform_already_used_by_another_creative(env):
    """Площадка первого креатива обязана оставаться доступной для второго."""
    second = LaunchPrepCreativeSet(deal_id=env.deal.id, no=NO_BASE + 10)
    env.db.add(second)
    env.db.commit()

    options = lp.target_options(env.deal.id, set_id=second.id, db=env.db,
                                current_user=_ADMIN)
    free = {p["publisher_id"] for p in options["all"] if not p["already"]}
    assert env.pubs[0].id in free, (
        "занятость считается по сделке — второму креативу площадку не предложат")

