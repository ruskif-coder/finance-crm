# -*- coding: utf-8 -*-
"""Статус площадки не только показывается, но и ЗАПИСЫВАЕТСЯ.

Найдено 17.09.2026 на сделке 54ZYCH. Обе рецензии по паре стояли «ок», экран трафика
показывал площадку готовой — а кнопка «ПИКСЕЛЬ WR» отвечала «0 заведённых».

Причина в том, что статус жил в двух видах. ЭКРАН считал его на лету из креативов
(`best_chain_status`), а в колонке `ad_campaign_placement.status` оставалось значение,
записанное при создании строки, — «у трафика». Пока на колонку смотрел только экран,
расхождение было невидимым; но по ней считают ДЕЙСТВИЯ — заведение вставок Weborama и
выгрузка в DSP берут «готовые» площадки именно оттуда.

Это та же болезнь, что с `erid` в тот же день: у значения есть читатели и нет писателя.
"""
import io
from pathlib import Path

from app.ad import build, flight


def test_the_sync_writes_the_status_back():
    """Синк пересчитывает колонку из креативов — иначе действия и экран расходятся."""
    src = io.open(Path(build.__file__), encoding="utf-8").read()
    block = src[src.index("def sync_creatives"):]
    assert "best_chain_status" in block, "статус площадки не пересчитывается в синке"
    assert "pl.status = nxt" in block, "пересчитанный статус не записывается"


def test_the_scale_translation_lives_in_one_place():
    """«Согласован» у креатива и «ждёт запуска» у площадки — один перевод на всех.

    Копия этого перевода была в роутере дашборда; синку нужен тот же, и вторая копия
    разошлась бы ровно там, где это дороже всего.
    """
    assert flight.as_placement_scale("согласован") == flight.PLACEMENT_READY
    assert flight.as_placement_scale("у площадки") == "у площадки"

    router = io.open(Path(build.__file__).parents[1] / "routers" / "traffic_dashboard.py",
                     encoding="utf-8").read()
    assert "_as_placement_scale = as_placement_scale" in router, (
        "в дашборде снова завелась своя копия перевода шкалы")


def test_a_manual_decision_is_not_overwritten():
    """Трафик нажал «запущен» — конвейер больше этой строкой не управляет.

    Иначе запущенная площадка возвращалась бы в «ждёт запуска» при каждом прогоне синка.
    """
    assert flight.effective_status("запущен", flight.PLACEMENT_READY) == "запущен"
    assert flight.effective_status("у трафика", flight.PLACEMENT_READY) == flight.PLACEMENT_READY


def test_weborama_reads_the_same_column_the_sync_writes():
    """Замыкаем круг: заведение вставок смотрит в ту колонку, которую синк обновляет."""
    from app.weborama import provision as wb

    assert flight.PLACEMENT_READY in wb.READY_STATUSES
    src = io.open(Path(wb.__file__), encoding="utf-8").read()
    assert "p.status in READY_STATUSES" in src
