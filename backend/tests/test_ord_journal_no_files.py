# -*- coding: utf-8 -*-
"""В журнал ОРД не пишется сам файл креатива — только размер и sha256 (аудит 29.09.2026)."""
import base64
import hashlib

from app.ord.submit import _strip


def test_file_body_is_replaced_by_digest_and_original_is_untouched():
    raw = b"\x89PNG" * 1000
    body = {"form": "Banner", "mediaData": [{"fileName": "a.png",
                                             "fileContentBase64": base64.b64encode(raw).decode()}]}
    out = _strip(body)
    stub = out["mediaData"][0]["fileContentBase64"]
    assert stub == {"omitted": True, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    assert out["mediaData"][0]["fileName"] == "a.png" and out["form"] == "Banner"
    assert isinstance(body["mediaData"][0]["fileContentBase64"], str), "в ОРД должен уйти полный файл"
