# -*- coding: utf-8 -*-
"""Адрес DSP и токен загрузки не выходят на экран, в тексты ошибок и в журнал обмена
(аудит 01.10.2026, К-2 и К-3). В адресе — имя поставщика (правило «не называть»), в
адресе загрузки — одноразовый токен; журнал обмена виден во вкладке «Логи» и скачивается."""
import httpx
import pytest

from app.dsp import client as C
from app.dsp import creatives as cr

HOST = "https://dsp-vendor.example.org/api/v2/?method=Campaign.add"
UPLOAD = "https://dsp-vendor.example.org/api/upload/?token=abc123secret"


def test_error_text_has_no_address():
    req = httpx.Request("POST", HOST)
    e = httpx.HTTPStatusError("boom for url '" + HOST + "'", request=req,
                              response=httpx.Response(500, request=req))
    t = C.safe_error(e)
    assert "dsp-vendor" not in t and "http" not in t and "500" in t
    t2 = C.safe_error(httpx.ConnectTimeout("timed out " + HOST))
    assert "dsp-vendor" not in t2 and "ConnectTimeout" in t2


def test_client_call_failure_carries_no_address(monkeypatch):
    c = C.MsClient.__new__(C.MsClient)
    c.partner_xxhash, c.contour, c._id, c._http = "P", "test", 0, None
    c._journal = lambda *a, **k: c.__dict__.setdefault("journaled", a)

    def boom(method, body):
        raise httpx.ConnectTimeout("timed out for url " + HOST)
    c._transport = boom
    with pytest.raises(C.MsError) as e:
        c.call("Campaign.add", {}, entity_type="campaign")
    assert "dsp-vendor" not in str(e.value)
    assert "dsp-vendor" not in str(c.journaled)


def test_upload_journal_and_error_have_no_token_or_host(monkeypatch):
    seen = {}

    class FakeClient:
        def upload_get_url(self, kind):
            return UPLOAD

        def journal_raw(self, *a):
            seen["journal"] = a
    from app.launch_prep import sandbox
    monkeypatch.setattr(sandbox, "prepare_for_dsp", lambda d: (d, []))
    monkeypatch.setattr(cr, "check_zip", lambda d, f="": None)
    monkeypatch.setattr(cr, "require_ad_size", lambda d: None)

    def fail(url, **kw):
        raise httpx.ConnectError("refused for " + UPLOAD)
    monkeypatch.setattr(httpx, "post", fail)
    with pytest.raises(cr.CreativeError) as e:
        cr.upload_zip(FakeClient(), b"PK\x03\x04", filename="b.zip", local_ref="cr1")
    blob = str(seen["journal"]) + str(e.value)
    assert "abc123secret" not in blob and "dsp-vendor" not in blob, blob


def test_demo_screen_does_not_show_the_address():
    import inspect
    from app.routers import dsp_demo
    src = inspect.getsource(dsp_demo.state)
    assert '"url": creds' not in src


def test_upload_url_response_is_not_journaled():
    c = C.MsClient.__new__(C.MsClient)
    c.partner_xxhash, c.contour, c._id, c._http = "P", "test", 0, None
    c._journal = lambda *a, **k: c.__dict__.setdefault("journaled", a)
    c._transport = lambda method, body: {"result": UPLOAD}
    assert c.call("Upload.getUploadFileUrl", {"type": "zip"}, entity_type="upload") == UPLOAD
    assert "abc123secret" not in str(c.journaled) and "dsp-vendor" not in str(c.journaled)


def test_targeting_link_error_has_no_address(monkeypatch):
    from app.dsp import targeting_link as TL
    import inspect
    assert "{e!r}" not in inspect.getsource(TL)


def test_targeting_card_has_no_admin_address():
    import inspect
    from app.dsp import targeting_creative as T
    assert '"admin_url":' not in inspect.getsource(T.campaign_state)


def test_jsonrpc_error_text_is_masked():
    c = C.MsClient.__new__(C.MsClient)
    c.partner_xxhash, c.contour, c._id, c._http = "P", "test", 0, None
    c._journal = lambda *a, **k: c.__dict__.setdefault("journaled", a)
    c._transport = lambda method, body: {"error": {"message": "see " + UPLOAD}}
    with pytest.raises(C.MsError) as e:
        c.call("Creative.add", {}, entity_type="creative")
    assert "abc123secret" not in str(e.value) and "abc123secret" not in str(c.journaled)
