# -*- coding: utf-8 -*-
"""Файлы доработки отдаются вложением и с типом из нашего списка (аудит 23.09.2026, 9.6).

Тип брался у площадки как есть, ответ шёл inline: `text/html` от площадки открылся бы
страницей на нашем адресе. Сейчас XSS нет (Bearer + скачивание), но появится при
переходе на cookie — поэтому закрыто заранее.
"""
from types import SimpleNamespace

from app.routers import traffic


class _Db:
    def __init__(self, rec):
        self.rec = rec

    def query(self, m):
        rec = self.rec
        return SimpleNamespace(filter=lambda *a: SimpleNamespace(first=lambda: rec))


def _serve(tmp_path, monkeypatch, ctype, name):
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    monkeypatch.setattr(traffic, "existing_upload_path", lambda p: str(f))
    rec = SimpleNamespace(path="x.bin", content_type=ctype, original_name=name)
    return traffic.get_shot(1, _Db(rec), SimpleNamespace(id=1))


def test_foreign_type_becomes_a_plain_download(tmp_path, monkeypatch):
    r = _serve(tmp_path, monkeypatch, "text/html", "shot.html")
    assert r.media_type == "application/octet-stream"
    assert r.headers["content-disposition"].startswith("attachment")


def test_known_image_keeps_its_type_but_is_still_an_attachment(tmp_path, monkeypatch):
    r = _serve(tmp_path, monkeypatch, "image/png", "shot.png")
    assert r.media_type == "image/png"
    assert r.headers["content-disposition"].startswith("attachment")
