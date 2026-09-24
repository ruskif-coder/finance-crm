# -*- coding: utf-8 -*-
"""Находки ревью этапа 5 (аудит 23.09.2026) — каждая своим прибором.

1. Ссылки площадки: запрещаются ЧУЖИЕ СХЕМЫ, а не всё, что без схемы. Карточка
   отправляет форму целиком, и `t.me/чат` или `@чат`, лежащие в поле, роняли сохранение
   (а экран — в белый: 422 со списком ошибок рисовался как текст).
2. Деньги: слово ищется с начала слова, но «предоплата», «себестоимость», «vCPM» и
   «150руб» — тоже деньги.
3. Почтовый клиент: 4xx от получателя (серые списки) — временно; неверный пароль и
   сертификат — окончательно, повтор их не лечит.
4. Письмо на повторной попытке — не «ждёт почту» и не «не ушло»: иначе человек
   отправит текст руками, а досылка — ещё раз.
5. Приостановленный кабинет не получает и писем, не только бота.
6. Предпросмотр письма площадке — тем же адресом кабинета, что настоящее письмо.
"""
import smtplib
import ssl
from types import SimpleNamespace

import pytest

from app.links import safe_url
from app.mail import client as mail
from app.mail import send as msend
from app.notify.outward.send import strip_money


# ── 1 ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("v", ["t.me/chat", "@chat", "нет", "https://t.me/x", "tg://x"])
def test_text_without_a_scheme_is_accepted(v):
    assert safe_url(v) == v


@pytest.mark.parametrize("v", ["javascript:alert(1)", "data:text/html,x", "vbscript:x",
                               "JaVaScRiPt:alert(1)", "file:///etc/passwd"])
def test_foreign_schemes_are_refused(v):
    with pytest.raises(ValueError):
        safe_url(v)


# ── 2 ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fact", [("условия", "предоплата 50 %"), ("итог", "себестоимость"),
                                  ("модель", "vCPM 120"), ("модель", "eCPM"),
                                  ("итог", "150руб")])
def test_money_hidden_inside_words_is_still_cut(fact):
    assert strip_money([fact]) == []


# ── 3 ────────────────────────────────────────────────────────────────────────

def _cfg():
    return mail.MailConfig(host="smtp.example.invalid", port=465, user="u", password="p",
                           sender="noreply@example.invalid", sender_name="Т", mode="ssl")


class _Srv:
    def __init__(self, exc):
        self.exc = exc

    def send_message(self, msg):
        raise self.exc

    def quit(self):
        pass


@pytest.mark.parametrize("exc,temporary", [
    (smtplib.SMTPRecipientsRefused({"a@b.c": (450, b"greylisted")}), True),
    (smtplib.SMTPRecipientsRefused({"a@b.c": (550, b"no such user")}), False),
    (smtplib.SMTPResponseException(451, b"try later"), True),
    (smtplib.SMTPResponseException(554, b"rejected"), False),
])
def test_sending_errors_are_sorted(monkeypatch, exc, temporary):
    monkeypatch.setattr(mail, "config", _cfg)
    monkeypatch.setattr(mail, "_connect", lambda cfg: _Srv(exc))
    with pytest.raises(mail.MailError) as e:
        mail.send(to="someone@example.org", subject="т", body="т")
    assert isinstance(e.value, mail.MailTemporary) is temporary


@pytest.mark.parametrize("exc,temporary", [
    (ConnectionRefusedError(), True),
    (TimeoutError(), True),
    (smtplib.SMTPAuthenticationError(535, b"bad password"), False),
    (ssl.SSLCertVerificationError("bad cert"), False),
])
def test_connection_errors_are_sorted(monkeypatch, exc, temporary):
    def boom(cfg):
        raise exc
    monkeypatch.setattr(mail, "config", _cfg)
    monkeypatch.setattr(mail, "_connect", boom)
    with pytest.raises(mail.MailError) as e:
        mail.send(to="someone@example.org", subject="т", body="т")
    assert isinstance(e.value, mail.MailTemporary) is temporary


# ── 4 ────────────────────────────────────────────────────────────────────────

def test_a_retrying_letter_is_named_as_such():
    row = SimpleNamespace(status="queued", error="Почтовый сервер недоступен", send_after=1)
    assert msend.outcome(row) == "retry"
    assert msend.outcome(SimpleNamespace(status="queued", error=None, send_after=None)) == "queued"
    assert msend.outcome(SimpleNamespace(status="sent", error=None, send_after=None)) == "sent"


# ── 5 ────────────────────────────────────────────────────────────────────────

def test_a_suspended_cabinet_gets_no_letters_either():
    import inspect

    from app.notify.outward import digest, send
    assert "приостановлен" in inspect.getsource(send._recipients)
    assert "приостановлен" in inspect.getsource(digest._run)


# ── 6 ────────────────────────────────────────────────────────────────────────

def test_the_preview_of_a_publisher_letter_points_to_the_cabinet():
    import io
    from pathlib import Path

    from app.mail import editor, preview
    for mod in (editor, preview):
        src = io.open(Path(mod.__file__), encoding="utf-8").read()
        assert "render.abs_url(" not in src, (
            f"{Path(mod.__file__).name}: предпросмотр собирает ссылку от внутреннего адреса")
