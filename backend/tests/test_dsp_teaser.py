# -*- coding: utf-8 -*-
"""Тизер Купера в DSP (владелец 13.10.2026): вся логика — в `app/dsp/teaser.py`.

Эталон — креатив Купера в кабинете: TEASER, картинка 640×200, иконка 80×80 по умолчанию, тексты
заглушкой, ссылка клика (диплинк) + веб-адрес, ЕРИД. Диплинк уходит как есть: что DSP его пока
отклоняет по API, владелец решил не ждать.
"""
import io
import pathlib
from types import SimpleNamespace as NS

import pytest

from app.dsp import creatives as cr
from app.dsp import teaser as T

APP = pathlib.Path(__file__).resolve().parent.parent / "app"
DEEP = "storefront://multisearch_promo?slug=bystrayadostavka45980"
WEB = "https://web.kuper.ru/multisearch_promo?slug=bystrayadostavka45980"
ICON = "https://cdn.example/icons/80x80.png"


def _img(w=640, h=200, fmt="JPEG"):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 60)).save(buf, fmt)
    return buf.getvalue()


def test_format_of_defaults_to_html():
    assert T.format_of(None) == "HTML" and T.format_of({}) == "HTML"
    assert T.is_teaser({"creative_format": "TEASER"}) and not T.is_teaser({"creative_format": "HTML"})


@pytest.mark.parametrize("fmt,f,ok", [
    ("TEASER", NS(is_archive=False, original_name="a.jpg"), True),
    ("TEASER", NS(is_archive=False, original_name="a.PNG"), True),
    ("TEASER", NS(is_archive=True, original_name="a.zip"), False),
    ("TEASER", NS(is_archive=False, original_name="a.gif"), False),
    ("HTML", NS(is_archive=True, original_name="a.zip"), True),
    ("HTML", NS(is_archive=False, original_name="a.jpg"), False),
    ("TEASER", None, False), ("VIDEO_VAST", NS(is_archive=False, original_name="a.mp4"), False)])
def test_material_problem(fmt, f, ok):
    assert (T.material_problem(fmt, f) is None) == ok


def test_format_warning_silent_without_files_and_when_any_fits():
    assert T.format_warning("TEASER", []) is None
    assert T.format_warning("TEASER", [NS(is_archive=True, original_name="a.zip")])
    both = [NS(is_archive=True, original_name="a.zip"), NS(is_archive=False, original_name="a.jpg")]
    assert T.format_warning("TEASER", both) is None


def test_image_check_accepts_only_640x200_jpg_png():
    T.check_image(_img(), "a.jpg")
    T.check_image(_img(fmt="PNG"), "a.png")
    for bad in (_img(300, 250), b"", b"not an image"):
        with pytest.raises(cr.CreativeError):
            T.check_image(bad, "x.jpg")
    with pytest.raises(cr.CreativeError):
        T.check_image(_img(fmt="GIF"), "x.gif")


def test_params_follow_the_reference_creative():
    p = T.build_params(title="Купер", link=DEEP, adomain=WEB, erid="2SDnjdrA48K",
                       img_url="https://cdn3.example/640x200.jpg", icon_url=ICON, total_shows=1000, pixel="https://px")
    assert p["type"] == "TEASER" and p["link"] == DEEP and p["adomain"] == WEB and p["erid"] == "2SDnjdrA48K"
    d = p["data"]
    assert d["imgMask"].endswith("640x200.jpg") and d["imgFormats"] == ["640x200"]
    assert d["iconMask"] == ICON and d["iconFormats"] == ["80x80"]
    assert d["title"] and d["text"] and d["wrapper"] is False
    assert p["limits"]["show"] == {"total": 1000, "hour": 0, "day": 0}
    assert p["pixel"] == "https://px"
    for absent in ("size", "self_inn", "self_name", "extension_link"):
        assert absent not in p


def test_links_prefer_app_link_and_keep_web_as_final():
    assert T.links_of(NS(advertiser_url=WEB, deeplink_url=DEEP)) == (DEEP, WEB)
    assert T.links_of(NS(advertiser_url=WEB, deeplink_url=None)) == (WEB, WEB)


