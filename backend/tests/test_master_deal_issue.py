# -*- coding: utf-8 -*-
"""Выставление пакета: вилка ЭДО / бумага (владелец 19.10.2026).

ЭДО (до подключения интеграции): «отправлено в ЭДО» → сразу «ждём оплату», документы закрыты отправкой.
Бумага: «подписано у нас» → «отправлено» (трек по желанию) → «ждём оплату»; висит «прикрепить сканы подписанных документов»,
через N дней (настройка, по умолчанию 14) — красным. Архив — только когда документы закрыты."""
from datetime import datetime, timedelta

import pytest

from app.master_deal import issue as IS
from app.master_deal import status as ST


class _M:
    def __init__(self, status="выставление", channel="бумага"):
        self.id, self.code, self.status, self.channel, self.updated_at = 1, "M-T", status, channel, None
        self.signed_by_us_at = self.signed_by_us_by = self.sent_at = self.sent_by = None
        self.track_no = self.docs_closed_at = self.docs_closed_by = None


class _U:
    id = 7
    role = type("R", (), {"key": "role_8", "is_master": False})()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    # 19.10.2026: скан — к каждому документу; «сканов нет» = список недостающих документов
    st = {"scans": 0}
    monkeypatch.setattr(ST, "channel_of", lambda db, m: m.channel)
    monkeypatch.setattr(IS, "channel_of", lambda db, m: m.channel)
    monkeypatch.setattr(IS, "missing_scans", lambda db, m: [] if st["scans"] else ["ДС № 2"])
    monkeypatch.setattr(ST, "_missing", lambda db, m: [] if st["scans"] else ["ДС № 2"])
    monkeypatch.setattr(IS, "due_days", lambda db: 30)
    monkeypatch.setattr(ST, "_due_days", lambda db: 30)
    return st


def test_edo_send_closes_docs_and_goes_to_payment():
    m = _M(channel="ЭДО")
    IS.sent(None, m, _U(), None)
    assert m.status == "ждём оплату" and m.sent_at and m.docs_closed_at and m.track_no is None


def test_paper_needs_our_signature_before_sending():
    m = _M()
    with pytest.raises(ST.StatusError) as e:
        IS.sent(None, m, _U(), "RA123")
    assert "подпиш" in e.value.message
    IS.signed_by_us(None, m, _U())
    IS.sent(None, m, _U(), " RA123 ")
    assert m.status == "ждём оплату" and m.track_no == "RA123" and m.docs_closed_at is None


def test_signed_by_us_only_for_paper_and_only_on_issue():
    with pytest.raises(ST.StatusError):
        IS.signed_by_us(None, _M(channel="ЭДО"), _U())
    with pytest.raises(ST.StatusError):
        IS.signed_by_us(None, _M(status="ждём 1С"), _U())


def test_send_twice_is_refused():
    m = _M(channel="ЭДО")
    IS.sent(None, m, _U(), None)
    m.status = "выставление"
    with pytest.raises(ST.StatusError):
        IS.sent(None, m, _U(), None)


def test_scans_close_paper_docs_and_last_removed_reopens(_env):
    m = _M(status="ждём оплату")
    m.signed_by_us_at = m.sent_at = datetime.utcnow()      # бумага уходит клиенту только после «подписано у нас» (`issue.sent`)
    _env["scans"] = 1
    IS.scans_changed(None, m, _U())
    assert m.docs_closed_at
    _env["scans"] = 0
    IS.scans_changed(None, m, _U())
    assert m.docs_closed_at is None


def test_scans_do_not_touch_edo_docs(_env):
    m = _M(status="ждём оплату", channel="ЭДО")
    m.docs_closed_at = datetime.utcnow()
    IS.scans_changed(None, m, _U())
    assert m.docs_closed_at, "у ЭДО документы закрыты отправкой — сканы их не открывают"


def test_hand_move_issue_to_payment_needs_sending():
    with pytest.raises(ST.StatusError) as e:
        ST.move(None, _M(), "ждём оплату", _U())
    assert "отправ" in e.value.message


