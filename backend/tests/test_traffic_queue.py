"""Конвейер трафиков: порядок ступеней, полномочия и сроки.

Разворот цепочки 28.08.2026 держится на четырёх утверждениях, и все они молчаливые —
нарушение любого не роняет ничего, а тихо меняет смысл данных:

  · площадку не спрашивают, пока трафик не ответил;
  · пары с вердиктом площадки и без вердикта трафика не существует;
  · `отказ` трафик поставить не может — это решение площадки, а не проверяющего;
  · незакрытая сделка не истекает никогда, и уборка её файлы не трогает.

Окружение берётся из соседнего файла: сделка, две площадки с временными кодами и готовый
комплект нужны здесь ровно те же, а вторая копия фикстуры разъехалась бы с первой.
"""
import io
import os
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.launch_prep.models import (LaunchPrepCreativeSet, LaunchPrepPair,
                                    LaunchPrepPairFile, LaunchPrepReview)
from app.sales.models import SalesRep
from app.routers import launch_prep as lp
from app.routers import traffic
from app.traffic import retention
# Фикстура берётся из соседнего файла, а не переписывается: общего conftest в проекте
# нет, каждый файл тестов самодостаточен, и вторая копия этой сборки разъехалась бы с
# первой. `noqa` ниже — обычная плата за такой импорт: имя параметра теста обязано
# совпадать с именем фикстуры, и ruff видит в этом переопределение.
from tests.test_launch_prep_pairs import _ADMIN, env  # noqa: F401


def _sent(env):  # noqa: F811
    """Комплект отправлен: пары есть, спрошен только трафик."""
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    return (env.db.query(LaunchPrepPair)
            .filter(LaunchPrepPair.set_id == env.cset.id)
            .order_by(LaunchPrepPair.id).all())


# ── область видимости ────────────────────────────────────────────────────────
#
# Правило менялось дважды за четыре дня, и оба раза молча: лишняя видимость ничего не
# роняет, недостача выглядит как пустая очередь. 31.08.2026 очередь распределялась —
# рядовой трафик видел только назначенное ему. 03.09.2026 владелец развернул обратно:
# разбирают по наличию времени, а не по назначению, значит очередь ОБЩАЯ.
#
# Приборы стоят на новом правиле целиком, а не «ослаблены»: разница между «видно всем»
# и «видно назначенному» — это разница между работающим конвейером и очередью, в
# которую никто не смотрит.

# Пользователь, которого нет в справочнике представителей: сегодня это состояние любого
# трафик-менеджера — профиль заводится только при первом назначении (app/sales/reps.py).
_UID_NOBODY = 10 ** 9


def _user(key, is_master, uid=None):
    """Пользователь ровно в той форме, в какой его читает `_apply_scope`."""
    return SimpleNamespace(id=uid, name='тест',
                           role=SimpleNamespace(key=key, is_master=is_master))


def _sees(db, user, deal_id, rep_id=None, all_reps=False):
    """Видит ли пользователь в очереди хоть одну пару этой сделки."""
    rows = traffic.queue('all', db, user, rep_id=rep_id, all_reps=all_reps)['rows']
    return any(r['deal']['id'] == deal_id for r in rows)


@pytest.fixture
def scope(env):  # noqa: F811
    """Два УЖЕ СУЩЕСТВУЮЩИХ представителя, а не заведённые тестом.

    `sales_reps.user_id` — внешний ключ на `users`, и выдуманный пользователь его не
    проходит. Заводить ради теста ещё и пользователя значило бы создавать учётную запись
    в боевой базе стенда; берём двух живых и не трогаем ничего, кроме назначения на нашей
    сделке, которое снимаем на выходе.
    """
    db = env.db
    reps = (db.query(SalesRep).filter(SalesRep.user_id.isnot(None))
            .order_by(SalesRep.id).limit(2).all())
    if len(reps) < 2:
        pytest.skip('нужны два представителя с привязанным пользователем')
    mine, other = reps
    _sent(env)
    yield SimpleNamespace(db=db, deal=env.deal, mine=mine, other=other,
                          uid_mine=mine.user_id, uid_other=other.user_id)
    env.deal.traffic_manager_id = None
    db.commit()


