# -*- coding: utf-8 -*-
"""Имитация загрузчика DSP для проверки баннера при отправке на согласование (владелец 16.11.2026).

Боевого креатива в DSP на отправке ещё нет, поэтому разметку собираем так, как её собрал бы загрузчик: свой `<base>`, мета
ЕРИД и рекламодателя, настройки видимости и скрипт видимости в конце `<head>`, ровно одна ссылка в теле — обёртка
`{LINK_UNESC}` (собственные ссылки баннера загрузчик убирает: замер 16.11 по 720 разметкам DSP — в теле всегда одна `<a>`)."""
import base64
import re

import pytest

from app.dsp import banner_emulate as be

VSRC = "https://static.dsp.example/engine/viewability.js"
BANNER = ('<!DOCTYPE html><html><head><base href="./"><meta name="ad.size" content="width=0,height=0">'
          '<link href="a.css" rel="stylesheet"></head>'
          '<body><a class="banner" href="{LINK_UNESC}" target="_top"><div class="bg"></div></a>'
          '<a href="https://other.example/">ещё</a><script src="a.js"></script></body></html>')


def _emul(html=BANNER, **kw):
    args = {"base": "https://banner.invalid/", "erid": "2SDtest", "ord_name": 'ООО "Тест"', "ord_inn": "7700000000",
            "viewability_src": VSRC, **kw}
    return be.emulate_loader(html, **args)


def test_head_gets_dsp_meta_base_and_viewability_at_the_end():
    out = _emul()
    head = out[:out.index("</head>")]
    assert '<meta name="ad.erid" content="2SDtest">' in head
    assert "&quot;inn&quot;:&quot;7700000000&quot;" in head and "ad.ordinfo" in head
    assert head.count("<base ") == 1 and '<base href="https://banner.invalid/">' in head
    assert head.rstrip().endswith(f'<script type="text/javascript" src="{VSRC}"></script>')
    assert head.index("window.adsn.viewability") < head.index(VSRC)
    assert '<meta name="ad.id" content="{CAMP_ID}-{CR_ID}">' in head


def test_body_has_exactly_one_link_the_dsp_wrapper():
    body = _emul()[_emul().index("<body"):]
    assert len(re.findall(r"<a\b", body)) == 1
    assert body.startswith('<body><a href="{LINK_UNESC}" target="_blank" style="cursor:pointer">')
    assert '<div class="bg"></div>' in body and "ещё" in body and "</a></body>" in body


def test_without_label_and_setting_nothing_is_invented():
    out = _emul(ord_name=None, ord_inn=None, viewability_src="")
    assert "ad.ordinfo" not in out and "viewability.js" not in out
    assert '<meta name="ad.erid" content="2SDtest">' in out


def test_markup_without_head_or_body_still_gets_both():
    out = _emul(html='<div class="x">баннер</div>')
    assert "<head>" in out and '<body><a href="{LINK_UNESC}"' in out and "баннер" in out


def test_click_link_is_landing_else_publisher_site():
    assert be.click_link("https://shop.example/item", "apteka.example") == ("https://shop.example/item", "посадочная")
    assert be.click_link(None, "apteka.example") == ("https://apteka.example", "сайт площадки")
    assert be.click_link("  ", "https://apteka.example/") == ("https://apteka.example/", "сайт площадки")
    assert be.click_link(None, None) == (None, None)


def test_sandbox_files_are_read_with_a_cap(tmp_path):
    (tmp_path / "img").mkdir()
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "img" / "bg.png").write_bytes(b"\x89PNG")
    files = be.sandbox_files(str(tmp_path), cap=1024)
    assert set(files) == {"index.html", "img/bg.png"}
    assert base64.b64decode(files["img/bg.png"]) == b"\x89PNG"
    with pytest.raises(be.TooBig):
        be.sandbox_files(str(tmp_path), cap=5)


def test_head_without_closing_tag_is_handled():
    """16.11.2026, живой баннер: `<head>` без `</head>` (допустимо в HTML) ронял имитацию."""
    out = _emul(html='<html><head><meta charset="utf-8"><link href="a.css" rel="stylesheet"><body><div>x</div></body></html>')
    head = out[:out.index("</head>")]
    assert "ad.erid" in head and head.rstrip().endswith(f'src="{VSRC}"></script>') and '<link href="a.css"' in head
    assert out.count("</head>") == 1 and '<body><a href="{LINK_UNESC}"' in out
