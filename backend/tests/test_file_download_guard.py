# -*- coding: utf-8 -*-
"""Скачивание файлов сделки: белый список держится НА КАЖДОМ шаге переадресации.

ЗАЧЕМ. 11.09.2026 в проект добавили `_allowed_file_url` — белый список доменов для
адресов, которые приходят из ответа портала. Проверка стояла ровно один раз, до запроса,
а сам запрос шёл с `follow_redirects=True`. httpx идёт по переадресации на любой хост и
любую схему, поэтому один ответ `302 Location: http://finance_db:5432/…` уводил наш
запрос внутрь docker-сети — туда, куда снаружи не достучаться, а изнутри бэкенда легко.
Тело писалось на диск как файл сделки.

Это класс ошибок «проверили не то, что использовали»: список выглядел защитой и ею не был.
Оба свойства ниже закреплены тестом именно потому, что глазами их не видно — в коде
разница ровно в одном именованном аргументе.

Второе свойство — потолок размера. `r.content` буферизует ответ целиком, а у контейнера
`mem_limit: 512m`: достаточно испорченного поля, чтобы синк убил процесс.
"""
import httpx
import pytest

from app.sales.bitrix import deal_sync as ds

OK = "https://portal.bitrix24.ru/file/1"


class _FakeStream:
    """Подделка ответа httpx.stream: статус, заголовки и тело кусками."""

    def __init__(self, status, headers=None, chunks=()):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)

    def iter_bytes(self):
        for c in self._chunks:
            yield c


def _patch(monkeypatch, script):
    """script: словарь «адрес → ответ». Заодно записывает, куда реально ходили."""
    visited = []

    def fake_stream(method, url, **kw):
        visited.append(url)
        assert kw.get("follow_redirects") is False, (
            "запрос обязан идти БЕЗ автоматических переадресаций — иначе проверка "
            "адреса проверяет не тот адрес, по которому мы в итоге пойдём")
        return script[url]

    monkeypatch.setattr(ds.httpx, "stream", fake_stream)
    return visited


# ── адрес проверяется на каждом шаге ─────────────────────────────────────────

def test_redirect_outside_the_allowlist_is_refused(monkeypatch):
    evil = "http://finance_db:5432/steal"
    visited = _patch(monkeypatch, {
        OK: _FakeStream(302, {"location": evil}),
        evil: _FakeStream(200, {}, [b"secret"]),
    })
    with pytest.raises(ValueError, match="переадресация"):
        ds._fetch_allowed(OK)
    assert evil not in visited, (
        "мы сходили по адресу за пределами белого списка — именно это и запрещено")


def test_redirect_inside_the_allowlist_is_followed(monkeypatch):
    second = "https://portal.bitrix24.ru/storage/1"
    _patch(monkeypatch, {
        OK: _FakeStream(302, {"location": second}),
        second: _FakeStream(200, {"content-type": "application/pdf"}, [b"%PDF"]),
    })
    body, headers = ds._fetch_allowed(OK)
    assert body == b"%PDF"
    assert headers["content-type"] == "application/pdf"


def test_relative_redirect_stays_on_the_same_host(monkeypatch):
    """Относительный Location — законный ответ; он не должен читаться как чужой хост."""
    _patch(monkeypatch, {
        OK: _FakeStream(302, {"location": "/storage/7"}),
        "https://portal.bitrix24.ru/storage/7": _FakeStream(200, {}, [b"ok"]),
    })
    assert ds._fetch_allowed(OK)[0] == b"ok"


def test_redirect_loop_ends(monkeypatch):
    """Кольцо переадресаций обязано кончиться отказом, а не вечным запросом."""
    _patch(monkeypatch, {OK: _FakeStream(302, {"location": OK})})
    with pytest.raises(ValueError, match="слишком много"):
        ds._fetch_allowed(OK)


# ── потолок размера ──────────────────────────────────────────────────────────

def test_oversized_body_is_cut_off(monkeypatch):
    """Чтение обрывается ПО ХОДУ, а не после того, как всё уже в памяти."""
    monkeypatch.setattr(ds, "FILE_MAX_BYTES", 1024)
    huge = (b"x" * 512 for _ in range(1000))
    _patch(monkeypatch, {OK: _FakeStream(200, {}, huge)})
    with pytest.raises(ValueError, match="больше"):
        ds._fetch_allowed(OK)


def test_body_at_the_limit_passes(monkeypatch):
    monkeypatch.setattr(ds, "FILE_MAX_BYTES", 1024)
    _patch(monkeypatch, {OK: _FakeStream(200, {}, [b"y" * 1024])})
    assert len(ds._fetch_allowed(OK)[0]) == 1024


# ── сам список ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "http://portal.bitrix24.ru/f",          # не https
    "https://bitrix24.ru.evil.tld/f",       # суффикс подделан слева
    "https://finance_db/f",                 # внутренняя сеть
    "https://169.254.169.254/latest/meta",  # метаданные облака
])
def test_allowlist_refuses(url):
    assert ds._allowed_file_url(url) is False