def test_unassigned_work_is_visible_to_everyone(scope):
    """Неназначенное видит КАЖДЫЙ — на этом стоит общая очередь.

    Прежнее правило (31.08.2026) прятало «ничьё» от всех, кроме мастера с включённым
    «все». Практическое следствие было такое: пока `traffic_manager_id` пуст — а он пуст
    у всех сделок на стенде, — очередь у рядового трафика пустая, и отправленный
    материал выглядит потерянным.
    """
    scope.deal.traffic_manager_id = None
    scope.db.commit()
    assert _sees(scope.db, _user('role_120', False, scope.uid_mine), scope.deal.id)
    assert _sees(scope.db, _user('role_120', False, scope.uid_other), scope.deal.id)
    assert _sees(scope.db, _user('role_120', False, _UID_NOBODY), scope.deal.id), (
        'трафик без профиля в справочнике не видит ничего — а профиля нет ни у кого'
    )
    assert _sees(scope.db, _user('role_121', True, scope.uid_mine), scope.deal.id)


def test_assignment_does_not_hide_work_from_others(scope):
    """Назначение — ОТМЕТКА, а не граница видимости.

    Именно этим новое правило отличается от старого: ответственный у кампании остаётся
    и меняется вручную до старта, но чужую работу он ни от кого не закрывает.
    """
    scope.deal.traffic_manager_id = scope.other.id
    scope.db.commit()
    assert _sees(scope.db, _user('role_120', False, scope.uid_other), scope.deal.id)
    assert _sees(scope.db, _user('role_120', False, scope.uid_mine), scope.deal.id)
    assert _sees(scope.db, _user('role_120', False, _UID_NOBODY), scope.deal.id)
    assert _sees(scope.db, _user('admin', False, None), scope.deal.id)


def test_rep_filter_narrows_the_queue_for_anyone(scope):
    """Фильтр «чья кампания» доступен всем и именно СУЖАЕТ список.

    Он остался от переключателя мастера, но сменил смысл: раньше расширял доступ, теперь
    только режет уже видимое. Поэтому проверяем обе стороны — и что выбранного видно, и
    что невыбранного не видно.
    """
    scope.deal.traffic_manager_id = scope.other.id
    scope.db.commit()
    rank = _user('role_120', False, scope.uid_mine)
    assert _sees(scope.db, rank, scope.deal.id, rep_id=scope.other.id)
    assert not _sees(scope.db, rank, scope.deal.id, rep_id=scope.mine.id)
    # `all_reps` остался в контракте ручки и ничего не меняет: очередь и так полная.
    assert _sees(scope.db, rank, scope.deal.id, all_reps=True)


def test_anyone_can_act_on_what_he_can_see(scope):
    """Область ДЕЙСТВИЙ равна области видимости.

    Прибор пережил разворот правила и остался прежним по смыслу: строки видно — значит
    по ним можно нажать. Обратное со стороны выглядит хуже запрета: список есть, а
    каждое нажатие отвечает «пара не найдена».
    """
    scope.deal.traffic_manager_id = scope.other.id
    scope.db.commit()
    pair = (scope.db.query(LaunchPrepPair)
            .join(LaunchPrepCreativeSet,
                  LaunchPrepCreativeSet.id == LaunchPrepPair.set_id)
            .filter(LaunchPrepCreativeSet.deal_id == scope.deal.id).first())
    assert pair, 'у сделки нет пары — проверять нечего'

    for who in (_user('role_121', True, scope.uid_mine),
                _user('role_120', False, scope.uid_mine),
                _user('role_120', False, _UID_NOBODY)):
        assert traffic._pair_in_scope(scope.db, pair.id, who), 'ответили 404 на видимое'


def test_sending_no_longer_requires_a_traffic_manager(env):  # noqa: F811
    """Отправка без назначенного трафика проходит (владелец 03.09.2026).

    Проверка стояла в `send_set` с 31.08 и была тупиком вдвойне: очередь стала общей, а
    назначать было НЕКОГО — у трафиков нет профиля в справочнике ответственных, и список
    кандидатов возвращал пустоту. Прибор держит именно «проходит», а не «список не пуст»:
    справочник наполнится, а правило должно остаться.
    """
    env.deal.traffic_manager_id = None
    env.db.commit()
    pairs = _sent(env)
    assert pairs, 'без ответственного материал не ушёл — проверка вернулась'


