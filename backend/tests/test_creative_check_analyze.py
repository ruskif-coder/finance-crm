# -*- coding: utf-8 -*-
"""Проверка креатива на странице «Проверка креатива» (07.10.2026).

Правило владельца: блокируем ТОЛЬКО полную несовместимость и битый архив; всё остальное — замечания.
Креатив может быть простой картинкой: она заворачивается в HTML5-архив, который принимает загрузчик DSP.
"""
import io
import struct
import zipfile

import pytest

from app.creative_check import analyze as az


def _png(w, h):
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", w, h) + b"\x08\x06\x00\x00\x00" + b"\x00" * 8


def _gif(w, h):
    return b"GIF89a" + struct.pack("<HH", w, h) + b"\x00" * 10


def _jpeg(w, h):
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + sof + b"\xff\xd9"


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, b in files.items():
            z.writestr(n, b)
    return buf.getvalue()


GOOD = ('<html><head><meta name="ad.size" content="width=300,height=250"></head>'
        '<body><a href="{LINK_UNESC}"><img src="a.png"></a></body></html>')


def test_image_sizes_are_read_from_headers():
    assert az.image_size(_png(300, 250)) == (300, 250)
    assert az.image_size(_gif(728, 90)) == (728, 90)
    assert az.image_size(_jpeg(320, 100)) == (320, 100)
    assert az.image_size(b"<svg xmlns='http://www.w3.org/2000/svg' width='160' height='600'></svg>") == (160, 600)
    assert az.image_size(b"not an image") is None


def test_picture_becomes_an_html5_archive_the_dsp_accepts():
    r = az.analyze("banner.png", _png(300, 250))
    assert r.kind == "image" and r.info["size"] == "300x250"
    z = zipfile.ZipFile(io.BytesIO(r.zip_bytes))
    names = z.namelist()
    assert "index.html" in names and any(n.startswith("banner.") for n in names)
    html = z.read("index.html").decode()
    assert 'content="width=300,height=250"' in html and "{LINK_UNESC}" in html
    from app.dsp import creatives as cr
    cr.require_ad_size(r.zip_bytes)          # загрузчик не откажет по 2053


def test_good_html5_has_no_remarks():
    r = az.analyze("b.zip", _zip({"index.html": GOOD, "a.png": _png(1, 1)}))
    assert r.kind == "html5" and r.warnings == [] and r.prepared == []
    assert r.info["size"] == "300x250"


def test_missing_size_and_click_are_fixed_and_reported_not_blocked():
    r = az.analyze("b.zip", _zip({"index.html": "<html><head></head><body><a href='#'>x</a></body></html>"}))
    assert set(r.prepared) >= {"ad.size", "link"}
    assert r.info["size"] == "адаптивный"


def test_external_resources_scripts_and_http_are_warnings():
    html = GOOD.replace("<body>", "<body><script src='https://cdn.example.com/x.js'></script>"
                        "<script>eval('1')</script><img src='http://x.example.com/p.png'>")
    r = az.analyze("b.zip", _zip({"index.html": html}))
    text = " ".join(r.warnings)
    assert "cdn.example.com" in text and "eval" in text and "http://" in text


def test_broken_archive_and_missing_html_block():
    with pytest.raises(az.CheckRejected) as e:
        az.analyze("b.zip", b"PK\x03\x04 not really a zip")
    assert "архив" in " ".join(e.value.messages).lower()
    with pytest.raises(az.CheckRejected) as e:
        az.analyze("b.zip", _zip({"readme.txt": "x"}))
    assert "html" in " ".join(e.value.messages).lower()


def test_unsupported_and_unreadable_files_block():
    for name, data in [("a.mp4", b"\x00" * 100), ("a.exe", b"MZ"), ("a.png", b"not a png"), ("a.zip", b"")]:
        with pytest.raises(az.CheckRejected):
            az.analyze(name, data)


def test_heavy_picture_is_a_remark_not_a_block():
    r = az.analyze("b.png", _png(300, 250) + b"\x00" * (600 * 1024))
    assert any("КБ" in w or "вес" in w.lower() for w in r.warnings)
