# -*- coding: utf-8 -*-
"""Выставление пакета — по документам (владелец 02.11.2026; прежняя версия 19.10 отмечала отправку на пакете целиком).

У каждого документа — свой статус подписи (`doc_sign`). Пакет его только сводит:
  «выставление» → «ждём оплату» — сам, когда выставлены ВСЕ документы (и руками — только при этом же условии);
  архив — когда подписаны ВСЕ; бумага по-прежнему через «Оплачено» → «ждём сканы»;
  отклонённый документ красит «что нужно сейчас» и называет себя.
Поломки: пакет уходит в оплату с невыставленным УПД; в архив с отклонённым ДС; отклонение не видно в реестре."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.master_deal import issue as IS
from app.master_deal import status as ST


class _M:
    def __init__(self, status="выставление", channel="ЭДО", start=False):
        self.id, self.code, self.status, self.channel, self.updated_at = 1, "M-T", status, channel, None
        self.issued_at_start = start


def _d(state, label, channel="ЭДО"):
    return SimpleNamespace(sign_state=state, sign_channel=channel, label=label)


class _U:
    id = 7
    role = type("R", (), {"key": "admin", "is_master": True})()


@pytest.fixture(autouse=True)
def env(monkeypatch):
    st = {"docs": [_d("выставлен", "ДС № 2"), _d(None, "УПД № 1")], "sent_at": None}
    monkeypatch.setattr(ST, "channel_of", lambda db, m: m.channel)
    monkeypatch.setattr(IS, "docs", lambda db, m: st["docs"])
    monkeypatch.setattr(IS, "doc_label", lambda d: d.label)
    monkeypatch.setattr(IS, "last_sent_at", lambda db, m: st["sent_at"])
    monkeypatch.setattr(IS, "due_days", lambda db: 30)
    return st


def test_pack_goes_to_payment_by_itself_when_every_doc_is_out(env):
    m = _M()
    assert IS.sync(None, m) is False and m.status == "выставление", "УПД ещё не выставлен"
    env["docs"][1].sign_state = "выставлен"
    assert IS.sync(None, m) is True and m.status == "ждём оплату"


def test_rejected_doc_holds_the_pack(env):
    env["docs"][1].sign_state = "отклонён"
    m = _M()
    assert IS.sync(None, m) is False
    with pytest.raises(ST.StatusError) as e:
        ST.move(None, m, "ждём оплату", _U())
    assert "УПД № 1" in e.value.message


def test_archive_needs_every_doc_signed(env):
    env["docs"] = [_d("подписан", "ДС № 2"), _d("выставлен", "УПД № 1")]
    m = _M("ждём оплату")
    with pytest.raises(ST.StatusError) as e:
        ST.move(None, m, "архив", _U())
    assert "УПД № 1" in e.value.message and "ДС № 2" not in e.value.message
    env["docs"][1].sign_state = "подписан"
    ST.move(None, m, "архив", _U())
    assert m.status == "архив"


def test_paper_still_goes_through_paid_and_waiting_for_signed(env):
    env["docs"] = [_d("выставлен", "ДС № 2", "бумага")]
    m = _M("ждём оплату", channel="бумага")
    assert ST.sequence(None, m)[-3:] == ("ждём оплату", "ждём сканы", "архив")
    ST.move(None, m, "ждём сканы", _U())
    with pytest.raises(ST.StatusError):
        ST.move(None, m, "архив", _U())


def test_no_docs_no_archive(env):
    env["docs"] = []
    with pytest.raises(ST.StatusError):
        ST.move(None, _M("ждём оплату"), "архив", _U())


@pytest.mark.parametrize("docs,status,text,tone", [
    ([("выставлен", "ДС № 2"), (None, "УПД № 1")], "выставление", "отправить клиенту в Диадок · осталось 1 из 2", "info"),
    ([("согласован", "ДС № 2"), (None, "УПД № 1"), (None, "УПД № 2")], "выставление", "отправить клиенту в Диадок · 3 документа", "info"),
    ([("выставлен", "ДС № 2"), ("отклонён", "УПД № 1")], "выставление", "клиент отклонил: УПД № 1", "bad"),
    ([("подписан", "ДС № 2"), ("отклонён", "УПД № 1")], "ждём оплату", "клиент отклонил: УПД № 1", "bad"),
    ([("подписан", "ДС № 2"), ("выставлен", "УПД № 1")], "ждём оплату", "ждём оплату", "info"),
    ([("подписан", "ДС № 2"), ("выставлен", "УПД № 1")], "ждём сканы", "ждём подписанных · не хватает 1", "warn"),
    ([("подписан", "ДС № 2")], "ждём сканы", "всё подписано — закрыть пакет", "info"),
])
def test_todo(env, docs, status, text, tone):
    env["docs"] = [_d(s, lab) for s, lab in docs]
    t = ST.todo(None, _M(status))
    assert (t["text"], t["tone"]) == (text, tone)


def test_waiting_for_signed_turns_red_after_due_days(env):
    env["docs"] = [_d("выставлен", "ДС № 2")]
    env["sent_at"] = datetime.utcnow() - timedelta(days=31)
    assert ST.todo(None, _M("ждём сканы"))["tone"] == "bad"


@pytest.mark.parametrize("status,channel,signed,want", [
    ("выставление", "ЭДО", False, "send"),
    ("выставление", "бумага", False, "docs"),
    ("выставление", None, False, "contract"),
    ("ждём оплату", "бумага", False, "paid"),
    ("ждём оплату", "ЭДО", False, "docs"),
    ("ждём оплату", "ЭДО", True, "archive"),
    ("ждём сканы", "бумага", False, "docs"),
    ("ждём сканы", "бумага", True, "archive"),
])
def test_row_step(env, status, channel, signed, want):
    env["docs"] = [_d("подписан" if signed else "выставлен", "ДС № 2", channel or "ЭДО")]
    assert ST.row_step(None, _M(status, channel)) == want


def test_waiting_for_closing_is_start_packs_only_and_not_a_closed_status():
    from app.agency_terms import calc
    assert ST.STATUSES.index("ждём закрытия") < ST.STATUSES.index("ждём 1С")
    assert "ждём закрытия" not in calc._done_statuses(), "стартовый пакет не закрыт — в расчёт СК не идёт"
    assert "ждём закрытия" not in ST.sequence(None, _M("черновик"))
    assert "ждём закрытия" in ST.sequence(None, _M("черновик", start=True))
    with pytest.raises(ST.StatusError):                                  # ставит только система
        ST.move(None, _M("ждём закрытия", start=True), "ждём 1С", _U())
    assert ST.todo(None, _M("ждём закрытия", start=True))["who"] == "аккаунт"


def test_back_by_status_step_is_refused(env):
    """Назад — «Вернуть стадию» (revert.py, 12.11.2026); на «ждём оплату» он документов не трогает — test_master_revert."""
    m = _M("ждём сканы", channel="бумага")
    with pytest.raises(ST.StatusError):
        ST.move(None, m, "ждём оплату", _U())


@pytest.mark.parametrize("name,ok", [("скан.pdf", True), ("скан.JPG", True), ("все.zip", False), ("x.rar", False)])
def test_one_file_one_document_no_archives(name, ok):
    assert IS.scan_ext_ok(name) is ok


def test_send_count_is_for_the_row_button(env):
    env["docs"] = [_d("выставлен", "ДС № 2"), _d(None, "УПД № 1"), _d(None, "УПД № 2")]
    assert ST.send_count(None, _M("выставление")) == {"left": 2, "total": 3}
    assert ST.send_count(None, _M("ждём оплату")) is None