# ── порядок ступеней ─────────────────────────────────────────────────────────
def test_platform_cannot_answer_before_traffic(env):  # noqa: F811
    """Главный прибор разворота. Проверка на СЕРВЕРЕ, а не на экране: спрятанная кнопка
    возвращается первым же рефакторингом, и тогда порог ЕРИД начнёт считать «ок»,
    за которым не стояло ни одной проверки материала."""
    pairs = _sent(env)
    with pytest.raises(HTTPException) as e:
        lp.pair_verdict(pairs[0].id, lp.PairVerdictIn(verdict='ок'), env.db, _ADMIN)
    assert 'трафик' in e.value.detail.lower()


def test_pair_with_platform_verdict_always_has_traffic_verdict(env):  # noqa: F811
    """Инвариант порядка в его окончательном виде: по всей базе, а не по нашим строкам.

    Он важнее любого отдельного сценария — на нём стоит право не проверять вердикт
    трафика второй раз в расчёте порога ЕРИД.
    """
    pairs = _sent(env)
    traffic.pair_verdict(pairs[0].id, traffic.VerdictIn(verdict='ок'), env.db, _ADMIN)
    lp.pair_verdict(pairs[0].id, lp.PairVerdictIn(verdict='ок'), env.db, _ADMIN)

    with_platform = {r.pair_id for r in env.db.query(LaunchPrepReview).filter(
        LaunchPrepReview.kind == 'площадка',
        LaunchPrepReview.verdict.isnot(None),
        LaunchPrepReview.pair_id.isnot(None))}
    with_traffic = {r.pair_id for r in env.db.query(LaunchPrepReview).filter(
        LaunchPrepReview.kind == 'трафики',
        LaunchPrepReview.verdict.isnot(None),
        LaunchPrepReview.pair_id.isnot(None))}
    assert not (with_platform - with_traffic), (
        f"пары с вердиктом площадки без вердикта трафика: {with_platform - with_traffic}")


# ── полномочия ───────────────────────────────────────────────────────────────
def test_traffic_may_not_refuse_a_platform(env):  # noqa: F811
    """Закрыть площадку — не полномочие трафика (владелец). Отказ, записанный им,
    вывел бы площадку из кампании молча и навсегда: обратного перехода у неё нет."""
    pairs = _sent(env)
    with pytest.raises(HTTPException) as e:
        traffic.pair_verdict(pairs[0].id, traffic.VerdictIn(verdict='отказ', reason='нет'),
                             env.db, _ADMIN)
    assert 'площадк' in e.value.detail.lower()


def test_rework_requires_a_reason(env):  # noqa: F811
    pairs = _sent(env)
    with pytest.raises(HTTPException) as e:
        traffic.pair_verdict(pairs[0].id, traffic.VerdictIn(verdict='на переделку'),
                             env.db, _ADMIN)
    assert 'переделать' in e.value.detail.lower()


def test_traffic_verdict_is_immutable(env):  # noqa: F811
    pairs = _sent(env)
    traffic.pair_verdict(pairs[0].id, traffic.VerdictIn(verdict='ок'), env.db, _ADMIN)
    with pytest.raises(HTTPException) as e:
        traffic.pair_verdict(pairs[0].id, traffic.VerdictIn(verdict='на переделку',
                                                            reason='передумал'),
                             env.db, _ADMIN)
    assert 'уже выставлен' in e.value.detail


def test_bulk_skips_already_answered_instead_of_failing(env):  # noqa: F811
    """Восемь одинаковых «ок» — обычный день. Если одна из пар закрыта соседом минуту
    назад, терять из-за неё остальные семь незачем; но и молчать об этом нельзя."""
    pairs = _sent(env)
    traffic.pair_verdict(pairs[0].id, traffic.VerdictIn(verdict='ок'), env.db, _ADMIN)
    out = traffic.bulk_verdict(
        traffic.BulkVerdictIn(pair_ids=[p.id for p in pairs], verdict='ок'),
        env.db, _ADMIN)
    assert out == {"done": len(pairs) - 1, "skipped": 1}


