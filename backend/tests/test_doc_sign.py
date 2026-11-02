# -*- coding: utf-8 -*-
"""Подпись у каждого документа пакета — ДС и УПД (владелец 02.11.2026): клиент может отказать в подписи одного документа после
всех согласований, поэтому «отправлено» на пакете не говорит, что с каждым документом.

ДС: выпущен → согласован → (бумага: подписан у нас) → выставлен → подписан | отклонён → снова выставлен.
УПД: пришёл из 1С → (бумага: подписан у нас) → выставлен → подписан | отклонён.
Поломки, которые ловит набор: прыжок через шаг (ДС «подписан» сразу после выпуска), подпись бумаги без скана, отказ без
причины, отметка на черновике, ДС без «согласован» уходит клиенту, у УПД появляются шаги ДС."""
from types import SimpleNamespace

import pytest

from app.master_deal import doc_sign as DS


def _ds(state="выпущен", channel=None, no=5):
    return SimpleNamespace(__tablename__="sales_annexes", id=1, no=no, sign_state=state, sign_channel=channel,
                           master_deal_id=10, contract_id=3)


def _upd(state=None, channel=None):
    return SimpleNamespace(__tablename__="master_deal_upds", id=2, sign_state=state, sign_channel=channel, master_deal_id=10,
                           upd_no=1)


@pytest.fixture
def env(monkeypatch):
    st = {"channel": "ЭДО", "scan": None, "events": []}
    monkeypatch.setattr(DS, "_contract_channel", lambda db, doc: st["channel"])
    monkeypatch.setattr(DS, "_scan_id", lambda db, doc: st["scan"])
    monkeypatch.setattr(DS, "_write_event", lambda db, doc, **kw: st["events"].append(kw))
    return st


U = SimpleNamespace(id=7)


def test_ds_edo_path(env):
    d = _ds()
    for s in ("согласован", "выставлен", "подписан"):
        DS.mark(None, d, s, U)
    assert d.sign_state == "подписан" and d.sign_channel == "ЭДО"
    assert [e["state"] for e in env["events"]] == ["согласован", "выставлен", "подписан"]


def test_ds_paper_needs_our_signature_then_scan(env):
    env["channel"] = "бумага"
    d = _ds("согласован")
    with pytest.raises(DS.SignError) as e:
        DS.mark(None, d, "выставлен", U)
    assert "у нас" in e.value.message
    DS.mark(None, d, "подписан у нас", U)
    DS.mark(None, d, "выставлен", U)
    with pytest.raises(DS.SignError) as e:
        DS.mark(None, d, "подписан", U)
    assert "скан" in e.value.message
    env["scan"] = 44
    DS.mark(None, d, "подписан", U)
    assert d.sign_state == "подписан" and env["events"][-1]["file_id"] == 44


@pytest.mark.parametrize("frm,to", [("выпущен", "подписан"), ("выпущен", "выставлен"), ("согласован", "подписан"),
                                    ("подписан", "отклонён"), ("подписан", "выставлен")])
def test_no_jumps(env, frm, to):
    with pytest.raises(DS.SignError):
        DS.mark(None, _ds(frm), to, U)


def test_draft_has_no_marks(env):
    with pytest.raises(DS.SignError) as e:
        DS.mark(None, _ds(None, no=None), "согласован", U)
    assert "не подтвержд" in e.value.message


def test_rejection_needs_reason_and_goes_round_again(env):
    d = _ds("выставлен", "ЭДО")
    with pytest.raises(DS.SignError):
        DS.mark(None, d, "отклонён", U, reason="  ")
    DS.mark(None, d, "отклонён", U, reason="не тот период")
    assert d.sign_state == "отклонён" and env["events"][-1]["reason"] == "не тот период"
    DS.mark(None, d, "выставлен", U)                      # переделали вне системы — номер прежний, уходит снова
    DS.mark(None, d, "подписан", U)
    assert d.sign_state == "подписан"


def test_channel_is_kept_from_first_send(env):
    d = _ds("согласован")
    DS.mark(None, d, "выставлен", U)
    env["channel"] = "бумага"                              # у договора потом поменяли признак — ушедший документ остаётся ЭДО
    DS.mark(None, d, "подписан", U)
    assert d.sign_channel == "ЭДО"


def test_upd_has_no_ds_steps(env):
    u = _upd()
    with pytest.raises(DS.SignError):
        DS.mark(None, u, "согласован", U)
    DS.mark(None, u, "выставлен", U)
    DS.mark(None, u, "подписан", U)
    assert u.sign_state == "подписан"


def test_upd_paper(env):
    env["channel"] = "бумага"
    u = _upd()
    with pytest.raises(DS.SignError):
        DS.mark(None, u, "выставлен", U)
    DS.mark(None, u, "подписан у нас", U)
    DS.mark(None, u, "выставлен", U)
    env["scan"] = 9
    DS.mark(None, u, "подписан", U)
    assert u.sign_state == "подписан" and u.sign_channel == "бумага"


def test_contract_without_channel_cannot_send(env):
    env["channel"] = None
    with pytest.raises(DS.SignError) as e:
        DS.mark(None, _ds("согласован"), "выставлен", U)
    assert "ЭДО или бумага" in e.value.message


def test_summary_of_pack_docs():
    docs = [_ds("подписан", "ЭДО"), _upd("выставлен", "ЭДО"), _upd("отклонён", "ЭДО")]
    s = DS.summary(docs)
    assert s == {"total": 3, "sent": 2, "signed": 1, "rejected": 1, "all_sent": False, "all_signed": False}
    assert DS.summary([_ds("выставлен", "ЭДО"), _upd("подписан", "ЭДО")])["all_sent"] is True
    assert DS.summary([])["all_signed"] is False, "пакет без документов не «подписан целиком»"
