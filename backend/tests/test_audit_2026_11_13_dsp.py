# -*- coding: utf-8 -*-
"""Аудит 13.11.2026 — DSP (владелец 14.11: «пакет дёшево — да»). Наружу ничего не уходит: клиент и HTTP подменены."""
from types import SimpleNamespace

import pytest

import app.model_registry  # noqa: F401
from app.dsp import campaigns as C
from app.dsp.client import MsError


class _Client:
    def __init__(self, listing):
        self.listing, self.added = listing, []

    def last_ok_xxhash(self, *a):
        return None

    def unknown_outcome(self, *a):
        return True

    def campaign_list_by_partner(self):
        return self.listing

    def campaign_add(self, params, local_ref=None):
        self.added.append(params)
        return "NEW"


class _Db:
    def query(self, *a):
        return SimpleNamespace(get=lambda _id: SimpleNamespace(id=_id))

    def flush(self):
        pass


def test_unsure_add_with_no_match_is_refused_not_repeated(monkeypatch):
    """Сломать: вернуть `if unsure: raise` только в ветку сбоя списка — прошлый add без ответа и другое имя кампании
    (сделку переименовали) дадут вторую кампанию в чужом кабинете, по API её не удалить."""
    monkeypatch.setattr(C, "build_campaign_params", lambda camp, deal: {"title": "РК новое имя"})
    cl = _Client([{"xxhash": "abc", "title": "РК старое имя"}])
    with pytest.raises(MsError) as e:
        C.ensure_campaign(_Db(), SimpleNamespace(id=7, deal_id=1, ms_campaign_xxhash=None), cl, commit=False)
    assert cl.added == [] and "без ответа" in str(e.value)


def test_unsure_add_finds_the_campaign_by_title(monkeypatch):
    monkeypatch.setattr(C, "build_campaign_params", lambda camp, deal: {"title": "РК"})
    cl = _Client([{"xxhash": "abc", "title": "РК"}])
    camp = SimpleNamespace(id=7, deal_id=1, ms_campaign_xxhash=None)
    assert C.ensure_campaign(_Db(), camp, cl, commit=False) == "ABC" and cl.added == []


@pytest.mark.parametrize("call", ["zip", "teaser", "targeting"])
def test_uploads_respect_the_external_writes_switch(monkeypatch, call):
    """Сломать: убрать проверку выключателя — стенд с `EXTERNAL_WRITES=off` грузит файлы в боевое хранилище DSP."""
    import httpx
    from app.dsp import creatives, targeting_link, teaser
    monkeypatch.setenv("EXTERNAL_WRITES", "off")
    posted = []
    monkeypatch.setattr(httpx, "post", lambda *a, **k: posted.append(a) or (_ for _ in ()).throw(AssertionError("ушло наружу")))
    client = SimpleNamespace(upload_get_url=lambda kind: "https://upload.example/x")
    with pytest.raises(Exception) as e:
        if call == "zip":
            creatives.upload_zip(client, b"PK-not-a-zip")
        elif call == "teaser":
            teaser.upload_image(client, b"\x89PNG-not-an-image", "t.png")
        else:
            targeting_link.issue("12345", url="https://admin.example")
    assert posted == [] and "EXTERNAL_WRITES" in str(e.value)


def test_prio_fact_file_is_sync_and_reads_within_the_limit():
    """Аудит 13.11.2026: `async def` + `await file.read()` целиком — разбор xlsx останавливал процесс, а тело читалось до
    проверки предела. Сломать: вернуть `async def` или чтение без предела."""
    import inspect
    from app.routers import prio
    assert not inspect.iscoroutinefunction(prio.prio_fact_file)
    assert "read(FACT_FILE_MAX + 1)" in inspect.getsource(prio.prio_fact_file)
