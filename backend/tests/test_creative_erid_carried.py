# -*- coding: utf-8 -*-
"""Маркер доезжает от комплекта до креатива кампании — и без него в сеть не уходим.

Найдено на живой сделке 54ZYCH 17.09.2026: согласование прошло, ЕРИД получен, креатив в
кабинете трафика появился — а маркера в нём нет. Колонка `ad_campaign_creative.erid`
ЧИТАЛАСЬ в двух местах (экран трафика и выгрузка в DSP) и НЕ ЗАПОЛНЯЛАСЬ НИКЕМ: 0 из 1
на проде.

Это не косметика. `dsp/provision` подставляет её в `wrap_html` и в тело креатива —
баннер уехал бы в сеть БЕЗ МАРКИРОВКИ, и узнали бы мы об этом не от себя.
"""
import io
import re
from pathlib import Path

from app.ad import build
from app.dsp import provision


def test_the_sync_copies_the_marker_from_the_set():
    """Синк переносит `cs.erid` в креатив кампании.

    Прибор на ИСХОДНИК: поднять живую цепочку в тесте — это сделка, медиаплан, комплект,
    пара и два вердикта, то есть проверка превратилась бы в фикстуру на сто строк, а
    ломается здесь ровно одна строка переноса.
    """
    src = io.open(Path(build.__file__), encoding="utf-8").read()
    block = src[src.index("def sync_creatives"):]
    assert "cs.erid" in block, "маркер не выбирается из комплекта"
    assert re.search(r'row\.erid\s*=\s*r\["erid"\]', block), (
        "маркер не переносится в креатив кампании")


def test_an_empty_marker_does_not_wipe_the_carried_one():
    """Маркер приходит ПОЗЖЕ согласования. Пустое значение не должно стирать уже
    перенесённое — иначе следующий же прогон синка обнулит выданный ЕРИД."""
    src = io.open(Path(build.__file__), encoding="utf-8").read()
    block = src[src.index("def sync_creatives"):]
    i = block.index('row.erid = r["erid"]')
    assert 'if r["erid"]:' in block[max(0, i - 200):i], (
        "перенос маркера идёт без проверки на пустоту")


def test_a_creative_without_a_marker_is_not_uploaded():
    """Реклама без маркировки в сеть не уходит. Отказ — словами, а не молчанием."""
    class _C:
        status = "согласован"
        erid = ""

    class _P:
        is_direct = False
        status = "ждёт запуска"
        weborama_pixel = "px"

    why = provision._blocker({"creative": _C(), "placement": _P(), "file": object(),
                              "target": object(), "publisher": object()},
                             False, None)
    assert why and "ЕРИД" in why, f"креатив без маркера не остановлен: {why!r}"


def test_a_marked_creative_passes_the_same_check():
    """Обратная половина: с маркером эта проверка молчит — иначе прибор доказывал бы
    только то, что мы всё запретили."""
    class _C:
        status = "согласован"
        erid = "Kra23r5Lz"

    class _P:
        is_direct = False
        status = "ждёт запуска"
        weborama_pixel = "px"

    class _F:
        is_archive = True

    class _Pub:
        domain = "maksavit.ru"
        our_code = True

    class _T:
        advertiser_url = "https://maksavit.ru/catalog/espumizan"

    why = provision._blocker({"creative": _C(), "placement": _P(), "file": _F(),
                              "target": _T(), "publisher": _Pub()},
                             False, None)
    # Дальше по списку стоят свои причины (домен площадки и прочее) — нам важно ровно
    # одно: с маркером проверка на маркер молчит.
    assert why is None or "ЕРИД" not in why


def test_the_archive_is_carried_with_the_marker():
    """Файл комплекта доезжает до строки креатива РК — с ТОГО ЖЕ комплекта, что и маркер.

    `ad_campaign_creative.file_id` — четвёртая за два дня колонка с читателями и без
    писателя. Выгрузка в DSP берёт по ней zip; пустая означает отказ «к креативу не
    привязан файл комплекта» на кнопке, которая на вид должна работать (замер 18.09.2026,
    сделка PFPYGX).

    Берём архив комплекта пары — тот, что площадка согласовала.
    """
    import inspect

    from app.ad import build
    src = inspect.getsource(build.sync_creatives)
    assert "row.file_id = archives[" in src, "файл не переносится вовсе"
    assert 'archives.get(r["set_id"])' in src, (
        "файл берётся не с того комплекта: нужен комплект ПАРЫ")
    # Пустым не затираем — иначе пересборка после удаления файла обнулила бы связь у
    # креатива, который уже уехал в DSP.
    assert "if archives.get(" in src


def test_the_creative_number_is_the_number_people_see():
    """Номер креатива в РК = номер комплекта в сделке.

    18.09.2026: на карточке сделки «Креатив №4», а в DSP он же уезжал как
    `PFPYGX-MXV-cr1` — номер считался порядковым внутри площадки. Два номера у одной
    вещи гарантируют путаницу при разборе: человек ищет cr4 и не находит.

    Номер — номер СВОЕГО комплекта: доработка — новый порядковый креатив (владелец
    23.09.2026; поведение закреплено в `test_rework_is_a_new_creative.py`). И
    перенумеровывается только то, что ещё не уехало в DSP — имя заведённого креатива там
    уже зафиксировано, переименовать его нечем, и расхождение «у нас cr4, в кабинете cr1»
    было бы хуже исходной путаницы.
    """
    import inspect

    from app.ad import build
    src = inspect.getsource(build.sync_creatives)
    assert "set_no" in src and "creative_no=no" in src, "номер не связан с комплектом"
    assert "set_no.get(sid)" in src, "номер обязан браться у своего комплекта"
    assert 'not (row.ms_creative_xxhash or "").strip()' in src, (
        "заведённый в DSP креатив переименовывать нельзя")