class FakeClient:
    def __init__(self, info=None):
        self.added, self.edited, self.info = [], [], info

    def upload_get_url(self, kind):
        assert kind == "teaser"
        return "https://upload.example/api/upload/?token=x"

    def creative_add(self, camp, params, local_ref=None):
        self.added.append((camp, params))
        return "NEWHASH"

    def creative_edit(self, xx, params, local_ref=None):
        self.edited.append((xx, params))

    def creative_get_info(self, xx):
        return self.info

    def journal_raw(self, *a, **k):
        pass


def _spec(known=None, deeplink=DEEP, **kw):
    from app.dsp import assemble
    tgt = NS(advertiser_url=WEB, deeplink_url=deeplink)
    click, adomain = assemble.links_for("TEASER", tgt)
    return assemble.Spec(ref="cr1", known=known, fmt="TEASER", title="Креатив 1", link=click,
                         adomain=adomain, erid="2SDnjdrA48K", load=lambda: (_img(), "t.jpg"),
                         icon_url=kw.pop("icon_url", ICON), **kw)


@pytest.fixture()
def fake_upload(monkeypatch):
    class R:
        def raise_for_status(self): pass
        def json(self): return {"result": {"file": {"file_url": "https://cdn3.example/640x200.jpg", "resolution": "640x200"}}}
    monkeypatch.setattr(T.httpx, "post", lambda *a, **k: R())


def test_ensure_uploads_image_then_adds_teaser_once(fake_upload):
    from app.dsp import assemble
    c = FakeClient()
    out = assemble.ensure(c, "CAMP", _spec(total_shows=500))
    assert out.xxhash == "NEWHASH" and out.html is None and len(c.added) == 1 and not c.edited
    params = c.added[0][1]
    assert params["link"] == DEEP and params["adomain"] == WEB
    assert params["data"]["imgMask"] == "https://cdn3.example/640x200.jpg"
    assert params["limits"]["show"]["total"] == 500


def test_ensure_completes_an_empty_object_instead_of_adding_a_second(fake_upload):
    from app.dsp import assemble
    c = FakeClient({"data": {}})
    out = assemble.ensure(c, "CAMP", _spec(known="OLD"))
    assert out.xxhash == "OLD" and not c.added and c.edited[0][0] == "OLD"


def test_ensure_keeps_a_creative_that_is_already_complete(fake_upload):
    from app.dsp import assemble
    c = FakeClient({"data": {"imgMask": "u"}})
    assert assemble.ensure(c, "CAMP", _spec(known="OLD")).xxhash == "OLD"
    assert not c.added and not c.edited


def test_ensure_refuses_when_the_previous_add_has_no_answer(fake_upload):
    from app.dsp import assemble
    c = FakeClient()
    c.unknown_outcome = lambda *a: True

    def boom():
        raise RuntimeError("зависла")
    with pytest.raises(RuntimeError):
        assemble.ensure(c, "CAMP", _spec(on_unknown=boom))
    assert not c.added


def test_state_reads_the_cabinet():
    assert T.state(FakeClient({"data": {"imgMask": "u"}}), "X") == "ok"
    assert T.state(FakeClient({"data": {}}), "X") == "empty"


def test_all_teaser_code_lives_in_the_dsp_package():
    """Правило владельца 13.10.2026: движения с DSP — через пакет `app/dsp`, кусками по системе не разносим."""
    offenders = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel == "dsp/teaser.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "imgMask" in text or "iconMask" in text or 'upload_get_url("teaser")' in text:
            offenders.append(rel)
    assert not offenders, offenders


def test_teaser_is_refused_before_any_upload_when_the_icon_setting_is_empty(fake_upload):
    from app.dsp import assemble
    c = FakeClient()
    with pytest.raises(cr.CreativeError) as e:
        assemble.ensure(c, "CAMP", _spec(icon_url=""))
    assert "dsp_teaser_icon_url" in str(e.value) and not c.added


def test_no_vendor_cdn_address_in_the_code():
    """Адрес CDN поставщика DSP — только в настройке (правило владельца: имя поставщика нигде в гите)."""
    bad = []
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if ("terra" + "traf") in text.lower():   # имя собрано, чтобы самому тесту не быть нарушением
            bad.append(path.relative_to(APP).as_posix())
    assert not bad, bad
