# -*- coding: utf-8 -*-
"""Подписан ли ДС (app/sales/annex_signed.py): одна функция с источниками — ЭДО (место под него), отметка подписи на самом
ДС (`sign_state`, 02.11.2026), иначе «не подписан»; расхождение источников — тревога.

До 02.11.2026 вторым источником был ЛЮБОЙ файл ДС у сделки: подписанный ДС без скана считался неподписанным и на закрытии
пересобирался по факту под тем же номером, а приложенный неподписанный проект — подписанным. Поломка, которую ловит набор:
файл у сделки снова решает подпись."""
from types import SimpleNamespace

from app.sales import annex_signed as AS


def _a(state):
    return SimpleNamespace(id=1, sign_state=state)


def test_not_signed_until_marked(monkeypatch):
    monkeypatch.setattr(AS, "_from_edo", lambda db, a: None)
    for st in (None, "выпущен", "согласован", "выставлен", "отклонён"):
        assert AS.signed_state(None, _a(st)) == {"signed": False, "source": None, "source_label": "нет данных", "at": None,
                                                 "conflict": False}


def test_mark_on_annex_makes_it_signed(monkeypatch):
    monkeypatch.setattr(AS, "_from_edo", lambda db, a: None)
    monkeypatch.setattr(AS, "_signed_at", lambda db, a: "2026-11-02T10:00:00")
    st = AS.signed_state(None, _a("подписан"))
    assert st["signed"] and st["source"] == "mark" and st["at"] == "2026-11-02T10:00:00"


def test_file_on_deal_no_longer_counts():
    import inspect
    assert "sales_deal_files" not in inspect.getsource(AS), "подпись решает отметка на ДС, а не файл у сделки"


def test_edo_wins_and_conflict_is_flagged(monkeypatch):
    monkeypatch.setattr(AS, "_from_edo", lambda db, a: {"signed": False, "at": None})
    monkeypatch.setattr(AS, "_signed_at", lambda db, a: None)
    st = AS.signed_state(None, _a("подписан"))
    assert st["source"] == "edo" and st["signed"] is False and st["conflict"] is True