def test_ok_opens_exactly_one_platform_row(env):  # noqa: F811
    pairs = _sent(env)
    traffic.pair_verdict(pairs[0].id, traffic.VerdictIn(verdict='ок'), env.db, _ADMIN)
    assert env.db.query(LaunchPrepReview).filter(
        LaunchPrepReview.pair_id == pairs[0].id,
        LaunchPrepReview.kind == 'площадка').count() == 1


def test_rework_does_not_open_a_platform_row(env):  # noqa: F811
    """Материал завернули — площадка о нём так и не узнала. Заведённая строка ожидания
    означала бы «спросили», и молчание считалось бы по вопросу, которого не было."""
    pairs = _sent(env)
    traffic.pair_verdict(pairs[0].id, traffic.VerdictIn(verdict='на переделку',
                                                        reason='тяжёлый файл'),
                         env.db, _ADMIN)
    assert env.db.query(LaunchPrepReview).filter(
        LaunchPrepReview.pair_id == pairs[0].id,
        LaunchPrepReview.kind == 'площадка').count() == 0


# ── очередь ──────────────────────────────────────────────────────────────────
def test_queue_shows_waiting_pairs_with_prefix(env):  # noqa: F811
    pairs = _sent(env)
    rows = traffic.queue('waiting', env.db, _ADMIN)["rows"]
    mine = [r for r in rows if r["pair_id"] in {p.id for p in pairs}]
    assert len(mine) == len(pairs)
    assert all(r["pair_prefix"] and r["pair_prefix"].count('-') == 1 for r in mine), (
        "полного кода пары до схождения не существует — показываем префикс")
    assert all(r["verdict"] is None for r in mine)

    traffic.pair_verdict(pairs[0].id, traffic.VerdictIn(verdict='ок'), env.db, _ADMIN)
    left = traffic.queue('waiting', env.db, _ADMIN)["rows"]
    assert pairs[0].id not in {r["pair_id"] for r in left}, (
        "отвеченная пара обязана уходить из очереди, иначе она не пустеет")


def test_queue_count_matches_waiting_and_drops_on_verdict(env):  # noqa: F811
    """Счётчик для меню считает ровно неразобранное и убывает с каждым вердиктом.

    Отдельная лёгкая ручка (`/queue/count`), но число обязано совпадать с длиной очереди
    ожидания: иначе значок в шапке заявит одно, а экран покажет другое.
    """
    pairs = _sent(env)
    mine = {p.id for p in pairs}

    def waiting_here():
        rows = traffic.queue('waiting', env.db, _ADMIN)["rows"]
        return len([r for r in rows if r["pair_id"] in mine])

    # Счётчик = длина очереди ожидания в той же области. Админ видит всё, поэтому
    # сравниваем именно с полным waiting, а не только со своими парами.
    all_waiting = len(traffic.queue('waiting', env.db, _ADMIN)["rows"])
    assert traffic.queue_count(env.db, _ADMIN)["waiting"] == all_waiting
    assert waiting_here() == len(pairs)

    before = traffic.queue_count(env.db, _ADMIN)["waiting"]
    traffic.pair_verdict(pairs[0].id, traffic.VerdictIn(verdict='ок'), env.db, _ADMIN)
    after = traffic.queue_count(env.db, _ADMIN)["waiting"]
    assert after == before - 1, "вердикт не уменьшил счётчик неразобранного"


# ── файлы ────────────────────────────────────────────────────────────────────
def test_file_limit_is_enforced(env):  # noqa: F811
    """Предел проверяется кодом: триггеров в проекте нет ни одного, и заводить первый
    ради счётчика не стоит — но правило без прибора не живёт."""
    import asyncio

    from app.traffic import files as tf

    pairs = _sent(env)
    for i in range(tf.MAX_PAIR_FILES):
        env.db.add(LaunchPrepPairFile(pair_id=pairs[0].id, path=f'shots/fake{i}.webp',
                                      original_name=f'f{i}.png', size_bytes=1))
    env.db.commit()

    from fastapi import UploadFile
    up = UploadFile(file=io.BytesIO(b'x'), filename='over.png')
    with pytest.raises(HTTPException) as e:
        asyncio.run(traffic.upload_shot(pairs[0].id, up, env.db, _ADMIN))
    assert str(tf.MAX_PAIR_FILES) in e.value.detail

    env.db.query(LaunchPrepPairFile).filter(
        LaunchPrepPairFile.pair_id == pairs[0].id).delete(synchronize_session=False)
    env.db.commit()


