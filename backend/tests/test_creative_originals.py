"""Исходник баннера хранится рядом с подготовленным (владелец 25.09.2026).

Подготовка под нашу DSP (адаптивный `ad.size`, макрос ссылки, раскладка в корень) пишет в
архив НАШИ вставки. Площадке, которая скачивает баннер в кабинете, они не нужны: она
крутит его своей системой и ждёт тот архив, что прислал клиент. До этого исходник
перезаписывался — площадка скачала бы архив с чужими ей макросами.
"""
import io
import os
import zipfile

from app.launch_prep import originals, sandbox
from app.routers import launch_prep as lp
from tests.test_creative_ad_size_upload import _flags, _restore, _upload, _zip
from tests.test_launch_prep_pairs import env  # noqa: F401

RAW = _zip('<html><head></head><body><a href="%banner.reference_mrc_user1%">b</a></body></html>')


def _entry(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    return z.read('index.html').decode('utf-8')


def test_prepared_upload_keeps_the_original_byte_for_byte(env):  # noqa: F811
    saved = _flags(env, True, False)
    f = _upload(env, RAW)
    try:
        with open(os.path.join(lp.UPLOADS_ROOT, f.path), 'rb') as fh:
            assert sandbox.DSP_CLICK_MACRO in _entry(fh.read()), "на диске не подготовленный"
        orig = originals.path_for_publisher(f.path)
        assert orig != os.path.join(lp.UPLOADS_ROOT, f.path), "исходник не сохранён"
        with open(orig, 'rb') as fh:
            assert fh.read() == RAW, "исходник не байт в байт"
    finally:
        lp._remove_file(f.path, f.sandbox_token)
        _restore(env, saved)


def test_untouched_upload_has_no_second_copy(env):  # noqa: F811
    saved = _flags(env, False, False)          # чужая DSP — архив не трогаем
    f = _upload(env, RAW)
    try:
        assert originals.path_for_publisher(f.path) == os.path.join(lp.UPLOADS_ROOT, f.path)
        assert not os.path.exists(originals.original_abs(f.path))
    finally:
        lp._remove_file(f.path, f.sandbox_token)
        _restore(env, saved)


def test_removing_the_file_removes_its_original(env):  # noqa: F811
    saved = _flags(env, True, False)
    f = _upload(env, RAW)
    orig = originals.original_abs(f.path)
    assert os.path.exists(orig)
    lp._remove_file(f.path, f.sandbox_token)
    _restore(env, saved)
    assert not os.path.exists(orig), "исходник остался сиротой"
