"""Кто сделал баннер — обязательный выбор при загрузке (владелец 27.09.2026).

«наш» — собрали мы, «рекламодатель» — прислал клиент: такой баннер может быть кривым, и
трафик видит на креативе плашку «проверьте внимательнее». Выбор обязателен на СЕРВЕРЕ,
а не только на экране: иначе любой другой путь загрузки молча оставит поле пустым.
"""
import asyncio
import io

import pytest
from fastapi import HTTPException, UploadFile

from app.launch_prep import banner_origin
from app.launch_prep.models import LaunchPrepCreativeFile
from app.routers import launch_prep as lp
from tests.test_creative_ad_size_upload import _drop, _zip
from tests.test_launch_prep_pairs import _ADMIN, env  # noqa: F401

HTML = '<html><head><meta name="ad.size" content="width=240,height=400"></head></html>'


def _up(env, origin, clear=True):  # noqa: F811
    if clear:   # у креатива один материал — файл фикстуры снимаем
        env.db.query(LaunchPrepCreativeFile).filter(
            LaunchPrepCreativeFile.set_id == env.cset.id).delete()
        env.db.commit()
    up = UploadFile(filename='banner.zip', file=io.BytesIO(_zip(HTML)))
    return asyncio.run(lp.upload_file(env.cset.id, None, up, env.db, _ADMIN, origin=origin))


def _last(env):  # noqa: F811
    return (env.db.query(LaunchPrepCreativeFile)
            .filter(LaunchPrepCreativeFile.set_id == env.cset.id)
            .order_by(LaunchPrepCreativeFile.id.desc()).first())


@pytest.mark.parametrize('bad', [None, '', 'чей-то'])
def test_upload_without_a_choice_is_refused(env, bad):  # noqa: F811
    before = env.db.query(LaunchPrepCreativeFile).filter(
        LaunchPrepCreativeFile.set_id == env.cset.id).count()
    with pytest.raises(HTTPException) as e:
        _up(env, bad, clear=False)
    assert e.value.status_code == 400
    assert 'кто сделал' in e.value.detail.lower()
    assert env.db.query(LaunchPrepCreativeFile).filter(
        LaunchPrepCreativeFile.set_id == env.cset.id).count() == before, "файл лёг без выбора"


def test_advertiser_banner_is_marked_for_traffic(env):  # noqa: F811
    _up(env, 'рекламодатель')
    f = _last(env)
    try:
        assert f.origin == 'рекламодатель'
        out = lp.deal_creatives(env.deal.id, db=env.db, current_user=_ADMIN)
        s = next(x for x in out['sets'] if x['id'] == env.cset.id)
        assert s['from_advertiser'] is True
        assert any(x['origin'] == 'рекламодатель' for x in s['files'])
    finally:
        _drop(f)


def test_our_banner_is_not_marked(env):  # noqa: F811
    _up(env, 'наш')
    f = _last(env)
    try:
        assert f.origin == 'наш'
        assert banner_origin.from_advertiser(
            env.db.query(LaunchPrepCreativeFile).filter(
                LaunchPrepCreativeFile.set_id == env.cset.id).all()) is False
    finally:
        _drop(f)


def test_rule_is_any_file_from_the_advertiser():
    F = lambda o: type('F', (), {'origin': o})  # noqa: E731
    assert banner_origin.from_advertiser([F('наш'), F('рекламодатель')]) is True
    assert banner_origin.from_advertiser([F('наш'), F(None)]) is False
    assert banner_origin.from_advertiser([]) is False


def test_traffic_queue_carries_the_mark(env):  # noqa: F811
    """Плашка у трафика — из того же правила, что в карточке сделки."""
    from app.routers import traffic
    f = env.db.query(LaunchPrepCreativeFile).filter(
        LaunchPrepCreativeFile.set_id == env.cset.id).first()
    f.origin = 'рекламодатель'
    env.db.commit()
    lp.send_set(env.cset.id, lp.SendIn(), env.db, _ADMIN)
    rows = [r for r in traffic.queue('all', env.db, _ADMIN)['rows']
            if r['set']['id'] == env.cset.id]
    assert rows and all(r['set']['from_advertiser'] is True for r in rows)


def test_second_upload_to_a_creative_is_refused(env):  # noqa: F811
    """«Новой версии» у загруженного креатива нет (владелец 27.09.2026): подмена материала
    под тем же креативом — потенциал для ошибок. Не тот файл — удалить креатив и завести
    новый. Запрет на сервере: спрятанная кнопка не запрет."""
    have = env.db.query(LaunchPrepCreativeFile).filter(
        LaunchPrepCreativeFile.set_id == env.cset.id).count()
    assert have, "у креатива фикстуры должен быть материал"
    with pytest.raises(HTTPException) as e:
        _up(env, 'наш', clear=False)
    assert e.value.status_code == 400
    assert 'удалите креатив' in e.value.detail
