# -*- coding: utf-8 -*-
"""Файл креатива РК выбирается по ФОРМАТУ поверхности площадки (02.11.2026).

Сборка РК привязывала к креативу только АРХИВ комплекта. Тизерной площадке (kuper, формат
TEASER) нужна картинка jpg/png, архива в её комплекте нет — `file_id` оставался пустым, и
выгрузка отвечала «к креативу не привязан файл комплекта». Замер на проде 02.11: 0 из 15
тизерных креативов с файлом, сделка VX2QWE.

Поломка, которую ловит тест: выбор файла снова перестал смотреть на формат — тизер без
картинки или HTML-площадка с картинкой вместо архива."""
from types import SimpleNamespace as NS

from app.ad import build
from app.dsp import teaser

ZIP = NS(id=1, is_archive=True, original_name="banner.zip", path="creatives/cre1_banner.zip")
JPG = NS(id=2, is_archive=False, original_name="kuper (1).jpg", path="creatives/cre1_k.jpg")
PNG = NS(id=3, is_archive=False, original_name="kuper.png", path="creatives/cre1_k.png")


def test_teaser_gets_the_picture_even_when_an_archive_comes_first():
    assert teaser.pick_file(teaser.TEASER, [ZIP, JPG, PNG]) is JPG


def test_html_keeps_the_first_archive():
    assert teaser.pick_file(teaser.HTML, [JPG, ZIP]) is ZIP


def test_nothing_fits_nothing_is_picked():
    assert teaser.pick_file(teaser.TEASER, [ZIP]) is None
    assert teaser.pick_file(teaser.HTML, [JPG]) is None
    assert teaser.pick_file(teaser.HTML, []) is None


def test_the_build_asks_the_surface_format():
    rule = {"channel": "dsp", "creative_format": "TEASER"}
    assert build.creative_file_id([ZIP, JPG], rule) == 2
    assert build.creative_file_id([JPG, ZIP], {"creative_format": "HTML"}) == 1
    assert build.creative_file_id([JPG, ZIP], None) == 1, "без правила — HTML, как было"
    assert build.creative_file_id([ZIP], rule) is None
