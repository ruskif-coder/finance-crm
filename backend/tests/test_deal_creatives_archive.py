"""«Скачать» у карточки «Креативы» в документах сделки (владелец 27.09.2026).

Один архив на сделку: внутри — ЧИСТЫЕ архивы всех прикреплённых на сборке креативов
(исходник клиента, без наших вставок под DSP), под именами из системы: номер креатива и
название, если оно есть.
"""
import asyncio
import io
import os
import zipfile

import pytest
from fastapi import HTTPException, UploadFile

from app.launch_prep import originals
from app.launch_prep.models import LaunchPrepCreativeFile
from app.routers import launch_prep as lp
from tests.test_creative_ad_size_upload import _flags, _restore, _zip
from tests.test_launch_prep_pairs import _ADMIN, env  # noqa: F401

RAW = _zip('<html><head></head><body><a href="%banner.reference_mrc_user1%">b</a></body></html>')


def _upload(env, data, origin='рекламодатель'):  # noqa: F811
    env.db.query(LaunchPrepCreativeFile).filter(
        LaunchPrepCreativeFile.set_id == env.cset.id).delete()
    env.db.commit()
    up = UploadFile(filename='banner.zip', file=io.BytesIO(data))
    asyncio.run(lp.upload_file(env.cset.id, None, up, env.db, _ADMIN, origin=origin))
    return (env.db.query(LaunchPrepCreativeFile)
            .filter(LaunchPrepCreativeFile.set_id == env.cset.id).one())


def _entries(resp):
    return zipfile.ZipFile(io.BytesIO(resp.body))


def test_archive_holds_the_clean_original_under_the_system_name(env):  # noqa: F811
    saved = _flags(env, True, False)          # наш веб — подготовка под DSP сработает
    env.cset.title = 'Скидка'
    env.db.commit()
    f = _upload(env, RAW)
    try:
        assert os.path.exists(originals.original_abs(f.path)), "подготовка не сработала"
        r = lp.deal_creatives_archive(env.deal.id, db=env.db, current_user=_ADMIN)
        z = _entries(r)
        name = f'Креатив №{env.cset.no} — Скидка.zip'
        assert z.namelist() == [name]
        assert z.read(name) == RAW, "в архиве не исходник клиента"
        assert 'attachment' in r.headers['content-disposition']
    finally:
        lp._remove_file(f.path, f.sandbox_token)
        _restore(env, saved)


def test_untitled_creative_is_named_by_number(env):  # noqa: F811
    env.cset.title = None
    env.db.commit()
    f = _upload(env, RAW, origin='наш')
    try:
        z = _entries(lp.deal_creatives_archive(env.deal.id, db=env.db, current_user=_ADMIN))
        assert z.namelist() == [f'Креатив №{env.cset.no}.zip']
    finally:
        lp._remove_file(f.path, f.sandbox_token)


def test_deal_without_creatives_is_404(env):  # noqa: F811
    env.db.query(LaunchPrepCreativeFile).filter(
        LaunchPrepCreativeFile.set_id == env.cset.id).delete()
    env.db.commit()
    with pytest.raises(HTTPException) as e:
        lp.deal_creatives_archive(env.deal.id, db=env.db, current_user=_ADMIN)
    assert e.value.status_code == 404


def test_deal_rows_say_how_many_creatives_are_ready(env):  # noqa: F811
    """Карточка «Креативы» показывает «Скачать» только при прикреплённых креативах."""
    from app.routers.sales_dashboard import creatives_ready_by_deal
    env.db.query(LaunchPrepCreativeFile).filter(
        LaunchPrepCreativeFile.set_id == env.cset.id).delete()
    env.db.commit()
    assert creatives_ready_by_deal(env.db, [env.deal.id]).get(env.deal.id, 0) == 0
    f = _upload(env, RAW, origin='наш')
    try:
        assert creatives_ready_by_deal(env.db, [env.deal.id])[env.deal.id] == 1
    finally:
        lp._remove_file(f.path, f.sandbox_token)
