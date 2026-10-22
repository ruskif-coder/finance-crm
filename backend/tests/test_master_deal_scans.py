# -*- coding: utf-8 -*-
"""Стадия «ждём сканы» и скан к каждому документу (владелец 19.10.2026: «1) да 2) скан к документу … касается бумажных
документов, электронные будем брать из ЭДО»).

Бумага: … → ждём оплату → «Оплачено» → ждём сканы → архив. В архив — только когда приложен скан к КАЖДОМУ ДС и КАЖДОМУ
УПД пакета; один файл — один документ, архивы не принимаются. ЭДО: стадии «ждём сканы» нет, из «ждём оплату» сразу в архив."""
from datetime import datetime

import pytest

from app.master_deal import issue as IS
from app.master_deal import status as ST


class _M:
    def __init__(self, status, channel="бумага"):
        self.id, self.code, self.status, self.channel, self.updated_at = 1, "M-T", status, channel, None
        self.signed_by_us_at = self.signed_by_us_by = self.sent_at = self.sent_by = None
        self.track_no = self.docs_closed_at = self.docs_closed_by = None
        if channel == "бумага" and status in ("ждём оплату", "ждём сканы", "архив"):
            self.signed_by_us_at = self.sent_at = datetime.utcnow()


class _U:
    id = 7
    role = type("R", (), {"key": "admin", "is_master": True})()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    st = {"missing": ["ДС № 2", "УПД № 1"]}
    for mod in (ST, IS):
        monkeypatch.setattr(mod, "channel_of", lambda db, m: m.channel)
    monkeypatch.setattr(IS, "missing_scans", lambda db, m: list(st["missing"]))
    monkeypatch.setattr(ST, "_missing", lambda db, m: list(st["missing"]))
    monkeypatch.setattr(ST, "_due_days", lambda db: 30)
    return st


def test_statuses_order():
    assert ST.STATUSES == ("черновик", "согласование", "ждём 1С", "выставление", "ждём оплату", "ждём сканы", "архив")


def test_paper_goes_through_scans_edo_skips_them():
    assert ST.sequence(None, _M("ждём оплату")) [-3:] == ("ждём оплату", "ждём сканы", "архив")
    assert "ждём сканы" not in ST.sequence(None, _M("ждём оплату", "ЭДО"))
    m = _M("ждём оплату", "ЭДО")
    m.docs_closed_at = datetime.utcnow()
    ST.move(None, m, "архив", _U())
    assert m.status == "архив"
    with pytest.raises(ST.StatusError):
        ST.move(None, _M("ждём оплату", "ЭДО"), "ждём сканы", _U())


def test_paid_moves_paper_to_scans(_env):
    m = _M("ждём оплату")
    ST.move(None, m, "ждём сканы", _U())
    assert m.status == "ждём сканы"
    with pytest.raises(ST.StatusError):
        ST.move(None, _M("ждём оплату"), "архив", _U())          # бумага — через «ждём сканы»


def test_archive_needs_every_scan(_env):
    m = _M("ждём сканы")
    with pytest.raises(ST.StatusError) as e:
        ST.move(None, m, "архив", _U())
    assert "ДС № 2" in e.value.message and "УПД № 1" in e.value.message
    _env["missing"] = []
    m.docs_closed_at = datetime.utcnow()
    ST.move(None, m, "архив", _U())
    assert m.status == "архив"


def test_docs_closed_only_when_all_scans(_env):
    m = _M("ждём сканы")
    IS.scans_changed(None, m, _U())
    assert m.docs_closed_at is None, "один скан из двух — документы ещё не закрыты"
    _env["missing"] = []
    IS.scans_changed(None, m, _U())
    assert m.docs_closed_at


@pytest.mark.parametrize("status,missing,text,who,tone", [
    ("ждём оплату", ["ДС № 2"], "ждём оплату", "финансы", "info"),
    ("ждём сканы", ["ДС № 2", "УПД № 1"], "прикрепить сканы подписанных · не хватает 2", "аккаунт", "warn"),
    ("ждём сканы", [], "сканы на месте — закрыть пакет", "аккаунт", "info"),
])
def test_todo(_env, status, missing, text, who, tone):
    _env["missing"] = missing
    t = ST.todo(None, _M(status))
    assert (t["text"], t["who"], t["tone"]) == (text, who, tone)


@pytest.mark.parametrize("status,channel,missing,closed,want", [
    ("ждём оплату", "бумага", ["x"], False, "paid"),
    ("ждём оплату", "ЭДО", [], True, "archive"),
    ("ждём сканы", "бумага", ["x"], False, "scans"),
    ("ждём сканы", "бумага", [], True, "archive"),
])
def test_row_step(_env, status, channel, missing, closed, want):
    _env["missing"] = missing
    m = _M(status, channel)
    if closed:
        m.docs_closed_at = datetime.utcnow()
    assert ST.row_step(None, m) == want


def test_back_from_scans_to_payment(_env):
    m = _M("ждём сканы")
    ST.move(None, m, "ждём оплату", _U())
    assert m.status == "ждём оплату" and m.sent_at, "назад из «ждём сканы» — это не отмена отправки"


@pytest.mark.parametrize("name,ok", [("скан.pdf", True), ("скан.JPG", True), ("все.zip", False), ("x.rar", False)])
def test_one_file_one_document_no_archives(name, ok):
    assert IS.scan_ext_ok(name) is ok
