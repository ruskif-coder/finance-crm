# -*- coding: utf-8 -*-
"""Стенд не пишет во внешние боевые системы, когда в .env стоит EXTERNAL_WRITES=off (аудит 21.10.2026, P4).

Стенд ходит в БОЕВОЙ DSP: любой пересчёт лимитов со стенда менял реальные креативы (08.10). У приоритезации адрес по
умолчанию тоже боевой. Флаг закрывает ИЗМЕНЯЮЩИЕ вызовы на уровне транспорта каждого клиента; чтение остаётся. Без флага
поведение прежнее — прод работает как работал. Сеть в тестах не трогается: отказ раньше любого HTTP."""
import httpx
import pytest

from app import external_writes as EW


@pytest.fixture
def off(monkeypatch):
    monkeypatch.setenv("EXTERNAL_WRITES", "off")

    def no_network(*a, **k):
        raise AssertionError("запрос ушёл в сеть при EXTERNAL_WRITES=off")
    monkeypatch.setattr(httpx, "post", no_network)
    monkeypatch.setattr(httpx, "request", no_network)


@pytest.mark.parametrize("val,want", [(None, True), ("on", True), ("off", False), ("0", False), ("no", False), ("FALSE", False)])
def test_flag_values(monkeypatch, val, want):
    if val is None:
        monkeypatch.delenv("EXTERNAL_WRITES", raising=False)
    else:
        monkeypatch.setenv("EXTERNAL_WRITES", val)
    assert EW.allowed() is want


def test_dsp_write_is_refused_read_is_not_classified_as_write(off):
    from app.dsp.client import MsClient, MsError
    c = MsClient(url="https://dsp.invalid/", token="t", journal=False)
    with pytest.raises(MsError, match="EXTERNAL_WRITES"):
        c._http("Creative.edit", {"params": {}})
    assert EW.dsp_is_read("Creative.getInfo") and EW.dsp_is_read("Upload.getUploadFileUrl")
    assert not EW.dsp_is_read("Campaign.setStatus") and not EW.dsp_is_read("Upload.file")


def test_prio_write_is_refused(off):
    from app.prio.client import PrioApiError, PrioClient
    c = PrioClient(token="t", base_url="https://prio.invalid")
    with pytest.raises(PrioApiError, match="EXTERNAL_WRITES"):
        c.create({"site_id": 1})
    with pytest.raises(PrioApiError, match="EXTERNAL_WRITES"):
        c.update(1, {"toggle_on": False})


def test_weborama_write_is_refused(off):
    from app.weborama.client import WcmClient, WcmError
    c = WcmClient.__new__(WcmClient)
    c._transport, c.url, c.timeout, c._token, c.account_id = None, "https://wr.invalid", 5, "x", "1"
    with pytest.raises(WcmError, match="EXTERNAL_WRITES"):
        c._send("POST", "/insertions", data={"a": 1})
