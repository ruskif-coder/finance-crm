# -*- coding: utf-8 -*-
"""Копия нацеливания — один проход на комплект (02.10.2026): запуск РК, просьба о ссылке
и отправка трафику могли одновременно увидеть «копии нет» и завести две в DSP."""
import inspect

import app.main  # noqa: F401
from app import ext_lock
from app.dsp import targeting_creative as tc


def test_ensure_takes_its_own_lock_per_set():
    assert hasattr(ext_lock, "DSP_TARGETING_COPY")
    assert len({ext_lock.DSP_PROVISION, ext_lock.WEBORAMA_PROVISION, ext_lock.MAIL_FLUSH,
                ext_lock.OUTWARD_DIGEST, ext_lock.STAFF_DISPATCH, ext_lock.WEBORAMA_DEMO,
                ext_lock.DSP_TARGETING_COPY}) == 7, "ключ замка не должен совпасть с чужим"
    src = inspect.getsource(tc.ensure)
    assert "only_one(" in src and "DSP_TARGETING_COPY" in src
