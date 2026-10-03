# -*- coding: utf-8 -*-
"""Макрос рандомизатора Weborama — одно правило для заявки и паспорта (02.10.2026).

Заявка решала по признаку «наш код», паспорт внешних площадок — по каналу из
«Особенностей площадок»; для app-площадок с правилом они расходились, и один и тот же
пиксель уходил с `{RND}` в одном файле и `%system.random%` в другом.
"""
import inspect

import pytest

from app.weborama import naming


@pytest.mark.parametrize("our_code,channel,kind", [
    (True, None, "dsp"), (False, None, "adfox"),
    (True, "adfox", "adfox"), (True, "outside", "adfox"),
    (False, "dsp", "dsp"),
])
def test_channel_first_then_our_code(our_code, channel, kind):
    assert naming.macro_kind(our_code, channel) == kind


def test_both_callers_use_the_rule():
    from app.traffic import offsite_export
    from app.weborama import request_xlsx
    for fn in (offsite_export.pixel_for, request_xlsx.pixels_for_set):
        src = inspect.getsource(fn)
        assert "macro_kind(" in src, fn.__name__
        assert 'else "adfox"' not in src, fn.__name__