def test_upload_renames_by_chain_and_converts(env):  # noqa: F811
    """Имя собираем мы, а не инструмент съёмки; картинка ложится пережатой."""
    import asyncio

    from fastapi import UploadFile

    from tests.test_traffic_files import _noisy_png

    pairs = _sent(env)
    src = _noisy_png(600, 400)
    up = UploadFile(file=io.BytesIO(src), filename='Снимок экрана 2026-08-28.png')
    out = asyncio.run(traffic.upload_shot(pairs[0].id, up, env.db, _ADMIN))
    try:
        assert out["name"].endswith('.webp')
        assert 'cr' in out["name"] and out["name"].isascii()
        assert out["original_name"] == 'Снимок экрана 2026-08-28.png', (
            "что принесли — сохраняем; на диск и в архив это имя не идёт")
        assert out["size_bytes"] < len(src)
    finally:
        rec = env.db.query(LaunchPrepPairFile).filter(
            LaunchPrepPairFile.id == out["id"]).first()
        if rec:
            try:
                os.remove(os.path.join(traffic.UPLOADS_ROOT, rec.path))
            except OSError:
                pass
            env.db.delete(rec)
            env.db.commit()


def test_single_archive_is_renamed_not_rewrapped(env):  # noqa: F811
    """HTML5-баннер приходит архивом. Второй zip вокруг него заставлял бы распаковывать
    дважды, чтобы добраться до того же файла, — а нужно было только имя."""
    from fastapi.responses import FileResponse

    from app.launch_prep.models import LaunchPrepCreativeFile

    pairs = _sent(env)
    rec = (env.db.query(LaunchPrepCreativeFile)
           .filter(LaunchPrepCreativeFile.set_id == env.cset.id).first())
    rec.original_name = 'banner_final_v2.zip'
    rec.path = 'creatives/cre_test_traffic.zip'
    env.db.commit()
    full = os.path.join(traffic.UPLOADS_ROOT, rec.path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'wb') as fh:
        fh.write(b'PK\x03\x04 not a real archive')
    try:
        out = traffic.creative_archive(pairs[0].id, env.db, _ADMIN)
        assert isinstance(out, FileResponse), "одиночный файл не заворачивается в zip"
        assert out.filename == f"{env.deal.code}-cr{env.cset.no}.zip", out.filename
    finally:
        os.remove(full)


def test_target_urls_returns_plain_strings(env):  # noqa: F811
    """Найдено сквозным прогоном 28.08.2026: выпуск маркера падал на `TypeError`.

    Запрос просил одну сущность и распаковывался как кортеж — `for (t,) in ...`. Шаг
    стоит последним в цепочке и сеть в тестах не трогается, поэтому годился только
    прибор на саму выборку: она обязана отдавать СТРОКИ, а не строки-кортежи.
    """
    pairs = _sent(env)
    urls = lp._target_urls(env.db, env.cset.id)
    assert len(urls) == len(pairs)
    assert all(u is None or isinstance(u, str) for u in urls), urls


# ── сроки ────────────────────────────────────────────────────────────────────
def test_open_deal_never_expires():
    """Безопасное поведение по умолчанию: отказ уборки обязан выглядеть как «файлы
    копятся», а не как «файлы исчезли»."""
    for days in (retention.SCREENSHOT_DAYS, retention.SANDBOX_DAYS, retention.ARCHIVE_DAYS):
        assert retention.is_expired(None, days, date(2030, 1, 1)) is False


def test_expiry_counts_from_the_exit_moment():
    closed = datetime(2026, 1, 1, 12, 0)
    assert not retention.is_expired(closed, 30, date(2026, 1, 31))
    assert retention.is_expired(closed, 30, date(2026, 2, 1))


def test_ladder_order_is_not_accidental():
    """Чем ближе файл к доказательству, тем дольше он живёт. Перестановка этих чисел
    местами означала бы, что мы стираем доказательства раньше самих баннеров."""
    assert retention.SCREENSHOT_DAYS < retention.SANDBOX_DAYS < retention.ARCHIVE_DAYS


