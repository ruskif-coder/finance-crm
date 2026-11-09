# -*- coding: utf-8 -*-
"""Разбор разметки креатива SSP для премодерации (07.11.2026).

Образцы — синтетические, но повторяют устройство живой разметки SSP (замер 07.11 на 120 креативах):
мета ЕРИД и сведений для ОРД, скрипт видимости, ссылка клика через редирект SSP с дважды закодированной
посадочной, до четырёх скрытых пикселей. Хосты выдуманы — имён поставщиков в коде нет.
"""
from app.premod import markup as M

CLICK = ("https://ssp.example/?c=moderation&a=redirect&url=https%3A%2F%2Flog%2Etrk%2Eexample%2Fnew%2Fc%2FTRK1"
         "%3Fsrc%3Dus%26rurl%3Dhttps%253A%252F%252Fshop%252Eexample%252Fpromo%253Ferid%253D{erid}%2526x%253D1")


def creative(erid="2Wabc", trk="TRK1", domain="site1%2Eru", rnd="111", ad_id="AAA-111",
             img="https://cdn.example/banner/300x250.gif", inn="7700000000", size="width=300,height=250"):
    return (
        '<!DOCTYPE html><html><head>'
        f'<meta name="ad.erid" content="{erid}">'
        '<meta name="ad.ordinfo" content="{&quot;customer&quot;:{&quot;name&quot;:&quot;ООО \\&quot;Ромашка\\&quot;&quot;,'
        f'&quot;inn&quot;:&quot;{inn}&quot;}}}}">'
        f'<meta name="ad.id" content="{ad_id}">'
        + (f'<meta name="ad.size" content="{size}">' if size else '') +
        '<script type="text/javascript">window.adsn=window.adsn ||{};window.adsn.viewability = '
        f'{{"s_trk": "{trk}"}};</script>'
        '<script type="text/javascript" src="https://static.trk.example/engine/viewability.js"></script>'
        f'<meta name="ms.id" content="{trk}"></head><body>'
        f'<a href="{CLICK.format(erid=erid)}" target="_blank"><img src="{img}" style="width:300px;height:250px;"/></a>'
        "<img src='https://pix.trk.example/sync/check' style='width:0px;height:0px;display:none;' />"
        f"<img src='https://pix.trk.example/show?s_trk={trk}&domain={domain}&rnd={rnd}' "
        "style='width:0px;height:0px;display:none;' />"
        '</body></html>'
    )


def test_reads_erid_ord_and_size_from_meta():
    h = creative()
    assert M.erid(h) == "2Wabc"
    assert M.ord_info(h) == {"name": 'ООО "Ромашка"', "inn": "7700000000"}
    assert M.size(h) == "300x250"


def test_size_zero_is_adaptive_and_missing_is_none():
    assert M.size(creative(size="width=0,height=0")) == "адаптивный"
    assert M.size(creative(size=None)) is None


def test_landing_is_unwrapped_from_both_redirects():
    """Посадочная лежит внутри редиректа SSP и трекера — дважды закодированной."""
    assert M.landing(creative()) == "https://shop.example/promo?erid=2Wabc&x=1"


def test_sanitize_drops_pixels_viewability_and_click():
    """Наш просмотр не должен засчитаться площадке показом, а клик — переходом."""
    s = M.sanitize(creative())
    assert "display:none" not in s and "pix.trk.example" not in s
    assert "viewability" not in s
    assert "ssp.example" not in s                       # ссылки клика больше нет
    assert "cdn.example/banner/300x250.gif" in s        # сам баннер на месте


def test_external_hosts_after_sanitize():
    h = creative().replace("</head>", '<script src="https://lib.example/anim.js"></script></head>')
    assert M.external_hosts(M.sanitize(h)) == ["lib.example"]


def test_same_banner_for_two_publishers_gives_one_hash():
    """Одна картинка, разные ЕРИД, трекинг, площадка, rnd и ad.id → один пакет."""
    a = creative(erid="2Waaa", trk="T1", domain="one%2Eru", rnd="1", ad_id="X-1")
    b = creative(erid="2Wbbb", trk="T2", domain="two%2Eru", rnd="2", ad_id="X-2")
    assert M.image_hash(a) == M.image_hash(b)


def test_other_picture_or_other_advertiser_gives_other_hash():
    base = creative()
    assert M.image_hash(base) != M.image_hash(creative(img="https://cdn.example/banner/728x90.gif"))
    assert M.image_hash(base) != M.image_hash(creative(inn="7800000000"))


def test_advertiser_counter_script_is_dropped_and_not_in_hash():
    """Счётчик рекламодателя (`<script data-pixel=…>`, у 41 из 120) засчитал бы наш просмотр показом;
    параметры у него свои на каждую заявку — в хеш пакета он попадать не должен."""
    pix = '<script type="text/javascript" data-placement="" data-pixel="https://cnt.example/j?p={p}" ' \
          'src="https://cnt.example/AV_pixel.js" ></script></body>'
    a = creative().replace("</body>", pix.format(p="one"))
    b = creative().replace("</body>", pix.format(p="two"))
    assert "cnt.example" not in M.sanitize(a)
    assert M.image_hash(a) == M.image_hash(b)


def test_same_customer_written_differently_gives_one_hash():
    """Живая пара 07.11: заказчик один, а мета `ad.ordinfo` записана по-разному (экранирование)."""
    a = creative()
    b = a.replace(r"ООО \&quot;Ромашка\&quot;", r"\u041e\u041e\u041e \&quot;Ромашка\&quot;")
    assert a != b
    assert M.ord_info(a) == M.ord_info(b)
    assert M.image_hash(a) == M.image_hash(b)
