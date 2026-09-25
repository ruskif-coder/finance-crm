"""Загрузка баннера для нашей DSP: хранится уже подготовленным (владелец 25.09.2026).

Подготовка — вшить адаптивный `ad.size`, если размер не объявлен, и поставить макрос
ссылки DSP вместо заглушки чужой системы. Только для креатива, у которого есть ВЕБ-площадка
с НАШИМ кодом: баннер под чужую DSP несёт её макросы, и подмена сломала бы клик там.

Проверяется сама ручка загрузки: правило держится, только если подготовленный архив лёг
и на диск, и в песочницу — иначе предпросмотр и DSP разойдутся.
"""
import asyncio
import io
import os
import zipfile

from fastapi import UploadFile

from app.dsp.creatives import ad_size_in_zip
from app.launch_prep import sandbox
from app.launch_prep.models import LaunchPrepCreativeFile
from app.routers import launch_prep as lp
from tests.test_launch_prep_pairs import _ADMIN, env  # noqa: F401


def _flags(env, *flags):  # noqa: F811
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


def _zip(html):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('index.html', html)
        z.writestr('bg.jpg', b'\xff\xd8JPEG')
    return buf.getvalue()


def _upload(env, data):  # noqa: F811
    up = UploadFile(filename='banner.zip', file=io.BytesIO(data))
    asyncio.run(lp.upload_file(env.cset.id, None, up, env.db, _ADMIN))
    return (env.db.query(LaunchPrepCreativeFile)
            .filter(LaunchPrepCreativeFile.set_id == env.cset.id,
                    LaunchPrepCreativeFile.is_archive.is_(True))
            .order_by(LaunchPrepCreativeFile.id.desc()).first())


def _drop(f):
    path = os.path.join(lp.UPLOADS_ROOT, f.path)
    if os.path.exists(path):
        os.remove(path)
    sandbox.remove(lp.UPLOADS_ROOT, f.sandbox_token)


def test_upload_without_ad_size_is_stored_adaptive(env):  # noqa: F811
    saved = _flags(env, True, False)
    f = _upload(env, _zip('<html><head></head><body>баннер</body></html>'))
    try:
        with open(os.path.join(lp.UPLOADS_ROOT, f.path), 'rb') as fh:
            assert ad_size_in_zip(fh.read()) == (0, 0), "на диске лежит неисправленный архив"
        shown = os.path.join(lp.UPLOADS_ROOT, sandbox.SANDBOX_DIR, f.sandbox_token, f.entry_path)
        with open(shown, encoding='utf-8') as fh:
            assert 'ad.size' in fh.read(), "песочница показывает не тот архив, что уйдёт в DSP"
        assert f.ratio is None, "адаптивный баннер размера не имеет — сетка типовых размеров"
    finally:
        _drop(f)
        _restore(env, saved)


def test_upload_with_ad_size_keeps_it(env):  # noqa: F811
    f = _upload(env, _zip('<html><head><meta name="ad.size" content="width=240,height=400">'
                          '</head></html>'))
    try:
        assert f.ratio == '240x400'
    finally:
        _drop(f)


def test_banner_for_foreign_dsp_is_stored_untouched(env):  # noqa: F811
    """Ни одной веб-площадки с нашим кодом — баннер уйдёт в чужую DSP со своими макросами."""
    saved = _flags(env, False, False)
    src = _zip('<html><head></head><body><a href="%banner.reference_mrc_user1%">b</a>'
               '</body></html>')
    f = _upload(env, src)
    try:
        with open(os.path.join(lp.UPLOADS_ROOT, f.path), 'rb') as fh:
            assert fh.read() == src, "баннер под чужую DSP переписан — сломали его клик"
    finally:
        _drop(f)
        _restore(env, saved)


def test_foreign_click_macro_is_replaced_for_our_web(env):  # noqa: F811
    saved = _flags(env, True, False)
    f = _upload(env, _zip('<html><head><meta name="ad.size" content="width=0,height=0">'
                          '</head><body><a href="%banner.reference_mrc_user1%">b</a>'
                          '</body></html>'))
    try:
        shown = os.path.join(lp.UPLOADS_ROOT, sandbox.SANDBOX_DIR, f.sandbox_token, f.entry_path)
        with open(shown, encoding='utf-8') as fh:
            assert 'href="{LINK_UNESC}"' in fh.read()
    finally:
        _drop(f)
        _restore(env, saved)