def test_archive_needs_closed_docs(_env):
    """Бумага — в архив из «ждём сканы» и со всеми сканами (подробно — test_master_deal_scans); ЭДО — из «ждём оплату»."""
    m = _M(status="ждём сканы")
    m.signed_by_us_at = datetime.utcnow()
    with pytest.raises(ST.StatusError) as e:
        ST.move(None, m, "архив", _U())
    assert "скан" in e.value.message
    _env["scans"] = 1
    m.docs_closed_at = datetime.utcnow()
    ST.move(None, m, "архив", _U())
    assert m.status == "архив"


@pytest.mark.parametrize("prep,text,who,tone", [
    (lambda m: None, "распечатать и подписать у нас", "финансы", "info"),
    (lambda m: setattr(m, "signed_by_us_at", datetime.utcnow()), "отправить клиенту · бумага", "аккаунт", "info"),
])
def test_todo_paper_on_issue(prep, text, who, tone):
    m = _M()
    prep(m)
    t = ST.todo(None, m)
    assert (t["text"], t["who"], t["tone"]) == (text, who, tone)


def test_todo_edo_on_issue():
    assert ST.todo(None, _M(channel="ЭДО"))["text"] == "отправить в ЭДО"


def test_todo_payment_and_scans(_env):
    m = _M(status="ждём оплату")
    m.sent_at = datetime.utcnow() - timedelta(days=3)
    assert (ST.todo(None, m)["text"], ST.todo(None, m)["who"]) == ("ждём оплату", "финансы")
    m.status = "ждём сканы"
    t = ST.todo(None, m)
    assert t["text"] == "прикрепить сканы подписанных · не хватает 1" and t["tone"] == "warn"
    m.sent_at = datetime.utcnow() - timedelta(days=31)
    assert ST.todo(None, m)["tone"] == "bad"
    _env["scans"] = 1
    assert ST.todo(None, m)["text"] == "сканы на месте — закрыть пакет"


def test_scans_still_close_paper_if_contract_switched_to_edo_later(_env):
    """Пакет ушёл бумагой, потом у договора поставили ЭДО — сканы всё равно закрывают этот пакет (ветку держит подпись у нас)."""
    m = _M(status="ждём оплату", channel="ЭДО")
    m.signed_by_us_at = m.sent_at = datetime.utcnow()
    _env["scans"] = 1
    IS.scans_changed(None, m, _U())
    assert m.docs_closed_at


def test_back_from_payment_cancels_sending():
    """Откат «ждём оплату» → «выставление» — отмена отправки: отметку снимаем, иначе отправить снова нельзя."""
    master = type("R", (), {"key": "role_9", "is_master": True})()
    u = _U()
    u.role = master
    m = _M(channel="ЭДО")
    IS.sent(None, m, u, None)
    ST.move(None, m, "выставление", u)
    assert m.sent_at is None and m.docs_closed_at is None
    IS.sent(None, m, u, None)
    assert m.status == "ждём оплату"
    p = _M()
    IS.signed_by_us(None, p, u)
    IS.sent(None, p, u, "RA1")
    ST.move(None, p, "выставление", u)
    assert p.sent_at is None and p.track_no is None and p.signed_by_us_at, "подпись у нас — физический факт, её не снимаем"


# ── действие из строки реестра (хендофф «мастер и шапка», 19.10.2026): только шаги-отметки без ввода данных ──

@pytest.mark.parametrize("status,channel,prep,want", [
    ("выставление", "ЭДО", None, "edo_sent"),
    ("выставление", "бумага", None, "signed"),
    ("выставление", "бумага", "signed", "paper_sent"),
    ("ждём оплату", "бумага", "sent", "paid"),
    ("ждём оплату", "бумага", "closed", "paid"),
    ("ждём оплату", "ЭДО", "closed", "archive"),
    ("ждём 1С", None, None, "contract"),
    ("ждём 1С", "ЭДО", None, "docs_1c"),
    ("согласование", "ЭДО", None, None),
    ("архив", "ЭДО", "closed", None),
])
def test_row_step(status, channel, prep, want):
    m = _M(status=status, channel=channel)
    now = datetime.utcnow()
    if prep in ("signed", "sent"):
        m.signed_by_us_at = now
    if prep == "sent":
        m.sent_at = now
    if prep == "closed":
        m.sent_at = m.docs_closed_at = now
        if channel == "бумага":                 # бумага ушла клиенту только после «подписано у нас»
            m.signed_by_us_at = now
    assert ST.row_step(None, m) == want
