# -*- coding: utf-8 -*-
"""Прибор на состояние во внешних системах — Weborama и DSP.

Две вещи, которые ломаются молча и правдоподобно, поэтому закреплены тестом, а не
комментарием:

  1. **Знаменатель покрытия.** Площадка, которая крутит сама, не идёт ни в числитель, ни
     в знаменатель. Стоит ей туда попасть — «13 из 19» никогда не станет «19 из 19», и
     зелёной плашки не увидит никто: экран будет вечно жёлтым при полностью заведённой РК.
  2. **Порядок Weborama → DSP.** Пиксель показа вшивается В КРЕАТИВ, и площадка без
     пикселя выгрузке не подлежит. Уехавший без счётчика баннер придётся заводить заново,
     а узнаем мы об этом через месяц по пустым отчётам.

Без базы: обе проверяемые функции чистые, и заводить ради них сессию значило бы проверять
заодно и данные стенда.
"""
from types import SimpleNamespace as NS

from app.ad import external as ext
from app.dsp import provision as dsp_prov


def _state(wb, ds):
    return {"weborama": {"state": wb}, "dsp": {"state": ds}}


def test_direct_placement_is_out_of_both_numerator_and_denominator():
    states = {
        1: _state(ext.READY, ext.REGISTERED),
        2: _state(ext.NOT_NEEDED, ext.NOT_NEEDED),   # крутит сама
        3: _state(ext.MISSING, ext.MISSING),
    }
    got = ext.totals(states)
    assert got["weborama"] == {"done": 1, "need": 2}
    assert got["dsp"] == {"done": 1, "need": 2}


def test_full_coverage_reaches_done_equals_need():
    """Полностью заведённая РК обязана сойтись — иначе плашка не позеленеет никогда."""
    states = [_state(ext.READY, ext.RUNNING), _state(ext.READY, ext.REGISTERED),
              _state(ext.NOT_NEEDED, ext.NOT_NEEDED)]
    got = ext.totals(states)
    assert got["weborama"]["done"] == got["weborama"]["need"] == 2
    assert got["dsp"]["done"] == got["dsp"]["need"] == 2


def test_hung_attempt_is_not_counted_as_done():
    """«Неизвестно» — это незакрытая попытка. Считать её сделанной значит разрешить
    повтор, а повтор заводит вторую вставку, которую у них не удалить."""
    got = ext.totals([_state(ext.UNKNOWN, ext.MISSING)])
    assert got["weborama"] == {"done": 0, "need": 1}


def _row(**over):
    row = {
        "creative": NS(status="согласован", ms_creative_xxhash=None, erid="2Vf", ms_title="t"),
        "placement": NS(status="ждёт запуска", is_direct=False, weborama_pixel="px",
                        plan_show=1000, id=1),
        "publisher": NS(domain="example.ru", name="Пример", our_code=True),
        "file": NS(is_archive=True, original_name="b.zip", path="creatives/b.zip"),
        "target": NS(advertiser_url="https://example.ru/item"),
    }
    row.update(over)
    return row


def test_dsp_refuses_a_placement_without_the_weborama_pixel():
    row = _row(placement=NS(status="ждёт запуска", is_direct=False, weborama_pixel=None,
                            plan_show=1000, id=1))
    why = dsp_prov._blocker(row)
    assert why and "Weborama" in why


def test_dsp_takes_a_ready_placement():
    assert dsp_prov._blocker(_row()) is None


def test_dsp_refuses_an_unapproved_creative():
    """«У трафика» и «у площадки» означают, что вердикта ещё нет. Несогласованный баннер
    в кабинете — это показ несогласованного баннера."""
    row = _row(creative=NS(status="у площадки", ms_creative_xxhash=None, erid=None,
                           ms_title="t"))
    assert "вердикта" in (dsp_prov._blocker(row) or "")


def test_dsp_skips_a_placement_that_rotates_on_its_own():
    row = _row(placement=NS(status="запущен", is_direct=True, weborama_pixel=None,
                            plan_show=None, id=1))
    assert "крутит сама" in (dsp_prov._blocker(row) or "")