def test_last_exit_takes_the_latest(env):  # noqa: F811
    """Ушла со стадии и вернулась — считаем от последнего выхода."""
    base = datetime(2026, 1, 1)
    rows = [(14, base), (14, base + timedelta(days=40)), (13, None)]
    assert retention.last_exit(rows) == base + timedelta(days=40)
    assert retention.last_exit([]) is None


def test_closed_at_reads_the_ord_stage(env):  # noqa: F811
    """Стадия ищется по ИМЕНИ, а не по id: на другом стенде id окажется другим."""
    assert retention.ORD_REPORT_STAGE == 'Отчёты в ОРД'
    # У свежей сделки выхода нет — и это None, а не «давно».
    assert retention.closed_at(env.db, env.deal.id) is None or isinstance(
        retention.closed_at(env.db, env.deal.id), datetime)


# ── нацеливание и площадки не в нашей DSP ────────────────────────────────────
#
# Площадка без нашего кода крутится в ДРУГОЙ DSP (владелец 24.09.2026). Кука нацеливания
# ставится нашей DSP, поэтому на таком сайте баннер не появится — а страница ссылки при
# этом выглядит как успех, и трафик решает, что сломан баннер. Правило одно на систему:
# креатив, ВСЕ площадки которого не в нашей DSP, нацеливания не получает ни по кнопке,
# ни тихо при отправке; частично такой — получает, а чужие строки помечены.

class _NoCalls:
    """Клиент DSP, которого нельзя трогать: любой вызов — провал теста."""

    def __getattr__(self, name):
        raise AssertionError(f"поход в DSP ({name}) у комплекта, которому он бесполезен")


def _our_code(env, *flags):  # noqa: F811
    saved = [(p.id, p.our_code) for p in env.pubs]
    for p, f in zip(env.pubs, flags):
        p.our_code = f
    env.db.commit()
    return saved


def _restore(env, saved):  # noqa: F811
    from app.sales.models import SalesPublisher
    for pid, f in saved:
        env.db.query(SalesPublisher).filter(SalesPublisher.id == pid).update({"our_code": f})
    env.db.commit()


def _my_rows(env, pairs):  # noqa: F811
    rows = traffic.queue('all', env.db, _ADMIN)["rows"]
    return [r for r in rows if r["pair_id"] in {p.id for p in pairs}]


def test_targeting_is_refused_when_no_publisher_runs_our_dsp(env, monkeypatch):  # noqa: F811
    from app.dsp import targeting_creative as tc
    from app.routers import traffic_catalog
    # Кабинет задан НАРОЧНО: без него `ensure` отказывал бы и сам, «не задан кабинет», и
    # проверка тихого пути прошла бы даже без правила (ревью 24.09.2026). С кабинетом
    # единственное, что держит её от похода в DSP, — само правило.
    monkeypatch.setattr(traffic_catalog, "targeting_cabinet",
                        lambda db: ("PARTNER000000001", "CAMPAIGN00000001"))
    saved = _our_code(env, False, False)
    try:
        pairs = _sent(env)
        mine = _my_rows(env, pairs)
        assert mine and all(r["set"]["targeting_blind"] is True for r in mine), (
            "креатив без единой площадки в нашей DSP обязан прийти помеченным")
        assert all(r["publisher"]["our_code"] is False for r in mine)
        with pytest.raises(tc.TargetingCreativeError) as e:
            tc.ensure(env.db, env.cset, client=_NoCalls())
        assert "не в нашей DSP" in str(e.value)
        # Тихий путь отправки тоже не ходит наружу и не падает.
        assert tc.ensure_quietly(env.db, env.cset, client=_NoCalls()) is None
        # И уже заведённую копию не отдаёт: на этих сайтах она не покажется так же.
        env.cset.ms_targeting_creative_xxhash = "OLDCOPY000000001"
        env.db.commit()
        assert tc.ensure_quietly(env.db, env.cset, client=_NoCalls()) is None, (
            "заведённая копия у креатива не в нашей DSP выдана как годная")
    finally:
        _restore(env, saved)


