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

from app.launch_prep.models import (LaunchPrepPair, LaunchPrepPairFile,
                                    LaunchPrepReview)
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
# Единственное правило модуля, которое до 29.08.2026 не держал ни один прибор. Проверять
# его на живых людях дорого вдвойне: `traffic_manager_id` пуст у всех 916 сделок, а
# пользователей с ролями трафика ноль — то есть первый же назначенный человек обнаружил
# бы ошибку собой, и обнаружил бы её как «мне не видно моей работы».
#
# Назначение тест ставит сам и убирает за собой. Утверждений три, и каждое ломается
# молча: лишняя видимость не падает, недостача выглядит как пустая очередь.

# Пользователь, которого нет в справочнике представителей: проверяем ветку «своих строк
# нет» — сегодня это состояние любого нового трафик-менеджера до заведения карточки.
_UID_NOBODY = 10 ** 9


def _user(key, is_master, uid=None):
    """Пользователь ровно в той форме, в какой его читает `_apply_scope`."""
    return SimpleNamespace(id=uid, name='тест',
                           role=SimpleNamespace(key=key, is_master=is_master))


def _sees(db, user, deal_id):
    """Видит ли пользователь в очереди хоть одну пару этой сделки."""
    rows = traffic.queue('all', db, user)['rows']
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


def test_unassigned_deal_is_visible_to_everyone(scope):
    """Неназначенное — общее. На этом сегодня стоит вся очередь: назначений нет."""
    assert scope.deal.traffic_manager_id is None
    assert _sees(scope.db, _user('role_120', False, scope.uid_mine), scope.deal.id)
    assert _sees(scope.db, _user('role_120', False, scope.uid_other), scope.deal.id)
    assert _sees(scope.db, _user('role_120', False, _UID_NOBODY), scope.deal.id), (
        'у трафика без своей строки в справочнике очередь не должна быть пустой'
    )


def test_assigned_deal_is_hidden_from_others(scope):
    """Назначенное видит адресат — и не видит сосед."""
    scope.deal.traffic_manager_id = scope.mine.id
    scope.db.commit()
    assert _sees(scope.db, _user('role_120', False, scope.uid_mine), scope.deal.id)
    assert not _sees(scope.db, _user('role_120', False, scope.uid_other), scope.deal.id)
    assert not _sees(scope.db, _user('role_120', False, _UID_NOBODY), scope.deal.id), (
        'без своей строки видно только ничьё — иначе назначение ничего не значит'
    )


def test_master_and_admin_see_assigned_work(scope):
    """Мастер видит чужое назначение — иначе он не мастер.

    Признак берётся из `roles.is_master`, а не из имени роли: «Мастер траффик» — это
    подпись в интерфейсе, и переименование роли не должно отбирать полномочие.
    """
    scope.deal.traffic_manager_id = scope.other.id
    scope.db.commit()
    assert _sees(scope.db, _user('role_121', True, scope.uid_mine), scope.deal.id)
    assert _sees(scope.db, _user('admin', False, None), scope.deal.id)
    assert not _sees(scope.db, _user('role_120', False, scope.uid_mine), scope.deal.id)


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