def test_targeting_stays_when_at_least_one_publisher_runs_our_dsp(env, monkeypatch):  # noqa: F811
    from app.dsp import targeting_creative as tc
    # Комплект не слепой — значит отправка пошла бы заводить копию в настоящий DSP.
    # Тестам туда нельзя: удаления в чужом кабинете нет.
    monkeypatch.setattr(tc, "ensure_quietly", lambda *a, **k: None)
    saved = _our_code(env, True, False)
    try:
        pairs = _sent(env)
        mine = _my_rows(env, pairs)
        assert mine and all(r["set"]["targeting_blind"] is False for r in mine), (
            "хотя бы одна площадка в нашей DSP — кнопка нужна")
        flags = {r["publisher"]["id"]: r["publisher"]["our_code"] for r in mine}
        assert flags == {env.pubs[0].id: True, env.pubs[1].id: False}, (
            "чужую площадку строка обязана назвать, иначе её не отличить")
        assert tc.blind_sets(env.db, [env.cset.id]) == set()
    finally:
        _restore(env, saved)


def test_set_without_pairs_is_not_called_blind(env):  # noqa: F811
    """До отправки пар нет: «не знаем» не равно «не покажет» — кнопку не прячем."""
    from app.dsp import targeting_creative as tc
    assert tc.blind_sets(env.db, [env.cset.id]) == set()


def test_refused_publisher_does_not_keep_the_button(env, monkeypatch):  # noqa: F811
    """«Наша» площадка отказалась, осталась чужая — нацеливание уже не покажет ничего."""
    from app.dsp import targeting_creative as tc
    monkeypatch.setattr(tc, "ensure_quietly", lambda *a, **k: None)
    saved = _our_code(env, True, False)
    try:
        _sent(env)
        env.targets[0].state = 'отказ площадки'
        env.db.commit()
        assert tc.blind_sets(env.db, [env.cset.id]) == {env.cset.id}
    finally:
        _restore(env, saved)


def test_app_surface_never_gets_targeting(env, monkeypatch):  # noqa: F811
    """Кука нацеливания ставится БРАУЗЕРУ. Приложение её не видит — у него своё
    хранилище, — поэтому пара на поверхности app нацеливания не получает, даже если код
    на площадке наш (владелец 24.09.2026: у Максавита веб чужой, а приложение наше)."""
    from app.dsp import targeting_creative as tc
    monkeypatch.setattr(tc, "ensure_quietly", lambda *a, **k: None)
    saved = _our_code(env, True, True)
    try:
        for t in env.targets:
            t.surface_kind = 'app'
        env.db.commit()
        pairs = _sent(env)
        assert tc.blind_sets(env.db, [env.cset.id]) == {env.cset.id}
        mine = _my_rows(env, pairs)
        assert mine and all(r["targeting_miss"] == "приложение" for r in mine), (
            "строка обязана назвать причину — приложение, а не чужую DSP")
    finally:
        _restore(env, saved)


def test_row_names_why_targeting_misses(env, monkeypatch):  # noqa: F811
    from app.dsp import targeting_creative as tc
    monkeypatch.setattr(tc, "ensure_quietly", lambda *a, **k: None)
    saved = _our_code(env, True, False)
    try:
        pairs = _sent(env)
        miss = {r["publisher"]["id"]: r["targeting_miss"] for r in _my_rows(env, pairs)}
        assert miss == {env.pubs[0].id: None, env.pubs[1].id: "не в нашей DSP"}
    finally:
        _restore(env, saved)


def test_verdict_asks_to_stop_targeting_of_the_creative(env, monkeypatch):  # noqa: F811
    """После решения трафика конвейер просит остановить копию нацеливания креатива —
    остановит ли, решает `stop_when_done` (все ли площадки отвечены)."""
    from app.dsp import targeting_creative as tc
    monkeypatch.setattr(tc, "ensure_quietly", lambda *a, **k: None)
    asked = []
    monkeypatch.setattr(tc, "stop_when_done", lambda db, set_id, **k: asked.append(set_id) or True)
    pairs = _sent(env)
    traffic.pair_verdict(pairs[0].id, traffic.VerdictIn(verdict='ок'), env.db, _ADMIN)
    assert asked == [env.cset.id]
    traffic.bulk_verdict(traffic.BulkVerdictIn(pair_ids=[p.id for p in pairs[1:]], verdict='ок'),
                         env.db, _ADMIN)
    assert asked[-1] == env.cset.id and len(asked) == 2
